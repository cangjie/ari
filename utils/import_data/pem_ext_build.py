#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把官网 219 条与 Wikidata 73 条去重，够不着现有 196 件的那些生成为新展品。

    python3 pem_ext_build.py --review          # -> pem_ext_candidates.csv，人看
    python3 pem_ext_build.py --emit > pem_ext_data.py

**三轮比对，全部复用现成的严格匹配器，不发明新阈值**（2026-09-21 实测）：

    P1  官网 219 × Wikidata 73   按馆藏号精确匹配            ->  5 对
    P2  现有 196 × 官网 219      meta_fill_official_pem.match ->  14 自动 + 1 VERIFIED
                                 非循环校验 13/13 一致、0 冲突
    P3  现有 196 × Wikidata 73   题名强包含 + 作者            ->  0 对

P3 为 0 不是 bug：现有 196 件的名称是描述性转写而非编目题名，
179/196 对不上任何官方藏品（AGENTS.md 有详述）。这正是本轮要缓解的问题 ——
新增的这批**带馆藏号或 QID，可核验**，与原来那 196 件不是一个成色，
两批的完备度分数不可直接比较。

**为什么走单一 `pem` 馆 key 而不是另起 `pem_ext`。**
`gallery` 的唯一键是 `(museum_id, name_key)`，第二个馆 key 就得把 26 个展厅复制一份，
于是游客站在俞吉濬展厅里只看得到一半展品 —— 直接打败了「把展品归拢到展厅」这件事本身。
MFA 能分两个 key 是因为它没有展厅基准表。

**seq 稳定性**：现有 196 件的 `source_seq` 是 `artwork_tier_v3` / `artwork_meta` /
`artwork_evidence` / `llm_call_item` 四张表的软键，**一个都不能动**。所以：
  ① 本模块只发 197 及以后的号；
  ② 每行带**显式 seq**，是提交进仓库的数据，不是排序的副产品；
  ③ 重跑按**身份键**（馆藏号 / QID）幂等，已有的键保持原 seq，只在尾部追加新的；
  ④ 源 Excel 行数 ≠ 196、seq ≤ 196、seq 重复，一律 sys.exit。
**断号不算错**：某条候选以后消失了就留个洞，为了连续而重新编号会让它之后的
每一件展品换号 —— 那正是本节要防的事。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import unicodedata

import meta_lib as M
import pem_gallery_data as G
import pem_official_data as PO
import pem_site_data as PS
import pem_wikidata_data as PW
from meta_fill_official_pem import match as official_match
from pem_site_scrape import link_official

SEQ_BASE = 197
EXCEL = os.path.join("artworks", "PEM_带tier_c.xlsx")
EXCEL_ROWS = 196
SECTION_URL = "https://www.pem.org/the-pem-collection/"

OUT_CANDIDATES = "pem_ext_candidates.csv"
OUT_OVERRIDES = "pem_ext_overrides.csv"


def norm_acc(a: str | None) -> str | None:
    """馆藏号归一化。**只去前导零，不去尾零** —— `12.15` 和 `12.150` 可能是两件东西。"""
    s = re.sub(r"[^A-Z0-9.]", "", (a or "").upper())
    return s.lstrip("0") or None


def norm_title(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def excel_fingerprint() -> tuple[str, int]:
    """源 Excel 的指纹与行数，写进数据模块，两个读取方都断言。"""
    import openpyxl
    h = hashlib.sha256(open(EXCEL, "rb").read()).hexdigest()
    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    n = sum(1 for r in wb["All Tiers"].iter_rows(min_row=2, values_only=True)
            if r[2] or r[3])
    wb.close()
    return h, n


# ---------------------------------------------------------------- 载入三方
def load_official() -> list[dict]:
    """官网 219 条：pem_site_data（图片/在展/原文）× pem_official_data（编目字段）。"""
    pairs, problems = link_official(PS.records(), PO.records())
    if problems:
        sys.exit(f"[fatal] {len(problems)} 条官网记录对不上编目数据，"
                 f"先跑 pem_site_scrape.py --verify 查清：{problems[:3]}")
    out = []
    for site, off, how in pairs:
        accs = [a for a in PO.accessions(off) if a and a.lower() != "n/a"]
        out.append({
            "kind": "official",
            "section": site["section"],
            "title": (off.get("title") or "").strip(),
            "heading": site["heading"],
            "desc": site["desc"],
            "image": site["image"],
            "onview": site["onview"],
            "artist": _na(off.get("artist")),
            "date": _na(off.get("date")),
            "material": _na(off.get("material")),
            "acquisition": _na(off.get("acquisition")),
            "culture": _na(off.get("culture")),
            "accessions": accs,
            "link_how": how,
            "url": SECTION_URL + site["section"],
        })
    return out


def _na(v):
    v = (v or "").strip()
    return None if not v or v.lower() == "n/a" else v


def wd_creators(vals) -> str | None:
    """
    Wikidata 的 P170 会返回**匿名创作者节点**（`.well-known/genid/<hash>`）。
    那不是一个人，是「此处有个说不出名字的作者」的占位 —— 存进去会变成一个
    看起来像人名的哈希串（AGENTS.md 第 12 条踩过）。一律丢掉。
    """
    good = [v for v in (vals or []) if "genid" not in v and not v.startswith("http")]
    return "; ".join(good) or None


def wd_year(vals) -> str | None:
    """
    P571 给的是 ISO 时间戳 `1800-01-01T00:00:00Z`，年份精度的条目也长这样。
    **只取年份**：原样存下去，`1830-01-01` 会被下游当成省略写法的区间 `1830–01`
    （AGENTS.md 第 12 条实测过）。负号是公元前，保留。
    """
    out = []
    for v in vals or []:
        m = re.match(r"^(-?\d{1,5})-", v)
        if m:
            y = int(m.group(1))
            s = f"{abs(y)} BCE" if y < 0 else str(y)
            if s not in out:
                out.append(s)
    return "; ".join(out) or None


def load_wikidata() -> list[dict]:
    out, untitled = [], []
    for w in PW.records():
        labs = w.get("labels", {})
        en = (labs.get("en") or [None])[0]
        if not en:
            # 没有名字的东西进不了库（artwork.name_key 非空），而拿 QID 当名字
            # 就是给它编一个 —— 排除，但要报出来，不能悄悄少两条。
            untitled.append(w["qid"])
            continue
        out.append({
            "kind": "wikidata",
            "qid": w["qid"],
            "title": en,
            "artist": wd_creators(w.get("creator")),
            "date": wd_year(w.get("inception")),
            "material": "; ".join(w.get("material", [])) or None,
            "accessions": list(w.get("accession", [])),
            "image": (w.get("image") or [None])[0],
            "onview": None,
            "section": None,
            "url": f"https://www.wikidata.org/wiki/{w['qid']}",
        })
    if untitled:
        print(f"  [info] Wikidata 有 {len(untitled)} 条没有任何语种的标签，已排除："
              f"{', '.join(untitled)}", file=sys.stderr)
    return out


def load_existing() -> list[dict]:
    conn = M.connect()
    cur = conn.cursor()
    # **只取 Excel 来的那 196 件**（source_seq <= EXCEL_ROWS）。本模块生成的新行
    # 入库之后也在 PEM 名下 —— 不加这个条件，重跑时新行会拿去跟自己比对、
    # 匹配上自己，然后被当成「已认领」从候选里剔除。2026-09-22 入库后第一次重跑，
    # 靠下面那条件数断言拦下来的。
    cur.execute("""SELECT a.source_seq, tn.text FROM artwork a
                   JOIN museum m ON m.id = a.museum_id AND m.key_name = 'pem'
                   JOIN content_text tn ON tn.content_id = a.name_cid AND tn.lang = 'en'
                   WHERE a.source_seq <= %s
                   ORDER BY a.source_seq""", (EXCEL_ROWS,))
    arts = [{"seq": r[0], "name": r[1]} for r in cur.fetchall()]
    cur.execute("""SELECT am.source_seq, t.text FROM artwork_meta am
                   JOIN content_text t ON t.content_id = am.value_cid AND t.lang = 'en'
                   WHERE am.museum_key = 'pem' AND am.key_name = 'artist'
                     AND am.source_seq <= %s""", (EXCEL_ROWS,))
    artist_of = dict(cur.fetchall())
    for a in arts:
        a["artist"] = artist_of.get(a["seq"])
    if len(arts) != EXCEL_ROWS:
        sys.exit(f"[fatal] 库里 PEM 展品 {len(arts)} 件，预期 {EXCEL_ROWS} 件。"
                 f"seq 的稳定性前提不成立，停下。")
    return arts


# ---------------------------------------------------------------- 三轮比对
def dedupe(official, wikidata, existing):
    """返回 (新增候选, 统计)。每条候选带 identity 身份键与 merged 合并来源。"""
    stats = {}

    # P2 —— 现有 196 × 官网 219。认领掉的官网记录不再作为新展品。
    claimed_titles, conflicts = set(), 0
    auto = {}
    for a in existing:
        m = official_match(a, PO.records())
        if m:
            auto[a["seq"]] = m
            claimed_titles.add(norm_title(m[0].get("title")))
    for seq, acc in PO.VERIFIED.items():
        if seq in auto:
            got = (auto[seq][0].get("accession") or "").strip()
            if got != acc.strip():
                conflicts += 1
                print(f"  ⚠ VERIFIED 冲突 seq={seq} 自动={got!r} 人工={acc!r}", file=sys.stderr)
        else:
            for r in PO.records():
                if acc in (PO.accessions(r) or []):
                    claimed_titles.add(norm_title(r.get("title")))
    if conflicts:
        sys.exit(f"[fatal] 自动匹配与 VERIFIED 有 {conflicts} 处冲突 —— "
                 f"匹配器错了就该停下，不能把错的关联写进库。")
    stats["P2 认领现有展品"] = len(auto) + sum(
        1 for s in PO.VERIFIED if s not in auto)

    off_new = [o for o in official if norm_title(o["title"]) not in claimed_titles]
    stats["官网剩余（作为新展品）"] = len(off_new)

    # P1 —— 官网 × Wikidata，按馆藏号合并成一条
    by_acc = {}
    for o in off_new:
        for a in o["accessions"]:
            k = norm_acc(a)
            if k:
                by_acc.setdefault(k, o)
    merged = 0
    wd_new = []
    for w in wikidata:
        hit = None
        for a in w["accessions"]:
            k = norm_acc(a)
            if k and k in by_acc:
                hit = by_acc[k]
                break
        if hit is not None:
            hit.setdefault("qid", w["qid"])
            hit.setdefault("wd_image", w["image"])
            merged += 1
        else:
            wd_new.append(w)
    stats["P1 官网×Wikidata 合并"] = merged

    # P3 —— 现有 196 × Wikidata。题名强包含 + 至少两个实词。
    ex_titles = [(a["seq"], norm_title(a["name"])) for a in existing]
    STOP = {"the", "a", "an", "of", "and", "in", "with", "for"}
    p3 = 0
    wd_final = []
    for w in wd_new:
        t = norm_title(w["title"])
        strong = set(t.split()) - STOP
        hit = None
        if t and len(strong) >= 2:
            for seq, et in ex_titles:
                if t in et or et in t:
                    hit = seq
                    break
        if hit:
            p3 += 1
        else:
            wd_final.append(w)
    stats["P3 现有×Wikidata"] = p3
    stats["Wikidata 净新增"] = len(wd_final)

    cands = off_new + wd_final
    for c in cands:
        c["identity"] = identity_of(c)
    seen = {}
    for c in cands:
        if c["identity"] in seen:
            sys.exit(f"[fatal] 身份键重复：{c['identity']!r}。"
                     f"幂等前提不成立，先查清 —— 重复的键会让 seq 在重跑时漂移。")
        seen[c["identity"]] = c
    stats["新增候选合计"] = len(cands)
    return cands, stats


def identity_of(c) -> str:
    """身份键，按优先级：馆藏号 > QID > 栏目#题名。seq 绑定在它上面，重跑不漂。"""
    for a in c.get("accessions") or []:
        k = norm_acc(a)
        if k:
            return f"acc:{k}"
    if c.get("qid"):
        return f"qid:{c['qid']}"
    return f"sec:{c['section']}#{norm_title(c['title'])[:48]}"


# ---------------------------------------------------------------- 展厅
def gallery_for(c):
    try:
        return G.resolve_onview(c.get("onview"))
    except KeyError as e:
        sys.exit(f"[fatal] 在展原句里的目标 {e} 没有登记在 "
                 f"pem_gallery_data.ONVIEW_MAP 里。去登记它 —— 对应到某个实体展厅，"
                 f"或显式写 None。官网改了写法要被发现，不能静默变成「没展厅」。")


def assign_seqs(cands):
    """
    给候选发号。**已在 pem_ext_data.py 里的身份键保持原号**，只有新键才取尾号。
    """
    existing_map = {}
    try:
        import pem_ext_data as E
        existing_map = {r["identity"]: r["seq"] for r in E.ITEMS}
    except Exception:                                   # noqa: BLE001 —— 首次生成时还没有
        pass
    used = set(existing_map.values())
    nxt = max(used) + 1 if used else SEQ_BASE
    for c in sorted(cands, key=lambda x: (x["kind"], x.get("section") or "", x["identity"])):
        if c["identity"] in existing_map:
            c["seq"] = existing_map[c["identity"]]
        else:
            c["seq"] = nxt
            nxt += 1
    bad = [c for c in cands if c["seq"] <= EXCEL_ROWS]
    if bad:
        sys.exit(f"[fatal] {len(bad)} 条候选拿到了 <= {EXCEL_ROWS} 的号，"
                 f"会覆盖现有展品的软键。")
    seqs = sorted(c["seq"] for c in cands)
    if len(set(seqs)) != len(seqs):
        sys.exit("[fatal] seq 有重复")
    # **断号是允许的，而且是对的。** 某条候选以后消失了（Wikidata 条目被删、
    # 人工裁决 drop 掉），留个洞即可；为了连续而重新编号，会让所有在它之后的
    # 展品换号 —— 那正是 seq 稳定性要防的事。号一旦发出去就不再动。
    gaps = [n for n in range(seqs[0], seqs[-1] + 1) if n not in set(seqs)] if seqs else []
    if gaps:
        print(f"  [info] seq 有 {len(gaps)} 个断号（{gaps[:8]}{'…' if len(gaps) > 8 else ''}）"
              f"—— 这是对的，号发出去就不收回", file=sys.stderr)
    return cands


# ---------------------------------------------------------------- 产出
CAND_COLS = ["seq", "identity", "kind", "section", "title", "artist", "date",
             "material", "accession", "qid", "gallery", "gallery_why",
             "onview_raw", "image", "url", "desc"]


def row_of(c):
    g, why = gallery_for(c)
    return {
        "seq": c["seq"], "identity": c["identity"], "kind": c["kind"],
        "section": c.get("section") or "", "title": c.get("title") or "",
        "artist": c.get("artist") or "", "date": c.get("date") or "",
        "material": c.get("material") or "",
        "accession": "; ".join(c.get("accessions") or []),
        "qid": c.get("qid") or "", "gallery": g or "", "gallery_why": why,
        "onview_raw": c.get("onview") or "", "image": c.get("image") or "",
        "url": c.get("url") or "", "desc": c.get("desc") or "",
    }


def load_overrides():
    """人工裁决：identity -> drop / merge=<seq>。文件不存在就是没有裁决。"""
    if not os.path.exists(OUT_OVERRIDES):
        return {}
    out = {}
    with open(OUT_OVERRIDES, encoding="utf-8") as f:
        for r in csv.DictReader(l for l in f if not l.lstrip().startswith("#")):
            ident, act = (r.get("identity") or "").strip(), (r.get("action") or "").strip()
            if ident and act:
                out[ident] = act
    return out


def write_candidates(cands):
    with open(OUT_CANDIDATES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAND_COLS, lineterminator="\n")
        w.writeheader()
        for c in sorted(cands, key=lambda x: x["seq"]):
            w.writerow(row_of(c))
    print(f"  -> {OUT_CANDIDATES}（{len(cands)} 行）", file=sys.stderr)
    if not os.path.exists(OUT_OVERRIDES):
        with open(OUT_OVERRIDES, "w", encoding="utf-8", newline="") as f:
            f.write("# 人工裁决。identity 取 pem_ext_candidates.csv 的同名列。\n")
            f.write("# action: drop（这条不要） / merge=<现有展品的 source_seq>（其实是同一件）\n")
            f.write("identity,action,note\n")
        print(f"  -> {OUT_OVERRIDES}（空模板，按需填）", file=sys.stderr)


def emit(cands):
    ov = load_overrides()
    kept = [c for c in cands if ov.get(c["identity"]) != "drop"]
    merged = {c["identity"]: ov[c["identity"]]
              for c in cands if ov.get(c["identity"], "").startswith("merge=")}
    kept = [c for c in kept if c["identity"] not in merged]
    sha, rows = excel_fingerprint()
    if rows != EXCEL_ROWS:
        sys.exit(f"[fatal] 源 Excel 现在有 {rows} 行，预期 {EXCEL_ROWS}。"
                 f"现有展品的 source_seq 会整体平移，本模块的号全部作废。")

    w = sys.stdout.write
    w('#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n')
    w('"""PEM 的新增展品。**由 pem_ext_build.py --emit 生成，勿手工编辑。**\n\n')
    w(f'{len(kept)} 件，source_seq 从 {SEQ_BASE} 起。来源：\n')
    w('  官网藏品栏目页（pem_site_data + pem_official_data），带馆藏号，Tier 1；\n')
    w('  Wikidata P195=Q3373790，带 QID，Tier 3。\n\n')
    w('**与原有的 196 件不是一个成色。** 那 196 件的名称是描述性转写，179 件对不上\n')
    w('任何官方藏品；这批带馆藏号或 QID，可核验。两批的完备度分数不可直接比较。\n\n')
    w('`import_artworks.read_museum` 在读完 Excel 之后追加这些行。\n')
    w('**seq 是提交进仓库的数据，不是排序的副产品** —— 改动本文件的顺序不影响任何一行的号。\n')
    w('"""\n\n')
    w('# 源 Excel 的指纹。现有 196 件的 source_seq 由它决定，\n')
    w('# 对不上就说明源文件变了，本模块的号全部作废。\n')
    w('SOURCE_XLSX_SHA256 = %r\n' % sha)
    w('EXCEL_ROWS = %d\n' % EXCEL_ROWS)
    w('SEQ_BASE = %d\n\n' % SEQ_BASE)
    w('ITEMS: list[dict] = [\n')
    for c in sorted(kept, key=lambda x: x["seq"]):
        r = row_of(c)
        w('    dict(seq=%d, identity=%r, kind=%r,\n' % (r["seq"], r["identity"], r["kind"]))
        w('         title=%r,\n' % r["title"])
        w('         desc=%r,\n' % (r["desc"] or None))
        for k in ("artist", "date", "material", "accession", "qid",
                  "section", "gallery", "onview_raw", "image", "url"):
            w('         %s=%r,\n' % (k, r[k] or None))
        w('         gallery_why=%r),\n' % r["gallery_why"])
    w(']\n\n')
    w('ACCESSION_BY_SEQ = {r["seq"]: r["accession"] for r in ITEMS if r["accession"]}\n\n\n')
    w('def import_rows(museum_key="pem"):\n')
    w('    """\n')
    w('    转成 import_artworks.read_museum 的行格式，在 Excel 那 196 行之后追加。\n\n')
    w('    · name_key 取英文题名 —— PEM 是英文源馆，与现有 196 行同规矩；\n')
    w('      中文一律留 None，由 translate_artwork.py 补并落进 translations_*.csv。\n')
    w('    · gallery 已经是 26 个实体展厅里的名字（由证据定出），所以带\n')
    w('      gallery_resolved=True，**跳过 LABEL_MAP 那一步** —— 那是给旧主题标签用的。\n')
    w('    · on_view 只有两态来源：馆方页面写了在展就是「在展」，没写就是「未知」。\n')
    w('      **没写不等于不在展**，不要把 None 读成「未在展」。\n')
    w('    · tier 一律 None：这批还没评级，导出时应当显示为「无评级」而不是任何一档。\n')
    w('    """\n')
    w('    rows = []\n')
    w('    for r in ITEMS:\n')
    w('        rows.append(dict(\n')
    w('            museum_key=museum_key, source_seq=r["seq"],\n')
    w('            name_key=r["title"], name_zh=None, name_en=r["title"],\n')
    w('            gallery=r["gallery"], gallery_resolved=True,\n')
    w('            desc_zh=None, desc_en=r["desc"],\n')
    w('            medium=r["material"], tier=None, reason=None,\n')
    w('            irreplaceability=None,\n')
    w('            on_view=("在展" if r["onview_raw"] else "未知"),\n')
    w('            has_image=bool(r["image"]), image_url=r["image"],\n')
    w('            official_url=r["url"],\n')
    w('        ))\n')
    w('    return rows\n\n\n')
    w('def tier_rows():\n')
    w('    """\n')
    w('    转成 tier_v3.load_items 的行格式。**与 import_rows 同出一处** ——\n')
    w('    tier_v3 直接读 Excel，漏了这里它就永远看不到新行（「两条腿必须一致」）。\n\n')
    w('    category 取官网栏目名：源 Excel 那一列叫「Category / 类别」，\n')
    w('    对新行而言最诚实的对应物就是馆方自己把它归在哪个栏目。Wikidata 行没有栏目，留空。\n')
    w('    """\n')
    w('    out = []\n')
    w('    for r in ITEMS:\n')
    w('        sec = r["section"] or ""\n')
    w('        out.append({\n')
    w('            "seq": r["seq"], "name_en": r["title"], "name_cn": "",\n')
    w('            "gallery": r["gallery"] or "",\n')
    w('            "description": r["desc"] or "",\n')
    w('            "category": sec.replace("-", " ").title() if sec else "",\n')
    w('            "tier_old": "",\n')
    w('        })\n')
    w('    return out\n\n\n')
    w('def _check():\n')
    w('    seqs = [r["seq"] for r in ITEMS]\n')
    w('    assert len(set(seqs)) == len(seqs), "seq 有重复"\n')
    w('    assert not seqs or min(seqs) > EXCEL_ROWS, "seq 撞上了现有展品"\n')
    w('    assert seqs == sorted(seqs), "seq 未按升序排列"\n')
    w('    # 断号是允许的：号一旦发出去就不收回。为了连续而重新编号，\n')
    w('    # 会让它之后的每一件展品换号 —— 那正是 seq 稳定性要防的事。\n')
    w('    ids = [r["identity"] for r in ITEMS]\n')
    w('    assert len(set(ids)) == len(ids), "身份键有重复"\n')
    w('\n\n_check()\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", action="store_true", help="出候选 CSV 给人看")
    ap.add_argument("--emit", action="store_true", help="把数据模块写到标准输出")
    a = ap.parse_args()
    if not (a.review or a.emit):
        ap.error("给 --review 或 --emit")

    official, wikidata, existing = load_official(), load_wikidata(), load_existing()
    print(f"官网 {len(official)} 条 / Wikidata {len(wikidata)} 条 / "
          f"现有展品 {len(existing)} 件", file=sys.stderr)
    cands, stats = dedupe(official, wikidata, existing)
    for k, v in stats.items():
        print(f"  {k:28} {v}", file=sys.stderr)
    assign_seqs(cands)
    gal = sum(1 for c in cands if gallery_for(c)[0])
    print(f"  {'其中能定位到实体展厅':28} {gal}", file=sys.stderr)
    print(f"  {'seq 区间':28} {min(c['seq'] for c in cands)}–"
          f"{max(c['seq'] for c in cands)}", file=sys.stderr)

    if a.review:
        write_candidates(cands)
    else:
        emit(cands)


if __name__ == "__main__":
    main()
