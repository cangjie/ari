#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从三个抓取数据模块确定性地生成伪满皇宫博物院的源 Excel，零网络、零 API。

    python3 wmhg_build.py            # 写 artworks/伪满皇宫_展品清单.xlsx + wmhg_seq_map.csv + 体检报告
    python3 wmhg_build.py --check    # 只做配对与体检，不写文件

输入（`wmhg_site_scrape.py --scrape` 产出，都已提交）：
    wmhg_site_data.py        官网藏品，中文 29 件 + 英文 24 条（两套 id 不相通）
    wmhg_exhibition_data.py  常设/专题展览、临时展览、展览回顾
    wmhg_article_data.py     站内搜索入选的文章

**范围是用户 2026-09-24 逐项定的**，不在这里自行扩大：
· 藏品：官网「藏品」栏目全收；英文版当馆方原文入库（机翻也照录）
· 文章补展品：**只收当前在展的展**里点了名的 —— 实际只有御纹章展 2026-01 新增的 5 件
· 节点：官网常设列表上真在展的 16 个 + 御纹章展 + 2023 年馆方导览（文章 2657）多列的 10 个，
  后者注明出处与年份、在展状态记「未核实」

**序号按身份键幂等**（AGENTS.md 第 14 条）：身份键 -> source_seq 存在 wmhg_seq_map.csv，
已有的键永不改号，新键追加在末尾，消失的键留空号。不为了连续去重新编号。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import pathlib
import re
import statistics
import sys
from collections import Counter

import wmhg_article_data as art
import wmhg_exhibition_data as exh
import wmhg_site_data as site

HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.wmhg.com.cn"
XLSX = HERE / "artworks" / "伪满皇宫_展品清单.xlsx"
SEQ_MAP = HERE / "wmhg_seq_map.csv"
REPORT = HERE / "wmhg_samples" / "build_report.txt"

# ---------------------------------------------------------------- 中英配对
# 中文类目 ↔ 英文类目。按类目名对译逐个核对过：瓷器↔Porcelain、日本画↔Japanese Painting、
# 奏折↔Memorial、纪念章↔Commemorative Medal、宫廷文物↔Cultural Relic、铜镜↔Bronze Mirror、
# 画报↔Pictorial。只在同一类目内配对
CAT_PAIRS = {"13": "252", "14": "253", "15": "254", "16": "255", "17": "256", "18": "257", "19": "258"}

# 英文里的测试记录：标题含「testdata」，简介里的数字与 1632 完全相同，是同一件的副本
EN_TEST = {"1793": "标题含 testdata，数字锚点与 1632（今右卫门青花加彩花卉纹尊）完全相同"}

# 自动配对的数字锚点不够（< AUTO_MIN）时，只认这里登记过的。每条写明凭什么
EN_MANUAL = {
    "1641": ("507", "锚点只有 0.3、3 两个；正文核对：伪满国势调查纪念章 ↔ "
                    "Memorial Medallion for the Investigation of Puppet Manchukuo Situation"),
    "1637": ("477", "锚点只有 38.5、97 两个（尺寸一致）；题名是逐字机翻：喜多川龟麿《出游图》 ↔ "
                    "Xiduochuan Turtle Bran Travel Map（龟麿 → Turtle Bran，出游图 → Travel Map）"),
    "1644": ("481", "锚点只有 0.3、15 两个；正文核对：溥仪《国本奠定诏书》定天照大神为「国神」↔ "
                    "Puyi issued the Imperial Letter of Establishment of the Nation … God of State"),
    "1645": ("480", "锚点只有 1937.3、27 两个（即纪念章上的「1937.3.27」）；正文核对：东边道「大讨伐」"
                    "与王凤阁 ↔ Commemorative Medallion of the Puppet Manchu East[ern Border Road Crusade]"),
}
# 只有英文版有、中文 29 件里没有的。照样入库：name_en 为馆方原文，中文名留给 translate_artwork.py
EN_ONLY = {"1636": "Jiugu Colorful Flower and Bird Plate（九谷烧彩绘花鸟盘），中文栏目里没有这一件"}
AUTO_MIN = 3


def _anchors(text: str) -> set[str]:
    """简介里的数字锚点。去掉 1–9 这类个位数 —— 「1 枚」「3 种」到处都是，没有区分度。"""
    return {n for n in re.findall(r"\d+(?:\.\d+)?", text) if len(n) >= 2 or "." in n}


def pair_en(r) -> dict[str, str]:
    """-> {中文 id: 英文 id}。自动配对要求同类目、锚点重合 ≥ AUTO_MIN、且双方互为唯一最佳。"""
    zh_by_cat: dict[str, list[str]] = {}
    for k, v in site.ZH.items():
        zh_by_cat.setdefault(v["category_id"], []).append(k)
    pairs: list[tuple[str, str]] = []          # (中文 id, 英文 id)。先存列表，查完重再转 dict
    rows = []
    for ek, ev in sorted(site.EN.items(), key=lambda x: int(x[0])):
        if ek in EN_TEST:
            rows.append((ek, "—", 0, "剔除：" + EN_TEST[ek]))
            continue
        zc = next((z for z, e in CAT_PAIRS.items() if e == ev["category_id"]), None)
        cands = sorted(((len(_anchors(ev["desc"]) & _anchors(site.ZH[zk]["desc"])), zk)
                        for zk in zh_by_cat.get(zc, [])), reverse=True)
        best = cands[0] if cands else (0, None)
        second = cands[1][0] if len(cands) > 1 else 0
        if ek in EN_MANUAL:
            zk, why = EN_MANUAL[ek]
            pairs.append((zk, ek))
            rows.append((ek, zk, best[0] if best[1] == zk else 0, "人工核对：" + why))
        elif ek in EN_ONLY:
            rows.append((ek, "—", best[0], "只有英文：" + EN_ONLY[ek]))
        elif best[0] >= AUTO_MIN and best[0] > second:
            pairs.append((best[1], ek))
            rows.append((ek, best[1], best[0], "自动"))
        else:
            sys.exit(f"[fatal] 英文 {ek}「{ev['name']}」配不上：最佳 {cands[:3]}。"
                     f"核对后登记进 EN_MANUAL 或 EN_ONLY，不要放宽 AUTO_MIN")
    dz = [z for z, n in Counter(z for z, _ in pairs).items() if n > 1]
    de = [e for e, n in Counter(e for _, e in pairs).items() if n > 1]
    if dz or de:
        sys.exit(f"[fatal] 配对不唯一：中文 {dz} 被配了不止一次 / 英文 {de}")
    out = dict(pairs)
    r.say("\n## 中英配对（英文 id -> 中文 id，锚点重合数）")
    for ek, zk, n, how in rows:
        zn = site.ZH[zk]["name"] if zk in site.ZH else ""
        r.say(f"  {ek:>5} -> {zk:>5} {n:>2}  {site.EN[ek]['name'][:44]:46} {zn:24} {how}")
    r.say(f"配上 {len(out)} 对；中文没有英文版的 {len(site.ZH) - len(out)} 件；"
          f"只有英文的 {len(EN_ONLY)} 件；剔除测试记录 {len(EN_TEST)} 条")
    return out


# ---------------------------------------------------------------- 文章补展品
YWZ_ARTICLE = "/detail/3263.html"
YWZ_NAME = "兰徽幻影——溥仪“御纹章”文物展"
YWZ_PLACE = "怀远楼二楼清宴堂"
# 文章 3263 里「新增文物」一节逐件点名的 5 件，按原文顺序。名字必须在原文里逐字出现
YWZ_ITEMS = ["伪满黄釉“万寿”团纹盅", "伪满黄釉“宫”字盅", "日本七宝烧黄地凤纹香炉",
             "日本七宝烧黄地凤纹瓶", "日本七宝烧翠竹三鸡纹盘口瓶"]
YWZ_END = "展览揭示了"
# 文章里的这件与官网藏品是同一件：用词几乎逐字相同（铜胎，敞口，短颈，丰肩，直腹，平足，
# 通体金黄色珐琅地，五彩凤凰），尺寸口径 15.3 一致、高 36 / 36.6、底径 15.3 / 15.2 有出入，
# 判为重新测量。用户 2026-09-24 确认是同一件：不另建行，只给 478 补在展证据
YWZ_SAME_AS = {"日本七宝烧黄地凤纹瓶": "478"}


def ywz_items() -> list[dict]:
    text = art.ARTICLES[YWZ_ARTICLE]["text"]
    marks = YWZ_ITEMS + [YWZ_END]
    pos = []
    for m in marks:
        if text.count(m) != 1:
            sys.exit(f"[fatal] 文章 {YWZ_ARTICLE} 里「{m}」出现 {text.count(m)} 次，应恰好 1 次")
        pos.append(text.index(m))
    if pos != sorted(pos):
        sys.exit(f"[fatal] 文章 {YWZ_ARTICLE} 里 5 件的出现顺序与 YWZ_ITEMS 不一致")
    out = []
    for i, name in enumerate(YWZ_ITEMS):
        block = text[pos[i]:pos[i + 1]].strip()
        out.append(dict(name=name, desc=block[len(name):].strip()))
    return out


# ---------------------------------------------------------------- 节点
# 常设列表上但不是「现在可以去看的一个展/一处空间」的，逐条写明理由
EXHIB_DROP = {"1888": "展期 2020-08-12，过期的临时展仍挂在常设列表上",
              "1890": "博物院概览，不是一个展"}
BASIC = {"54", "1353"}                 # 基本陈列；其余常设条目都是宫廷原状陈列（殿宇、园林、遗址）
GUIDE_ARTICLE = "/detail/2657.html"    # 2023 年中秋馆方导览「不能错过的 30 个必逛打卡点」
# 导览里有、官网常设列表里没有的。键是导览原文里的名称（逐字），值是（所在建筑, 对象层级）。
# 所在建筑只填导览原文写明的；宫廷旧址区的殿宇是原状陈列，休闲娱乐区与薰南楼是展区
GUIDE_NODES = {
    "西厢房": ("", "原状陈列"), "南厢房": ("", "原状陈列"), "嘉乐殿": ("", "原状陈列"),
    "卤簿车库": ("", "展区"), "百年机车馆": ("", "展区"), "御用跑马场": ("", "展区"),
    "薰南楼": ("", "展区"),
    "艰苦卓绝十四年——东北人民抗战史实陈列": ("东北沦陷史陈列馆", "专题陈列"),
    "侵华日军第一〇〇部队细菌战罪证陈列": ("东北沦陷史陈列馆", "专题陈列"),
    "天地英雄气 千秋尚凛然——缅怀东北抗战英烈和英雄群体": ("东北沦陷史陈列馆", "专题陈列"),
}


def _para_with(text: str, name: str) -> str:
    """原文里第一个「含 name 且不止 name 本身」的段落，逐字返回（导览每个地点另有一行小标题）。"""
    for para in text.split("\n"):
        if name in para and para.strip() != name:
            return para.strip()
    sys.exit(f"[fatal] {GUIDE_ARTICLE} 里没有介绍「{name}」的段落")


# ---------------------------------------------------------------- 组装
ON_UNKNOWN = "馆藏（在展状态未知）"
ON_PERM = "常设展览·当前在展"
ON_YWZ = f"当前在展（{YWZ_NAME}，据 2026-01-20 官网文章）"
ON_GUIDE = "2023 年馆方导览列出（现状未核实）"


# 简介开头的栏目标签。抓取时只去掉了单独成行的「简介」「Introduction」，
# 带冒号的「简介：」与英文版的「brief introduction」「Introduction:」漏了（中文 12 条、英文 12 条）
LABEL_RE = re.compile(r"^\s*(简介|brief introduction|introduction)\s*[：:]?\s*", re.I)
ZH_CAT_NAME = {e: next(v["category"] for v in site.ZH.values() if v["category_id"] == z)
               for z, e in CAT_PAIRS.items()
               if any(v["category_id"] == z for v in site.ZH.values())}


def _desc(text: str) -> str:
    return LABEL_RE.sub("", text, count=1).strip()


def _en_text(text: str) -> str:
    """英文版取来的文本。**一个拉丁字母都没有的，不当英文用。**

    馆方英文版有的页面没翻译，直接放了中文原文：en/1639（《武士之女》）标题是英文，
    简介是整段中文（332 个汉字、0 个字母）。照录进「英文简介」列会让人以为馆方有英译；
    入库时 detect_lang 判中文、丢掉这一格（判得对）。2026-09-26 我曾把这误诊成
    「detect_lang 把夹汉字的英文判成中文」，看了原文才知道那段本来就是中文。"""
    t = _desc(text)
    return t if re.search(r"[A-Za-z]", t) else ""


def _abs(u: str) -> str:
    return BASE + u if u.startswith("/") else u


def build_rows(r) -> list[dict]:
    en_of = pair_en(r)
    ywz = ywz_items()
    same = {v: k for k, v in YWZ_SAME_AS.items()}          # 官网 id -> 文章里的名字
    rows: list[dict] = []

    for k, v in sorted(site.ZH.items(), key=lambda x: int(x[0])):
        e = site.EN.get(en_of.get(k, ""), {})
        on, hall, src = ON_UNKNOWN, "", "wmhg_official"
        if k in same:
            on, hall = ON_YWZ, YWZ_PLACE
            src = f"wmhg_official + 文章 {YWZ_ARTICLE}（在展证据）"
        rows.append(dict(key=f"c:{k}", hall=hall, name=v["name"], desc=_desc(v["desc"]),
                         image=_abs(v["images"][0]) if v["images"] else "", on=on, url=v["url"],
                         level="藏品", cat=v["category"], name_en=_en_text(e.get("name", "")),
                         desc_en=_en_text(e.get("desc", "")), oid=f"collection/{k}" + (f" · en/{en_of[k]}" if k in en_of else ""),
                         src=src))
        if e.get("desc") and not rows[-1]["desc_en"]:
            r.say(f"  · 英文版 en/{en_of[k]} 的简介里没有一个英文字母（馆方没翻译），英文简介留空：{v['name']}")
    for ek in sorted(EN_ONLY, key=int):
        e = site.EN[ek]
        rows.append(dict(key=f"en:{ek}", hall="", name="", desc="", image=_abs(e["images"][0]) if e["images"] else "",
                         on=ON_UNKNOWN, url=e["url"], level="藏品", cat=ZH_CAT_NAME[e["category_id"]],
                         name_en=e["name"], desc_en=_desc(e["desc"]), oid=f"en/{ek}", src="wmhg_official（仅英文版）"))
    a = art.ARTICLES[YWZ_ARTICLE]
    for it in ywz:
        if it["name"] in YWZ_SAME_AS:
            continue
        rows.append(dict(key=f"a:3263:{it['name']}", hall=YWZ_PLACE, name=it["name"], desc=it["desc"],
                         image="", on=ON_YWZ, url=a["url"], level="藏品", cat="御纹章展新增文物",
                         name_en="", desc_en="", oid=f"article/3263", src="wmhg_article"))

    review = set(exh.REVIEW)
    for k, v in sorted(exh.EXHIBITIONS.items(), key=lambda x: int(x[0])):
        if k in EXHIB_DROP or k in review or "常设展览" not in v["kinds"]:
            continue
        rows.append(dict(key=f"x:{k}", hall=v["title"] if k not in BASIC else "", name=v["title"],
                         desc=v["desc"], image=_abs(v["images"][0]) if v["images"] else "",
                         on=ON_PERM, url=v["url"], level="基本陈列" if k in BASIC else "原状陈列",
                         cat="常设展览", name_en="", desc_en="", oid=f"exhib/{k}", src="wmhg_official"))
    first_para = a["text"].split("\n")[0]
    info = a["text"][a["text"].index("展 览 信 息"):].split("文、图")[0].strip()
    rows.append(dict(key="t:3263", hall=YWZ_PLACE, name=YWZ_NAME, desc=first_para + "\n" + info,
                     image=_abs(a["images"][0]) if a["images"] else "", on=ON_YWZ, url=a["url"],
                     level="专题陈列", cat="馆内专题展（文章）", name_en="", desc_en="",
                     oid="article/3263", src="wmhg_article"))
    g = art.ARTICLES[GUIDE_ARTICLE]
    for name, (hall, level) in GUIDE_NODES.items():
        rows.append(dict(key=f"g:2657:{name}", hall=hall or name, name=name, desc=_para_with(g["text"], name),
                         image="", on=ON_GUIDE, url=g["url"], level=level, cat="2023 年馆方导览",
                         name_en="", desc_en="", oid="article/2657", src="wmhg_guide_2023"))
    return rows


def assign_seq(rows: list[dict], write: bool, r) -> None:
    old: dict[str, int] = {}
    if SEQ_MAP.exists():
        with open(SEQ_MAP, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                old[row["key"]] = int(row["seq"])
    if len(set(old.values())) != len(old):
        sys.exit(f"[fatal] {SEQ_MAP.name} 里有重复的 seq")
    nxt = max(old.values(), default=0) + 1
    new_keys = []
    for row in rows:
        if row["key"] not in old:
            old[row["key"]] = nxt
            new_keys.append(row["key"])
            nxt += 1
        row["seq"] = old[row["key"]]
    gone = sorted(set(old) - {row["key"] for row in rows}, key=lambda k: old[k])
    r.say(f"\n## 序号：沿用 {len(rows) - len(new_keys)}，新增 {len(new_keys)}，"
          f"本次不再出现（留空号，不回收）{len(gone)} {gone[:8]}")
    if write:
        with open(SEQ_MAP, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["key", "seq"])
            for k, s in sorted(old.items(), key=lambda x: x[1]):
                w.writerow([k, s])


# ---------------------------------------------------------------- 体检（onboard-museum 步骤 2）
def health(rows: list[dict], r) -> None:
    r.say("\n## 体检")
    objs = [x for x in rows if x["level"] == "藏品"]
    nodes = [x for x in rows if x["level"] != "藏品"]
    r.say(f"总 {len(rows)} 行：藏品 {len(objs)}，节点 {len(nodes)} {Counter(x['level'] for x in nodes)}")
    for label, part in (("藏品", objs), ("节点", nodes)):
        n = len(part) or 1
        L = [len(x["desc"]) for x in part]
        r.say(f"  {label}：有中文名 {sum(1 for x in part if x['name'])}/{n}，"
              f"有中文简介 {sum(1 for x in part if x['desc'])}/{n}（中位 {statistics.median(L) if L else 0} 字），"
              f"有图 {sum(1 for x in part if x['image'])}/{n}，有英文名 {sum(1 for x in part if x['name_en'])}/{n}，"
              f"官方页面 {sum(1 for x in part if x['url'])}/{n}")
        r.say(f"    出处 {Counter(x['src'].split('（')[0].split(' +')[0] for x in part)}；"
              f"陈列状态 {Counter(x['on'] for x in part)}")
    dims = sum(1 for x in objs if re.search(r"(高|口径|直径|长|宽|纵|横)\s*[\d.]+\s*(厘米|cm|公分)", x["desc"]))
    r.say(f"  藏品简介里写了尺寸的 {dims}/{len(objs)}；馆藏号：官网与文章都不给（0/{len(objs)}）")
    r.say("  名称性质：藏品名是馆方编目式题名（器型+纹饰+年代，或「作者《题名》」），"
          "能指向具体一件；不是 PEM 那种描述性转写")
    short = [x["name"] for x in nodes if len(x["desc"]) < 60]
    if short:
        r.say(f"  ⚠ 节点简介不足 60 字：{short}")


# ---------------------------------------------------------------- 写 Excel
HEADER = ["序号", "展厅", "展品名称", "展品简介", "展品图片", "陈列状态", "官方页面", "Tier",
          "对象层级", "类目", "英文名称", "英文简介", "官网ID", "出处"]


def write_xlsx(rows: list[dict], r) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "展品清单"
    objs = sum(1 for x in rows if x["level"] == "藏品")
    ws.append(["伪满皇宫博物院 展品清单"])
    ws.append([f"资料整理日期：{dt.date.today():%Y 年 %m 月} | 数据来源：{BASE} 官方页面 | "
               f"藏品 {objs} 件、节点 {len(rows) - objs} 个 | 由 wmhg_build.py 生成，勿手工编辑"])
    ws.append([])
    ws.append(HEADER)
    for c in ws[4]:
        c.font = Font(bold=True)
    for x in sorted(rows, key=lambda x: x["seq"]):
        ws.append([x["seq"], x["hall"], x["name"], x["desc"], x["image"], x["on"], x["url"], "",
                   x["level"], x["cat"], x["name_en"], x["desc_en"], x["oid"], x["src"]])
    for col, width in zip("ABCDEFGHIJKLMN", (6, 22, 30, 60, 30, 26, 30, 6, 10, 16, 30, 60, 22, 24)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=5):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    info = wb.create_sheet("参观实用信息")
    info.append(["伪满皇宫博物院 — 参观实用信息"])
    info.append([])
    info.append(["项目", "内容"])
    for k, v in (
        ("数据范围", "官网「藏品」栏目全部藏品；官网常设展览中当前在展的宫廷原状陈列与基本陈列；"
                     "御纹章展（据 2026-01-20 官网文章）；2023 年馆方导览另列的展区与陈列"),
        ("数据来源", f"{BASE}（2026-09-24 抓取，wmhg_site_scrape.py）。境外网络连不上，须在国内网络抓"),
        ("藏品", "官网只发布了 29 件（中文）+ 1 件只有英文版；馆藏总数馆方自称 5.2–7 万件。"
                 "国家文物局「博物中国」上本馆没有藏品条目；Wikidata 上 0 件"),
        ("陈列状态", "官网藏品页不写在不在展，一律「在展状态未知」，除非有文章写明（御纹章展）。"
                     "2023 年导览列出的展区现状未核实"),
        ("英文", "官网英文版照录（馆方机翻，日本人名按拼音音译等），中英按简介里的数字锚点配对"),
        ("图片版权", "图片地址指向伪满皇宫博物院官方服务器，版权归该院，仅供个人查阅"),
    ):
        info.append([k, v])
    info.column_dimensions["A"].width = 14
    info.column_dimensions["B"].width = 100
    XLSX.parent.mkdir(exist_ok=True)
    wb.save(XLSX)
    r.say(f"\n写出 {XLSX.relative_to(HERE)}（{len(rows)} 行）")


class Report:
    def __init__(self):
        self.lines: list[str] = []

    def say(self, *a) -> None:
        line = " ".join(str(x) for x in a)
        self.lines.append(line)
        print(line, flush=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")        # 中文 Windows 控制台默认 GBK；
    sys.stderr.reconfigure(encoding="utf-8")        # sys.exit 的报错走 stderr，也要改
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="只做配对与体检，不写文件")
    args = ap.parse_args()
    r = Report()
    r.say(f"# 伪满皇宫博物院 源表生成{'（只检查）' if args.check else ''}")
    rows = build_rows(r)
    assign_seq(rows, write=not args.check, r=r)
    health(rows, r)
    if not args.check:
        write_xlsx(rows, r)
        REPORT.write_text("\n".join(r.lines) + "\n", "utf-8")


if __name__ == "__main__":
    main()
