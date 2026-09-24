#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓伪满皇宫博物院官网（www.wmhg.com.cn）的藏品与展览，产出提交进仓库的数据模块。

    python3 wmhg_site_scrape.py --probe --allow-expired-cert        # 阶段 1：探路
    python3 wmhg_site_scrape.py --probe-extra --allow-expired-cert  # 补探：「博物中国」、官网文章

**必须在国内网络下跑。** 2026-09-24 实测：境外出口（美国 IP）连官网一律超时，
WebFetch 直接被拒（61.138.187.2:443 ECONNREFUSED）；国家文物局「博物中国」、
首博、故宫的站也一样。Wikidata 上 P195=Q83332（本馆）的条目为 0，
境外没有替代来源 —— 走不了 MFA 那条路。

**已知的页面结构**（来自 2022/2024 年的 Wayback 存档，以现场 --probe 为准）：

    /collection_list.html   藏品页。类目标签 `<a class="side-item" data-category="13">`，
                            2022 年是 13–19 共 7 个：瓷器、日本画、奏折、纪念章、
                            宫廷文物、铜镜、画报。列表由 AJAX 灌入：
                              GET /searchs/collection.html?tpl_file=collection_list
                                  &pagesize=9&category_id=<id>&site_id=0
                            返回 HTML 片段，翻页链接在 `.page-mod .page-item a` 里
    /permanent.html         常设展览（原状陈列、基本陈列），分页 /permanent/p/<n>.html，
                            详情 /exhib/detail/<id>.html
    /special_exhib.html     专题展览
    /en/  /ja/  /tr/        外文版，路径同构

**探路只做三件事**：原始响应逐个存进 `wmhg_raw/`（gitignore，第二次跑直接读盘、
不再打扰官网）；挑出样本复制进 `wmhg_samples/`（入仓库 —— 写解析器的机器连不上官网，
要靠这批样本离线开发）；打印一份报告，同时写进 `wmhg_samples/probe_report.txt`。
**不解析字段、不产出数据模块**：AJAX 片段长什么样还没见过，现在写解析器等于猜。

纪律同 `pem_site_scrape.py`：
· 先读 robots.txt，被禁的路径一概不请求；有 Crawl-delay 照办，没有也至少隔 1.5 秒。
· **碰到人机验证或限流就停**，不绕（同 MFA 的 CAPTCHA，AGENTS.md 第 5 条）。
· 整趟约 40 次请求。
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as html_mod
import json
import pathlib
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import Counter

from tls import ssl_ctx, ssl_ctx_allow_expired

BASE = "https://www.wmhg.com.cn"
HOST_3D = "https://3d.wmhg.com.cn/"
UA = "ari-metadata-research/1.0 (museum visit-planning dataset; contact via repo)"
MIN_SLEEP = 1.5
HERE = pathlib.Path(__file__).resolve().parent

# 人机验证或限流页的字样。只在「状态码可疑」或「页面很短」时才认 ——
# 正常页头部的登录弹窗里也可能写着「验证码」，见字就停会把探路卡死在第一页
BLOCK_PAT = re.compile(r"验证码|人机验证|安全验证|滑块|访问过于频繁|请求过于频繁|"
                       r"captcha|human verification", re.I)
BLOCK_STATUS = {403, 429, 503}

# 详情页上可能出现的字段标签。**只用来在报告里提示有哪些字段，不做抽取** ——
# 抽取要等看过样本、按标签原文逐个登记之后（AGENTS.md 第 7 条：不按位置猜）
LABELS_ZH = ("名称|作品名称|藏品名称|文物名称|年代|时代|朝代|材质|质地|尺寸|规格|级别|等级|"
             "藏品号|藏品编号|编号|总登记号|类别|分类|来源|作者|产地|窑口|数量|简介|说明")
LABEL_ZH_RE = re.compile(rf"({LABELS_ZH})\s*[：:]\s*([^：:]{{1,40}})")
LABEL_EN_RE = re.compile(r"\b([A-Z][A-Za-z ]{1,20}):\s*([^:]{1,40})")


class Unreachable(Exception):
    """连不上。第一个请求就这样，说明这台机器的出口在境外。"""


class Blocked(Exception):
    """人机验证或限流。不绕，停。"""


class CertError(Exception):
    """证书校验失败。连上了，只是证书不对 —— 与出口问题是两回事，别报成「连不上」。"""


# ---------------------------------------------------------------- 请求
class Fetcher:
    """带缓存与限速的 GET。同一 URL 第二次直接读盘。"""

    def __init__(self, raw: pathlib.Path, samples: pathlib.Path, refresh: bool,
                 allow_expired: bool = False):
        self.raw, self.samples, self.refresh = raw, samples, refresh
        raw.mkdir(parents=True, exist_ok=True)
        samples.mkdir(parents=True, exist_ok=True)
        self.mf_path = raw / "manifest.json"
        self.manifest = (json.loads(self.mf_path.read_text("utf-8"))
                         if self.mf_path.exists() else {})
        # 按主机分别记：官网与「博物中国」各有各的 robots
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.delay = MIN_SLEEP
        self.n_live = 0
        self._last = 0.0
        self._ctx = ssl_ctx()
        # 2026-09-24 官网证书已过期（Mac 上国内网络实测 CERTIFICATE_VERIFY_FAILED:
        # certificate has expired）。只对本馆域名、只跳过有效期，要显式开关才用
        self._ctx_expired_ok = ssl_ctx_allow_expired() if allow_expired else None

    def get(self, url: str, *, ajax: bool = False, referer: str | None = None,
            sample: str | None = None) -> tuple[int, str]:
        """-> (HTTP 状态, 正文)。状态 0 表示 robots 不许，没有发请求。"""
        rp = self.robots.get(urllib.parse.urlsplit(url).netloc)
        if rp is not None and not rp.can_fetch(UA, url):
            return 0, ""
        ent = self.manifest.get(url)
        if ent and not self.refresh and (self.raw / ent["file"]).exists():
            status, text = ent["status"], (self.raw / ent["file"]).read_text("utf-8")
        else:
            status, text = self._live(url, ajax, referer)
            fname = _fname(url)
            (self.raw / fname).write_text(text, "utf-8")
            self.manifest[url] = dict(
                file=fname, status=status, bytes=len(text.encode("utf-8")),
                fetched_at=dt.datetime.now().isoformat(timespec="seconds"))
            self.mf_path.write_text(
                json.dumps(self.manifest, ensure_ascii=False, indent=1), "utf-8")
        if status in BLOCK_STATUS or (len(text) < 5000 and BLOCK_PAT.search(text)):
            raise Blocked(f"{url} -> HTTP {status}，{len(text)} 字节："
                          f"{_txt(text)[:200]!r}")
        if sample:
            (self.samples / sample).write_text(text, "utf-8")
        return status, text

    def _live(self, url: str, ajax: bool, referer: str | None) -> tuple[int, str]:
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": UA}
        if ajax:
            # jQuery 的 $.get 会带这个头，有的后端据此决定只回片段还是回整页
            headers["X-Requested-With"] = "XMLHttpRequest"
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        host = urllib.parse.urlsplit(url).hostname or ""
        ctx = (self._ctx_expired_ok
               if self._ctx_expired_ok and (host == "wmhg.com.cn" or host.endswith(".wmhg.com.cn"))
               else self._ctx)
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                status, body, ctype = r.status, r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            status, body, ctype = e.code, e.read(), e.headers.get("Content-Type", "")
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                raise CertError(f"{url}: {e.reason.verify_message}") from e
            raise Unreachable(f"{url}: {e.reason}") from e
        except ssl.SSLCertVerificationError as e:
            raise CertError(f"{url}: {e.verify_message}") from e
        except (socket.timeout, TimeoutError, ConnectionError) as e:
            raise Unreachable(f"{url}: {e}") from e
        finally:
            self._last = time.monotonic()
        self.n_live += 1
        m = re.search(r"charset=([\w-]+)", ctype or "")
        return status, body.decode(m.group(1) if m else "utf-8", "replace")


def _fname(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    s = p.netloc + p.path + ("?" + p.query if p.query else "")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:180] + ".html"


# ---------------------------------------------------------------- 页面小工具
def _txt(s: str) -> str:
    """HTML -> 纯文本，去脚本与样式、去标签、解实体、压空白。"""
    s = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html_mod.unescape(s)).strip()


def _abs(base: str, href: str) -> str:
    # 不用 urljoin：离线自测时 base 是 Wayback 的长路径，urljoin 会把根路径拼到 web.archive.org 上
    if href.startswith(("http://", "https://")):
        return href
    return base + (href if href.startswith("/") else "/" + href)


def _links(frag: str) -> list[tuple[str, str]]:
    return [(m.group(1).strip(), _txt(m.group(2)))
            for m in re.finditer(r'<a\b[^>]*?href\s*=\s*"([^"]*)"[^>]*>(.*?)</a>',
                                 frag, re.S | re.I)]


def _split_links(frag: str) -> tuple[list[str], list[str]]:
    """片段里的链接 -> (详情链接, 翻页链接)，各自去重、保序。"""
    det, pag = [], []
    for href, _ in _links(frag):
        if not href or href.startswith(("javascript", "#")):
            continue
        if "searchs" in href or re.search(r"[?&]p(age)?=|/p/\d+", href):
            pag.append(href)
        elif re.search(r"\d+\.html?$", href):
            det.append(href)
    return list(dict.fromkeys(det)), list(dict.fromkeys(pag))


def _ids(hrefs) -> set[str]:
    return {m.group(1) for h in hrefs if (m := re.search(r"(\d+)\.html?$", h))}


def _shape(href: str) -> str:
    return re.sub(r"\d+", "N", urllib.parse.urlsplit(href).path)


def _title(page: str) -> str:
    m = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    return _txt(m.group(1)) if m else ""


def _heads(page: str) -> list[str]:
    return [t for m in re.finditer(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", page, re.S | re.I)
            if (t := _txt(m.group(1)))][:6]


def _imgs(page: str) -> list[str]:
    """正文图片：去掉站点主题素材（/Public/static/themes/…）。"""
    return [s for s in dict.fromkeys(re.findall(r'<img\b[^>]*?src\s*=\s*"([^"]+)"', page, re.I))
            if "/static/themes" not in s and not s.startswith("data:")]


def _labels(page: str, en: bool = False) -> list[str]:
    rx = LABEL_EN_RE if en else LABEL_ZH_RE
    seen: dict[str, str] = {}
    for k, v in rx.findall(_txt(page)):
        seen.setdefault(k.strip(), v.strip())
    return [f"{k}：{v}" for k, v in list(seen.items())[:14]]


def _totals(frag: str) -> list[str]:
    """「共 N 条 / 共 N 页」之类的字样，加上翻页链接里出现过的最大页码。"""
    out = [f"共{n}{u}" for n, u in re.findall(r"共\s*(\d+)\s*(条|件|页|个)", _txt(frag))]
    nums = [int(t) for _, t in _links(frag) if t.isdigit()]
    if nums:
        out.append(f"翻页最大页码 {max(nums)}")
    return out


def _categories(page: str) -> list[tuple[str, str]]:
    """藏品页侧栏的类目 -> [(category_id, 名称)]，不含「全部」。"""
    return [(m.group(1), _txt(m.group(2)))
            for m in re.finditer(r'data-category\s*=\s*"(\d*)"[^>]*>(.*?)</a>', page, re.S | re.I)
            if m.group(1)]


def _js_param(page: str, name: str) -> str | None:
    """内联脚本里 `var search = { tpl_file : 'collection_list', pagesize : 9, … }` 的取值。"""
    m = re.search(rf"\b{name}\s*:\s*['\"]?([\w-]+)", page)
    return m.group(1) if m else None


def _ajax_endpoint(page: str) -> str | None:
    m = re.search(r'\$\.(?:get|post)\(\s*"([^"]*searchs/collection[^"?]*)', page)
    return m.group(1) if m else None


def _exhibs(page: str) -> dict[str, str]:
    """展览列表页 -> {展览 id: 标题}。同一个 id 的图片链接没有文字，取第一个非空的。"""
    out: dict[str, str] = {}
    for href, text in _links(page):
        m = re.search(r"/exhib/detail/(\d+)\.html", href)
        if m and (text or m.group(1) not in out):
            out[m.group(1)] = out.get(m.group(1)) or text
    return out


# ---------------------------------------------------------------- 探路
class Report:
    def __init__(self):
        self.lines: list[str] = []

    def say(self, *a) -> None:
        line = " ".join(str(x) for x in a)
        self.lines.append(line)
        print(line, flush=True)


SITE_PATHS = ("/collection_list.html", "/searchs/collection.html", "/permanent.html",
              "/exhib/detail/1.html", "/en/collection_list.html", "/searchs/keywords/x")


def probe_robots(f: Fetcher, base: str, r: Report, paths=SITE_PATHS,
                 sample: str = "robots.txt") -> None:
    r.say(f"\n## robots.txt（{urllib.parse.urlsplit(base).netloc}）")
    st, text = f.get(base + "/robots.txt", sample=sample)
    rp = urllib.robotparser.RobotFileParser()
    # 404 按惯例等于全部允许；其余非 200 也按空规则处理，但在报告里写明
    rp.parse(text.splitlines() if st == 200 else [])
    f.robots[urllib.parse.urlsplit(base).netloc] = rp
    cd = rp.crawl_delay(UA)
    f.delay = max(f.delay, float(cd or 0))
    r.say(f"HTTP {st}，Crawl-delay={cd}，实际间隔 {f.delay}s")
    if st == 200:
        for line in text.splitlines()[:40]:
            r.say("    " + line)
    for path in paths:
        r.say(f"  {path}: {'允许' if rp.can_fetch(UA, base + path) else '⚠ 禁止'}")


def probe_collection(f: Fetcher, base: str, r: Report, lang: str) -> dict[str, list[str]]:
    """一个语种的藏品页 + 每个类目的第 1 页 + 每个类目 1 个详情页。-> {类目: 详情链接}"""
    prefix = "" if lang == "zh" else f"/{lang}"
    r.say(f"\n## 藏品（{lang}）{prefix}/collection_list.html")
    st, page = f.get(f"{base}{prefix}/collection_list.html", sample=f"collection_list_{lang}.html")
    cats = _categories(page)
    tpl = _js_param(page, "tpl_file") or "collection_list"
    ps = _js_param(page, "pagesize") or "9"
    site = _js_param(page, "site_id") or "0"
    ep = _ajax_endpoint(page) or "/searchs/collection.html"
    r.say(f"HTTP {st}，<title> {_title(page)!r}")
    r.say(f"类目 {len(cats)} 个：{cats}")
    r.say(f"脚本参数：tpl_file={tpl} pagesize={ps} site_id={site}，接口 {ep}")
    if not cats:
        r.say(f"⚠ 页面上没找到 data-category —— 结构变了，看样本 collection_list_{lang}.html")

    def coll(cat: str, pagesize, sample: str | None = None) -> tuple[int, str]:
        q = urllib.parse.urlencode(dict(tpl_file=tpl, pagesize=pagesize,
                                        category_id=cat, site_id=site))
        return f.get(_abs(base, ep) + "?" + q, ajax=True,
                     referer=f"{base}{prefix}/collection_list.html", sample=sample)

    details: dict[str, list[str]] = {}
    for cid, name in [("", "全部")] + cats:
        st, frag = coll(cid, ps, sample=f"coll_{lang}_cat{cid or 'all'}_p1.html")
        det, pag = _split_links(frag)
        details[cid] = det
        r.say(f"  [{cid or '全部'}] {name}: HTTP {st}，{len(frag)} 字节；"
              f"详情链接 {len(det)} 个 {Counter(map(_shape, det)).most_common(2)}；"
              f"翻页链接 {len(pag)} 个 {pag[:3]}；{_totals(frag)}")

    first = next((c for c, _ in cats if details.get(c)), None)
    if lang == "zh" and first is not None:
        # 大一点的 pagesize 能把请求数压下来；后端不认就还是 9 条，也不损失什么
        st, frag = coll(first, 60)
        r.say(f"  pagesize=60 试探（类目 {first}）：HTTP {st}，"
              f"详情链接 {len(_split_links(frag)[0])} 个（默认 pagesize={ps} 时 "
              f"{len(details[first])} 个）")

    for cid, name in cats if lang == "zh" else cats[:1]:
        if not details.get(cid):
            continue
        href = details[cid][0]
        st, pg = f.get(_abs(base, href), sample=f"coll_detail_{lang}_cat{cid}.html")
        r.say(f"  详情 [{cid}] {name} {href}: HTTP {st}，<title> {_title(pg)!r}")
        r.say(f"      标题：{_heads(pg)}")
        r.say(f"      带标签的字段：{_labels(pg, en=(lang == 'en'))}")
        r.say(f"      正文图片：{_imgs(pg)[:3]}")
    return details


def probe_exhibitions(f: Fetcher, base: str, r: Report) -> None:
    for kind, path in (("常设展览", "/permanent.html"), ("专题展览", "/special_exhib.html")):
        stem = path[1:-len(".html")]
        r.say(f"\n## {kind} {path}")
        st, page = f.get(base + path, sample=f"{stem}.html")
        items = _exhibs(page)
        r.say(f"HTTP {st}，<title> {_title(page)!r}，本页展览 {len(items)} 个")
        if not items:
            eps = re.findall(r'\$\.(?:get|post)\(\s*"([^"]+)"', page)
            r.say(f"⚠ 页面上没有 /exhib/detail/ 链接，内联脚本请求的接口：{eps}")
        # 翻页只显示邻近几页（2024 年存档里第 4 页只列出 1、2、3、5），所以边抓边发现
        seen, todo, bad = {1}, set(), {}
        while True:
            todo |= {int(n) for n in re.findall(rf"/{stem}/p/(\d+)\.html", page)} - seen
            if not todo or len(seen) >= 30:
                break
            n = min(todo)
            todo.discard(n)
            seen.add(n)
            st, page = f.get(f"{base}/{stem}/p/{n}.html")
            if st != 200:
                bad[n] = st
            items.update({k: v for k, v in _exhibs(page).items() if v or k not in items})
        r.say(f"共 {len(seen)} 页（其中取不到的 {bad or '无'}），展览 {len(items)} 个。"
              f"列表页上的标题会截断，全称以详情页为准：")
        for k, v in items.items():
            r.say(f"    {k:>5}  {v}")
        if kind == "常设展览":
            for k in list(items)[:2]:
                st, pg = f.get(f"{base}/exhib/detail/{k}.html", sample=f"exhib_detail_{k}.html")
                r.say(f"  详情 {k}: HTTP {st}，<title> {_title(pg)!r}")
                r.say(f"      标题：{_heads(pg)}")
                r.say(f"      带标签的字段：{_labels(pg)}")
                r.say(f"      正文图片 {len(_imgs(pg))} 张：{_imgs(pg)[:2]}")


def probe_3d(f: Fetcher, r: Report) -> None:
    r.say(f"\n## 三维藏品站 {HOST_3D}")
    try:
        st, page = f.get(HOST_3D, sample="3d_index.html")
    except (Unreachable, CertError) as e:
        r.say(f"取不到：{e}")
        return
    js = re.findall(r'<script\b[^>]*?src\s*=\s*"([^"]+\.js[^"]*)"', page, re.I)
    frames = re.findall(r'<iframe\b[^>]*?src\s*=\s*"([^"]+)"', page, re.I)
    r.say(f"HTTP {st}，{len(page)} 字节，<title> {_title(page)!r}；脚本 {js[:5]}；iframe {frames}")
    found: Counter = Counter()
    for src in js[:3]:
        u = urllib.parse.urljoin(HOST_3D, src)
        if urllib.parse.urlsplit(u).netloc != urllib.parse.urlsplit(HOST_3D).netloc:
            continue
        _, code = f.get(u)
        for m in re.finditer(r'["\'](/?(?:api|apis|v\d)/[\w/.-]+|https?://[\w.-]+/[\w/.-]*api[\w/.-]*)["\']',
                             code):
            found[m.group(1)] += 1
    r.say(f"脚本里出现的接口路径：{found.most_common(20)}")


def probe(f: Fetcher, base: str, r: Report) -> None:
    r.say(f"# 伪满皇宫博物院官网探路 {dt.datetime.now().isoformat(timespec='seconds')}")
    r.say(f"base = {base}")
    probe_robots(f, base, r)
    zh = probe_collection(f, base, r, "zh")
    en = probe_collection(f, base, r, "en")
    zh_ids = set().union(*map(_ids, zh.values())) if zh else set()
    en_ids = set().union(*map(_ids, en.values())) if en else set()
    r.say(f"\n中英两版各类目第 1 页的详情 id：中 {len(zh_ids)}，英 {len(en_ids)}，"
          f"交集 {len(zh_ids & en_ids)}")
    r.say("\n## 日文版")
    st, page = f.get(base + "/ja/collection_list.html", sample="collection_list_ja.html")
    r.say(f"HTTP {st}，类目 {_categories(page)}，site_id={_js_param(page, 'site_id')}")
    probe_exhibitions(f, base, r)
    probe_3d(f, r)


# ---------------------------------------------------------------- 补探（--probe-extra）
# 第一轮（2026-09-24）的结论：官网只发布了约 30 件藏品，中文类目页已 404
# （「系统发生错误」），但 AJAX 接口还通。用户决定先补探两处再定规模：
#   ① 国家文物局「博物中国」—— 可移动文物普查的馆方报送数据，详情页带「级别」
#   ② 官网资讯/学术栏目里介绍单件藏品的文章
# 顺带把第一轮缺的中文详情页样本补上（写解析器要用）。

MC_BASE = "https://www.museumschina.cn"
# 「博物中国」上本馆介绍页的 id（WebSearch 结果）。**列表筛选用的 museums= 是另一套
# 14 位编号**（存档里的形如 61072721800224），不能拿这个直接筛，要现场找
MC_MUSEUM_PAGE = "202208231954219157"
# 2022 年存档里中文类目的 id；现在类目页 404，只能照旧值试接口认不认
ZH_CATS_2022 = [("13", "瓷器"), ("14", "日本画"), ("15", "奏折"), ("16", "纪念章"),
                ("17", "宫廷文物"), ("18", "铜镜"), ("19", "画报")]


def _coll_items(frag: str, id_re: str) -> dict[str, str]:
    """藏品列表片段 -> {官网 id: 名称}。名称优先取 `<span class="p" title="…">` 的属性值 ——
    标签里的文字过长会被截成「…」，英文版尤其如此。"""
    out: dict[str, str] = {}
    for m in re.finditer(r'<div class="list-item">(.*?)</a>', frag, re.S):
        h = re.search(id_re, m.group(1))
        name = re.search(r'<span class="p"(?:[^>]*?title="([^"]*)")?[^>]*>(.*?)</span>',
                         m.group(1), re.S)
        if h:
            out[h.group(1)] = (html_mod.unescape(name.group(1) or "").strip()
                               or _txt(name.group(2))) if name else ""
    return out


def _excerpt(page: str, key: str, n: int = 500) -> str:
    """正文摘录：key 出现两次以上时取第二次之后（第一次多半在 <title> 或面包屑里）。"""
    x = _txt(page)
    i = x.find(key)
    j = x.find(key, i + 1) if i >= 0 else -1
    k = j if j >= 0 else i
    return x[k:k + n] if k >= 0 else x[:n]


def _walk_pages(f: Fetcher, base: str, first: str, page_re: str, *, ajax=False,
                referer=None, cap: int = 60) -> list[str]:
    """从第一页出发，边抓边发现翻页链接（翻页器只显示邻近几页）。-> 各页正文"""
    pages, seen, todo = [first], set(), set()
    while True:
        todo |= set(re.findall(page_re, pages[-1])) - seen
        if not todo or len(seen) >= cap:
            return pages
        href = min(todo, key=lambda h: int(re.search(r"(\d+)\D*$", h).group(1)))
        todo.discard(href)
        seen.add(href)
        _, text = f.get(_abs(base, html_mod.unescape(href)), ajax=ajax, referer=referer)
        pages.append(text)


def probe_zh_more(f: Fetcher, base: str, r: Report) -> None:
    r.say("\n# 中文藏品补探")
    ep, ref = base + "/searchs/collection.html", base + "/collection_list.html"

    def coll(cat: str, pagesize=9, sample=None):
        q = urllib.parse.urlencode(dict(tpl_file="collection_list", pagesize=pagesize,
                                        category_id=cat, site_id=0))
        return f.get(f"{ep}?{q}", ajax=True, referer=ref, sample=sample)

    _, first = coll("")
    pages = _walk_pages(f, base, first, r'href="(/searchs/collection/[^"]*?/p/\d+\.html)"',
                        ajax=True, referer=ref)
    allitems: dict[str, str] = {}
    for p in pages:
        allitems.update(_coll_items(p, r"/collection/detail/(\d+)\.html"))
    r.say(f"「全部」共 {len(pages)} 页，藏品 {len(allitems)} 件：")
    for k, v in allitems.items():
        r.say(f"    {k:>5}  {v}")
    st, frag = coll("", 60)
    r.say(f"pagesize=60 一次取「全部」：HTTP {st}，{len(_coll_items(frag, r'/collection/detail/(\d+)\.html'))} 件")

    union: set[str] = set()
    for cid, name in ZH_CATS_2022:
        st, frag = coll(cid, 60, sample=f"coll_zh_cat{cid}_p1.html")
        got = _coll_items(frag, r"/collection/detail/(\d+)\.html")
        union |= set(got)
        r.say(f"  类目 {cid} {name}：HTTP {st}，{len(got)} 件 {list(got.values())[:4]}")
    r.say(f"各类目并集 {len(union)} 件；不在任何类目里的 {sorted(set(allitems) - union)}；"
          f"类目里有而「全部」没有的 {sorted(union - set(allitems))}")

    ids = sorted(allitems, key=int)
    for k in dict.fromkeys([ids[0], ids[len(ids) // 2], ids[-1]] if ids else []):
        st, pg = f.get(f"{base}/collection/detail/{k}.html", sample=f"coll_detail_zh_{k}.html")
        r.say(f"  详情 {k} {allitems[k]}：HTTP {st}，<title> {_title(pg)!r}")
        r.say(f"      带标签的字段：{_labels(pg)}")
        r.say(f"      正文图片 {len(_imgs(pg))} 张：{_imgs(pg)[:2]}")
        r.say(f"      正文摘录：{_excerpt(pg, allitems[k])}")


def probe_mc(f: Fetcher, r: Report) -> None:
    r.say("\n# 博物中国 museumschina.cn（国家文物局数据中心）")
    probe_robots(f, MC_BASE, r, paths=("/Collection", "/collection/details", "/museums/details"),
                 sample="mc_robots.txt")
    st, page = f.get(f"{MC_BASE}/museums/details?id={MC_MUSEUM_PAGE}", sample="mc_museum.html")
    r.say(f"本馆介绍页：HTTP {st}，<title> {_title(page)!r}")
    r.say(f"  摘录：{_excerpt(page, '藏品', 300)}")
    mids = Counter(re.findall(r"museums=(\d+)", page))
    r.say(f"  页面上出现的 museums= 取值：{mids.most_common(5)}")
    mid = mids.most_common(1)[0][0] if mids else None
    if not mid:
        # 退路：拿官网上已知的藏品名去搜，结果里「收藏单位」链接的 museums= 就是本馆编号
        for kw in ("兰花御纹章", "伪满国势调查纪念章", "伪满"):
            st, pg = f.get(f"{MC_BASE}/Collection?" + urllib.parse.urlencode({"searchkey": kw}))
            hit = [re.search(r"museums=(\d+)", h).group(1) for h, t in _links(pg)
                   if "museums=" in h and "伪满皇宫" in t]
            r.say(f"  搜「{kw}」：HTTP {st}，{'本馆编号 ' + hit[0] if hit else '结果里没有本馆'}")
            if hit:
                mid = hit[0]
                break
    if not mid:
        r.say("⚠ 没找到本馆在「博物中国」上的筛选编号，看样本 mc_museum.html")
        return

    def lst(extra: dict, sample=None):
        q = urllib.parse.urlencode(dict(museums=mid, **extra))
        st, pg = f.get(f"{MC_BASE}/Collection?{q}", sample=sample)
        det = list(dict.fromkeys(re.findall(r'href="(/collection/details\?id=[^"]+)"', pg, re.I)))
        maxp = max((int(n) for n in re.findall(r"pages=(\d+)", pg)), default=0)
        return st, pg, det, maxp

    st, pg, det, maxp = lst(dict(pages=1, size=20), sample="mc_list_p1.html")
    units = Counter(_txt(u) for u in re.findall(
        r'class="ex_info_address">\s*<a[^>]*>(.*?)</a>', pg, re.S))
    r.say(f"museums={mid}：HTTP {st}，本页 {len(det)} 件，翻页最大页码 {maxp}（每页 20）；"
          f"收藏单位 {units.most_common(3)}")
    st2, _, det2, maxp2 = lst(dict(pages=1, size=100))
    r.say(f"  size=100 试探：HTTP {st2}，本页 {len(det2)} 件，翻页最大页码 {maxp2}")

    # 按「级别」各取第 1 页，估各级件数。级别的取值码从筛选栏的链接里读，不写死
    levels = {t: re.search(r"level=(\d+)", h).group(1) for h, t in _links(pg)
              if "level=" in h and t in ("一级", "二级", "三级", "一般", "未定级")}
    r.say(f"  级别筛选码：{levels}")
    for name, code in levels.items():
        st, _, d, mp = lst(dict(level=code, pages=1, size=20))
        r.say(f"    {name}：HTTP {st}，第 1 页 {len(d)} 件，翻页最大页码 {mp}")

    for i, href in enumerate(det[:2], 1):
        st, dp = f.get(MC_BASE + href, sample=f"mc_detail_{i}.html")
        r.say(f"  详情 {href}：HTTP {st}，<title> {_title(dp)!r}")
        r.say(f"      摘录：{_excerpt(dp, '收藏单位', 400)}")


def probe_articles(f: Fetcher, base: str, r: Report) -> None:
    r.say("\n# 官网文章（找介绍单件藏品的）")
    art_re = r"/detail/\d+\.html"
    for i, kw in enumerate(("藏品", "文物", "馆藏", "珍品", "赏析"), 1):
        st, pg = f.get(f"{base}/searchs/keywords/{urllib.parse.quote(kw)}",
                       sample=f"search_kw{i}.html")
        arts = [(h, t) for h, t in dict.fromkeys(_links(pg)) if re.search(art_re, h) and t]
        r.say(f"  站内搜「{kw}」：HTTP {st}，文章链接 {len(arts)} 个；{_totals(pg)}")
        for h, t in arts[:12]:
            r.say(f"      {h}  {t[:40]}")
    for path in ("/information.html", "/focusnews.html", "/achievements.html", "/papers.html"):
        st, pg = f.get(base + path, sample=f"list_{path[1:-5]}.html")
        arts = [(h, t) for h, t in dict.fromkeys(_links(pg)) if re.search(art_re, h) and t]
        hit = [(h, t) for h, t in arts if re.search(r"藏|文物|赏|珍|器|瓷|画|章", t)]
        r.say(f"  {path}：HTTP {st}，<title> {_title(pg)!r}，文章 {len(arts)} 篇，"
              f"题目沾边的 {len(hit)} 篇；{_totals(pg)}")
        for h, t in hit[:10]:
            r.say(f"      {h}  {t[:40]}")


def probe_extra(f: Fetcher, base: str, r: Report) -> None:
    r.say(f"# 伪满皇宫博物院补探 {dt.datetime.now().isoformat(timespec='seconds')}")
    r.say(f"base = {base}")
    probe_robots(f, base, r)
    probe_zh_more(f, base, r)
    try:
        probe_mc(f, r)
    except (Unreachable, CertError) as e:
        # 两处补探互不依赖：「博物中国」取不到不妨碍看官网文章
        r.say(f"⚠ 「博物中国」取不到：{e}")
    probe_articles(f, base, r)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")        # 中文 Windows 控制台默认 GBK，--help 也要
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--probe", action="store_true", help="阶段 1：探路，只存原始响应与样本")
    ap.add_argument("--probe-extra", action="store_true",
                    help="补探：中文藏品补齐、「博物中国」本馆藏品、官网介绍藏品的文章")
    ap.add_argument("--base", default=BASE,
                    help="只在离线自测时改，例如 Wayback 存档："
                         "https://web.archive.org/web/2024id_/https://www.wmhg.com.cn")
    ap.add_argument("--out", default=str(HERE), help="wmhg_raw/ 与 wmhg_samples/ 的上级目录")
    ap.add_argument("--refresh", action="store_true", help="不读本地缓存，全部重新请求")
    ap.add_argument("--allow-expired-cert", action="store_true",
                    help="官网证书过期时用：只对 *.wmhg.com.cn 跳过有效期检查，"
                         "证书链与域名照常校验（tls.ssl_ctx_allow_expired）")
    args = ap.parse_args()
    if args.probe == args.probe_extra:
        ap.error("--probe 与 --probe-extra 二选一。字段解析要等看过样本再写")
    run, report_name = ((probe, "probe_report.txt") if args.probe
                        else (probe_extra, "probe_extra_report.txt"))

    out = pathlib.Path(args.out)
    f = Fetcher(out / "wmhg_raw", out / "wmhg_samples", args.refresh,
                allow_expired=args.allow_expired_cert)
    r = Report()
    if args.allow_expired_cert:
        r.say("⚠ 本次对 *.wmhg.com.cn 跳过了证书有效期检查（--allow-expired-cert），"
              "证书链与域名照常校验")
    code = 0
    try:
        run(f, args.base.rstrip("/"), r)
    except CertError as e:
        r.say(f"\n[fatal] 证书校验失败：{e}")
        r.say("连上了，是对方证书的问题，不是出口问题。若上面写的是「certificate has expired」，"
              "加 --allow-expired-cert 重跑（只跳过有效期，证书链与域名照常校验）；"
              "其他证书错误不要绕，停下来问用户。")
        code = 4
    except Unreachable as e:
        r.say(f"\n[fatal] 连不上官网：{e}")
        if f.n_live or len(f.manifest) > 1:
            # 前面已经通过，中途才被拒：更像限流，不是出口问题。换网络没用，重试也别急着来
            r.say("前面的请求是通的，中途被拒 —— 多半是限流。已抓到的在缓存里，"
                  "隔一阵再跑会从断点接着来；连续被拒就停下来问用户。")
        else:
            r.say("境外出口连官网一律超时（2026-09-24 实测），换国内网络再跑。")
        code = 2
    except Blocked as e:
        r.say(f"\n[stop] 碰到人机验证或限流：{e}")
        r.say("不绕。已抓到的留在缓存里，停下来问用户。")
        code = 3
    finally:
        r.say(f"\n本次实际请求 {f.n_live} 次，其余命中本地缓存（{f.raw}）")
        (f.samples / report_name).write_text("\n".join(r.lines) + "\n", "utf-8")
    sys.exit(code)


if __name__ == "__main__":
    main()
