#!/usr/bin/env python3
"""按「作者 + 创作时期」分组，由 haiku-4.5 在组内找重复。

用法：
    python3 dedupe_group.py --dry-run      # 只看分组，不调模型
    python3 dedupe_group.py --only 42,30   # 只跑含这些行的组（验证用）
    python3 dedupe_group.py                # 全量

## 策略（用户 2026-09-17 定）

**重复只可能发生在同一作者同一时期的作品之间。** 所以：

  1. 按作者分桶。作者键 = Wikidata 创作者 QID；模型读出但 Wikidata 没收的名字用
     `name:<归一化名>`；真佚名（Wikidata 给匿名节点或根本没作者）统一归「佚名」。
  2. 同一作者内按年代切成时期：年代区间不冲突的归同一时期
     （冲突的容差按年代分档，见 dedupe_lib.year_relation）。
     **没有年代的件挂到该作者的每一个时期里** —— 否则原清单大批无年代的行
     （神奈川冲浪里、五色鹦鹉图卷）进不了任何组。
  3. 「佚名」不是一个人，不能整桶两两比。佚名桶内再用**稀有词**分块：
     共用一个全表罕见的词（menkaura、triad、heiji）且年代不冲突，才进同一组。
  4. 每组交给 haiku，只问一件事：组内哪些记录指向同一件实物。
  5. **模型给出的簇再过一道确定性闸**（在 dedupe_apply 里）：簇内任两件年代冲突即作废。
     「只可能是同一时期」由代码保证，不靠模型自觉。

跨作者的配对**结构上不可能出现** —— 这就同时消掉了上一轮那个硬矛盾：
原清单「朱迪斯与霍洛芬斯的头颅」被同时判成马苏斯和斯坦茨奥内两幅不同的画。
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import pathlib
import sys

import dedupe_lib as L
import dedupe_llm as LLM
import dedupe_recall as R

HERE = pathlib.Path(__file__).parent
FACTS = HERE / "dedupe_facts.json"
EXTRACT = HERE / "dedupe_extract.json"
OUT_GROUPS = HERE / "dedupe_groups.json"
OUT = HERE / "dedupe_clusters.json"

ANON = "佚名"
GROUP_MAX = 40          # 单组上限；超过就按年代顺序切块（块间重叠几件，防边界漏配）
OVERLAP = 5
PACK = 48               # 一次调用装多少条记录。AGENTS.md：加大批次是唯一有效的省法
RARE_MAX = 8            # 佚名分块用的「稀有词」：全表出现不超过这么多行
ANON_JACCARD = 0.2      # 佚名连边还要求题名重叠度至少这么多，防单链传递


def load_items(xlsx: str) -> tuple[list[dict], dict]:
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    rows = R.load_rows(xlsx)
    raw = {r["_row"]: r for r in rows}
    items = R.build(rows, facts, R.load_en_bridge())
    alias = R.alias_index(facts)
    ext = json.loads(EXTRACT.read_text(encoding="utf-8")) if EXTRACT.exists() else {}
    if not ext:
        print(f"⚠ 缺 {EXTRACT.name} —— 252 行作者未补，它们会全部落进「佚名」")
    works = facts.get("works", {})
    for i in items:
        e = ext.get(str(i["row"]))
        if e:
            if not i["creator_qid"]:
                for nm in (e["author_en"], e["author_zh"]):
                    q = alias.get(L.norm_person(nm)) if nm else None
                    if q:
                        i["creator_qid"] = q
                        break
                if not i["creator_qid"] and (e["author_en"] or e["author_zh"]):
                    i["author_name"] = L.norm_person(e["author_en"] or e["author_zh"])
            if not i["span"] and e["date_text"]:
                i["span"] = L.year_span(e["date_text"])
        # 作者键
        if i["creator_qid"]:
            i["akey"] = i["creator_qid"]
        elif i.get("author_name"):
            i["akey"] = "name:" + i["author_name"]
        else:
            i["akey"] = ANON
        i["_raw"] = raw[i["row"]]
    return items, facts


def periods(rows: list[dict]) -> list[list[dict]]:
    """同一作者内切时期。有年代的按区间不冲突聚类；无年代的挂到每个时期。"""
    dated = sorted([r for r in rows if r["span"]], key=lambda r: (r["span"][0], r["span"][1]))
    undated = [r for r in rows if not r["span"]]
    clusters: list[list[dict]] = []
    env = None
    for r in dated:
        if clusters and L.year_relation(env, r["span"]) != "conflict":
            clusters[-1].append(r)
            env = (min(env[0], r["span"][0]), max(env[1], r["span"][1]), env[2] or r["span"][2])
        else:
            clusters.append([r])
            env = r["span"]
    if not clusters:
        return [undated] if undated else []
    return [c + undated for c in clusters]


def chunk(rows: list[dict]) -> list[list[dict]]:
    if len(rows) <= GROUP_MAX:
        return [rows]
    rows = sorted(rows, key=lambda r: (r["span"] is None, r["span"] or (0, 0, False)))
    out, step = [], GROUP_MAX - OVERLAP
    for k in range(0, len(rows), step):
        out.append(rows[k:k + GROUP_MAX])
        if k + GROUP_MAX >= len(rows):
            break
    return out


def _title_tokens(i: dict) -> tuple[set[str], set[str]]:
    """题名词块，**中英分开**。先去掉末尾括注 —— 那里放的是年代、材质、作者，不是题名；
    「（13 世纪初）」里的「世纪初」会把高丽青瓷和北宋绘画串到一起。

    中英必须分开算重叠度：混在一起时，一侧带一串中文三字词、另一侧只有英文，
    重叠度会被稀释到阈值以下 —— 《门卡乌拉王与王后》那对就是这么掉出去的。"""
    en = " ".join(L._PAREN_TAIL.sub("", x) for x in i["en_raw"])
    zh = " ".join(L._PAREN_TAIL.sub("", x) for x in i["zh_raw"])
    return ({x for x in L.en_tokens(en) if len(x) >= 4}, L.cjk_tokens(zh, 3))


def anon_groups(items: list[dict], anon: list[dict]) -> list[list[dict]]:
    """佚名桶：共用全表罕见的题名词、题名有一定重叠、且年代不冲突，才连成一组。

    ⚠ 单靠「共用一个稀有词」会单链传递成大组：实测第一版（二字词块）连出 167 件、
    改三字词块仍有 107 件 —— 元青花罐、高丽青瓷、罗马雕像被串进了门卡乌拉那一组，
    切块时同一件的两条被分到不同块。所以连边还要求**题名重叠度 ≥ ANON_JACCARD**，
    一个偶然的共同词不足以把两件东西拉到一起。
    """
    df = collections.Counter()
    toks = {}
    for i in items:
        t = _title_tokens(i)
        toks[i["key"]] = t
        df.update(t[0] | t[1])
    parent = {a["key"]: a["key"] for a in anon}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_tok = collections.defaultdict(list)
    for a in anon:
        for t in toks[a["key"]][0] | toks[a["key"]][1]:
            if 2 <= df[t] <= RARE_MAX:
                by_tok[t].append(a)
    for t, g in by_tok.items():
        for x, y in itertools.combinations(g, 2):
            if L.year_relation(x["span"], y["span"]) == "conflict":
                continue
            (xe, xz), (ye, yz) = toks[x["key"]], toks[y["key"]]
            if max(L.jaccard(xe, ye), L.jaccard(xz, yz)) < ANON_JACCARD:
                continue
            parent[find(x["key"])] = find(y["key"])
    comps = collections.defaultdict(list)
    for a in anon:
        comps[find(a["key"])].append(a)
    return [c for c in comps.values() if len(c) >= 2]


def build_groups(items: list[dict]) -> list[dict]:
    by_a = collections.defaultdict(list)
    for i in items:
        by_a[i["akey"]].append(i)
    groups = []
    for ak, rows in by_a.items():
        if ak == ANON:
            continue
        for p in periods(rows):
            for c in chunk(p):
                if len(c) >= 2:
                    groups.append({"akey": ak, "rows": c})
    for c in anon_groups(items, by_a.get(ANON, [])):
        for cc in chunk(c):
            groups.append({"akey": ANON, "rows": cc})
    for n, g in enumerate(groups):
        g["gid"] = n
    return groups


def fmt_row(i: dict) -> str:
    en = sorted(x for x in i["en_raw"] if x and x != i["name"])
    zh = sorted(x for x in i["zh_raw"] if x and x != i["name"] and L.has_cjk(x))
    span = i["span"]
    yr = "" if not span else (("约" if span[2] else "") + str(span[0])
                              + (f"–{span[1]}" if span[1] != span[0] else ""))
    acc = sorted(set().union(*i["acc"].values()))
    bits = [f"[{i['row']}] {i['name'][:110]}"]
    if en:
        bits.append(f"英={en[0][:80]}")
    if zh:
        bits.append(f"中={zh[0][:40]}")
    if yr:
        bits.append(f"年代={yr}")
    if acc:
        bits.append(f"馆藏号={','.join(acc[:2])}")
    return "  " + " | ".join(bits)


SYS = """每一组都是**同一位作者、同一时期**的博物馆藏品记录（「佚名」组是作者不可考、
但题名里有共同罕见词的一批）。记录来自同一馆（波士顿美术馆）的三批数据，
**同一件实物常以中英两条记录并存，两个题名可能没有任何共同字符**。

任务：找出每组里**指向同一件实物**的记录，按簇列出。没有重复的组返回空列表。

判为同一件：
  · 题名互为翻译或通行异名：`Slave Ship` = `奴隸船`；
    `Red Fuji`（赤富士）= `Fine Wind, Clear Weather`（凯风快晴）；
    `Menkaura` = `Mycerinus`（同一位法老的两种译名）。
  · 同一部作品的整体与分件、分卷、分开：「平治物语绘卷」与「平治物语绘卷·三条殿夜讨卷」；
    同一套册页的各开。
  · 年代差几十年不构成否决，古代作品断代本来就有出入。

不是同一件（**最常见的误判，务必分清**）：
  · 同一作者的**不同作品**：北斋《神奈川冲浪里》≠ 北斋《凯风快晴》；
    写乐同一年画的不同演员、同一系列的不同地点，都是不同的件。
  · `Untitled`、`Portrait of a Woman`、`Landscape` 这类通用题名，除非有别的证据，不要合。
  · 题名只差一个限定词但确是两幅画的（`Valley of the Petite Creuse` 与
    `Valley of the Creuse (Sunlight Effect)`）。

拿不准就不合 —— 合错会让两件不同东西的数据张冠李戴，漏合只是多一条重复记录。
每个簇给一句中文 reason。簇里只能出现本组的行号。"""

SCHEMA = {"type": "object", "properties": {"groups": {"type": "array", "items": {
    "type": "object", "properties": {
        "gid": {"type": "integer"},
        "clusters": {"type": "array", "items": {
            "type": "object", "properties": {
                "rows": {"type": "array", "items": {"type": "integer"}},
                "reason": {"type": "string"}},
            "required": ["rows", "reason"], "additionalProperties": False}}},
    "required": ["gid", "clusters"], "additionalProperties": False}}},
    "required": ["groups"], "additionalProperties": False}


def pack(groups: list[dict]) -> list[list[dict]]:
    calls, cur, n = [], [], 0
    for g in sorted(groups, key=lambda g: len(g["rows"])):
        if cur and n + len(g["rows"]) > PACK:
            calls.append(cur)
            cur, n = [], 0
        cur.append(g)
        n += len(g["rows"])
    if cur:
        calls.append(cur)
    return calls


def run_calls(calls: list[list[dict]], tag: str):
    """逐次调用并清洗结果。返回 (簇列表, 缓存命中数, 作答了的组, 清洗计数)。"""
    out, hit = [], 0
    answered: set[int] = set()
    cleaned = collections.Counter()
    for k, call in enumerate(calls):
        want = {g["gid"]: {r["row"] for r in g["rows"]} for g in call}
        user = "\n\n".join(f"### 组 {g['gid']}（作者：{g['akey']}）\n"
                           + "\n".join(fmt_row(r) for r in g["rows"]) for g in call)

        # 校验只管**结构性**问题（答非所问、大面积漏答）—— 这类才值得重问。
        # 细节问题就地清洗，不重付：2026-09-17 第一版校验要求「每个簇的行都在本组、
        # 且至少两行」，haiku 偶尔把别组行号混进来或给出单行簇，整批被判作废，
        # call 3 连续重试，每次都是一次完整的付费调用。
        def ok(d, w=want):
            got = {x.get("gid") for x in d.get("groups", [])}
            return len(got & set(w)) >= 0.8 * len(w)
        r, cached = LLM.ask(SYS, "按组找出指向同一件实物的记录：\n\n" + user, SCHEMA,
                            stage="dedupe_group", scope=f"{tag} {k}", validate=ok)
        hit += cached
        answered_here = set()
        for x in r["groups"]:
            gid = x.get("gid")
            if gid not in want:
                continue
            answered_here.add(gid)
            for c in x["clusters"]:
                rows_ok = sorted(set(c["rows"]) & want[gid])     # 剔掉混进来的别组行号
                dropped_rows = set(c["rows"]) - want[gid]
                if dropped_rows:
                    cleaned["别组行号"] += len(dropped_rows)
                if len(rows_ok) < 2:
                    cleaned["单行簇"] += 1
                    continue
                out.append({"gid": gid,
                            "akey": next(g["akey"] for g in call if g["gid"] == gid),
                            "rows": rows_ok, "reason": c["reason"]})
        answered |= answered_here
        missing = set(want) - answered_here
        if missing:
            cleaned["模型漏答的组"] += len(missing)
        print(f"  {k + 1}/{len(calls)}" + ("（缓存）" if cached else "")
              + (f"  漏答 {len(missing)} 组" if missing else ""), flush=True)

    return out, hit, answered, cleaned


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="exports/展品_波士顿美术馆_展厅检索.xlsx")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="只跑含这些行号的组，逗号分隔（验证用）")
    ap.add_argument("--no-second-pass", action="store_true", help="不对佚名组复问")
    ap.add_argument("--anon-only", action="store_true",
                    help="只补跑佚名组（两遍），结果与已有 dedupe_clusters.json 取并集；"
                         "具名作者组的旧结论原样保留")
    ap.add_argument("--include-ext", action="store_true",
                    help="连「全是 ext·wikidata 且有作者」的组也送模型（默认跳过）")
    args = ap.parse_args()

    items, _ = load_items(args.xlsx)
    groups = build_groups(items)
    ak = collections.Counter(i["akey"] if i["akey"] in (ANON,) or i["akey"].startswith("name:")
                             and False else ("佚名" if i["akey"] == ANON else
                                             "名字未入 Wikidata" if i["akey"].startswith("name:")
                                             else "有作者 QID") for i in items)
    print(f"作者键分布：{dict(ak)}")
    slots = sum(len(g["rows"]) for g in groups)
    in_any = {r["key"] for g in groups for r in g["rows"]}
    print(f"分组：{len(groups)} 组（佚名 {sum(1 for g in groups if g['akey']==ANON)}），"
          f"记录槽位 {slots}，覆盖 {len(in_any)} / {len(items)} 行")
    print(f"组大小：{sorted(collections.Counter(min(len(g['rows']),40)//5*5 for g in groups).items())}")

    # 「全是 ext·wikidata 且有具名作者」的组默认不送模型：
    # 组里每一行是 Wikidata 上**不同的实体**（QID 各不相同），同作者同时期的不同 QID
    # 几乎总是不同作品 —— 歌川国员同一年 40 张大阪名所图、写乐同一年 30 张役者绘都在这里。
    # 这一类占 666 组、约 71 次调用，花钱去确认「它们确实不同」不划算。
    # **佚名组例外，照跑**：它们已按稀有词块筛过，量小，
    # 且《平治物语绘卷》那对（两条都是 ext·wikidata、都佚名）就在里面。
    skipped = [g for g in groups if g["akey"] != ANON
               and {r["sub"] for r in g["rows"]} == {"ext·wikidata"}]
    if not args.include_ext:
        groups = [g for g in groups if g not in skipped]
        print(f"跳过「全是 ext·wikidata 且有作者」的 {len(skipped)} 组"
              f"（{sum(len(g['rows']) for g in skipped)} 槽位；要跑加 --include-ext）")

    if args.anon_only:
        groups = [g for g in groups if g["akey"] == ANON]
        print(f"--anon-only：只跑 {len(groups)} 个佚名组")

    if args.only:
        want = {int(x) for x in args.only.split(",")}
        groups = [g for g in groups if want & {r["row"] for r in g["rows"]}]
        print(f"--only：保留含 {sorted(want)} 的 {len(groups)} 组")

    calls = pack(groups)
    print(f"打包成 {len(calls)} 次调用（每次 ≤{PACK} 条），模型 {LLM.MODEL}")
    OUT_GROUPS.write_text(json.dumps(
        [{"gid": g["gid"], "akey": g["akey"], "rows": [r["row"] for r in g["rows"]]}
         for g in build_groups(items)], ensure_ascii=False, indent=1), encoding="utf-8")

    # 花钱之前先算清楚：按当前分组重跑，有几次能命中本地缓存
    mem = LLM._load()
    n_hit = sum(1 for call in calls
                if LLM._key(LLM.MODEL, SYS, "按组找出指向同一件实物的记录：\n\n" + "\n\n".join(
                    f"### 组 {g['gid']}（作者：{g['akey']}）\n" + "\n".join(fmt_row(r) for r in g["rows"])
                    for g in call), SCHEMA) in mem)
    print(f"预计缓存命中 {n_hit}/{len(calls)} 次，需实调 {len(calls) - n_hit} 次")

    if args.dry_run:
        for g in groups[:3]:
            print(f"\n组 {g['gid']}（{g['akey']}）：")
            print("\n".join(fmt_row(r) for r in g["rows"][:6]))
        return

    out, hit, answered, cleaned = run_calls(calls, "call")

    # 佚名组再问一遍（倒序排列，提示词不同 → 不命中第一遍的缓存）。
    # 佚名组没有「作者相同」这层结构性证据，模型输出的随机性影响最大：
    # 2026-09-17 同一个组（成员完全一样）问两次，一次判出《门卡乌拉王与王后》，一次漏了。
    # 两遍取并集提高召回；误合并由 dedupe_apply 里的弱证据闸兜住。
    if not args.no_second_pass:
        anon = [dict(g, rows=list(reversed(g["rows"]))) for g in groups if g["akey"] == ANON]
        if anon:
            calls2 = pack(anon)
            print(f"\n佚名组复问：{len(anon)} 组，{len(calls2)} 次调用")
            out2, hit2, _, cleaned2 = run_calls(calls2, "anon-pass2")
            seen = {(c["gid"], tuple(c["rows"])) for c in out}
            for c in out2:
                if (c["gid"], tuple(c["rows"])) not in seen:
                    c["pass"] = 2
                    out.append(c)
            hit += hit2
            cleaned.update(cleaned2)
            calls = calls + calls2

    if any(cleaned.values()):
        print(f"\n就地清洗：{dict(cleaned)}")

    target = OUT if not args.only else OUT.with_name("dedupe_clusters_probe.json")
    prev = None
    if args.anon_only and OUT.exists():
        # 与已有结论取并集：旧簇全留（写回时两道闸会用修好的年代重新把关），新簇补进来
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        have = {tuple(sorted(c["rows"])) for c in prev["clusters"]}
        added = [c for c in out if tuple(sorted(c["rows"])) not in have]
        print(f"\n与已有结论合并：旧簇 {len(prev['clusters'])}，新增 {len(added)}")
        for c in added:
            print(f"   + {c['rows']}  {c['reason'][:60]}")
        out = prev["clusters"] + added
    # 连同「哪些行送过模型」一起落盘 —— 写回工作簿时要据此区分
    # 「查过且独一」与「没查过」，这两种在上一轮里长得一样（151 件零候选被当成独有）。
    sent = sorted({r["row"] for g in groups if g["gid"] in answered for r in g["rows"]}
                  | (set(prev["sent_rows"]) if prev else set()))
    skipped_rows = sorted(({r["row"] for g in skipped for r in g["rows"]}
                           | (set(prev.get("skipped_ext_rows", [])) if prev else set())) - set(sent))
    target.write_text(json.dumps({
        "model": LLM.MODEL, "strategy": "作者+时期分组（用户 2026-09-17 定）",
        "sent_rows": sent, "skipped_ext_rows": skipped_rows if not args.include_ext else [],
        "clusters": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已写出 {target.name}：{len(out)} 个簇，涉及 {sum(len(c['rows']) for c in out)} 行"
          f"（缓存命中 {hit}/{len(calls)} 次）")


if __name__ == "__main__":
    main()
