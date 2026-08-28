#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 ari 库导出成 Excel，中文版与英文版各一套。

产出（默认写到 exports/zh-CN/ 与 exports/en/）：
  1 个「城市与博物馆遗产地列表」文件，三个 sheet 对应源 Excel 的三张表
  6 个「展品」文件，每馆一个，各含 S / A / B / C / 无评级 五个 sheet

两个版本互为镜像：同一份数据、同样的列序与 sheet 顺序，只是表头、正文、
ENUM 取值、sheet 名与文件名全部换成对应语种。**六个展品文件在同一版本内
列集完全一致**，取所有馆字段的并集，某馆没有的留空；sheet 没有数据也照建
并写表头，这样按 sheet 名读文件的脚本不会崩。

库里 continent / category / track / on_view 是中文 ENUM —— 当初刻意保留为
代码而非进内容表（6 个固定值不是自由文本），英文靠下面 VALUE_MAPS 映射。
加语种时这里要一起加。

用法：
  python export_excel.py --host 44.207.251.65 --user ari \
      --password-file ~/.ari-dbpass --database ari --out exports
  python export_excel.py ... --lang en        # 只出英文版

密码优先从 --password-file 读（建议权限 600），其次读环境变量 MYSQL_PASSWORD，
避免出现在命令行与 shell 历史里。

依赖：openpyxl、PyMySQL
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from decimal import Decimal

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ZH, EN = "zh-CN", "en"
LANGS = (ZH, EN)

# ---------------------------------------------------------------- 语种相关文案
DIR_NAME = {ZH: "zh-CN", EN: "en"}

TIER_SHEETS = {                      # 五个 sheet 恒定存在，顺序固定
    ZH: ["S", "A", "B", "C", "无评级"],
    EN: ["S", "A", "B", "C", "Unrated"],
}
UNRATED = {ZH: "无评级", EN: "Unrated"}

LIST_FILE = {ZH: "城市与博物馆遗产地列表", EN: "Cities and Heritage Sites"}
ARTWORK_FILE_PREFIX = {ZH: "展品_", EN: "Artworks - "}

SHEET_CITY = {ZH: "城市列表", EN: "Cities"}
SHEET_SITE = {ZH: "博物馆遗产地列表", EN: "Museums and Heritage Sites"}
SHEET_CHANGE = {ZH: "等级变动明细", EN: "Tier Changes"}

# ENUM 取值的中英对照。库里存中文，英文版按这里换。
VALUE_MAPS = {
    "continent": {"亚洲": "Asia", "欧洲": "Europe", "非洲": "Africa",
                  "北美洲": "North America", "南美洲": "South America",
                  "大洋洲": "Oceania"},
    "category": {"综合类": "Comprehensive", "艺术博物馆": "Art Museum",
                 "考古遗址": "Archaeological Site", "历史建筑群": "Historic Architecture",
                 "宗教遗产": "Religious Heritage"},
    "track": {"博物馆": "Museum", "遗址地": "Heritage Site"},
    "on_view": {"在展": "On view", "未在展": "Not on view", "未知": "Unknown"},
    "bool": {"是": "Yes", "否": "No"},
}


def mapv(kind, value, lang):
    if value is None or lang == ZH:
        return value
    return VALUE_MAPS[kind].get(value, value)


def tier_delta_text(d, lang):
    if d > 0:
        return f"↑升 {d} 档" if lang == ZH else f"↑ Up {d}"
    if d < 0:
        return f"↓降 {-d} 档" if lang == ZH else f"↓ Down {-d}"
    return "—"


# ---------------------------------------------------------------- 列定义
# 每列一个 (中文表头, 英文表头)。列序两版一致，改这里等于同时改两版。
CITY_COLUMNS = [
    ("排名", "Rank"), ("城市", "City"), ("国家", "Country"), ("大洲", "Continent"),
    ("艺术博物馆得分", "Art Museum Score"), ("历史文明得分", "History Score"),
    ("考古宗教遗产得分", "Archaeology & Religious Heritage Score"),
    ("建筑文化价值得分", "Architecture Score"), ("旅游可达性得分", "Accessibility Score"),
    ("综合得分", "Total Score"), ("博物馆遗产地数量", "Site Count"),
    ("代表性机构", "Flagship Institution"), ("类型", "Category"),
]

SITE_COLUMNS = [
    ("城市排名", "City Rank"), ("新Tier", "New Tier"), ("原Tier", "Previous Tier"),
    ("等级变动", "Tier Change"), ("赛道", "Track"), ("名称", "Name"),
    ("所在城市", "City"), ("所在国家", "Country"), ("所在大洲", "Continent"),
    ("综合得分", "Total Score"),
    ("维度1", "Dimension 1"), ("维度2", "Dimension 2"), ("维度3", "Dimension 3"),
    ("维度4", "Dimension 4"), ("维度5", "Dimension 5"), ("维度6", "Dimension 6"),
    ("定级理由", "Tier Rationale"), ("年参观人数", "Annual Visitors"),
    ("统计年份", "Visitor Year"), ("门类", "Collection Type"),
    ("原数据来源", "Data Source"),
    ("是博物馆", "Is Museum"), ("是遗址地", "Is Heritage Site"),
]

CHANGE_COLUMNS = [
    ("原Tier", "Previous Tier"), ("新Tier", "New Tier"), ("变动", "Change"),
    ("赛道", "Track"), ("名称", "Name"), ("所在城市", "City"), ("所在国家", "Country"),
    ("综合得分", "Total Score"), ("变动原因", "Change Reason"),
    ("规则版本(前)", "Rule Version (From)"), ("规则版本(后)", "Rule Version (To)"),
]

ARTWORK_COLUMNS = [
    ("博物馆", "Museum"), ("序号", "No."), ("展厅", "Gallery"),
    ("展品名称", "Artwork Name"), ("Tier", "Tier"), ("陈列状态", "Display Status"),
    ("展品简介", "Description"), ("门类", "Medium"),
    ("评级理由", "Tier Rationale"), ("不可替代性得分", "Irreplaceability Score"),
    ("有配图", "Has Image"), ("展品图片", "Image URL"), ("官方页面", "Official Page"),
]


def headers(columns, lang):
    return [c[0] if lang == ZH else c[1] for c in columns]


# ---------------------------------------------------------------- 写表
HEAD_FILL = PatternFill("solid", fgColor="DDEBF7")
HEAD_FONT = Font(bold=True)


def cell(v):
    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f == int(f) else f
    return v


def write_sheet(ws, cols, rows, lang):
    hdr = headers(cols, lang)
    ws.append(hdr)
    for i in range(1, len(hdr) + 1):
        h = ws.cell(row=1, column=i)
        h.fill, h.font = HEAD_FILL, HEAD_FONT
        h.alignment = Alignment(vertical="center")
    for r in rows:
        ws.append([cell(v) for v in r])
    ws.freeze_panes = "A2"
    for i, name in enumerate(hdr, 1):
        width = sum(2 if ord(ch) > 127 else 1 for ch in name)
        for r in rows[:400]:
            v = r[i - 1]
            if v is None:
                continue
            width = max(width, sum(2 if ord(ch) > 127 else 1 for ch in str(v)[:80]))
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 8), 60)


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()


# ---------------------------------------------------------------- 取数
class Exporter:
    def __init__(self, conn):
        self.cur = conn.cursor()
        self.text = {}
        self.cur.execute("SELECT content_id, lang, text FROM content_text")
        for cid, lang, txt in self.cur.fetchall():
            self.text[(cid, lang)] = txt
        self.fallbacks = 0

    def q(self, sql, args=None):
        self.cur.execute(sql, args or ())
        return self.cur.fetchall()

    def t(self, cid, lang):
        """取指定语种文本。理论上零缺译；真缺了就回落并计数，不静默留空。"""
        if not cid:
            return None
        v = self.text.get((cid, lang))
        if v is None:
            other = EN if lang == ZH else ZH
            v = self.text.get((cid, other))
            if v is not None:
                self.fallbacks += 1
        return v

    def cities(self, lang):
        cnt = dict(self.q("SELECT city_id, COUNT(*) FROM cultural_site GROUP BY city_id"))
        out = []
        for (cid, rank, ncid, cocid, cont, s1, s2, s3, s4, s5, st, cat, fcid) in self.q("""
                SELECT c.id, c.city_rank, c.name_cid, c.country_cid, c.continent,
                       c.score_art_museum, c.score_history, c.score_archaeology,
                       c.score_architecture, c.score_accessibility, c.score_total,
                       c.category, f.name_cid
                FROM city c LEFT JOIN cultural_site f ON f.id = c.flagship_site_id
                ORDER BY c.city_rank"""):
            out.append([rank, self.t(ncid, lang), self.t(cocid, lang),
                        mapv("continent", cont, lang),
                        s1, s2, s3, s4, s5, st, cnt.get(cid, 0),
                        self.t(fcid, lang), mapv("category", cat, lang)])
        return out

    def sites(self, lang):
        out = []
        for r in self.q("""
                SELECT c.city_rank, s.tier, s.tier_prev, s.tier_delta, s.track,
                       s.name_cid, c.name_cid, c.country_cid, c.continent, s.score_total,
                       s.dim1, s.dim2, s.dim3, s.dim4, s.dim5, s.dim6,
                       s.tier_reason_cid, s.annual_visitors, s.visitors_year,
                       s.collection_type_cid, s.data_source_cid,
                       s.is_museum, s.is_heritage_site
                FROM cultural_site s JOIN city c ON c.id = s.city_id
                ORDER BY s.score_total DESC"""):
            yn = lambda b: mapv("bool", "是" if b else "否", lang)
            out.append([r[0], r[1], r[2], tier_delta_text(r[3], lang),
                        mapv("track", r[4], lang),
                        self.t(r[5], lang), self.t(r[6], lang), self.t(r[7], lang),
                        mapv("continent", r[8], lang), r[9],
                        r[10], r[11], r[12], r[13], r[14], r[15],
                        self.t(r[16], lang), r[17], r[18],
                        self.t(r[19], lang), self.t(r[20], lang),
                        yn(r[21]), yn(r[22])])
        return out

    def changes(self, lang):
        out = []
        for r in self.q("""
                SELECT t.tier_from, t.tier_to, t.tier_delta, s.track,
                       s.name_cid, c.name_cid, c.country_cid, t.score_total,
                       t.change_reason_cid, t.rule_version_from, t.rule_version_to
                FROM cultural_site_tier_change t
                JOIN cultural_site s ON s.id = t.site_id
                JOIN city c ON c.id = s.city_id
                ORDER BY t.tier_delta DESC, t.score_total DESC"""):
            out.append([r[0], r[1], tier_delta_text(r[2], lang),
                        mapv("track", r[3], lang),
                        self.t(r[4], lang), self.t(r[5], lang), self.t(r[6], lang),
                        r[7], self.t(r[8], lang), r[9], r[10]])
        return out

    def museums(self):
        return self.q("SELECT id, key_name, name_cid FROM museum ORDER BY id")

    def artworks(self, museum_id, lang):
        out = defaultdict(list)
        for r in self.q("""
                SELECT m.name_cid, a.source_seq, g.name_cid, a.name_cid,
                       a.tier, a.on_view, a.description_cid, a.medium_cid,
                       a.tier_reason_cid, a.irreplaceability,
                       a.has_image, a.image_url, a.official_url
                FROM artwork a
                JOIN museum m ON m.id = a.museum_id
                LEFT JOIN gallery g ON g.id = a.gallery_id
                WHERE a.museum_id = %s
                ORDER BY FIELD(a.tier,'S','A','B','C'), a.source_seq""", (museum_id,)):
            has_img = None if r[10] is None else mapv("bool", "是" if r[10] else "否", lang)
            out[r[4] or UNRATED[lang]].append(
                [self.t(r[0], lang), r[1], self.t(r[2], lang), self.t(r[3], lang),
                 r[4], mapv("on_view", r[5], lang),
                 self.t(r[6], lang), self.t(r[7], lang), self.t(r[8], lang), r[9],
                 has_img, r[11], r[12]])
        return out


def export_one_lang(ex, lang, out_root):
    out = os.path.join(out_root, DIR_NAME[lang])
    os.makedirs(out, exist_ok=True)
    tag = "中文版" if lang == ZH else "English"
    print(f"\n[{tag}] -> {out}")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, cols, rows in (
            (SHEET_CITY[lang], CITY_COLUMNS, ex.cities(lang)),
            (SHEET_SITE[lang], SITE_COLUMNS, ex.sites(lang)),
            (SHEET_CHANGE[lang], CHANGE_COLUMNS, ex.changes(lang))):
        write_sheet(wb.create_sheet(title), cols, rows, lang)
        print(f"    {title:26} {len(rows):>5} 行")
    wb.save(os.path.join(out, LIST_FILE[lang] + ".xlsx"))
    print(f"    -> {LIST_FILE[lang]}.xlsx")

    for mid, key, name_cid in ex.museums():
        title = ex.t(name_cid, lang) or key
        by_tier = ex.artworks(mid, lang)
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        counts = []
        for sheet in TIER_SHEETS[lang]:
            rows = by_tier.get(sheet, [])
            write_sheet(wb.create_sheet(sheet), ARTWORK_COLUMNS, rows, lang)
            counts.append(f"{sheet} {len(rows)}")
        fn = safe_name(ARTWORK_FILE_PREFIX[lang] + title) + ".xlsx"
        wb.save(os.path.join(out, fn))
        print(f"    {title[:28]:30} {' / '.join(counts):40} -> {fn}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="ari")
    ap.add_argument("--password-file")
    ap.add_argument("--password", default=os.environ.get("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default="ari")
    ap.add_argument("--out", default="exports")
    ap.add_argument("--lang", choices=["zh-CN", "en", "both"], default="both")
    args = ap.parse_args()

    pw = args.password
    if args.password_file:
        pw = open(os.path.expanduser(args.password_file)).read().strip("\n")
    if not pw:
        sys.exit("没有密码：用 --password-file 或环境变量 MYSQL_PASSWORD")

    import pymysql
    conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                           password=pw, database=args.database, charset="utf8mb4")
    ex = Exporter(conn)
    print(f"多语种文本已载入 {len(ex.text)} 条")

    for lang in (LANGS if args.lang == "both" else [args.lang]):
        export_one_lang(ex, lang, args.out)

    if ex.fallbacks:
        print(f"\n[warn] {ex.fallbacks} 处取不到目标语种，已回落到另一语种 —— "
              f"说明库里有缺译，查 content_text")
    else:
        print("\n零回落：两个版本的每个文本字段都取到了目标语种")
    conn.close()
    print("完成")


if __name__ == "__main__":
    main()
