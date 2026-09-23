#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓 PEM 官网的藏品栏目页，产出提交进仓库的数据模块。

    python3 pem_site_scrape.py --collections > pem_site_data.py

**为什么要重抓一遍已经抓过的东西。**
`pem_official_data.py` 存的是 2026-08-31 那次抓取的八个字段
（TITLE ~ ARTIST ~ DATE ~ MATERIAL ~ ACCESSION ~ ACQUISITION ~ CULTURE ~ ONVIEW），
**没有图片**，而库里 196 件 PEM 展品的 `image_url` 现在是 0/196。本次重抓多拿三样：
图片 URL、编目原文整行（未拆字段）、在展/展览原句。

**抓回来的东西落进仓库，不是只落进库**（AGENTS.md：`incollect` 那 4 条至今无脚本可复现）。

**页面结构**（2026-09-21 实测，`african-art` 12 条为例）：
同一批记录在页面上渲染了两遍，两套都要用：

    masonry__block  × N   网格版：`<p class="masonry__onView1">ON VIEW</p>` 裸徽章
                          和 `masonry__onViewDescription`「On view in …」
    masMod__block   × N   详情版：`masMod__img@src` 图片、`masMod__heading` 题名+年代、
                          `masMod__desc` **编目原文整行**、`masMod__onViewDescription`

两套按相同顺序出现，但**不靠顺序对齐** —— 逐条比对两侧的图片 URL，对不上就退出。

**不按位置抽字段。** `masMod__desc` 整行逐字存下，不拆成作者/材质/年代
（AGENTS.md 第 7 条：MFA 那次按位置猜，3370 条人名被写成产地）。
**馆藏号也不抽** —— 试过，219 条里 74 条抽错或抽不到，详见下方 link_official 处的说明。
馆藏号一律取 `pem_official_data.py`，两边用 link_official() 对齐。

三个子命令，各产出一个提交进仓库的数据模块：

    --collections  219 条藏品记录 -> pem_site_data.py
    --exhibitions  被引用到的展览页点名的展厅 -> pem_exhibition_data.py
    --wikidata     PEM 名下 73 个 Wikidata 条目 -> pem_wikidata_data.py
    --verify       与 2026-08-31 那份 capture 逐条对齐（非循环校验）

robots.txt（2026-09-21 实测）只禁 `/craft/` `/all-mods/` `/all-modules/` `/fed-demos/`，
藏品页允许抓，且**没有 Crawl-delay**。仍然按 0.8s 间隔，不给人添堵。
"""

from __future__ import annotations

import argparse
import html as html_mod
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from html.parser import HTMLParser

from tls import ssl_ctx

BASE = "https://www.pem.org/the-pem-collection/"
UA = "ari-metadata-research/1.0 (museum visit-planning dataset; contact via repo)"
SLEEP = 0.8

# 栏目清单与 pem_official_data.RAW 的键一致；architecture 只有概述、没有逐件编目，
# 2026-08-31 抓取返回 NONE，这里仍然请求一次并期望 0 条 —— 「没有」要被确认，不能靠记忆。
SECTIONS = (
    "african-art", "american-art", "american-decorative-art", "asian-export-art",
    "chinese-art", "contemporary-art", "european-art", "fashion-textiles",
    "japanese-art", "korean-art", "maritime-art-and-history", "native-american-art",
    "natural-history", "oceanic-art", "photography", "phillips-library-collection",
    "south-asian-art", "architecture",
)


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx()) as r:
        return r.read().decode("utf-8", "replace")


def _txt(s: str) -> str:
    """HTML 片段 -> 纯文本，去标签、解实体、压空白。"""
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html_mod.unescape(s)).strip()


class _Blocks(HTMLParser):
    """
    抽出所有 class 以 prefix 开头的 block，每块内收集需要的子字段。

    用 html.parser 而不是正则啃整块 HTML：块里有嵌套 div，正则数不清配对。
    仍然用正则处理**块内**的小片段，那些是叶子节点，没有嵌套。
    """

    def __init__(self, prefix: str):
        super().__init__(convert_charrefs=False)
        self.prefix = prefix
        self.blocks: list[dict] = []
        self._depth = 0          # 当前 block 内的 div 嵌套深度，0 表示不在 block 里
        self._buf: list[str] = []
        self._img: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if tag == "div":
            if self._depth == 0:
                if f"{self.prefix}__block" in cls.split():
                    self._depth = 1
                    self._buf, self._img = [], None
                return
            self._depth += 1
        if self._depth and tag == "img" and f"{self.prefix}__img" in cls.split():
            if self._img is None:
                self._img = a.get("src")
        if self._depth:
            self._buf.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag):
        if not self._depth:
            return
        self._buf.append(f"</{tag}>")
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.blocks.append({"html": "".join(self._buf), "img": self._img})

    def handle_data(self, data):
        if self._depth:
            self._buf.append(data)

    def handle_entityref(self, name):
        if self._depth:
            self._buf.append(f"&{name};")

    def handle_charref(self, name):
        if self._depth:
            self._buf.append(f"&#{name};")


def _field(block_html: str, cls: str) -> str | None:
    """取块内某个叶子 div 的文本。找不到返回 None。"""
    m = re.search(rf'<div class="{re.escape(cls)}"\s*>(.*?)</div>', block_html, re.S)
    if not m:
        m = re.search(rf'<div class="{re.escape(cls)}">(.*?)</div>', block_html, re.S)
    return _txt(m.group(1)) if m else None


def parse_section(page: str, section: str) -> list[dict]:
    """
    解析一个栏目页。两套渲染都解，逐条用图片 URL 交叉校验。
    """
    mas = _Blocks("masMod"); mas.feed(page)
    grid = _Blocks("masonry"); grid.feed(page)

    if len(mas.blocks) != len(grid.blocks):
        sys.exit(f"[fatal] {section}: masMod 块 {len(mas.blocks)} 个、masonry 块 "
                 f"{len(grid.blocks)} 个，两套渲染对不上。页面结构变了，先去看页面。")

    out = []
    for i, (d, g) in enumerate(zip(mas.blocks, grid.blocks)):
        if d["img"] != g["img"]:
            sys.exit(f"[fatal] {section} 第 {i} 条：详情版图片 {d['img']!r} 与网格版 "
                     f"{g['img']!r} 不一致 —— 两套渲染不同序，不能按位置对齐。")
        desc = _field(d["html"], "masMod__desc")
        heading = _field(d["html"], "masMod__heading")
        ovd = _field(d["html"], "masMod__onViewDescription") \
            or _field(g["html"], "masonry__onViewDescription")

        # onViewDescription 里**不一定**是在展陈述。2026-09-21 实测 219 块：
        # 94 块有这个字段，其中 93 块以 "On view" 开头，剩下 1 块
        # （american-decorative-art#10「Side chair」）装的是编目原文 —— 页面作者放错了格。
        # 判别靠「是不是以 On view 开头」，不是靠「desc 缺了就往下找一格」：
        # 后者是 AGENTS.md 第 10 条那张表里的形状，页面一改就会把编目行当成在展状态。
        is_onview = bool(ovd) and re.match(r"(?i)^on view\b", ovd) is not None
        desc_src = "masMod__desc"
        if not desc and ovd and not is_onview:
            desc, desc_src = ovd, "masMod__onViewDescription（页面放错格）"

        if not desc or not heading:
            sys.exit(f"[fatal] {section} 第 {i} 条缺 heading 或 desc。"
                     f"heading={heading!r} desc={desc!r} onViewDescription={ovd!r}")
        if desc_src == "masMod__desc" and ovd and not is_onview:
            sys.exit(f"[fatal] {section} 第 {i} 条：desc 与 onViewDescription 都有，"
                     f"但后者不以 'On view' 开头，判别依据失效。onViewDescription={ovd!r}")

        # 在展：三态。None 是「页面没写」，不是「不在展」。
        onview = ovd if is_onview else None
        if not onview and re.search(r'class="masonry__onView1"\s*>\s*ON VIEW', g["html"]):
            onview = "ON VIEW"

        out.append({
            "section": section,
            "heading": heading,
            "desc": desc,
            "desc_src": desc_src,
            "image": d["img"],
            "onview": onview or None,
        })
    return out


# ------------------------------------------------------------------ 与旧 capture 对齐
#
# **本抓取器不提取馆藏号。** 2026-09-21 实测：按行尾模式抽，219 条里 74 条与
# `pem_official_data.py` 对不上 —— 大多是 desc 行根本不以馆藏号结尾（结尾是
# 「Courtesy of the Peabody Essex Museum.」之类），而 `Coffee service` 更糟：
# 真值 `137986.1-3AB, 4` 被抽成 `4`。**一个错的号比没有号危险得多**，
# 它会被当证据喂进下游。馆藏号一律取 `pem_official_data.py`（218/219，
# 且有 14 条会话内逐页核实过的 VERIFIED 作非循环校验）。
#
# 对齐**不能按位置**：2026-09-21 发现 `oceanic-art` 的 9 条在页面上换过顺序
# （旧序 Tapa/Bure kalou/Fan…，新序 Bure kalou/Fan/Kava…）。按 (栏目, 序号)
# 对齐会把 6 条张冠李戴，且不报错。

def _norm(s: str | None) -> str:
    """归一化：去变音符、弯引号转直引号、只留字母数字。"""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'),
                 ("”", '"'), ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def link_official(site_records, official_records):
    """
    把本次抓取的记录对上 `pem_official_data.py` 的编目记录。

    两级判据，**都不靠顺序**：
      ① 该栏目内，旧记录的全部馆藏号都出现在新记录的 desc 里（主判据）；
      ② 退到「旧题名与旧年代同时是新 heading 的子串」—— 只用题名会歧义
         （"Dress" 是 "Wedding dress" 的子串，实测 6 条撞车）。

    命中必须**唯一**。歧义或无命中都返回问题清单，由调用方决定退出。
    2026-09-21 实测：219 条全部唯一命中。
    """
    by_sec: dict[str, list] = {}
    for o in official_records:
        by_sec.setdefault(o["section"], []).append(o)

    pairs, problems = [], []
    used: dict[str, set] = {}
    for r in site_records:
        sec = r["section"]
        pool = by_sec.get(sec, [])
        seen = used.setdefault(sec, set())
        desc_k = re.sub(r"[^A-Z0-9.]", "", r["desc"].upper())
        head_n = _norm(r["heading"])

        cands = []
        for j, o in enumerate(pool):
            if j in seen:
                continue
            toks = [re.sub(r"[^A-Z0-9.]", "", a.upper())
                    for a in _accessions(o) if a and a.lower() != "n/a"]
            if toks and all(t in desc_k for t in toks):
                cands.append((j, o, "accession"))
        if len(cands) != 1:
            cands = [(j, o, "title+date") for j, o in enumerate(pool)
                     if j not in seen
                     and _norm(o.get("title")) and _norm(o.get("title")) in head_n
                     and _norm(o.get("date")) and _norm(o.get("date")) in head_n]

        if len(cands) == 1:
            j, o, how = cands[0]
            seen.add(j)
            pairs.append((r, o, how))
        else:
            problems.append((sec, r["heading"], f"{len(cands)} 个候选"))
    return pairs, problems


def _accessions(o):
    import pem_official_data as P
    return P.accessions(o)


def scrape_collections() -> dict[str, list[dict]]:
    data: dict[str, list[dict]] = {}
    for i, sec in enumerate(SECTIONS):
        if i:
            time.sleep(SLEEP)
        url = BASE + sec
        try:
            page = fetch(url)
        except urllib.error.HTTPError as e:
            sys.exit(f"[fatal] {url} HTTP {e.code} —— 抓取失败就停下，"
                     f"不要静默当成「这个栏目没有藏品」。")
        recs = parse_section(page, sec)
        print(f"  {sec:32} {len(recs):>3} 条", file=sys.stderr)
        if recs:
            data[sec] = recs
        else:
            print(f"     （0 条，与 2026-08-31 的 architecture 情况一致）", file=sys.stderr)
    return data


# ------------------------------------------------------------------ 展览页
SITEMAP_EX = "https://www.pem.org/sitemaps-1-section-exhibitions-1-sitemap.xml"

# 「Located in the X.」才是定位陈述。页面上还有一句套话
# 「…located inside the museum.」，小写且没有展厅名 —— 靠「大写 Located in」
# 加「后面必须出现 26 个展厅之一」两重判据挡掉，不靠语感。
LOCATED = re.compile(r"Located in (?:the )?([^.]{3,120})\.")


def onview_targets(site_records) -> dict[str, int]:
    """
    从藏品页的在展原句里取出「在展于什么」的去重清单。

    只抓被真正引用到的那些展览，不是 sitemap 里全部 188 个 ——
    2026-09-21 实测：110 条在展原句只指向 20 个目标。
    """
    out: dict[str, int] = {}
    for r in site_records:
        ov = (r.get("onview") or "").strip()
        if not ov or ov.upper() == "ON VIEW":
            continue
        t = re.sub(r"(?i)^on view in (the )?", "", ov).rstrip(". ").strip()
        out[t] = out.get(t, 0) + 1
    return out


def scrape_exhibitions(targets) -> dict[str, dict]:
    """
    对每个被引用的目标，去展览 sitemap 里找同名页面并读出「Located in …」。

    **命中必须唯一**：正文里出现两个以上展厅名就一个都不采用，只记录下来
    （*On This Ground* 就横跨两个普特南展厅，那是馆方自己的说法，
    不是我们没查清 —— 猜一个写进去才是错的）。
    """
    import pem_gallery_data as G
    names = [g["name_en"] for g in G.GALLERIES]

    xml = fetch(SITEMAP_EX)
    urls = re.findall(r"<loc>([^<]+)</loc>", xml)
    slug_of = {u.rsplit("/", 1)[-1]: u for u in urls}

    out: dict[str, dict] = {}
    for t in sorted(targets):
        slug = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
        url = slug_of.get(slug)
        if not url:                      # 模糊找一次，但只接受唯一命中
            key = re.sub(r"[^a-z0-9]+", "", t.lower())[:24]
            cand = [u for s, u in slug_of.items()
                    if key and key in re.sub(r"[^a-z0-9]+", "", s)]
            url = cand[0] if len(cand) == 1 else None
        if not url:
            out[t] = {"url": None, "galleries": [], "note": "展览 sitemap 里找不到同名页面"}
            continue

        time.sleep(SLEEP)
        body = _txt(fetch(url))
        stated = []
        for m in LOCATED.finditer(body):
            seg = m.group(1)
            stated += [n for n in names if n.lower() in seg.lower()]
        # 正文里直接出现的展厅名也算（On This Ground 的两个普特南就只在正文里）
        inline = [n for n in names if n.lower() in body.lower()]
        gals = sorted(set(stated) | set(inline))
        out[t] = {
            "url": url,
            "galleries": gals,
            "note": ("唯一" if len(gals) == 1 else
                     f"{len(gals)} 个展厅，歧义，不采用" if gals else "页面未点名展厅"),
        }
        print(f"  {t[:46]:48} {out[t]['note']}"
              f"{'：' + gals[0] if len(gals) == 1 else ''}", file=sys.stderr)
    return out


# ------------------------------------------------------------------ Wikidata
PEM_QID = "Q3373790"
ENDPOINTS = ("https://qlever.cs.uni-freiburg.de/api/wikidata",
             "https://query.wikidata.org/sparql")
PREFIX = """PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

# 一次一个属性，不做笛卡尔积。73 个条目、每个属性一条小查询，
# 比把七个 OPTIONAL 塞进一条安全得多 —— 多值属性凑一起会把行数炸开。
WD_PROPS = {
    "accession":  "wdt:P217",
    "creator":    "wdt:P170",
    "inception":  "wdt:P571",
    "material":   "wdt:P186",
    "image":      "wdt:P18",
    "location":   "wdt:P276",
    "instance":   "wdt:P31",
}
WD_LANGS = ("en", "zh", "zh-hans", "zh-hant", "ja")


def _sparql(query: str, timeout: int = 90):
    import json
    import urllib.parse
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                url = ep + "?" + urllib.parse.urlencode({"query": query})
                req = urllib.request.Request(
                    url, headers={"Accept": "application/sparql-results+json",
                                  "User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx()) as r:
                    return json.load(r)["results"]["bindings"]
            except Exception as e:                       # noqa: BLE001
                last = e
                time.sleep(3 * (attempt + 1))
    sys.exit(f"[fatal] 两个 SPARQL 端点都失败了，最后一个错误：{last}")


def scrape_wikidata() -> dict[str, dict]:
    rows = _sparql(PREFIX + f"SELECT ?i WHERE {{ ?i wdt:P195 wd:{PEM_QID} }}")
    qids = [r["i"]["value"].rsplit("/", 1)[-1] for r in rows]
    print(f"  PEM 名下 {len(qids)} 个条目", file=sys.stderr)
    data = {q: {"qid": q, "labels": {}, "altlabels": {}} for q in qids}

    for name, prop in WD_PROPS.items():
        time.sleep(1)
        rs = _sparql(PREFIX + f"""SELECT ?i ?v ?vl WHERE {{
              ?i wdt:P195 wd:{PEM_QID} ; {prop} ?v .
              OPTIONAL {{ ?v rdfs:label ?vl . FILTER(lang(?vl) = "en") }} }}""")
        n = 0
        for r in rs:
            q = r["i"]["value"].rsplit("/", 1)[-1]
            v = r["v"]["value"]
            if v.startswith("http://www.wikidata.org/entity/"):
                v = r.get("vl", {}).get("value") or v.rsplit("/", 1)[-1]
            data[q].setdefault(name, [])
            if v not in data[q][name]:
                data[q][name].append(v); n += 1
        print(f"  {name:12} {n} 个取值", file=sys.stderr)

    # 标签与别名。**中文标签实测为 0**，这件事必须写进数据模块，
    # 免得下一个人再去建一条「从 Wikidata 取中文」的代码路径。
    for kind, pred in (("labels", "rdfs:label"), ("altlabels", "skos:altLabel")):
        time.sleep(1)
        langs = ", ".join(f'"{x}"' for x in WD_LANGS)
        rs = _sparql(PREFIX + f"""SELECT ?i ?l WHERE {{
              ?i wdt:P195 wd:{PEM_QID} ; {pred} ?l .
              FILTER(lang(?l) IN ({langs})) }}""")
        for r in rs:
            q = r["i"]["value"].rsplit("/", 1)[-1]
            lit = r["l"]
            data[q][kind].setdefault(lit.get("xml:lang", "?"), []).append(lit["value"])
        cnt = {}
        for d in data.values():
            for lg in d[kind]:
                cnt[lg] = cnt.get(lg, 0) + 1
        print(f"  {kind:12} 按语种：{cnt}", file=sys.stderr)
    return data


def emit_wikidata(data: dict[str, dict]) -> None:
    w = sys.stdout.write
    zh = sum(1 for d in data.values()
             if any(k.startswith("zh") for k in d["labels"]))
    w('#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n')
    w('"""Wikidata 上挂在 PEM 名下的条目。'
      '**由 pem_site_scrape.py --wikidata 生成，勿手工编辑。**\n\n')
    w(f'P195 = wd:{PEM_QID}（Peabody Essex Museum），共 {len(data)} 条。\n')
    w('作为对照：MFA（Q49133）名下有 4429 条。**PEM 在 Wikidata 上的存量就是这么少**，\n')
    w('「照 MFA 的办法抓几千件扩充」这条路在 PEM 身上不成立。\n\n')
    w(f'**中文标签 {zh}/{len(data)} 条。** 实测就是 0 —— 不要再建「从 Wikidata 取中文」\n')
    w('的代码路径，PEM 这边的中文只能生成。\n\n')
    w('`location` 取自 P276，实测只到馆一级（取值就是博物馆本身），**没有展厅粒度**。\n')
    w('"""\n\n')
    w('ITEMS: dict[str, dict] = {\n')
    for q in sorted(data, key=lambda x: int(x[1:])):
        d = data[q]
        w('    %r: {\n' % q)
        for k in ("labels", "altlabels"):
            if d.get(k):
                w('        %r: %r,\n' % (k, d[k]))
        for k in WD_PROPS:
            if d.get(k):
                w('        %r: %r,\n' % (k, d[k]))
        w('    },\n')
    w('}\n\n\n')
    w('def records() -> list[dict]:\n')
    w('    return [{"qid": q, **v} for q, v in ITEMS.items()]\n\n\n')
    w('def en_label(qid: str) -> str | None:\n')
    w('    return (ITEMS.get(qid, {}).get("labels", {}).get("en") or [None])[0]\n')


def emit_exhibitions(data: dict[str, dict]) -> None:
    w = sys.stdout.write
    uniq = sum(1 for v in data.values() if len(v["galleries"]) == 1)
    w('#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n')
    w('"""PEM 展览页点名的展厅。**由 pem_site_scrape.py --exhibitions 生成，勿手工编辑。**\n\n')
    w(f'{len(data)} 个被藏品页引用到的目标，其中 {uniq} 个唯一点名了 26 个实体展厅之一。\n\n')
    w('**Tier 1 证据**：馆方自己在展览页上写的「Located in the X.」。\n')
    w('比「按栏目推断」硬得多 —— 后者说的是这件东西属于哪个门类，不是它在哪个房间。\n\n')
    w('`galleries` 有两个或更多时**一个都不要用**：*On This Ground* 横跨两个普特南展厅，\n')
    w('那是馆方的说法，挑一个写进去就是编。\n')
    w('"""\n\n')
    w('EXHIBITIONS: dict[str, dict] = {\n')
    for t in sorted(data):
        v = data[t]
        w('    %r: dict(url=%r,\n' % (t, v["url"]))
        w('        galleries=%r,\n' % (v["galleries"],))
        w('        note=%r),\n' % v["note"])
    w('}\n\n\n')
    w('def gallery_of(target: str) -> str | None:\n')
    w('    """在展原句里的目标 -> 唯一的实体展厅；歧义、没点名、没登记都返回 None。"""\n')
    w('    v = EXHIBITIONS.get(target)\n')
    w('    if not v:\n')
    w('        return None\n')
    w('    g = v["galleries"]\n')
    w('    return g[0] if len(g) == 1 else None\n')


def emit(data: dict[str, list[dict]]) -> None:
    total = sum(len(v) for v in data.values())
    w = sys.stdout.write
    w('#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n')
    w('"""PEM 官网藏品栏目页的抓取结果。**由 pem_site_scrape.py 生成，勿手工编辑。**\n\n')
    w(f'来源：{BASE}<栏目>\n')
    w(f'共 {total} 条，{len(data)} 个栏目。\n\n')
    w('每条四个字段，全部逐字照录：\n')
    w('    heading  —— 题名 + 年代，页面上的展示标题\n')
    w('    desc     —— **编目原文整行，未拆字段**。作者、产地、材质、入藏、馆藏号都在里面。\n')
    w('                 不要按位置拆 —— 各栏目的写法并不一致（AGENTS.md 第 7 条）。\n')
    w('    image    —— 图片 URL。库里 196 件的 image_url 原为 0/196，这是本次重抓的主要收获。\n')
    w('    onview   —— 在展原句。三种形态：None（页面没写）、"ON VIEW"（裸徽章）、\n')
    w('                 "On view in <展览或展厅>"。**None 是「页面没说」，不是「不在展」。**\n\n')
    w('**这里没有馆藏号**，而且不要试图从 desc 行尾抽 —— 实测 219 条里 74 条抽错或抽不到，\n')
    w('`Coffee service` 的 `137986.1-3AB, 4` 会被抽成 `4`。馆藏号取 `pem_official_data.py`，\n')
    w('两边用 `pem_site_scrape.link_official()` 对齐（馆藏号为主、题名+年代兜底，**不按位置** ——\n')
    w('`oceanic-art` 的 9 条在页面上换过顺序）。\n')
    w('"""\n\n')
    w('RECORDS: dict[str, list[dict]] = {\n')
    for sec in SECTIONS:
        if sec not in data:
            continue
        w(f'\n{sec!r}: [\n')
        for r in data[sec]:
            w('    dict(heading=%r,\n' % r["heading"])
            w('         desc=%r,\n' % r["desc"])
            w('         image=%r,\n' % r["image"])
            w('         onview=%r' % r["onview"])
            # 正常来源不写，只有异常来源留痕 —— 让例外在 git diff 里看得见
            if r["desc_src"] != "masMod__desc":
                w(',\n         desc_src=%r' % r["desc_src"])
            w('),\n')
        w('],\n')
    w('}\n\n\n')
    w('def records() -> list[dict]:\n')
    w('    """展平成一个列表，每条带 section。"""\n')
    w('    out = []\n')
    w('    for sec, rows in RECORDS.items():\n')
    w('        for i, r in enumerate(rows):\n')
    w('            out.append({**r, "section": sec, "idx": i})\n')
    w('    return out\n\n\n')
    w('if __name__ == "__main__":\n')
    w('    rs = records()\n')
    w('    print(f"共 {len(rs)} 条，来自 {len(RECORDS)} 个栏目页")\n')
    w('    print(f"有图片 {sum(1 for r in rs if r[\'image\'])} 条，"\n')
    w('          f"有在展原句 {sum(1 for r in rs if r[\'onview\'])} 条")\n')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collections", action="store_true",
                    help="抓 18 个藏品栏目页，把数据模块写到标准输出")
    ap.add_argument("--exhibitions", action="store_true",
                    help="抓藏品页引用到的展览页，读出「Located in …」，写数据模块到标准输出")
    ap.add_argument("--wikidata", action="store_true",
                    help="拉 PEM 名下的 Wikidata 条目，写数据模块到标准输出")
    ap.add_argument("--verify", action="store_true",
                    help="把已生成的 pem_site_data.py 与 pem_official_data.py 逐条对齐，"
                         "任何一条对不上就以非零码退出")
    a = ap.parse_args()
    if a.verify:
        verify()
    elif a.collections:
        emit(scrape_collections())
    elif a.wikidata:
        emit_wikidata(scrape_wikidata())
    elif a.exhibitions:
        import pem_site_data as S
        tg = onview_targets(S.records())
        print(f"藏品页引用到 {len(tg)} 个目标", file=sys.stderr)
        emit_exhibitions(scrape_exhibitions(tg))
    else:
        ap.error("给 --collections、--exhibitions、--wikidata 或 --verify")


def verify() -> None:
    """
    非循环校验：本次抓取与 2026-08-31 那份 capture 必须描述同一批对象。

    这一条比新数据更值钱 —— 它证明旧 capture 没有被手工改过，
    而那批数据正是 PEM 唯一的 Tier 1 来源。
    """
    import pem_official_data as OLD
    import pem_site_data as NEW

    site, official = NEW.records(), OLD.records()
    print(f"新抓 {len(site)} 条 / 旧存 {len(official)} 条")
    if len(site) != len(official):
        sys.exit(f"[fatal] 条数不等：{len(site)} vs {len(official)}")

    pairs, problems = link_official(site, official)
    by_how = {}
    for _, _, how in pairs:
        by_how[how] = by_how.get(how, 0) + 1
    print(f"唯一命中 {len(pairs)}（{by_how}），对不上 {len(problems)}")
    for sec, head, why in problems[:20]:
        print(f"   {sec:28} {head[:52]:54} {why}")
    if problems:
        sys.exit(f"[fatal] {len(problems)} 条对不上 —— 页面变了或旧 capture 被改过，先查清再往下走。")

    imgs = sum(1 for r in site if r["image"])
    ov = sum(1 for r in site if r["onview"])
    print(f"\n图片 {imgs}/{len(site)}，在展原句 {ov}/{len(site)}")
    print("通过：两次抓取描述同一批 219 件对象。")


if __name__ == "__main__":
    main()
