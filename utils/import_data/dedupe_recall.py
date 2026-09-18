#!/usr/bin/env python3
"""跨语言召回：找出可能是同一件实物的行对。零 API。

用法：
    python3 dedupe_recall.py --xlsx "exports/展品_波士顿美术馆_展厅检索.xlsx"

产物（全部入仓库）：
    dedupe_hard.json    L0/L1 硬证据直接判定的对
    dedupe_cands.json   送模型确认的候选对
    dedupe_nocand.csv   **零候选清单 + 原因码** —— 见下

## 上一轮最实质的缺陷：零候选被静默判成「独有」

203 件 old 里只有 52 件产出候选，**其余 151 件一个候选都没有、从未送进模型**，
默认当成「独有」。没有任何痕迹说明它们只是没被查过。
本脚本因此有三道硬约束：

  1. 收尾按子集打印候选覆盖率，**低于上次运行即非零退出**（`.dedupe_coverage.json`）
  2. `dedupe_nocand.csv` 每行带**机读原因码**，其中 `TITLE_TOO_GENERIC` 与
     `NO_TRANSLATION` 是**可修的** —— 补一条译名或别名就能重新召回
  3. 下游用 `"no_candidate"` 而不是 `null`，让「没查过」与「查过且独有」在数据里长得不一样

## 三个通道

| 通道 | 判据 | 为什么需要 |
|---|---|---|
| A 馆藏号 | **跨管线**相等 | 唯一能自动接受的硬证据（实测 15/15 正确） |
| B 题名 | 规范化后完全相等，或 Jaccard ≥ 0.5 | `捣练图` 那对靠它 |
| C 作者+年代 | 创作者 QID 相同 且 年代区间重叠 | **`赤富士 ↔ Fine Wind, Clear Weather` 只能靠它** |

⚠ **通道 B 单独命中不足以自动接受。** 实测原清单 21 个题名完全相等的命中里，
有 7 个是 `Saint Sebastian`、`Madonna and Child`、`Portrait of a Young Woman`
这类通用题名，正确答案可能一个都不是。所以**非特异题名**（全表出现 > 4 次）
不能单独产生候选，只作佐证 —— 不加这条，ext 内部会凭空多出 1300+ 对垃圾候选。

⚠ **必须跑 ext×ext。** 上一轮只做 old×ext，而用户举的三对里**有两对是 ext 内部**
（官网那 134 件 vs Wikidata 那 4224 件）。
"""
from __future__ import annotations

import argparse
import collections
import csv
import itertools
import json
import pathlib
import re
import sys

import openpyxl

import dedupe_lib as L

HERE = pathlib.Path(__file__).parent
FACTS = HERE / "dedupe_facts.json"
OUT_HARD = HERE / "dedupe_hard.json"
OUT_CANDS = HERE / "dedupe_cands.json"
OUT_NOCAND = HERE / "dedupe_nocand.csv"
COVERAGE = HERE / ".dedupe_coverage.json"
SHEET = "去重后总表"

GENERIC_MAX = 4          # 规范化题名全表出现超过这个数就算非特异
JACCARD_MIN = 0.5
TOPK = 5                 # 每个锚点最多留几个候选
# 年代未知时，仍允许「同作者」单独产生候选的组大小上限。
# 组越大，「同作者」越不携带信息（Q6284966 名下 106 件）。
UNKNOWN_YEAR_GROUP_MAX = 20
# 稀有词块：一个词全表出现不超过这么多行才算稀有（常见词不携带身份信息）
RARE_TOKEN_MAX = 8
RARE_TOKEN_JACCARD = 0.2


def load_rows(path: str) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    rows = []
    for n, r in enumerate(it, start=2):
        d = dict(zip(hdr, r))
        d["_row"] = n
        rows.append(d)
    return rows


EN_EXPORT = HERE / "exports" / "en" / "Artworks - Museum of Fine Arts, Boston.xlsx"


def load_en_bridge() -> dict[int, str]:
    """原清单的英文题名桥：`序号` → 英文名。

    **这是原清单唯一的翻译桥。** `translations_artwork_names.csv` 对原清单是 0/179
    覆盖（实测 grep：`雾的警告`、`神奈川冲浪里`、`九龙图卷` 一条都没有），
    因为那张表的 key 是源 Excel 里的原始串，而原清单的中文短名从未进过翻译流程。
    但合并前的英文导出里它们是满的：`雾的警告→The Fog Warning`、
    `神奈川冲浪里→The Great Wave off Kanagawa`、`奴隶船→The Slave Ship`。

    没有它，原清单 179 行在英文空间里是空的，题名通道整片失效。
    """
    if not EN_EXPORT.exists():
        print(f"⚠ 缺英文导出 {EN_EXPORT.name} —— 原清单的英文题名桥不可用，召回会偏低")
        return {}
    wb = openpyxl.load_workbook(EN_EXPORT, read_only=True, data_only=True)
    out: dict[int, str] = {}
    for sh in wb.sheetnames:
        it = wb[sh].iter_rows(values_only=True)
        hdr = list(next(it))
        if "No." not in hdr or "Artwork Name" not in hdr:
            continue
        i_no, i_nm = hdr.index("No."), hdr.index("Artwork Name")
        for r in it:
            try:
                no = int(r[i_no])
            except (TypeError, ValueError):
                continue
            if r[i_nm]:
                out.setdefault(no, str(r[i_nm]))
    return out


def artist_from_name_prefix(name: str, alias2qid: dict[str, str]) -> str | None:
    """从 `作者《题名》…` 的前缀抽作者，**只在它匹配上真实艺术家别名时才采纳**。

    ext·官网那 134 行没有作者列，作者嵌在名称串里。AGENTS.md 的教训是
    「从半结构化文本抽字段时绝不能按位置猜 —— 逐段按模式判别，认不出的一概不写」。
    这里的判别器就是 Wikidata 那 2 万余条创作者别名：前缀能落到 QID 才算数，
    落不到就当没有。实测 134 行里 25 行命中（含葛饰北斋 Q5586、J.M.W. Turner Q159758），
    落不到的 109 行多是埃及外棺、巴比伦釉砖这类**本来就没有作者**的器物。
    """
    if "《" not in name:
        return None
    pre = name.split("《")[0].strip()
    pre = re.sub(r"^[（(].*?[)）]", "", pre).strip()      # 去掉「（传）」这类前缀
    return alias2qid.get(L.norm_person(pre)) if pre else None


def alias_index(facts: dict) -> dict[str, str]:
    """创作者别名 → QID 的反查词典。跨语言归一全靠它（2 万余条，含繁简两种中文标签）。"""
    alias2qid: dict[str, str] = {}
    for cq, v in facts.get("creators", {}).items():
        names = list(v.get("labels", {}).values())
        for lst in v.get("aliases", {}).values():
            names += lst
        for nm in names:
            alias2qid.setdefault(L.norm_person(nm), cq)
    return alias2qid


def build_text_index(alias2qid: dict[str, str]) -> tuple[dict, dict]:
    """把创作者别名词典拆成「可在自由文本里安全查找」的两张表。

    **为什么需要**：原清单 184 行里只有 16 行有作者列，但简介里常常写着 ——
    「宋徽宗赵佶花鸟名作」「温斯洛·霍默海洋绘画代表作」「南宋陈容《九龙图》」。
    不从文本里把作者捞出来，整批原清单就进不了「作者+年代」通道
    （实测《五色鹦鹉图卷》就是这么漏掉的：对面那条作者是宋徽宗 Q7486，
    而它自己作者列为空、英文桥给的 `Five‑Coloured Parrot Scroll` 与
    `Five-colored parakeet…` 只共用一个 `five`，Jaccard 0.11）。

    **长度下限是防误判的唯一手段**（AGENTS.md：子串匹配撞上音译人名就是灾难）：
    中文别名至少 3 字（「赵佶」这类 2 字的一律不用，太容易撞），
    拉丁别名至少 6 个字母，且要求词边界。
    """
    cjk, latin = {}, {}
    for a, q in alias2qid.items():
        if not a:
            continue
        if L.has_cjk(a):
            if len(a) >= 3:
                cjk[a] = q
        elif len(a) >= 6:
            latin[a] = q
    return cjk, latin


def artist_from_text(text: str, cjk: dict, latin: dict) -> str | None:
    """在自由文本里找创作者别名，取**最长匹配**。找不到返回 None，不猜。"""
    s = str(text or "")
    if not s:
        return None
    best, best_len = None, 0
    core = "".join(L.CJK_RE.findall(s))
    for n in range(6, 2, -1):                       # 长的优先
        for i in range(len(core) - n + 1):
            q = cjk.get(core[i:i + n])
            if q and n > best_len:
                best, best_len = q, n
        if best:
            return best
    words = re.findall(r"[A-Za-z][A-Za-z'\-\.]*", s)
    for n in range(4, 0, -1):
        for i in range(len(words) - n + 1):
            key = L.norm_person(" ".join(words[i:i + n]))
            q = latin.get(key)
            if q and len(key) > best_len:
                best, best_len = q, len(key)
        if best:
            return best
    return best


def title_jaccard(x: dict, y: dict) -> float:
    """题名重叠度。**必须用原始串分词**，不能用 norm_title 的结果（见 build 里的注释）。"""
    return max(L.jaccard(L.en_tokens(" ".join(x["en_raw"])), L.en_tokens(" ".join(y["en_raw"]))),
               L.jaccard(L.cjk_tokens(" ".join(x["zh_raw"])), L.cjk_tokens(" ".join(y["zh_raw"]))))


def build(rows: list[dict], facts: dict, en_bridge: dict[int, str]) -> list[dict]:
    """把每行压成统一事实：子集、作者 QID、年代区间、题名渲染集合、馆藏号。"""
    works = facts.get("works", {})
    creators = facts.get("creators", {})
    alias2qid = alias_index(facts)
    cjk_alias, latin_alias = build_text_index(alias2qid)

    out = []
    for r in rows:
        q = L.qid_of(r)
        w = works.get(q, {}) if q else {}
        sub = L.subset(r)

        # ---- 作者：先用 Wikidata 的 P170，再退到表里的作者列反查别名词典
        # ⚠ 只认真正的 QID。Wikidata 的 P170 也会返回**匿名创作者节点**
        # （`.well-known/genid/<hash>`），那是「作者不可考」的占位，不是一个人。
        # 把它当作者用，会让一堆不同作品因为「同一个匿名节点」被召到一起 ——
        # 实测 2012.629 那组三件就各挂一个不同的 genid。
        cq = next((c for c in (w.get("creators") or []) if re.fullmatch(r"Q\d+", c)), None)
        raw_artist = str(r.get("作者") or "").strip()
        if not cq and L.artist_usable(raw_artist):
            cq = alias2qid.get(L.norm_person(raw_artist))
        name_all = str(r.get("展品名称") or "")
        if not cq:                                   # ext·官网：作者嵌在名称里
            cq = artist_from_name_prefix(name_all, alias2qid)
        if not cq:                                   # 原清单：作者只在简介文字里
            cq = artist_from_text(f"{name_all} {r.get('展品简介') or ''}",
                                  cjk_alias, latin_alias)
        artist_txt = raw_artist if L.artist_usable(raw_artist) else ""
        if not artist_txt and cq:
            lbls = creators.get(cq, {}).get("labels", {})
            artist_txt = lbls.get("zh") or lbls.get("en") or ""

        # ---- 年代：Wikidata P571 优先，其次表里三列，最后从名称里抠
        span = None
        for cand in (w.get("inception", [None])[0] if w.get("inception") else None,
                     r.get("绝对年代"), r.get("确切纪年"), r.get("年代"),
                     r.get("展品名称")):
            span = L.year_span(cand)
            if span:
                break

        # ---- 题名渲染集合
        name = str(r.get("展品名称") or "")
        en, zh = set(), set()
        for lg, v in (w.get("labels") or {}).items():
            (zh if lg.startswith("zh") else en if lg == "en" else zh).add(v)
        for lg, lst in (w.get("aliases") or {}).items():
            for v in lst:
                (zh if lg.startswith("zh") else en if lg == "en" else zh).add(v)
        # 名称里 《》 内外的片段：`葛饰北斋《凯风快晴》Red Fuji（…）` 两侧都要
        for seg in re.findall(r"《([^》]+)》", name):
            (zh if L.has_cjk(seg) else en).add(seg)
        rest = re.sub(r"《[^》]+》", " ", name)
        rest = re.sub(r"[（(][^（()]*[)）]\s*$", " ", rest)
        for seg in re.split(r"[，,；;·]", rest):
            seg = seg.strip()
            if len(seg) >= 3:
                (zh if L.has_cjk(seg) else en).add(seg)
        if name:
            (zh if L.has_cjk(name) else en).add(name)
        # 原清单的英文题名只有那份英文导出里有
        if sub == "原清单":
            try:
                en_name = en_bridge.get(int(r.get("序号")))
            except (TypeError, ValueError):
                en_name = None
            if en_name:
                en.add(en_name)

        out.append({
            "key": L.row_key(r), "row": r["_row"], "sub": sub, "qid": q,
            "tier": r.get("Tier"), "name": name,
            "creator_qid": cq, "artist_txt": artist_txt, "span": span,
            "acc": L.accessions(r),
            # 归一化串用于**精确相等**比较（去空格去冠词，`The Slave Ship`→`slaveship`）
            "en": {L.norm_title(x) for x in en if L.norm_title(x)},
            "zh": {L.norm_title(x) for x in zh if L.norm_title(x)},
            # ⚠ 原始串必须另存一份用于**分词**。`norm_title` 把空格也去掉了，
            # 拿它分词会得到 `triadkingmenkaura` 这样的整串单 token，
            # 两边永远没有交集 —— 题名重叠通道因此一直是死的（2026-09-16 发现）。
            "en_raw": en, "zh_raw": zh,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--no-gate", action="store_true", help="跳过覆盖率回退闸（首次运行用）")
    args = ap.parse_args()

    if not FACTS.exists():
        sys.exit(f"缺 {FACTS.name} —— 先跑 dedupe_facts.py")
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    rows = load_rows(args.xlsx)
    en_bridge = load_en_bridge()
    print(f"原清单英文题名桥：{len(en_bridge)} 条")
    items = build(rows, facts, en_bridge)
    print(f"读入 {len(items)} 行；子集 {collections.Counter(i['sub'] for i in items)}")
    print(f"可用作者 QID {sum(1 for i in items if i['creator_qid'])}｜"
          f"有年代 {sum(1 for i in items if i['span'])}")

    # ---------------- 非特异题名（全表出现次数）
    freq = collections.Counter()
    for i in items:
        for t in i["en"] | i["zh"]:
            freq[t] += 1
    generic = {t for t, n in freq.items() if n > GENERIC_MAX}
    print(f"非特异题名 {len(generic)} 个（出现 > {GENERIC_MAX} 次），只作佐证不单独召回")

    # ---------------- 通道 A：跨管线馆藏号
    hard, seen = [], set()
    by_acc: dict[tuple[str, str], list] = collections.defaultdict(list)
    for i in items:
        for pipe, s in i["acc"].items():
            for a in s:
                by_acc[(a, pipe)].append(i)
    accs = {a for a, _ in by_acc}
    for a in accs:
        wd, meta = by_acc.get((a, "wikidata"), []), by_acc.get((a, "meta"), [])
        for x, y in itertools.product(wd, meta):
            if x["key"] == y["key"]:
                continue
            pair = tuple(sorted([x["key"], y["key"]]))
            if pair in seen:
                continue
            # 自动接受前的零成本一致性检查：三条至少满足一条
            yr = L.year_relation(x["span"], y["span"])
            checks = {
                "作者不冲突": not (x["creator_qid"] and y["creator_qid"]
                               and x["creator_qid"] != y["creator_qid"]),
                "年代不冲突": yr != "conflict",
                "题名有交集": bool(x["en"] & y["en"] or x["zh"] & y["zh"]),
            }
            seen.add(pair)
            hard.append({"a": list(x["key"]), "b": list(y["key"]),
                         "a_row": x["row"], "b_row": y["row"],
                         "a_name": x["name"][:80], "b_name": y["name"][:80],
                         "rule": f"跨管线馆藏号 {a}", "checks": checks,
                         "auto": all(checks.values()) or sum(checks.values()) >= 2})
    print(f"通道 A（跨管线馆藏号）：{len(hard)} 对，"
          f"其中自动接受 {sum(1 for h in hard if h['auto'])}")

    # ---------------- 通道 D：组画/册页分件（用户 2026-09-16 定：合成一件）
    # 判据是**基号相同 + 作者 QID 相同**，不是只看基号 ——
    # 实测基号 2012.629 那组三件各挂一个不同的匿名创作者节点、题名也各不相同，
    # 只看基号会把三件不同的东西合成一件。
    by_base: dict[str, dict] = collections.defaultdict(dict)
    for i in items:
        for pipe, s in i["acc"].items():
            for a in s:
                if a.count(".") >= 2:
                    by_base[L.acc_base(a)][i["key"]] = i
    n_group = 0
    for base, members in by_base.items():
        g = list(members.values())
        cqs = {x["creator_qid"] for x in g if x["creator_qid"]}
        if len(g) < 2 or len(cqs) != 1 or any(not x["creator_qid"] for x in g):
            continue
        anchor = g[0]
        for other in g[1:]:
            pair = tuple(sorted([anchor["key"], other["key"]]))
            if pair in seen:
                continue
            seen.add(pair)
            n_group += 1
            hard.append({"a": list(anchor["key"]), "b": list(other["key"]),
                         "a_row": anchor["row"], "b_row": other["row"],
                         "a_name": anchor["name"][:80], "b_name": other["name"][:80],
                         "rule": f"组画分件 基号 {base}（作者 {cqs.pop() if cqs else '?'} 一致）",
                         "checks": {"基号相同": True, "作者一致": True}, "auto": True})
    print(f"通道 D（组画/册页分件）：{n_group} 对，全部自动接受")

    # ---------------- 通道 B/C：候选
    by_creator: dict[str, list] = collections.defaultdict(list)
    for i in items:
        if i["creator_qid"]:
            by_creator[i["creator_qid"]].append(i)
    by_title: dict[str, list] = collections.defaultdict(list)
    for i in items:
        for t in (i["en"] | i["zh"]) - generic:
            by_title[t].append(i)

    cands: dict[tuple, dict] = {}

    def add(x, y, channel, ev):
        if x["key"] == y["key"]:
            return
        pair = tuple(sorted([x["key"], y["key"]]))
        if pair in seen:
            return
        c = cands.setdefault(pair, {"a": x, "b": y, "channels": set(), "ev": {}})
        c["channels"].add(channel)
        c["ev"].update(ev)

    for t, group in by_title.items():                     # B：特异题名相等
        if len(group) < 2:
            continue
        for x, y in itertools.combinations(group, 2):
            add(x, y, "题名相等", {"title": t})

    for cq, group in by_creator.items():                  # C：作者 + 年代
        if len(group) < 2 or len(group) > 120:            # 超大组（匿名/佚名）跳过
            continue
        for x, y in itertools.combinations(group, 2):
            yr = L.year_relation(x["span"], y["span"])
            if yr == "conflict":
                continue
            j = title_jaccard(x, y)
            # ⚠ **年代未知不能当否决。** 早先这里写的是 `yr == "overlap" or j >= …`，
            # 于是「神奈川冲浪里」（原清单，无年代）与北斋其余三件一个候选都配不上 ——
            # 等于拿「未知」当了「冲突」，正是上一轮 151 件零候选的同一个错误。
            # 放开的代价靠**组大小**控制：同一位高产艺术家名下几十件作品，
            # 光「同作者」这一条几乎不携带信息；小组里它才算证据。
            if yr == "overlap" or j >= JACCARD_MIN or (
                    yr == "unknown" and len(group) <= UNKNOWN_YEAR_GROUP_MAX):
                add(x, y, "作者+年代", {"creator": cq, "year": yr, "jaccard": round(j, 2),
                                    "group": len(group)})

    # ---------------- 通道 E：稀有词块（给无名器物用）
    # 通道 C 要作者、通道 B 要题名相等或高重叠，**古代无名器物两条都够不着**：
    # 《门卡乌拉、哈索尔女神与野兔诺姆神三联像》Triad of King Menkaura 与
    # Triad of King Mycerinus and two Goddesses 是同一件，但没有作者、
    # 题名 Jaccard 只有 0.25（Menkaura 与 Mycerinus 是同一位法老的两种译名）。
    # 这里改用**稀有词**做分块：全表只出现几次的词（menkaura、triad、khamerernebty）
    # 一旦两条共用，就值得让模型看一眼。常见词（king、statue）不作数。
    tok_index: dict[str, list] = collections.defaultdict(list)
    for i in items:
        for t in L.en_tokens(" ".join(i["en_raw"])) | L.cjk_tokens(" ".join(i["zh_raw"]), 3):
            if len(t) >= 4:                      # 太短的词区分度不够
                tok_index[t].append(i)
    n_rare = 0
    for t, group in tok_index.items():
        if not (2 <= len(group) <= RARE_TOKEN_MAX):
            continue
        for x, y in itertools.combinations(group, 2):
            if L.year_relation(x["span"], y["span"]) == "conflict":
                continue
            if x["creator_qid"] and y["creator_qid"] and x["creator_qid"] != y["creator_qid"]:
                continue                          # 作者冲突，按用户判据直接排除
            j = title_jaccard(x, y)
            if j >= RARE_TOKEN_JACCARD:
                add(x, y, "稀有词块", {"token": t, "jaccard": round(j, 2)})
                n_rare += 1
    print(f"通道 E（稀有词块）：新增配对 {n_rare} 次")

    # 每个锚点最多留 TOPK 个：通道多的优先，其次 Jaccard 高的
    per_anchor: dict[tuple, list] = collections.defaultdict(list)
    for pair, c in cands.items():
        per_anchor[pair[0]].append((pair, c))
        per_anchor[pair[1]].append((pair, c))
    keep = set()
    for anchor, lst in per_anchor.items():
        lst.sort(key=lambda pc: (-len(pc[1]["channels"]), -pc[1]["ev"].get("jaccard", 0)))
        keep.update(p for p, _ in lst[:TOPK])

    out_cands = []
    for pair in keep:
        c = cands[pair]
        x, y = c["a"], c["b"]
        out_cands.append({
            "a": list(x["key"]), "b": list(y["key"]), "a_row": x["row"], "b_row": y["row"],
            "a_name": x["name"][:110], "b_name": y["name"][:110],
            "a_sub": x["sub"], "b_sub": y["sub"], "a_tier": x["tier"], "b_tier": y["tier"],
            "a_artist": x["artist_txt"], "b_artist": y["artist_txt"],
            "a_creator_qid": x["creator_qid"], "b_creator_qid": y["creator_qid"],
            "a_span": x["span"], "b_span": y["span"],
            "channels": sorted(c["channels"]), "evidence": c["ev"],
            # ext×ext（两个不同 QID）意味着 Wikidata 认为是两个实体，**默认只进复核清单**：
            # 量大（近 5000 对）且实测同管线同馆藏号 12/15 是假重复，全送模型是烧钱买噪声。
            # **但只对弱证据成立** —— 只靠「同作者」而年代还对不上的那批才是噪声。
            # 有稀有词块或题名相等这类身份证据的仍要送模型：
            # 《平治物语绘卷》与 `Night Attack on the Sanjô Palace…（Heiji monogatari emaki）`
            # 两条都是 ext·wikidata、都没有作者，靠共用的 `heiji`/`平治` 才配上对，
            # 一刀切会把它挡在模型之外。
            "review_only": (x["sub"] == "ext·wikidata" == y["sub"]
                            and c["channels"] <= {"作者+年代"}
                            and c["ev"].get("year") != "overlap"),
        })
    print(f"通道 B/C：候选 {len(out_cands)} 对"
          f"（其中只进复核清单的 ext×ext {sum(1 for c in out_cands if c['review_only'])}）")

    # ---------------- 零候选：必须可见
    has = {k for c in out_cands for k in (tuple(c["a"]), tuple(c["b"]))}
    has |= {k for h in hard for k in (tuple(h["a"]), tuple(h["b"]))}
    nocand = []
    for i in items:
        if i["key"] in has:
            continue
        if not i["creator_qid"] and not any(i["acc"].values()) and not (i["en"] | i["zh"]):
            code = "NO_ARTIST_NO_ACC_NO_TITLE"
        elif i["artist_txt"] and not i["creator_qid"]:
            code = "ARTIST_UNRESOLVED"
        elif (i["en"] | i["zh"]) and not ((i["en"] | i["zh"]) - generic):
            code = "TITLE_TOO_GENERIC"
        elif i["sub"] != "ext·wikidata" and not i["en"]:
            code = "NO_TRANSLATION"
        else:
            code = "NO_MATCH_FOUND"
        nocand.append({"来源表": i["key"][0], "来源行": i["key"][1], "子集": i["sub"],
                       "Tier": i["tier"], "展品名称": i["name"][:90], "原因码": code})
    with OUT_NOCAND.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["来源表", "来源行", "子集", "Tier", "展品名称", "原因码"])
        w.writeheader()
        w.writerows(nocand)

    OUT_HARD.write_text(json.dumps(hard, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_CANDS.write_text(json.dumps(out_cands, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------- 覆盖率与回退闸
    cov, tot = collections.Counter(), collections.Counter()
    for i in items:
        tot[i["sub"]] += 1
        if i["key"] in has:
            cov[i["sub"]] += 1
    print("\n候选覆盖率（有候选行数 / 参与行数）：")
    now = {}
    for s in tot:
        pct = cov[s] / tot[s] * 100
        now[s] = round(pct, 2)
        print(f"  {s:<14} {cov[s]:>5} / {tot[s]:<5} = {pct:5.1f}%")
    print(f"零候选 {len(nocand)} 行，原因码分布：{dict(collections.Counter(n['原因码'] for n in nocand))}")
    print(f"\n已写出 {OUT_HARD.name} / {OUT_CANDS.name} / {OUT_NOCAND.name}")

    prev = json.loads(COVERAGE.read_text()) if COVERAGE.exists() else None
    COVERAGE.write_text(json.dumps(now, ensure_ascii=False, indent=1), encoding="utf-8")
    if prev and not args.no_gate:
        drop = {s: (prev[s], now[s]) for s in now if s in prev and now[s] < prev[s] - 0.01}
        if drop:
            sys.exit(f"⚠ 候选覆盖率下降：{drop} —— 已中止（要放行加 --no-gate）")


if __name__ == "__main__":
    main()
