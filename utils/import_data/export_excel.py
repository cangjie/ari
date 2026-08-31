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
  # 全量（六馆 + 列表文件，中英两套），约 12 分钟
  python export_excel.py --defaults-file ~/.my.cnf --out exports

  python export_excel.py ... --lang en                      # 只出英文版
  python export_excel.py ... --museum pem --artworks-only   # 只出 PEM 展品文件

密码优先从 --defaults-file 指定的 MySQL 选项文件读（如 ~/.my.cnf，权限 600），
其次 --password-file，再次环境变量 MYSQL_PASSWORD。**不要用 --password**：
命令行里的口令会进 shell 历史，也会被权限系统写进 .claude/settings.json 的
allow 列表，而该文件必须提交进仓库 —— AGENTS.md 硬性约定。

整跑的瓶颈是跨公网预载 content_text（22234 行约 2.5 分钟），不是计算；
用 --museum 只导一个馆时这段开销照样要付，别以为会按比例变快。

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
    # artwork_meta.source 是自由文本不走内容表，所以「零回落」检查照不到它，
    # 英文版里会原样漏出中文。规则类来源取值有限，按这里映射；
    # 抓取类来源是 URL 或 wikidata:QID，本身语种中立，不用映射。
    "meta_source": {
        "源文件 Category 列": "Source file, Category column",
        "名称与英文简介解析": "Parsed from name and English description",
        "名称解析（作者, 作品名）": "Parsed from name (Artist, Title)",
    },
    "yes_no": {"是": "Yes", "否": "No"},
}

# 审计列的 ENUM 走另一张表，**映射方向是反的**。
# VALUE_MAPS 那几组的前提是「库里存中文，英文版按表换」；审计这几组库里存的是
# 英文 token（high / audit / FACT / weak），中文版才是需要换的那一边。
# 混进 VALUE_MAPS 会让中文版直接漏出 medium、audit 这种原始取值 —— 实测踩过。
# 同样不走内容表（审计轨迹逐轮重写，见 schema_audit.sql 末注），所以同样照不到
# 「零回落」检查，只能靠这里兜住。
ENUM_MAPS = {
    "confidence": {"high": ("高", "High"), "medium": ("中", "Medium"),
                   "low": ("低", "Low")},
    "evidence_type": {"FACT": ("事实", "FACT"), "INFERENCE": ("推断", "INFERENCE")},
    "source_quality": {"strong": ("强", "Strong"), "moderate": ("中等", "Moderate"),
                       "weak": ("弱", "Weak")},
    "completeness_src": {"rule": ("规则·字段填充率", "Rule (field fill rate)"),
                         "audit": ("审计·逐项判定", "Audit (judged)")},
}


def mape(kind, value, lang):
    """审计 ENUM 的双向映射：库里存英文 token，两个语种都要换。"""
    if value is None:
        return None
    zh, en = ENUM_MAPS[kind].get(value, (value, value))
    return zh if lang == ZH else en


def mapv(kind, value, lang):
    if value is None or lang == ZH:
        return value
    return VALUE_MAPS[kind].get(value, value)


def map_meta_source(value, lang):
    """来源明细的中英映射。抓取来源是 URL / wikidata:QID，语种中立，原样返回。"""
    if value is None or lang == ZH:
        return value
    if value.startswith(("http://", "https://", "wikidata:")):
        return value
    return VALUE_MAPS["meta_source"].get(value, value)


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


# 元数据质量审计列。放在展品固有字段之后、动态 metadata 列之前。
# 这一组回答的不是「这件东西是什么」，而是「我们凭什么说它是这一级」。
AUDIT_COLUMNS = [
    ("完备度", "Metadata Completeness"), ("完备度口径", "Completeness Basis"),
    ("Tier可信度", "Tier Confidence"), ("潜在Tier区间", "Potential Tier Range"),
    ("研究优先级", "Research Priority"), ("需复核", "Tier Review Flag"),
    ("复核原因", "Review Reason"),
    ("最关键缺失证据", "Most Important Missing Evidence"),
    ("缺失证据", "Missing Evidence"),
    ("建议研究问题", "Recommended Research Question"),
    ("去推断后仍成立", "Survives Without Inference"),
    ("最高来源等级", "Best Source Tier"),
]

# metadata 明细表的列。主表里每个键只占一格，冲突值会被并排挤在一起；
# 明细表按「一行一条取值」摊开，来源与可信度逐条可查，谁说了什么一目了然。
# 证据类型与来源质量两列是本轮加的：在这之前，源文件里的事实和 AI 写的
# significance 判断在表里长得一模一样，读表的人分不出哪句有外部资料撑着。
META_DETAIL_COLUMNS = [
    ("序号", "No."), ("展品名称", "Artwork Name"), ("键", "Key"),
    ("取值", "Value"), ("来源", "Source"), ("可信度", "Confidence"),
    ("证据类型", "Evidence Type"), ("来源质量", "Source Quality"),
    ("来源明细", "Source Detail"),
]
SHEET_META = {ZH: "metadata明细", EN: "Metadata Detail"}
SHEET_AUDIT = {ZH: "元数据审计汇总", EN: "Metadata Audit Summary"}

SUMMARY_TITLE = {ZH: "一、审计汇总", EN: "1. Audit Summary"}
TOP20_TITLE = {ZH: "二、最该优先研究的 20 件", EN: "2. Top 20 Research Priorities"}
TOP10_TITLE = {ZH: "三、最可能变级的 10 件（只列不改）",
               EN: "3. Top 10 Possible Tier Changes (listed, not applied)"}

SUMMARY_STAT_COLUMNS = [("指标", "Metric"), ("值", "Value")]
TOP20_COLUMNS = [
    ("排名", "Rank"), ("展品", "Object"), ("当前Tier", "Current Tier"),
    ("潜在Tier区间", "Potential Tier Range"), ("完备度", "Metadata Completeness"),
    ("Tier可信度", "Tier Confidence"), ("研究优先级", "Research Priority"),
    ("最关键缺失证据", "Most Important Missing Evidence"),
    ("建议研究问题", "Recommended Research Question"),
]
TOP10_COLUMNS = [
    ("排名", "Rank"), ("展品", "Object"), ("当前Tier", "Current Tier"),
    ("潜在Tier区间", "Potential Tier Range"), ("Tier可信度", "Tier Confidence"),
    ("研究优先级", "Research Priority"), ("理由", "Reason"),
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


def write_blocks(ws, blocks, lang):
    """一个 sheet 里放多张表，块间空一行，每块前加一行粗体标题。

    审计汇总天然是三张形状不同的表（汇总指标、Top 20、Top 10），
    拆成三个 sheet 会让人来回翻，塞进一张表又对不齐列。write_sheet 只会写
    单表头，故另起一个。列宽按所有块里最宽的一列取。
    """
    widths = {}
    row_i = 1
    for title, cols, rows in blocks:
        if title:
            c = ws.cell(row=row_i, column=1, value=title)
            c.font = Font(bold=True, size=12)
            row_i += 1
        hdr = headers(cols, lang)
        for i, h in enumerate(hdr, 1):
            c = ws.cell(row=row_i, column=i, value=h)
            c.fill, c.font = HEAD_FILL, HEAD_FONT
            c.alignment = Alignment(vertical="center")
            widths[i] = max(widths.get(i, 8),
                            sum(2 if ord(ch) > 127 else 1 for ch in h))
        row_i += 1
        for r in rows:
            for i, v in enumerate(r, 1):
                ws.cell(row=row_i, column=i, value=cell(v))
                if v is not None:
                    widths[i] = max(widths.get(i, 8),
                                    sum(2 if ord(ch) > 127 else 1 for ch in str(v)[:80]))
            row_i += 1
        row_i += 1                                  # 块间空一行
    for i, w in widths.items():
        ws.column_dimensions[get_column_letter(i)].width = min(max(w + 2, 8), 60)


def meta_cell(vals):
    """把一个键的多条取值压成一格。

    取值一致时只显示一次；不一致时全部保留并标注来源 —— 冲突本身是有用信息
    （源文件说 pre-contact 而 Wikidata 标 1825 年），不该由导出环节替人挑一个。
    完整来源与可信度见「metadata明细」sheet。
    """
    texts = [v[1] for v in vals if v[1]]
    if not texts:
        return None
    if len(set(texts)) == 1:
        return texts[0]
    return " | ".join(f"{v[1]}[{v[0]}]" for v in vals if v[1])


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

    def meta_keys(self, lang):
        """有实际取值的键，按 meta_key.sort_order 排。

        六个展品文件的列集必须一致（见文件头），所以这里取的是**全库**用到的键，
        而不是当前馆用到的键；某馆没有的留空。
        """
        return [(k, self.t(cid, lang)) for k, cid in self.q(
            "SELECT k.key_name, k.name_cid FROM meta_key k"
            " WHERE EXISTS (SELECT 1 FROM artwork_meta am WHERE am.key_name = k.key_name)"
            " ORDER BY k.sort_order")]

    def meta_of(self, museum_key, lang):
        """{source_seq: {key_name: [(source_key, 文本, 可信度, 来源明细, 证据类型, 来源质量), ...]}}"""
        out = defaultdict(lambda: defaultdict(list))
        for seq, key, skey, cid, conf, src, et, sq in self.q(
                "SELECT source_seq, key_name, source_key, value_cid, confidence, source,"
                " evidence_type, source_quality"
                " FROM artwork_meta WHERE museum_key = %s"
                " ORDER BY source_seq, key_name, source_key, ord", (museum_key,)):
            out[seq][key].append((skey, self.t(cid, lang), conf, src, et, sq))
        return out

    def pick(self, zh, en, lang):
        """审计文本成对存列（不走内容表，见 schema_audit.sql 末注）。

        缺目标语种时回落并计数 —— 与 t() 同样的口径，否则英文版会静默漏出中文，
        而这正是当初 artwork_meta.source 出过的问题。
        """
        want, other = (zh, en) if lang == ZH else (en, zh)
        if want:
            return want
        if other:
            self.fallbacks += 1
            return other
        return None

    def audit_of(self, museum_key, lang):
        """{source_seq: [AUDIT_COLUMNS 对应的值]}。没审过的馆只有规则版完备度。"""
        out = {}
        for (seq, comp, csrc, tconf, plow, pceil, prio, flag,
             rr, rr_en, miss, miss_en, tm, tm_en, rq, rq_en, surv, bst) in self.q(
                "SELECT source_seq, completeness, completeness_src, tier_confidence,"
                " potential_tier_low, potential_ceiling, research_priority,"
                " tier_review_flag, review_reason, review_reason_en,"
                " missing_evidence, missing_evidence_en, top_missing, top_missing_en,"
                " research_question, research_question_en, inference_only_survives,"
                " best_source_tier"
                " FROM artwork_evidence WHERE museum_key = %s", (museum_key,)):
            # 写成「下界–上界」，即差的那端在前：B–S 读作「最差 B，最好可能到 S」。
            # 两端相同就只写一级，「A」比「A–A」更像一句话。
            rng = None
            if plow and pceil:
                rng = plow if plow == pceil else f"{plow}–{pceil}"
            out[seq] = [
                comp, mape("completeness_src", csrc, lang),
                mape("confidence", tconf, lang), rng, prio,
                mapv("yes_no", "是" if flag else "否", lang),
                self.pick(rr, rr_en, lang),
                self.pick(tm, tm_en, lang),
                self.pick(miss, miss_en, lang),
                self.pick(rq, rq_en, lang),
                None if surv is None else mapv("yes_no", "是" if surv else "否", lang),
                bst,
            ]
        return out

    def audit_summary(self, museum_key, lang):
        """审计汇总的三块：指标、Top 20 该查的、Top 10 可能变级的。

        **只列不改。** 第三块给的是「这几件的结论最可能被新资料推翻」，
        不是「这几件应该改成什么」—— 改级要等资料真的查回来，
        拿现在这批不足的证据去改，改出来的还是同样不足的结论。
        """
        rows = self.q("""
            SELECT a.source_seq, a.name_cid, a.tier,
                   e.completeness, e.completeness_src, e.tier_confidence,
                   e.potential_tier_low, e.potential_ceiling, e.research_priority,
                   e.tier_review_flag, e.top_missing, e.top_missing_en,
                   e.research_question, e.research_question_en,
                   e.inference_only_survives, e.review_reason, e.review_reason_en
            FROM artwork a
            JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
            LEFT JOIN artwork_evidence e
                   ON e.museum_key = m.key_name AND e.source_seq = a.source_seq
            ORDER BY a.source_seq""", (museum_key,))
        if not rows:
            return None

        audited = [r for r in rows if r[5] is not None]     # tier_confidence 非空即审过
        comps = sorted(float(r[3]) for r in audited if r[3] is not None)
        conf = defaultdict(int)
        for r in audited:
            conf[r[5]] += 1

        def rng(r):
            lo, hi = r[6], r[7]
            if not (lo and hi):
                return None
            return lo if lo == hi else f"{lo}–{hi}"

        def span(r):
            order = {"S": 0, "A": 1, "B": 2, "C": 3}
            if not (r[6] and r[7]):
                return 0
            return abs(order[r[6]] - order[r[7]])

        et = dict(self.q("SELECT evidence_type, COUNT(*) FROM artwork_meta"
                         " WHERE museum_key = %s GROUP BY evidence_type", (museum_key,)))
        sq = dict(self.q("SELECT source_quality, COUNT(*) FROM artwork_meta"
                         " WHERE museum_key = %s GROUP BY source_quality", (museum_key,)))

        # (中文标签, English label, 值)
        stats = [
            ("对象总数", "Total Objects", len(rows)),
            ("已审计件数", "Audited Objects", len(audited)),
            ("平均完备度", "Average Metadata Completeness",
             round(sum(comps) / len(comps), 1) if comps else None),
            ("中位完备度", "Median Metadata Completeness",
             comps[len(comps) // 2] if comps else None),
            ("Tier 可信度 High", "Tier Confidence: High", conf.get("high", 0)),
            ("Tier 可信度 Medium", "Tier Confidence: Medium", conf.get("medium", 0)),
            ("Tier 可信度 Low", "Tier Confidence: Low", conf.get("low", 0)),
            ("需复核件数", "Tier Review Flag", sum(1 for r in audited if r[9])),
            ("S 中 Low/Medium 可信度", "S Tier with Low/Medium Confidence",
             sum(1 for r in audited if r[2] == "S" and r[5] in ("low", "medium"))),
            ("A 中 Low 可信度", "A Tier with Low Confidence",
             sum(1 for r in audited if r[2] == "A" and r[5] == "low")),
            ("B 中潜在 A/S 候选", "Potential B to A/S Candidates",
             sum(1 for r in audited if r[2] == "B" and r[7] in ("A", "S"))),
            ("S/A 中去推断后不成立", "S/A Not Surviving Without Inference",
             sum(1 for r in audited if r[14] == 0)),
            ("metadata 条数 FACT", "Metadata Claims: FACT", et.get("FACT", 0)),
            ("metadata 条数 INFERENCE", "Metadata Claims: INFERENCE", et.get("INFERENCE", 0)),
            ("metadata 来源质量 weak", "Metadata Source Quality: Weak", sq.get("weak", 0)),
            ("metadata 未标注", "Metadata Claims: Unlabelled", et.get(None, 0)),
        ]
        stat_rows = [[z if lang == ZH else e, v] for z, e, v in stats]

        top20 = sorted([r for r in audited if r[8] is not None],
                       key=lambda r: -float(r[8]))[:20]
        top20_rows = [
            [i, self.t(r[1], lang), r[2], rng(r), r[3],
             mape("confidence", r[5], lang), r[8],
             self.pick(r[10], r[11], lang), self.pick(r[12], r[13], lang)]
            for i, r in enumerate(top20, 1)]

        # 排序意图：区间跨得越宽 > 可信度越低 > 研究优先级越高。
        # 跨度 0（资料已能钉死一级）的一律排除 —— 它们按定义就不会变。
        conf_rank = {"low": 0, "medium": 1, "high": 2}
        cands = [r for r in audited if span(r) > 0]
        cands.sort(key=lambda r: (-span(r), conf_rank.get(r[5], 3), -float(r[8] or 0)))
        top10_rows = [
            [i, self.t(r[1], lang), r[2], rng(r),
             mape("confidence", r[5], lang), r[8],
             self.pick(r[15], r[16], lang) or self.pick(r[10], r[11], lang)]
            for i, r in enumerate(cands[:10], 1)]

        note = ("说明：本表只列出「结论最可能被新资料推翻」的对象，不代表建议改级。"
                "改级须等证据真的查回来。"
                if lang == ZH else
                "Note: these are the objects whose current Tier is most likely to be "
                "overturned by new evidence. This is not a recommendation to change any "
                "Tier; changes must wait until the evidence is actually gathered.")
        return [
            (SUMMARY_TITLE[lang], SUMMARY_STAT_COLUMNS, stat_rows),
            (TOP20_TITLE[lang], TOP20_COLUMNS, top20_rows),
            (TOP10_TITLE[lang] + "  —  " + note, TOP10_COLUMNS, top10_rows),
        ]

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


def export_one_lang(ex, lang, out_root, only=(), artworks_only=False):
    """only 为空时导全部六馆；非空则只导其中的 key_name。"""
    out = os.path.join(out_root, DIR_NAME[lang])
    os.makedirs(out, exist_ok=True)
    tag = "中文版" if lang == ZH else "English"
    print(f"\n[{tag}] -> {out}")

    if not artworks_only:
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

    mkeys = ex.meta_keys(lang)
    meta_cols = ARTWORK_COLUMNS + AUDIT_COLUMNS + [(lab, lab) for _, lab in mkeys]
    n_audit = len(AUDIT_COLUMNS)

    for mid, key, name_cid in ex.museums():
        if only and key not in only:
            continue
        title = ex.t(name_cid, lang) or key
        by_tier = ex.artworks(mid, lang)
        meta = ex.meta_of(key, lang)
        audit = ex.audit_of(key, lang)
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        counts = []
        detail = []
        for sheet in TIER_SHEETS[lang]:
            rows = []
            for r in by_tier.get(sheet, []):
                seq = r[1]                       # ARTWORK_COLUMNS 第 2 列是序号
                mm = meta.get(seq, {})
                rows.append(r + audit.get(seq, [None] * n_audit)
                            + [meta_cell(mm.get(k, [])) for k, _ in mkeys])
                for k, klab in mkeys:
                    for skey, txt, conf, src, et, sq in mm.get(k, []):
                        detail.append([seq, r[3], klab, txt, skey,
                                       mape("confidence", conf, lang),
                                       mape("evidence_type", et, lang),
                                       mape("source_quality", sq, lang),
                                       map_meta_source(src, lang)])
            write_sheet(wb.create_sheet(sheet), meta_cols, rows, lang)
            counts.append(f"{sheet} {len(rows)}")
        detail.sort(key=lambda x: (x[0], x[2], x[4]))
        write_sheet(wb.create_sheet(SHEET_META[lang]), META_DETAIL_COLUMNS, detail, lang)
        counts.append(f"{SHEET_META[lang]} {len(detail)}")

        # 审计汇总恒定建 sheet：没审过的馆也留一张空表，按 sheet 名读文件的
        # 脚本不会因为「这个馆还没审」而崩，与五个 tier sheet 同样的道理。
        blocks = ex.audit_summary(key, lang)
        write_blocks(wb.create_sheet(SHEET_AUDIT[lang]), blocks or [], lang)
        counts.append(f"{SHEET_AUDIT[lang]} {sum(len(b[2]) for b in blocks) if blocks else 0}")
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
    ap.add_argument("--defaults-file",
                    help="MySQL 选项文件（如 ~/.my.cnf，权限 600），"
                         "连接参数与口令都从中读取，命令行里不出现密码")
    ap.add_argument("--museum", default="",
                    help="只导这些馆的展品文件，逗号分隔的 museum.key_name，"
                         "如 pem 或 pem,ham；默认全部六馆")
    ap.add_argument("--artworks-only", action="store_true",
                    help="跳过「城市与博物馆遗产地列表」文件，只出展品文件")
    args = ap.parse_args()

    import pymysql
    if args.defaults_file:
        # 优先走选项文件：口令不进命令行，也不进 shell 历史与权限系统的 allow 列表
        conn = pymysql.connect(
            read_default_file=os.path.expanduser(args.defaults_file),
            charset="utf8mb4")
    else:
        pw = args.password
        if args.password_file:
            pw = open(os.path.expanduser(args.password_file)).read().strip("\n")
        if not pw:
            sys.exit("没有密码：用 --defaults-file、--password-file "
                     "或环境变量 MYSQL_PASSWORD")
        conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                               password=pw, database=args.database,
                               charset="utf8mb4")
    ex = Exporter(conn)
    print(f"多语种文本已载入 {len(ex.text)} 条")

    only = [k.strip() for k in args.museum.split(",") if k.strip()]
    if only:
        known = {k for _, k, _ in ex.museums()}
        unknown = set(only) - known
        if unknown:
            sys.exit(f"未知的馆标识 {sorted(unknown)}；可用：{sorted(known)}")

    for lang in (LANGS if args.lang == "both" else [args.lang]):
        export_one_lang(ex, lang, args.out, only, args.artworks_only)

    if ex.fallbacks:
        print(f"\n[warn] {ex.fallbacks} 处取不到目标语种，已回落到另一语种 —— "
              f"说明库里有缺译，查 content_text")
    else:
        print("\n零回落：两个版本的每个文本字段都取到了目标语种")
    conn.close()
    print("完成")


if __name__ == "__main__":
    main()
