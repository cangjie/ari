#!/usr/bin/env python3
"""给 MFA 展品抓尺寸（Dimensions）。先 Wikidata，再 Commons，最后 Gemini 免费层补缺。

用法：
    python3 fetch_dims.py --tier S --dry-run      # 只抓只算，不写表、不调 Gemini
    python3 fetch_dims.py --tier S                # 全流程，写回工作副本
    python3 fetch_dims.py --tier S,A --no-gemini  # 只要有出处的

## 来源与优先级（2026-09-18 实测后定）

| 来源 | 写进哪一列 | 说明 |
|---|---|---|
| Wikidata P2048/P2049/P2610/P2386/P2043/P2067 | `尺寸` | 主来源。S 级带 QID 的 15 件里 10 件有 |
| Commons 图片页 `{{Artwork}}` 的 dimensions | `尺寸` | **institution 必须是 MFA 才采用** |
| Gemini 免费层（无检索，凭记忆） | `尺寸（模型记忆·未核实）` | 只补前两者都没有的；用户 09-18 定，单独一列 |

**有出处的值与模型记忆绝不混在一列里。** 模型凭记忆报精确数字是最容易被编造的
—— 同一个模型曾给《雾的警告》报 `Gallery 222` 并自称「根据官方馆藏记录」。
混进来之后事后分不出真假，所以分列、带后缀，`尺寸` 有值的行一律不送模型。

## 踩过的坑

- **Wikidata 也会错**：`Watson and the Shark` 记「高 90in、宽 70in」，这幅是横幅
  （约 182 × 230 cm），高宽填反了。按 AGENTS.md 第 7 条**照录并注明来源，不擅自改**，
  原始值与单位留在证据文件里。
- **图片链接可能挂到别的作品上**：`Waves at Matsushima`（光琳，MFA）的图片是
  `Soutatsu Matsushima.jpg` —— 宗达的屏风，弗利尔美术馆藏。所以 Commons 那条要核 institution。
- **Wikimedia 按 IP 限流**：`wbsearchentities` 间隔 0.5 秒跑到第 12 次左右就 429，
  Commons 也一起被限。所以 Wikidata 只发**一次** SPARQL 把 MFA 名下全部条目拉下来、
  本地匹配，并缓存进 `mfa_wikidata_dims.json`（跑 A 级不必再联网）；Commons 间隔 ≥2 秒。
- **题名匹配要核作者**：`Paul Revere` 搜出来可能是 Revere 本人做的银器，
  我们要的是 Copley 画的那幅肖像。
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import openpyxl

import dedupe_lib as L
from tls import ssl_ctx

HERE = pathlib.Path(__file__).parent
XLSX = HERE / "exports" / "展品_波士顿美术馆_展厅检索.xlsx"
SHEET = "去重后总表"
WD_CACHE = HERE / "mfa_wikidata_dims.json"
GEMINI_CACHE = HERE / "dims_gemini_cache.jsonl"

COL_SRC = "尺寸"
COL_MEM = "尺寸（模型记忆·未核实）"
GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_KEY = "~/.gemini_key_free"          # 用户 09-18 定：Gemini 只走免费额度

MFA = "Q49133"
UA = "ari-museum-dims/1.0 (+https://github.com/cangjie/ari)"
ENDPOINTS = ("https://query.wikidata.org/sparql",
             "https://qlever.cs.uni-freiburg.de/api/wikidata")

# 尺寸属性 → (中文名, 是否算「长度」)。重量单列。
PROPS = {"P2048": "高", "P2049": "宽", "P2610": "深", "P2386": "直径", "P2043": "长", "P2067": "重"}
UNITS = {  # Wikidata 单位 QID → (换算到 cm 或 kg 的系数, 量纲)
    "Q174728": (1, "len"), "Q174789": (0.1, "len"), "Q11573": (100, "len"),
    "Q218593": (2.54, "len"), "Q3710": (30.48, "len"),
    "Q11570": (1, "mass"), "Q41803": (0.001, "mass"), "Q100995": (0.45359237, "mass"),
}
TEXT_UNITS = {"cm": 1, "mm": 0.1, "m": 100, "in": 2.54, "inch": 2.54, "inches": 2.54, "ft": 30.48}
LEN_MIN, LEN_MAX = 0.5, 3000        # cm；超出就当成坏数据丢掉
GALLERY_ROW = re.compile(r"展厅陈列|综合陈列|复原空间")


# ---------------------------------------------------------------- 工具

def fnum(x: float) -> str:
    return f"{round(x, 2):g}"


def fmt_dims(d: dict) -> str:
    """{'高': 90.8, '宽': 122.6, '重': 187.8} → '高 90.8 × 宽 122.6 cm；重 187.8 kg'"""
    lens = [f"{k} {fnum(d[k])}" for k in ("高", "宽", "深", "长", "直径") if k in d]
    out = (" × ".join(lens) + " cm") if lens else ""
    if "重" in d:
        out = (out + "；" if out else "") + f"重 {fnum(d['重'])} kg"
    return out


RATIO_MAX = 60     # 某一维超过其余维中位数的这么多倍，判为坏值（手卷九龙图是 32 倍）


def drop_outliers(d: dict) -> tuple[dict, list[str]]:
    """丢掉明显不合比例的那一维，其余照留。

    实测 `Bocca Baciata`（罗塞蒂，32.1 × 27 cm 的小画）在 Wikidata 上还挂着「长 2700 cm」，
    单看每个数都在 0.5–3000 cm 之内，只有放在一起才看得出是错的。
    """
    lens = {k: v for k, v in d.items() if k != "重"}
    if len(lens) < 3:
        return d, []
    out, notes = dict(d), []
    for k, v in lens.items():
        rest = sorted(x for kk, x in lens.items() if kk != k)
        med = rest[len(rest) // 2]
        if med > 0 and v / med > RATIO_MAX:
            out.pop(k)
            notes.append(f"{k} {fnum(v)} cm 是其余维度的 {v / med:.0f} 倍，判为坏值丢弃")
    return out, notes


def plausible(d: dict) -> bool:
    return all(LEN_MIN <= v <= LEN_MAX for k, v in d.items() if k != "重") and bool(d)


def http_json(url: str, *, data: bytes | None = None, headers: dict | None = None,
              timeout: int = 120, retries: int = 3) -> dict:
    """GET/POST 取 JSON。429 按 Retry-After 退避，取不到就抛，不返回空冒充「没有数据」。"""
    h = {"User-Agent": UA, **(headers or {})}
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx()) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                wait = int(e.headers.get("Retry-After") or 30)
                print(f"    429 限流，等 {wait} 秒后重试（{attempt + 1}/{retries}）", flush=True)
                time.sleep(min(wait, 120))
                continue
            if e.code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"请求失败：{url[:100]} —— {last}")


# ---------------------------------------------------------------- Wikidata

def wd_query() -> str:
    dims = "\n".join(
        f"  OPTIONAL {{ ?item p:{p}/psv:{p} ?v{p} . "
        f"?v{p} wikibase:quantityAmount ?a{p} ; wikibase:quantityUnit ?u{p} . }}"
        for p in PROPS)
    sel = " ".join(f"?a{p} ?u{p}" for p in PROPS)
    return f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?item ?label ?inv ?creator {sel} WHERE {{
  ?item wdt:P195 wd:{MFA} .
  OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) = "en") }}
  OPTIONAL {{ ?item wdt:P217 ?inv }}
  OPTIONAL {{ ?item wdt:P170 ?creator }}
{dims}
}}"""


def load_wikidata(refresh: bool) -> dict:
    """MFA 名下全部 Wikidata 条目的标签、馆藏号、作者与尺寸。一次查询，缓存进仓库。"""
    if WD_CACHE.exists() and not refresh:
        return json.loads(WD_CACHE.read_text(encoding="utf-8"))
    q = wd_query()
    rows, last = None, None
    for ep in ENDPOINTS:
        try:
            print(f"  SPARQL → {ep.split('/')[2]} …", flush=True)
            rows = http_json(ep, data=urllib.parse.urlencode({"query": q, "format": "json"}).encode(),
                             headers={"Accept": "application/sparql-results+json",
                                      "Content-Type": "application/x-www-form-urlencoded"},
                             timeout=180)["results"]["bindings"]
            break
        except Exception as e:                           # noqa: BLE001
            last = e
            print(f"    失败：{type(e).__name__} {str(e)[:120]}", flush=True)
    if rows is None:
        sys.exit(f"两个 SPARQL 端点都失败：{last}")

    def tail(v):
        return v.rsplit("/", 1)[-1]

    items: dict[str, dict] = {}
    for b in rows:
        q_ = tail(b["item"]["value"])
        it = items.setdefault(q_, {"label": None, "inv": set(), "creators": set(),
                                   "dims": collections.defaultdict(set)})
        if "label" in b:
            it["label"] = b["label"]["value"]
        if "inv" in b:
            it["inv"].add(b["inv"]["value"])
        if "creator" in b:
            it["creators"].add(tail(b["creator"]["value"]))
        for p in PROPS:
            if f"a{p}" in b:
                it["dims"][p].add((float(b[f"a{p}"]["value"]), tail(b[f"u{p}"]["value"])))
    out = {"fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "source": "Wikidata SPARQL, P195=Q49133", "items": {}}
    for q_, it in items.items():
        out["items"][q_] = {"label": it["label"], "inv": sorted(it["inv"]),
                            "creators": sorted(it["creators"]),
                            "dims": {p: sorted(v) for p, v in it["dims"].items()}}
    WD_CACHE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  MFA 名下 {len(out['items'])} 个条目，已缓存 {WD_CACHE.name}", flush=True)
    return out


def wd_dims(entry: dict) -> tuple[dict, list[str]]:
    """Wikidata 条目 → ({'高': cm, ...}, 备注)。同一属性有多个值时取最小的（通常是不含画框的）。"""
    out, notes = {}, []
    for p, vals in entry.get("dims", {}).items():
        conv = []
        for amt, unit in vals:
            f = UNITS.get(unit)
            if not f:
                notes.append(f"{PROPS[p]}：未识别单位 {unit}，丢弃")
                continue
            if (p == "P2067") != (f[1] == "mass"):
                notes.append(f"{PROPS[p]}：量纲不符（{unit}），丢弃")
                continue
            conv.append(amt * f[0])
        if conv:
            out[PROPS[p]] = min(conv)
            if len(set(round(c, 2) for c in conv)) > 1:
                notes.append(f"{PROPS[p]} 有多个值 {sorted(set(round(c, 2) for c in conv))}，取最小")
    out, more = drop_outliers(out)
    return out, notes + more


# ---------------------------------------------------------------- 题名匹配

def norm_acc(a: str) -> str:
    """只去前导零：`09.200` → `9.200`。

    **不去尾零** —— `12.15` 与 `12.150` 在 MFA 可能是两件不同的东西。
    Excel 把「馆藏号」列转成了数字（`09.200` 存成 `9.2`），那一列对不上就对不上；
    简介里「藏品编号 09.200」那段是原样字符串，`accessions()` 也会读到它。
    """
    parts = []
    for seg in str(a).strip().split("."):
        m = re.fullmatch(r"0*(\d+)([a-z]?)", seg)
        parts.append((m.group(1) + m.group(2)) if m else seg)
    return ".".join(parts)


def norm_full(s: str) -> str:
    """保留括号内容的题名规范化：只做大小写、全半角、标点空白的折叠。"""
    import unicodedata
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s)


def build_wd_index(wd: dict):
    by_full, by_title, by_acc = (collections.defaultdict(list) for _ in range(3))
    for q_, e in wd["items"].items():
        if e.get("label"):
            by_full[norm_full(e["label"])].append(q_)
            by_title[L.norm_title(e["label"])].append(q_)
        for a in e.get("inv", []):
            by_acc[norm_acc(a)].append(q_)
    return by_full, by_title, by_acc


def match_row(it: dict, wd: dict, by_full, by_title, by_acc) -> tuple[str | None, str]:
    """给没有 QID 的行找 Wikidata 条目。返回 (QID, 匹配方式)；找不到返回 (None, 原因)。"""
    # 1) 馆藏号：最硬
    for a in sorted(set().union(*it["acc"].values())):
        hits = by_acc.get(norm_acc(a), [])
        if len(hits) == 1:
            return hits[0], f"馆藏号 {a}"
    # 2) 题名完全相等 + 作者核对。**先保留括号比**：Wikidata 标签里的括号是题名的一部分，
    #    `norm_title` 会把末尾括号当注释剥掉，于是 `Grainstack (Sunset)` 与
    #    `Grainstack (Snow Effect)` 都成了 `grainstack`（2026-09-18 实测撞上）。
    cands = set()
    for t in it["en_raw"]:
        cands.update(by_full.get(norm_full(t), []))
    if not cands:
        for t in it["en_raw"]:
            cands.update(by_title.get(L.norm_title(t), []))
    if not cands:
        return None, "Wikidata 的 MFA 条目里没有同名的"
    if it.get("creator_qid"):
        ok = [q_ for q_ in cands if it["creator_qid"] in wd["items"][q_]["creators"]]
        if len(ok) == 1:
            return ok[0], f"题名相同且作者一致（{it['creator_qid']}）"
        if not ok:
            return None, f"同名条目 {sorted(cands)} 的作者都对不上 {it['creator_qid']}"
        return None, f"同名且同作者的条目不止一个：{sorted(ok)}"
    if len(cands) == 1:
        return next(iter(cands)), "题名相同（作者不可考，全馆唯一命中）"
    return None, f"作者不可考且同名条目不止一个：{sorted(cands)}"


# ---------------------------------------------------------------- 本表简介

_ZH_DIM = re.compile(r"(高|宽|长|深|直径|口径)(约)?\s*([\d.]+)\s*(厘米|公分|cm|毫米|mm|米|m)(?![a-z])")
_ZH_UNIT = {"厘米": 1, "公分": 1, "cm": 1, "毫米": 0.1, "mm": 0.1, "米": 100, "m": 100}
_ZH_KEY = {"高": "高", "宽": "宽", "长": "长", "深": "深", "直径": "直径", "口径": "直径"}


def desc_dims(text: str) -> tuple[dict | None, str]:
    """从本表简介里抽**写明了的**尺寸（如「像高约 142 厘米」）。没写就返回 None，不推断。

    只用于官网与原清单两个子集 —— 它们的简介是整理人从馆方页面摘的；
    ext·wikidata 的简介是「类别：畫作；藏品编号…」这种模板，没有尺寸可抽。
    """
    d, hits = {}, []
    for m in _ZH_DIM.finditer(str(text or "")):
        k = _ZH_KEY[m.group(1)]
        if k not in d:
            d[k] = float(m.group(3)) * _ZH_UNIT[m.group(4)]
            hits.append(m.group(0))
    return (d or None), "；".join(hits)


# ---------------------------------------------------------------- Commons

def commons_files(row: dict) -> list[str]:
    out = []
    for k, v in row.items():
        if k and "图片" in str(k) and v:
            for m in re.finditer(r"(?:Special:FilePath/|/wiki/File:)([^\s?#|]+)", str(v)):
                f = urllib.parse.unquote(m.group(1)).replace("_", " ")
                if f not in out:
                    out.append(f)
    return out


def parse_size_template(txt: str) -> dict | None:
    m = re.search(r"\{\{\s*[Ss]ize\s*\|([^{}]*)\}\}", txt)
    if not m:
        return None
    args = [a.strip() for a in m.group(1).split("|")]
    named = {k.strip().lower(): v.strip() for a in args if "=" in a for k, v in [a.split("=", 1)]}
    pos = [a for a in args if "=" not in a]
    unit = named.get("unit") or (pos.pop(0) if pos and not re.match(r"^[\d.]+$", pos[0]) else None)
    f = TEXT_UNITS.get((unit or "").lower())
    if not f:
        return None
    keys = ["高", "宽", "深"]
    vals = {}
    for i, v in enumerate(pos[:3]):
        if re.fullmatch(r"[\d.]+", v):
            vals[keys[i]] = float(v) * f
    for nk, zk in (("height", "高"), ("width", "宽"), ("depth", "深"), ("diameter", "直径")):
        if re.fullmatch(r"[\d.]+", named.get(nk, "")):
            vals[zk] = float(named[nk]) * f
    return vals or None


def parse_free_dims(txt: str) -> dict | None:
    """「90.8 × 122.6 cm」「H. 142 cm」这类自由文本。认不出返回 None，不猜。"""
    m = re.search(r"([\d.]+)\s*[×xX]\s*([\d.]+)(?:\s*[×xX]\s*([\d.]+))?\s*(cm|mm|m|in)\b", txt)
    if m:
        f = TEXT_UNITS[m.group(4)]
        out = {"高": float(m.group(1)) * f, "宽": float(m.group(2)) * f}
        if m.group(3):
            out["深"] = float(m.group(3)) * f
        return out
    m = re.search(r"\b(?:H|Height)\.?\s*:?\s*([\d.]+)\s*(cm|mm|m|in)\b", txt, re.I)
    if m:
        return {"高": float(m.group(1)) * TEXT_UNITS[m.group(2).lower()]}
    return None


def commons_dims(fname: str) -> tuple[dict | None, str]:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
         "titles": "File:" + fname, "redirects": 1, "format": "json", "formatversion": 2})
    r = http_json(url, timeout=60)
    pages = r.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None, "文件不存在"
    txt = pages[0]["revisions"][0]["slots"]["main"]["content"]
    # ⚠ `=` 后只许吃空格和制表符，不许吃换行：字段为空时，`\s*` 会越过换行把
    #    下一行「|department =」当成值（2026-09-18 实测）。
    inst = re.search(r"\|[ \t]*institution[ \t]*=[ \t]*(.*)", txt, re.I)
    inst_v = inst.group(1).strip() if inst else ""
    if not ("Fine Arts" in inst_v and "Boston" in inst_v):
        return None, f"馆藏机构不是 MFA（institution={inst_v[:60] or '无'}）"
    dm = re.search(r"\|[ \t]*dimensions[ \t]*=[ \t]*(.*)", txt, re.I)
    if not dm or not dm.group(1).strip():
        return None, "Artwork 模板没有 dimensions"
    raw = dm.group(1).strip()
    d = parse_size_template(raw) or parse_free_dims(raw)
    if not d:
        return None, f"dimensions 认不出：{raw[:80]}"
    return d, raw[:160]


# ---------------------------------------------------------------- Gemini（免费层）

GEM_SYS = """你在为波士顿美术馆（MFA Boston）的藏品核对**尺寸**。

对每件回答：你是否**确切知道**它的尺寸。
· 只有你确实记得这件具体藏品的尺寸时，才给 known=true 与数值；
  记不准、只知道大概、或只知道同类作品的尺寸，一律 known=false。
· **不要估算，不要按同类作品推断。** 写错的尺寸比空着有害 —— 它会被当成事实。
· 数值给「高、宽、深、直径」中适用的几项，unit 用 cm / mm / in / m 之一。
· 立体器物给高（必要时加宽、深或直径）；平面作品给高与宽。
note 用中文一句话，说明你的依据或为什么不知道。"""

GEM_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {
        "row": {"type": "integer"},
        "known": {"type": "boolean"},
        "height": {"type": ["number", "null"]},
        "width": {"type": ["number", "null"]},
        "depth": {"type": ["number", "null"]},
        "diameter": {"type": ["number", "null"]},
        "unit": {"type": "string", "enum": ["cm", "mm", "in", "m"]},
        "note": {"type": "string"}},
    "required": ["row", "known", "unit", "note"]}}},
    "required": ["items"]}


GEM_BATCH = 40     # 一次调用装多少件。205 件塞一次会被 MAX_TOKENS 截断


def _gem_cache() -> dict:
    cache = {}
    if GEMINI_CACHE.exists():
        for ln in GEMINI_CACHE.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                cache[r["key"]] = r["resp"]
    return cache


def gemini_fill(todo: list[dict]) -> tuple[dict[int, dict], list[int]]:
    """分批问 Gemini。返回 ({行号: {'dims','note'}}, 没问到的行号)。

    每批单独缓存；**当天免费额度用完就停**，已拿到的照常返回、照常写回，
    没问到的留给明天 —— 重跑时已问过的批直接命中缓存，不重付。
    """
    import gemini_api
    cache = _gem_cache()
    got: dict[int, dict] = {}
    unasked: list[int] = []
    quota_out = False
    for b in range(0, len(todo), GEM_BATCH):
        chunk = todo[b:b + GEM_BATCH]
        if quota_out:
            unasked += [t["row"] for t in chunk]
            continue
        lines = [f"row={t['row']}｜{t['name'][:140]}"
                 + (f"｜馆藏号 {t['acc']}" if t["acc"] else "") for t in chunk]
        user = "逐件作答，row 原样返回：\n\n" + "\n".join(lines)
        key = hashlib.sha256("\x00".join(
            [GEMINI_MODEL, GEM_SYS, user, json.dumps(GEM_SCHEMA, sort_keys=True)]).encode()).hexdigest()
        tag = f"批 {b // GEM_BATCH + 1}/{-(-len(todo) // GEM_BATCH)}"
        if key in cache:
            resp = cache[key]
            print(f"  Gemini {tag}：命中缓存", flush=True)
        else:
            want = {t["row"] for t in chunk}
            resp = None
            for attempt in range(3):
                try:
                    r, _ = gemini_api.ask(GEM_SYS, user, GEM_SCHEMA, model=GEMINI_MODEL,
                                          key_file=GEMINI_KEY)
                except Exception as e:                   # noqa: BLE001
                    msg = str(e)
                    print(f"  Gemini {tag} 失败：{type(e).__name__} {msg[:120]}", flush=True)
                    if "429" in msg and ("PerDay" in msg or "quota" in msg.lower()):
                        quota_out = True
                        break
                    time.sleep(15 * (attempt + 1))
                    continue
                if want <= {x.get("row") for x in r.get("items", [])}:
                    resp = r
                    break
                print(f"  Gemini {tag} 漏答，重问", flush=True)
            if resp is None:
                if quota_out:
                    print("  ⏹ 今天的免费额度用完了；已拿到的照常写回，其余明天重跑接上", flush=True)
                unasked += [t["row"] for t in chunk]
                continue
            with GEMINI_CACHE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "model": GEMINI_MODEL, "resp": resp},
                                   ensure_ascii=False) + "\n")
            print(f"  Gemini {tag}：{len(chunk)} 件", flush=True)
        for x in resp.get("items", []):
            if not x.get("known"):
                continue
            f = TEXT_UNITS.get(x.get("unit") or "")
            if not f:
                continue
            d = {zk: x[k] * f for k, zk in (("height", "高"), ("width", "宽"),
                                             ("depth", "深"), ("diameter", "直径"))
                 if isinstance(x.get(k), (int, float)) and x[k] > 0}
            d, _ = drop_outliers(d)
            if d and plausible(d):
                got[x["row"]] = {"dims": d, "note": x.get("note", "")}
    return got, unasked


# ---------------------------------------------------------------- 主流程

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="S")
    ap.add_argument("--xlsx", default=str(XLSX))
    ap.add_argument("--dry-run", action="store_true", help="不写表、不调 Gemini")
    ap.add_argument("--no-gemini", action="store_true")
    ap.add_argument("--no-commons", action="store_true")
    ap.add_argument("--refresh-wd", action="store_true", help="重新拉 Wikidata，不用缓存")
    args = ap.parse_args()

    import dedupe_group as G
    path = pathlib.Path(args.xlsx)
    tiers = {t.strip() for t in args.tier.split(",") if t.strip()}
    items, _ = G.load_items(str(path))
    items = [i for i in items if i["tier"] in tiers]
    raw = {i["key"]: i["_raw"] for i in items}
    print(f"Tier {sorted(tiers)}：{len(items)} 行（含已并入的）", flush=True)

    wd = load_wikidata(args.refresh_wd)
    by_full, by_title, by_acc = build_wd_index(wd)

    ev: dict[tuple, dict] = {}
    for it in items:
        r = raw[it["key"]]
        e = ev[it["key"]] = {"来源表": it["key"][0], "来源行": it["key"][1], "row": it["row"],
                             "name": it["name"], "sub": it["sub"], "tried": [], "chosen": None}
        if str(r.get(COL_SRC) or "").strip():
            e["chosen"] = {"source": "已有", "text": str(r[COL_SRC])}
            continue
        if GALLERY_ROW.search(it["name"]):
            e["tried"].append({"source": "跳过", "why": "这一行写的是展厅/陈列，不是单件"})
            continue
        # ---- Wikidata：先自带 QID，再看合并时搬过来的，最后题名匹配
        own = L.qid_of(r)
        extra = [L.qid_of({"官方页面": r.get(f"官方页面_补充{n}")}) for n in range(1, 13)]
        qids = [q_ for q_ in dict.fromkeys([own] + extra) if q_]
        how = None
        if not qids:
            q_, how = match_row(it, wd, by_full, by_title, by_acc)
            qids = [q_] if q_ else []
            if not q_:
                e["tried"].append({"source": "wikidata", "why": how})
        for q_ in qids:
            if how is None or how.startswith(("行自带", "合并时")):
                how = "行自带 QID" if q_ == own else "合并时搬来的 QID（官方页面_补充N）"
            ent = wd["items"].get(q_)
            if not ent:
                e["tried"].append({"source": "wikidata", "qid": q_,
                                   "why": "该 QID 不在 MFA 名下（可能已离馆）"})
                continue
            d, notes = wd_dims(ent)
            rec = {"source": "wikidata", "qid": q_, "match": how, "raw": ent.get("dims"),
                   "cm": d, "notes": notes}
            e["tried"].append(rec)
            if d and plausible(d):
                e["chosen"] = {"source": "wikidata", "qid": q_, "dims": d,
                               "text": f"{fmt_dims(d)}（来源：Wikidata {q_}）"}
                break
            rec["why"] = "条目在，但没有尺寸" if not d else "数值不合理，丢弃"

    # ---- 本表简介：官网/原清单行自己写明的尺寸
    for k, e in ev.items():
        if e["chosen"] or e["sub"] == "ext·wikidata" or any(
                t.get("source") == "跳过" for t in e["tried"]):
            continue
        d, hit = desc_dims(raw[k].get("展品简介"))
        if d and plausible(d):
            approx = "约" in hit
            e["tried"].append({"source": "本表简介", "cm": d, "raw": hit})
            e["chosen"] = {"source": "本表简介", "dims": d,
                           "text": f"{'约 ' if approx else ''}{fmt_dims(d)}（来源：本表简介「{hit}」）"}

    # ---- Commons：只补 Wikidata 没给出的
    if not args.no_commons:
        todo = [(k, e) for k, e in ev.items() if not e["chosen"]
                and not any(t.get("source") == "跳过" for t in e["tried"])]
        n = 0
        for k, e in todo:
            for fname in commons_files(raw[k])[:2]:
                if n:
                    time.sleep(2)
                n += 1
                try:
                    d, info = commons_dims(fname)
                except Exception as ex:                  # noqa: BLE001
                    e["tried"].append({"source": "commons", "file": fname,
                                       "why": f"请求失败 {type(ex).__name__}"})
                    continue
                e["tried"].append({"source": "commons", "file": fname,
                                   "cm": d, "why" if not d else "raw": info})
                if d and plausible(d):
                    e["chosen"] = {"source": "commons", "file": fname, "dims": d,
                                   "text": f"{fmt_dims(d)}（来源：Wikimedia Commons {fname}）"}
                    break
        print(f"  Commons：查了 {n} 个文件", flush=True)

    # ---- Gemini：只补前两者都没有的，结果进另一列
    # 同一去重组里只要有一个成员拿到了有出处的尺寸，其余成员就不送：
    # dedupe_apply 生成 v2 时会把被并入行的字段「填空」进主行，若一边是有出处的、
    # 另一边是模型记忆，主行两列就会同时有值，互斥被打破。
    by_gid = collections.defaultdict(list)
    for k in ev:
        gid = raw[k].get("去重组ID")
        if gid:
            by_gid[gid].append(k)
    for k, e in ev.items():
        gid = raw[k].get("去重组ID")
        if not e["chosen"] and gid and any(
                ev[m]["chosen"] and ev[m]["chosen"]["source"] != "已有" for m in by_gid[gid]):
            e["tried"].append({"source": "跳过", "why": f"同去重组 {gid} 已有有出处的尺寸"})
    mem: dict[tuple, dict] = {}
    left = [(k, e) for k, e in ev.items() if not e["chosen"]
            and not any(t.get("source") == "跳过" for t in e["tried"])]
    if left and not args.no_gemini and not args.dry_run:
        todo = []
        for k, e in left:
            it = next(i for i in items if i["key"] == k)
            acc = sorted(set().union(*it["acc"].values()))
            todo.append({"row": e["row"], "name": e["name"], "acc": acc[0] if acc else ""})
        print(f"  Gemini（{GEMINI_MODEL}，免费 key）补 {len(todo)} 件 …", flush=True)
        got, unasked = gemini_fill(todo)
        unasked = set(unasked)
        for k, e in left:
            if e["row"] in unasked:
                e["tried"].append({"source": "gemini_memory", "why": "免费额度用完，未问到（明天重跑）"})
                continue
            g = got.get(e["row"])
            e["tried"].append({"source": "gemini_memory", "model": GEMINI_MODEL,
                               "cm": g["dims"] if g else None,
                               "why": (g or {}).get("note") or "模型答不知道，或数值不合理"})
            if g:
                mem[k] = {"dims": g["dims"],
                          "text": f"{fmt_dims(g['dims'])}（{GEMINI_MODEL} 凭记忆，未核实）"}

    # ---- 统计
    stat = collections.Counter()
    for k, e in ev.items():
        if e["chosen"]:
            stat[e["chosen"]["source"]] += 1
        elif k in mem:
            stat["gemini_memory（另一列）"] += 1
        elif any(t.get("source") == "跳过" for t in e["tried"]):
            stat["跳过（展厅行或同组已有）"] += 1
        else:
            stat["空着"] += 1
    print(f"\n覆盖：{dict(stat)}", flush=True)
    for k, e in ev.items():
        v = e["chosen"]["text"] if e["chosen"] else (mem[k]["text"] if k in mem else
            "— " + "；".join(t.get("why", "") for t in e["tried"] if t.get("why"))[:70])
        print(f"  {k[0]}表{k[1]:<5} {e['name'][:34]:<36} {v[:78]}")

    out = HERE / f"dims_{'_'.join(sorted(t.lower() for t in tiers))}.json"
    out.write_text(json.dumps({
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "tiers": sorted(tiers), "coverage": dict(stat),
        "rows": [{**e, "gemini": mem.get(k)} for k, e in ev.items()]},
        ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    print(f"\n证据已写出 {out.name}")
    if args.dry_run:
        print("--dry-run：不写表")
        return

    # ---- 写回：只写空格子；新列加在表尾
    wb = openpyxl.load_workbook(path)
    ws = wb[SHEET]
    head = [c.value for c in ws[1]]
    n_rows, n_cols = ws.max_row, len(head)
    if COL_SRC not in head:
        sys.exit(f"表头里没有「{COL_SRC}」")
    c_src = head.index(COL_SRC) + 1
    if COL_MEM in head:
        c_mem = head.index(COL_MEM) + 1
    else:
        c_mem = n_cols + 1
        ws.cell(1, c_mem).value = COL_MEM
    ia, ib = head.index("来源表") + 1, head.index("来源行") + 1
    w_src = w_mem = 0
    for r in range(2, ws.max_row + 1):
        k = (ws.cell(r, ia).value, ws.cell(r, ib).value)
        e = ev.get(k)
        if not e:
            continue
        has_src = bool(str(ws.cell(r, c_src).value or "").strip())
        if not has_src and e["chosen"] and e["chosen"]["source"] != "已有":
            ws.cell(r, c_src).value = e["chosen"]["text"]
            w_src += 1
            has_src = True
        if not has_src and k in mem:
            ws.cell(r, c_mem).value = mem[k]["text"]
            w_mem += 1
        elif has_src and ws.cell(r, c_mem).value:
            ws.cell(r, c_mem).value = None          # 互斥：有出处就不留模型记忆
    if ws.max_row != n_rows:
        sys.exit("行数变了 —— 未保存")
    if [c.value for c in ws[1]][:n_cols] != head:
        sys.exit("列序变了 —— 未保存")
    bak = path.with_suffix(".xlsx.bak_dims")
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f"改动前已备份到 {bak.name}")
    wb.save(path)
    print(f"已写回 {path.name}：「{COL_SRC}」{w_src} 格，「{COL_MEM}」{w_mem} 格")
    print("接着重跑 dedupe_apply.py，让 去重后总表_v2 与两张重复展品 sheet 带上尺寸。")


if __name__ == "__main__":
    main()
