#!/usr/bin/env python3
"""把 PEM 官网栏目页的编目数据写进 artwork_meta，source_key='pem_official'。

数据源是 pem_official_data.py（18 个栏目页的抓取原文，逐字存在仓库里）。
提案第 4 节 **Tier 1**：馆方自己发布的编目数据。这是本库目前唯一的一级来源
—— PEM 官方藏品门户 explore-art.pem.org 已停服，196 件里官方页面链接 0 条。

【匹配必须严】
meta_scrape.py 的文件头记着上次的教训：宽松分词匹配 196×50 报出 28 条候选，
人工核对后只有 1 条是真的，其余全是 portrait / mask / ship 这类常见词碰巧撞上。
故本脚本沿用同一套 toks/STOP，并要求命中满足下列之一：

  ① 已人工核实（pem_official_data.VERIFIED）—— 最硬，直接按馆藏号取记录
  ② 作者姓氏出现在对方的 artist 字段中，且题名部分共同显著词 >= 1
  ③ 题名共同显著词 >= 3
  ④ 四位年份两边都出现（如 1279），且共同显著词 >= 1

②里「题名部分」是关键：作者名的词必须从共同词里剔除。同一作者的两件不同作品
姓名必然重合，拿它当匹配证据是循环论证。

【非循环校验】
VERIFIED 那 14 条不参与自动匹配的判定，跑完拿它去比自动匹配的结果：
2026-08-31 实测自动命中 12 件、馆藏号 12/12 一致、0 冲突。冲突会直接报错退出 ——
匹配器错了就该停下，而不是把错的关联写进库。

【中文取值】
库里所有展示文本都要中英双语（AGENTS.md 第 1 条），而抓回的是英文。
译文落在 translations_pem_official.csv，与其余 translations_*.csv 同一套格式与规矩：
**译名留在 CSV 里，不能只改数据库** —— set_meta 是按 source_key 清空重写的，
写在库里的译文重跑一次就没了。缺译时才调模型补，补完立刻追加进 CSV。
（不要用 meta_cache/：那个目录是 gitignore 的，译文放进去等于没留下。）
馆藏号语种中立，两边用同一个字符串。

用法：
    python3 meta_fill_official_pem.py --dry-run --model gpt-5.6-sol
    python3 meta_fill_official_pem.py --model gpt-5.6-sol
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

import meta_lib as M
import pem_official_data as P
from meta_scrape import toks

SOURCE_KEY = "pem_official"
KIND = "pem_official"
TRANS = Path(__file__).resolve().parent / "translations_pem_official.csv"
TRANS_HEADER = """\
# PEM 官网栏目页编目字段的中文译文
#
# key        —— 官网原文，去重键，须与 pem_official_data.py 里的抓取原文逐字一致
# zh / en    —— 两个语种的文本；en 即 key 本身
# confidence —— 官方 / AI / 存疑，只描述「译出来的那一半」
#
# 由 meta_fill_official_pem.py 增量补写，可直接手工编辑。
# **译名必须留在本文件**：set_meta 按 source_key 清空重写，只改数据库的话重跑就没了。
"""

# 抓回的字段 -> 库里的 meta_key。onview 不写：artwork.on_view 是独立的三态 ENUM，
# 由源文件决定；栏目页说的「ON VIEW」是页面写作那天的陈列状态，两者不是一回事，
# 混写会让「在展」这个字段同时有两种口径，而谁也说不清查询时该信哪个。
FIELD_KEY = {
    "artist":      "artist",
    "date":        "date_text",
    "material":    "material",
    "accession":   "accession_no",
    "acquisition": "acquisition",
    "culture":     "cultural_context",
}
# 馆藏号是编号不是文本，中英同串；其余要译
LANG_NEUTRAL = {"accession"}


def norm(s: str) -> str:
    """去掉变音符与各种非 ASCII 连字符。

    源数据里有 `Kū`、`Jizō` 和 U+2011 非断行连字符，官网写的是 Ku、Jizo、
    普通连字符。不规范化的话，同一个词在两边分出来的 token 根本对不上。
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[‐-―−]", "-", s)


def surname(s: str | None) -> str:
    if not s:
        return ""
    w = re.findall(r"[A-Za-z]{3,}", norm(s))
    return w[-1].lower() if w else ""


YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")


def match(art: dict, recs: list[dict]) -> tuple[dict, str] | None:
    """返回 (记录, 命中依据)。命中依据一并写进 source 字段，方便事后复核。"""
    tn = toks(norm(art["name"]))
    ta = toks(norm(art["artist"] or ""))
    sur = surname(art["artist"])
    yrs = set(YEAR.findall(norm(art["name"])))
    best = None
    for r in recs:
        tw = toks(norm(r["title"]))
        ov = (tn & tw) - ta                     # 剔除作者名，只看题名重合
        ra = norm(r["artist"] or "").lower()
        art_ok, who = (bool(sur) and sur in ra), sur
        # 作者名有时不在 artist 字段而写在展品名里（「John Thomson photograph of…」）。
        # 这种情况要求更严：姓名词 >= 5 字符，且**剔除姓名词之后**题名共同词仍 >= 2
        # —— 只凭一个词就认作者，撞上的几乎都是假的。
        # 注意这里全部用局部变量：早先直接改 sur / ov，改完的值会带进下一条记录，
        # 于是某一条的判定结果污染了后面所有条，且看不出任何异常。
        if not art_ok:
            name_sur = {t for t in tn if len(t) >= 5 and t in ra}
            if name_sur and len(ov - name_sur) >= 2:
                art_ok, who, ov = True, "/".join(sorted(name_sur)), ov - name_sur
        yr_ok = bool(yrs & set(YEAR.findall(norm(r["date"] or ""))))
        if art_ok and len(ov) >= 1:
            why = f"artist={who} title={'/'.join(sorted(ov))}"
        elif len(ov) >= 3:
            why = f"title={'/'.join(sorted(ov))}"
        elif yr_ok and len(ov) >= 1:
            why = f"year={'/'.join(sorted(yrs))} title={'/'.join(sorted(ov))}"
        else:
            continue
        if best is None or len(ov) > best[2]:
            best = (r, why, len(ov))
    return (best[0], best[1]) if best else None


def read_trans() -> tuple[dict[str, str], list[dict]]:
    """读译文表，返回 ({en: zh}, 原始行)。文件不存在时返回空。"""
    if not TRANS.exists():
        return {}, []
    with TRANS.open(encoding="utf-8") as f:
        lines = [l for l in f if not l.startswith("#")]
    rows = list(csv.DictReader(lines))
    return {r["key"]: r["zh"] for r in rows if r["zh"]}, rows


def write_trans(rows: list[dict]) -> None:
    with TRANS.open("w", encoding="utf-8", newline="") as f:
        f.write(TRANS_HEADER)
        w = csv.DictWriter(f, fieldnames=["kind", "key", "zh", "en", "confidence"])
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["key"]):
            w.writerow(r)


def translate(client, model, effort, todo: dict[str, str]) -> dict[str, str]:
    """英文取值 -> 中文。只译缓存里没有的。"""
    if not todo:
        return {}
    import audit_meta as A
    keys = sorted(todo)
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {
            "type": "object",
            "properties": {"en": {"type": "string"}, "zh": {"type": "string"}},
            "required": ["en", "zh"], "additionalProperties": False}}},
        "required": ["items"], "additionalProperties": False,
    }
    system = (
        "把博物馆编目字段从英文译成简体中文。这是藏品编目数据，不是文案：\n"
        "- 人名、机构名按通行译名；没有通行译名的保留原文，不要音译生造\n"
        "- 年代按中文习惯：'early 19th century'→'19 世纪早期'，'about 1800'→'约 1800 年'\n"
        "- 入藏信息保留捐赠人原名与年份：'Gift of John T. Prince, 1846'→"
        "'1846 年 John T. Prince 捐赠'\n"
        "- 材质按文物术语译：'Lacquered wood, gold leaf'→'髹漆木胎、金箔'\n"
        "**不要增补原文没有的信息，不要解释。** 逐条对应返回。")
    user = "请翻译以下 %d 条：\n" % len(keys) + "\n".join(f"- {k}" for k in keys)
    data = A.ask(client, model, system, user, "official_zh", schema, effort,
                 museum_key="pem")
    got = {d["en"]: d["zh"] for d in data["items"]}
    missing = [k for k in keys if k not in got]
    if missing:
        raise SystemExit(f"翻译漏了 {len(missing)} 条，例如：{missing[:3]}")
    return got


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--key-file", default="~/.openai_key")
    args = ap.parse_args()

    recs = P.records()
    by_acc = {}
    for r in recs:
        for a in P.accessions(r):
            by_acc.setdefault(a, r)

    conn = M.connect()
    cur = conn.cursor()
    cur.execute("""SELECT a.source_seq, tn.text, a.tier
                   FROM artwork a JOIN museum m ON m.id=a.museum_id AND m.key_name='pem'
                   JOIN content_text tn ON tn.content_id=a.name_cid AND tn.lang='en'
                   ORDER BY a.source_seq""")
    arts = [{"seq": r[0], "name": r[1], "tier": r[2]} for r in cur.fetchall()]
    # 已有的 artist 取值参与匹配 —— 作者姓氏是最可靠的单一信号
    cur.execute("""SELECT am.source_seq, t.text FROM artwork_meta am
                   JOIN content_text t ON t.content_id=am.value_cid AND t.lang='en'
                   WHERE am.museum_key='pem' AND am.key_name='artist'""")
    artist_of = dict(cur.fetchall())
    for a in arts:
        a["artist"] = artist_of.get(a["seq"])

    # ---- 匹配 ----
    auto, mapped = {}, {}
    for a in arts:
        m = match(a, recs)
        if m:
            auto[a["seq"]] = m

    # 非循环校验：自动匹配的结果拿人工核实过的那 14 条去比
    ok = conflict = 0
    for seq, acc in P.VERIFIED.items():
        if seq in auto:
            got = (auto[seq][0]["accession"] or "").strip()
            if got == acc.strip():
                ok += 1
            else:
                conflict += 1
                print(f"[冲突] seq {seq}：人工核实={acc}  自动匹配={got} "
                      f"({auto[seq][0]['title']})", file=sys.stderr)
    print(f"自动匹配 {len(auto)} 件；与人工核实集比对：一致 {ok}，冲突 {conflict}")
    if conflict:
        sys.exit("匹配器与人工核实结果冲突，已停止 —— 先查匹配规则，不要把错的关联写进库")

    # 人工核实的优先，自动匹配补足
    for seq, acc in P.VERIFIED.items():
        r = by_acc.get(acc)
        if r is None:
            sys.exit(f"VERIFIED 里 seq {seq} 的馆藏号 {acc} 在抓取数据中找不到 —— "
                     "多半是栏目页改版了，重抓 pem_official_data.py")
        mapped[seq] = (r, f"verified accession={acc}")
    for seq, m in auto.items():
        mapped.setdefault(seq, m)

    name_of = {a["seq"]: a["name"] for a in arts}
    print(f"\n合计关联 {len(mapped)} 件（人工核实 {len(P.VERIFIED)} + "
          f"自动新增 {len(mapped) - len(P.VERIFIED)}）：")
    for seq in sorted(mapped):
        r, why = mapped[seq]
        flag = "已核实" if seq in P.VERIFIED else "自动  "
        print(f"  {flag} seq {seq:3d}  {name_of[seq][:40]:42} -> "
              f"{r['title'][:38]:40} {r['accession'] or '—':14} [{why}]")

    # ---- 中文取值 ----
    need = set()
    for r, _ in mapped.values():
        for f in FIELD_KEY:
            if f not in LANG_NEUTRAL and r.get(f):
                need.add(r[f])
    cache, rows = read_trans()
    # 库里已有的中文译文优先：那 14 件当初是逐页比对过的，不该被新一轮机器翻译冲掉
    cur.execute("""SELECT te.text, tz.text FROM artwork_meta am
                   JOIN content_text te ON te.content_id=am.value_cid AND te.lang='en'
                   JOIN content_text tz ON tz.content_id=am.value_cid AND tz.lang='zh-CN'
                   WHERE am.museum_key='pem' AND am.source_key=%s""", (SOURCE_KEY,))
    seeded = 0
    for en, zh in cur.fetchall():
        if en in need and en not in cache:
            cache[en] = zh
            rows.append({"kind": KIND, "key": en, "zh": zh, "en": en,
                         "confidence": "官方"})
            seeded += 1
    if seeded:
        print(f"\n从库中已有译文回收 {seeded} 条（先前逐页核对过的，不重译）")

    todo = {t: "" for t in sorted(need) if t not in cache}
    if todo:
        if not args.model:
            sys.exit(f"有 {len(todo)} 条取值还没有中文，需要 --model 来翻译"
                     "（库里所有展示文本都必须中英双语）")
        import audit_meta as A
        client = A.LazyClient(args.key_file)
        print(f"翻译 {len(todo)} 条取值…")
        got = translate(client, args.model, A.norm_effort(args.effort), todo)
        cache.update(got)
        for en in sorted(got):
            rows.append({"kind": KIND, "key": en, "zh": got[en], "en": en,
                         "confidence": "AI"})
    if seeded or todo:
        write_trans(rows)
        print(f"  译文已写入 {TRANS.name}（共 {len(rows)} 条）")
    else:
        print("\n所有取值都已有译文，不调用翻译")

    # ---- 写库 ----
    mcache, n = {}, 0
    for seq in sorted(mapped):
        r, why = mapped[seq]
        for f, key in FIELD_KEY.items():
            v = r.get(f)
            if not v:
                continue
            zh = v if f in LANG_NEUTRAL else cache[v]
            M.set_meta(cur, "pem", seq, key, [(zh, v)], source_key=SOURCE_KEY,
                       source=r["url"], confidence="high",
                       filled_by="scrape", cache=mcache)
            n += 1
    print(f"\nartwork_meta：写入 {n} 条（source_key={SOURCE_KEY}），"
          f"新建值内容 {len(mcache)} 段")

    if args.dry_run:
        conn.rollback()
        print("--dry-run：未写库")
    else:
        conn.commit()
        print("已提交")
    conn.close()
    print("\n⚠ 写完要重跑 evidence_score.py —— best_source_tier 按实际来源重算，"
          "新增的 Tier 1 件数会变。")


if __name__ == "__main__":
    main()
