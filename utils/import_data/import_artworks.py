#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 artworks/ 下六个博物馆的展品清单导入 museum / gallery / artwork 三张表，
文本走 content / content_text 双语机制（与 import_data.py 共表，见下）。

用法：
  # 正式导入 MySQL
  python import_artworks.py --host 44.207.251.65 --user ari --password *** --database ari

  # 不连 MySQL，用 SQLite 试跑一遍验证清洗逻辑
  python import_artworks.py --sqlite ./aw.db

六个源文件格式各不相同，差异全部收敛在 MUSEUMS 里：
  - MFA 表头在第 1 行的 Master 页；1300 行中仅 203 行有数据，其余是空占位，
    且混入过一行表头（Tier 列出现值 'Tier'）—— 两者都靠「有没有名称」滤掉
  - PEM / HAM 读 All Tiers 页，表头第 1 行，但列序不同
  - 三个中文馆表头在第 4 行，列序一致

与 import_data.py 共用 content 表，各自只删自己名下的 kind，
并在互不重叠的ID段里显式分配ID（本侧 1,000,000 起）。任一侧单独重跑互不影响。

依赖：openpyxl；导入 MySQL 时另需 PyMySQL
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter

import openpyxl

from import_data import (CONF_TO_SOURCE, LANG_EN, LANG_ZH, Target, detect_lang,
                         load_translations)

ARTWORK_DIR = "artworks"

# 本数据集的内容ID段起点，与 import_data.py 的 0 段错开
CONTENT_ID_BASE = 1_000_000

CONTENT_KINDS = (
    "museum_name", "gallery_name", "gallery_theme",
    "artwork_name", "artwork_description", "artwork_medium", "artwork_tier_reason",
)

ON_VIEW_YES, ON_VIEW_NO, ON_VIEW_UNKNOWN = "在展", "未在展", "未知"

TIERS = {"S", "A", "B", "C"}


def s(v):
    """转成去空白的字符串，空值返回 None。"""
    if v is None:
        return None
    v = str(v).replace(" ", " ").strip()
    return v or None


def tier_of(v):
    """只认 S/A/B/C，其余（含「（原表未评）」、空）一律 None。"""
    v = s(v)
    return v if v in TIERS else None


def truthy(v):
    """Excel 里 True/False 有时是布尔有时是字符串。"""
    v = s(v)
    if v is None:
        return None
    return v.lower() in ("true", "1", "yes", "是")


# ---------------------------------------------------------------- 六个馆的差异
# cols 里的下标是 0 起的列号；缺的字段就不写。
# on_view 是一个把源值映射成三态的函数。
#
# **带两列 tier 的文件一律取原表的评级列，不取后来重算的那列：**
#   PEM  Tier=第 0 列      / tier_c=第 1 列        两列  36 条不一致
#   HAM  Tier=第 3 列      / tier_c=第 4 列        两列  86 条不一致
#   故宫 原 Tier=第 8 列   / Tier（重评）=第 7 列   两列 828 条不一致
# 重算列会把一批 S 降级（哈佛的莫高窟 320 窟壁画残片就被降到 B），
# 用户确认一律以原表评级为准。MFA / 国博 / 首博 只有一列 tier，无从选择。
#
# 故宫的两点后果，是已知代价不是 bug：
#   1. 原 Tier 有 157 条「（原表未评）」，由 tier_of() 归为 NULL（无评级）。
#   2. 第 9 列不可替代性得分与第 10 列评级理由属于重评那一套，与 tier 不同源。
#      即「评级理由」解释的是重评结论，未必解释得通原表评级。已向用户说明。
MUSEUMS = [
    dict(
        key="mfa_boston", name_zh="波士顿美术馆", name_en="Museum of Fine Arts, Boston",
        site_key="Museum of Fine Arts, Boston",
        file="MFA_Ariadne_1300_Artwork_Database.xlsx", sheet="Master", header_row=1,
        # 不取 Rank 列做 source_seq：MFA 的 Rank 是每个 Tier 段内各自从 1 排的
        # （S 段 1-100、A 段 1-300、B 段 1-900），在 Master 页里并不唯一，
        # 拿它当键会撞 uk_artwork_source。改用行序。
        cols=dict(tier=1, name_en=2, name_zh=3, gallery=4,
                  desc_en=8, desc_zh=9, on_view=12, medium=14),
        on_view=lambda r, c: ON_VIEW_YES if truthy(r[c["on_view"]]) else ON_VIEW_UNKNOWN,
    ),
    dict(
        key="pem", name_zh="皮博迪·埃塞克斯博物馆", name_en="Peabody Essex Museum",
        site_key=None,
        file="PEM_带tier_c.xlsx", sheet="All Tiers", header_row=1,
        # tier 取第 0 列的 Tier 而非第 1 列的 tier_c，与 HAM 同
        cols=dict(tier=0, name_en=2, name_zh=3, gallery=4,
                  desc_en=5, desc_zh=6, has_image=7, medium=8),
        # 源文件只有 Has Image，没有在展字段 —— 不能拿有没有图去推在展与否
        on_view=lambda r, c: ON_VIEW_UNKNOWN,
    ),
    dict(
        key="ham", name_zh="哈佛艺术博物馆", name_en="Harvard Art Museums",
        site_key=None,
        file="ham_带tier_c.xlsx", sheet="All Tiers", header_row=1,
        # tier 取第 3 列的 Tier 而非第 4 列的 tier_c —— 与 PEM 相反，见下方说明
        cols=dict(name_en=0, name_zh=1, gallery=2, tier=3,
                  desc_en=5, desc_zh=6, on_view=7, medium=8),
        on_view=lambda r, c: ON_VIEW_YES if truthy(r[c["on_view"]]) else ON_VIEW_NO,
    ),
    dict(
        key="nmc", name_zh="中国国家博物馆", name_en="National Museum of China",
        site_key="National Museum of China",
        file="国博在展文物清单_带Tier.xlsx", sheet="展品清单", header_row=4,
        cols=dict(seq=0, gallery=1, name_zh=2, desc_zh=3,
                  image_url=4, on_view=5, official_url=6, tier=7),
        on_view=lambda r, c: ON_VIEW_YES if s(r[c["on_view"]]) else ON_VIEW_UNKNOWN,
    ),
    dict(
        key="palace", name_zh="故宫博物院", name_en="Palace Museum (Forbidden City)",
        site_key="Palace Museum (Forbidden City)",
        file="故宫在展文物清单_Tier重评.xlsx", sheet="展品清单", header_row=4,
        # tier 取第 8 列「原 Tier」，第 7 列「Tier（重评）」不入库；理由见上方说明
        cols=dict(seq=0, gallery=1, name_zh=2, desc_zh=3, image_url=4,
                  on_view=5, official_url=6, tier=8, score=9, reason=10),
        on_view=lambda r, c: ON_VIEW_YES if s(r[c["on_view"]]) else ON_VIEW_UNKNOWN,
        gallery_index="展厅索引",
    ),
    dict(
        key="capital", name_zh="首都博物馆", name_en="Capital Museum",
        site_key=None,
        file="首博文物清单_带Tier.xlsx", sheet="展品清单", header_row=4,
        cols=dict(seq=0, gallery=1, name_zh=2, desc_zh=3,
                  image_url=4, on_view=5, official_url=6, tier=7),
        # 6133/6159 是「馆藏（在展状态未知）」，只有带 ✅ 的才算确认在展
        on_view=lambda r, c: ON_VIEW_YES if "在展" in (s(r[c["on_view"]]) or "")
                             and "未知" not in (s(r[c["on_view"]]) or "") else ON_VIEW_UNKNOWN,
    ),
]


# ---------------------------------------------------------------- 读取
def read_museum(m, base_dir):
    """读一个馆 -> (展品 list, 展厅 dict)。"""
    path = os.path.join(base_dir, m["file"])
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[m["sheet"]]
    c = m["cols"]
    need = max(c.values()) + 1

    items, seq_auto = [], 0
    for r in ws.iter_rows(min_row=m["header_row"] + 1, values_only=True):
        if len(r) < need:
            r = tuple(r) + (None,) * (need - len(r))
        name_zh = s(r[c["name_zh"]]) if "name_zh" in c else None
        name_en = s(r[c["name_en"]]) if "name_en" in c else None
        if not name_zh and not name_en:
            continue                       # MFA 的 1097 行空占位在这里被滤掉
        if name_en in ("ArtWorkName_EN", "Name (English)") or name_zh == "展品名称":
            continue                       # MFA Master 页混入的表头行
        seq_auto += 1
        seq = s(r[c["seq"]]) if "seq" in c else None
        try:
            seq = int(float(seq))
        except (TypeError, ValueError):
            seq = seq_auto                 # PEM/HAM 源表没有序号列，按出现顺序编

        img = s(r[c["image_url"]]) if "image_url" in c else None
        has_img = truthy(r[c["has_image"]]) if "has_image" in c else (img is not None or None)
        score = None
        if "score" in c:
            try:
                score = float(s(r[c["score"]]))
            except (TypeError, ValueError):
                score = None

        items.append(dict(
            museum_key=m["key"], source_seq=seq,
            name_key=name_zh or name_en, name_zh=name_zh, name_en=name_en,
            gallery=s(r[c["gallery"]]) if "gallery" in c else None,
            desc_zh=s(r[c["desc_zh"]]) if "desc_zh" in c else None,
            desc_en=s(r[c["desc_en"]]) if "desc_en" in c else None,
            medium=s(r[c["medium"]]) if "medium" in c else None,
            tier=tier_of(r[c["tier"]]) if "tier" in c else None,
            reason=s(r[c["reason"]]) if "reason" in c else None,
            irreplaceability=score,
            on_view=m["on_view"](r, c),
            has_image=has_img,
            image_url=img,
            official_url=s(r[c["official_url"]]) if "official_url" in c else None,
        ))

    # 展厅：先从展品里收集，再用「展厅索引」页补充元信息（目前只有故宫有）
    galleries = {}
    for it in items:
        if it["gallery"]:
            galleries.setdefault(it["gallery"], dict(
                museum_key=m["key"], name_key=it["gallery"],
                theme=None, location=None, minutes=None,
                official_url=it["official_url"],
            ))
    if m.get("gallery_index") and m["gallery_index"] in wb.sheetnames:
        gi = wb[m["gallery_index"]]
        for r in gi.iter_rows(min_row=4, values_only=True):
            gname = s(r[0])
            if not gname:
                continue
            # 索引页写「陶瓷馆」，展品表写「陶瓷馆（武英殿）」—— 用前缀对上
            for key, g in galleries.items():
                if key.startswith(gname):
                    g["location"] = s(r[1])
                    g["theme"] = s(r[2])
                    mm = re.search(r"(\d+)", s(r[3]) or "")
                    g["minutes"] = int(mm.group(1)) * 60 if "小时" in (s(r[3]) or "") else (
                        int(mm.group(1)) if mm else None)
    wb.close()
    return items, galleries


def read_all(base_dir):
    all_items, all_galleries = [], {}
    for m in MUSEUMS:
        items, gs = read_museum(m, base_dir)
        print(f"  {m['name_zh']:12} {len(items):>5} 件 / {len(gs):>3} 展厅")
        all_items += items
        for k, g in gs.items():
            all_galleries[(m["key"], k)] = g
    return all_items, all_galleries


# ---------------------------------------------------------------- 自检
def sanity_check(items, galleries):
    problems = []

    dup = [k for k, n in Counter((x["museum_key"], x["source_seq"]) for x in items).items() if n > 1]
    if dup:
        problems.append(f"{len(dup)} 组 (馆, 源序号) 重复，唯一键会插不进去：{dup[:5]}")

    known = set(galleries)
    orphan = {(x["museum_key"], x["gallery"]) for x in items
              if x["gallery"] and (x["museum_key"], x["gallery"]) not in known}
    if orphan:
        problems.append(f"{len(orphan)} 个展品的展厅不在展厅表：{sorted(orphan)[:3]}")

    noname = [x for x in items if not x["name_key"]]
    if noname:
        problems.append(f"{len(noname)} 条展品没有名称")

    bad = [x["name_key"] for x in items if x["on_view"] not in (ON_VIEW_YES, ON_VIEW_NO, ON_VIEW_UNKNOWN)]
    if bad:
        problems.append(f"{len(bad)} 条 on_view 取值非法：{bad[:3]}")

    no_gallery = sum(1 for x in items if not x["gallery"])
    if no_gallery:
        print(f"  [info] {no_gallery} 条展品没有展厅，gallery_id 将为 NULL")
    no_tier = Counter(x["museum_key"] for x in items if not x["tier"])
    if no_tier:
        print(f"  [info] 无 Tier 的展品：{dict(no_tier)}")
    return problems


# ---------------------------------------------------------------- 内容表
def collect_contents(items, galleries):
    """按 kind 去重收集全部可翻译文本。"""
    b = {k: set() for k in CONTENT_KINDS}
    for m in MUSEUMS:
        b["museum_name"].add(m["name_zh"])
    for g in galleries.values():
        b["gallery_name"].add(g["name_key"])
        if g["theme"]:
            b["gallery_theme"].add(g["theme"])
    for x in items:
        # 只登记「键文本」那一侧。双语馆的另一语种由 collect_pairs 挂到同一个内容ID上，
        # 若中英各建一条 content，另一条永远不会被 artwork 引用，白白留下孤儿内容
        b["artwork_name"].add(x["name_key"])
        desc = x["desc_zh"] or x["desc_en"]
        if desc:
            b["artwork_description"].add(desc)
        for f, kind in (("medium", "artwork_medium"), ("reason", "artwork_tier_reason")):
            if x[f]:
                b[kind].add(x[f])
    return {k: sorted(v) for k, v in b.items()}


def build_content_rows(buckets, trans, pairs, id_base=CONTENT_ID_BASE):
    """
    分配内容ID并生成 content / content_text 行。

    pairs 是源数据自带的双语对照 {(kind, 原文): 另一语种文本}，来自 MFA/PEM/HAM
    这三个本身就中英双语的馆 —— 它们的译文是源数据，不该标成 AI 翻译。
    """
    cid_of, content_rows, text_rows = {}, [], []
    stats = Counter()
    next_id = id_base
    for kind in CONTENT_KINDS:
        for key in buckets[kind]:
            next_id += 1
            cid_of[(kind, key)] = next_id
            content_rows.append((next_id, kind))

            texts = {detect_lang(key): (key, "原始")}
            other = pairs.get((kind, key))
            if other:                                   # 源数据自带的另一语种
                texts.setdefault(detect_lang(other), (other, "原始"))
            zh, en, conf = trans.get((kind, key), (None, None, ""))
            src = CONF_TO_SOURCE.get(conf, "AI翻译")
            if zh and LANG_ZH not in texts:
                texts[LANG_ZH] = (zh, src)
            if en and LANG_EN not in texts:
                texts[LANG_EN] = (en, src)
            for lang, (text, source) in texts.items():
                text_rows.append((next_id, lang, text[:512], source))
                stats[source] += 1
            if len(texts) < 2:
                stats["缺译"] += 1
    return cid_of, content_rows, text_rows, stats


def collect_pairs(items):
    """MFA/PEM/HAM 自带的中英对照 -> {(kind, 一侧): 另一侧}，双向都登记。"""
    pairs = {}
    for x in items:
        for zh, en, kind in ((x["name_zh"], x["name_en"], "artwork_name"),
                             (x["desc_zh"], x["desc_en"], "artwork_description")):
            if zh and en:
                pairs[(kind, zh)] = en
                pairs[(kind, en)] = zh
    for m in MUSEUMS:
        pairs[("museum_name", m["name_zh"])] = m["name_en"]
    return pairs


# ---------------------------------------------------------------- 写库
MUSEUM_COLS = ["id", "key_name", "name_cid", "site_key", "source_file"]
GALLERY_COLS = ["id", "museum_id", "name_key", "name_cid", "theme_cid",
                "location", "suggested_minutes", "official_url"]
ARTWORK_COLS = ["museum_id", "gallery_id", "source_seq", "name_key", "name_cid",
                "description_cid", "medium_cid", "tier", "tier_reason_cid",
                "irreplaceability", "on_view", "has_image", "image_url", "official_url"]


def load(t, items, galleries, trans):
    # 清空：展品三表全清，内容表只删本导入器名下的 kind
    for tb in ("artwork", "gallery", "museum"):
        t.exec(f"DELETE FROM {tb}")
    kinds = ", ".join(f"'{k}'" for k in CONTENT_KINDS)
    t.exec(f"DELETE FROM content_text WHERE content_id IN "
           f"(SELECT id FROM content WHERE kind IN ({kinds}))")
    t.exec(f"DELETE FROM content WHERE kind IN ({kinds})")
    if t.flavor == "mysql":
        for tb in ("artwork", "gallery", "museum"):
            t.exec(f"ALTER TABLE {tb} AUTO_INCREMENT = 1")

    # 内容
    buckets = collect_contents(items, galleries)
    cid, content_rows, text_rows, stats = build_content_rows(
        buckets, trans, collect_pairs(items))
    t.many(t.insert("content", ["id", "kind"]), content_rows)
    t.many(t.insert("content_text", ["content_id", "lang", "text", "source"]), text_rows)
    print(f"  content                 {len(content_rows):>6} 段"
          f"（{'、'.join(f'{k} {len(v)}' for k, v in buckets.items() if v)}）")
    print(f"  content_text            {len(text_rows):>6} 行"
          f"（原始 {stats['原始']} / 人工校对 {stats['人工校对']}"
          f" / AI翻译 {stats['AI翻译']} / 存疑 {stats['存疑']}）")
    if stats["缺译"]:
        print(f"  [info] {stats['缺译']} 段只有一个语种，展示时需按 locale 回落")

    # 博物馆：ID 显式给，顺序即 MUSEUMS 的顺序
    mid = {m["key"]: i for i, m in enumerate(MUSEUMS, 1)}
    t.many(t.insert("museum", MUSEUM_COLS),
           [(mid[m["key"]], m["key"], cid[("museum_name", m["name_zh"])],
             m["site_key"], m["file"]) for m in MUSEUMS])
    print(f"  museum                  {len(MUSEUMS):>6} 行")

    # 展厅：ID 也显式给，便于展品直接引用
    gid, grows = {}, []
    for i, ((mk, gname), g) in enumerate(sorted(galleries.items()), 1):
        gid[(mk, gname)] = i
        grows.append((i, mid[mk], gname, cid[("gallery_name", gname)],
                      cid[("gallery_theme", g["theme"])] if g["theme"] else None,
                      g["location"], g["minutes"], g["official_url"]))
    t.many(t.insert("gallery", GALLERY_COLS), grows)
    print(f"  gallery                 {len(grows):>6} 行")

    # 展品
    rows = []
    for x in items:
        rows.append((
            mid[x["museum_key"]],
            gid.get((x["museum_key"], x["gallery"])) if x["gallery"] else None,
            x["source_seq"], x["name_key"][:255], cid[("artwork_name", x["name_key"])],
            cid[("artwork_description", x["desc_zh"] or x["desc_en"])] if (x["desc_zh"] or x["desc_en"]) else None,
            cid[("artwork_medium", x["medium"])] if x["medium"] else None,
            x["tier"],
            cid[("artwork_tier_reason", x["reason"])] if x["reason"] else None,
            x["irreplaceability"], x["on_view"], x["has_image"],
            x["image_url"], x["official_url"],
        ))
    t.many(t.insert("artwork", ARTWORK_COLS), rows)
    print(f"  artwork                 {len(rows):>6} 行")
    print(f"  在展状态分布: {dict(Counter(x['on_view'] for x in items))}")

    # 孤儿内容守卫：每段内容都该被某一行引用。曾经踩过的坑是双语馆的简介
    # 中英各建了一条 content，而 artwork 只引用其中一条，白留一批没人用的内容
    used = {c for m in MUSEUMS for c in (cid[("museum_name", m["name_zh"])],)}
    used |= {c for g in grows for c in (g[3], g[4]) if c}
    used |= {c for r in rows for c in (r[4], r[5], r[6], r[8]) if c}
    orphan = len(content_rows) - len(used)
    if orphan:
        print(f"  [warn] {orphan} 段内容没有被任何行引用，多半是收集逻辑与写入逻辑取的键不一致")

    t.conn.commit()


# ---------------------------------------------------------------- SQLite 试跑
SQLITE_DDL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS museum (
  id INTEGER PRIMARY KEY,
  key_name TEXT NOT NULL UNIQUE,
  name_cid INTEGER NOT NULL REFERENCES content(id),
  site_key TEXT,
  source_file TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gallery (
  id INTEGER PRIMARY KEY,
  museum_id INTEGER NOT NULL REFERENCES museum(id) ON DELETE CASCADE,
  name_key TEXT NOT NULL,
  name_cid INTEGER NOT NULL REFERENCES content(id),
  theme_cid INTEGER REFERENCES content(id),
  location TEXT,
  suggested_minutes INTEGER,
  official_url TEXT,
  UNIQUE (museum_id, name_key)
);
CREATE TABLE IF NOT EXISTS artwork (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  museum_id INTEGER NOT NULL REFERENCES museum(id) ON DELETE CASCADE,
  gallery_id INTEGER REFERENCES gallery(id),
  source_seq INTEGER NOT NULL,
  name_key TEXT NOT NULL,
  name_cid INTEGER NOT NULL REFERENCES content(id),
  description_cid INTEGER REFERENCES content(id),
  medium_cid INTEGER REFERENCES content(id),
  tier TEXT CHECK (tier IS NULL OR tier IN ('S','A','B','C')),
  tier_reason_cid INTEGER REFERENCES content(id),
  irreplaceability REAL CHECK (irreplaceability IS NULL OR irreplaceability BETWEEN -100 AND 100),
  on_view TEXT NOT NULL DEFAULT '未知' CHECK (on_view IN ('在展','未在展','未知')),
  has_image INTEGER,
  image_url TEXT,
  official_url TEXT,
  UNIQUE (museum_id, source_seq)
);
"""

# 空跑时 content/content_text 也要有，直接复用榜单导入器的定义
SQLITE_CONTENT_DDL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS content (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS content_text (
  content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  lang TEXT NOT NULL,
  text TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '原始'
         CHECK (source IN ('原始','AI翻译','存疑','人工校对')),
  PRIMARY KEY (content_id, lang)
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=ARTWORK_DIR, help="六个 Excel 所在目录")
    ap.add_argument("--translations", nargs="*",
                    default=["translations_artwork_names.csv",
                             "translations_artwork_text.csv",
                             "translations_artwork_medium.csv"],
                    help="译名表；缺失的语种展示时靠回落，不阻断导入")
    ap.add_argument("--sqlite", help="试跑模式：写入指定 SQLite 文件而非 MySQL")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="ari")
    ap.add_argument("--password", default=os.environ.get("MYSQL_PASSWORD", ""))
    ap.add_argument("--password-file",
                    help="存放密码的文件（建议权限 600），优先于 --password；"
                         "避免密码出现在命令行与 shell 历史里")
    ap.add_argument("--database", default="ari")
    args = ap.parse_args()
    if args.password_file:
        args.password = open(os.path.expanduser(args.password_file)).read().strip("\n")

    print("读取六个馆 …")
    items, galleries = read_all(args.dir)
    print(f"  合计 {len(items)} 件 / {len(galleries)} 展厅")

    trans = load_translations(args.translations, CONTENT_KINDS)
    buckets = collect_contents(items, galleries)
    total_seg = sum(len(v) for v in buckets.values())
    if trans:
        n_doubt = sum(1 for v in trans.values() if v[2] == "存疑")
        print(f"读取译名表 … {len(trans)} 条 / 共 {total_seg} 段可翻译文本"
              + (f"（其中 {n_doubt} 条标记为存疑）" if n_doubt else ""))
    else:
        print(f"未找到译名表，{total_seg} 段文本只会有源语言一种")
    known = {(kind, key) for kind, keys in buckets.items() for key in keys}
    stale = [k for k in trans if k not in known]
    if stale:
        print(f"  [warn] 译名表有 {len(stale)} 条未匹配到原文（kind 或 key 写错？）：{stale[:3]}")

    print("数据自检 …")
    problems = sanity_check(items, galleries)
    if problems:
        print("  发现问题，已中止：")
        for p in problems:
            print("   -", p)
        sys.exit(1)
    print("  通过")

    print("写入数据库 …")
    if args.sqlite:
        import sqlite3
        if os.path.exists(args.sqlite):
            os.remove(args.sqlite)
        conn = sqlite3.connect(args.sqlite)
        conn.executescript(SQLITE_CONTENT_DDL)
        conn.executescript(SQLITE_DDL)
        load(Target(conn, "sqlite"), items, galleries, trans)
        conn.close()
    else:
        import pymysql
        conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                               password=args.password, database=args.database,
                               charset="utf8mb4", autocommit=False)
        load(Target(conn, "mysql"), items, galleries, trans)
        conn.close()
    print("完成")


if __name__ == "__main__":
    main()
