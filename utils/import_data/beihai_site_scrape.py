#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓北海公园官网（www.beihaipark.com.cn）的景点、文化、导览栏目，产出提交进仓库的原始数据。

    python3 beihai_site_scrape.py --probe     # 探路：栏目树 + 每个栏目第 1 页 + 每个栏目 1 篇详情（约 60 次请求）
    python3 beihai_site_scrape.py --scrape    # 正式抓取：内容栏目全部列表与详情，新闻类栏目只取列表（约 5–15 分钟）

**必须在国内网络下跑。** 2026-10-08 实测：境外出口（美国 IP）连 www.beihaipark.com.cn、
北京市公园管理中心 gygl.beijing.gov.cn 一律超时（同伪满皇宫、吉林省博物院，AGENTS.md 第 16、17 条）。
两条命令可以接着跑：探路的响应在缓存里，正式抓取不会重复请求。

**已知的站点结构**（来自 Wayback 2026-09-19 存档的前端代码，以现场为准）：

    Vue 单页应用（Vite 构建），后台是 JeecgBoot。页面本身没有内容，数据由 axios 从
    `https://www.beihaipark.com.cn/api` 取，响应形如 {success, code, message, result}。
    请求头带 X-Access-Token：访客令牌由 GET /jeecg-summary/userUtil/NoLoginToken 取得
    （前端碰到 401 或「Token失效」时自动去取，本脚本开头就取）。

    GET /smart-bhpark/modules/busSecurityColumn/queryBySiteIdAndDataCode?siteId=<站点>&dataCode=<栏目代码>
        一个页面的栏目树。result 是 {栏目代码: {columnInfo: {…, articleList: […]}}}。
        中文站 siteId=b91a543a5c3c48488c8cf7e86d0b4700，英文站（dataCode=yingwen）siteId=5a4edcbec072478ea6009131d7578f5e。
        前端用到的 dataCode：homePage、explore、culture、guide、about、activity、yingwen。
    GET /smart-bhpark/modules/busSecurityArticle/list?fdColumnId=<栏目 id>&pageNo=<页>&pageSize=<条>
        栏目下的文章列表，result = {records, total, pages}。
    GET /smart-bhpark/index/busSecurityIndex/queryById/<文章 id>
        文章详情：fdTitle、fdSynopsis、fdContent（HTML）、fdPicture、fdPublishTime、fdExternalLinksUrl …

    「景点介绍」是 explore 下的 explore-jdjs，标题是「中文名 English name」连写（前端按首个
    非汉字处拆开）；英文站对应 yingwen-jdjs。fdIsExternalLinks=="2" 的文章是外链，
    前端直接打开 fdExternalLinksUrl，详情接口里可能没有正文 —— 外链一概不跟（不在白名单），只记下来。

**抓什么**（DETAIL_PREFIX）：explore、culture、guide、yingwen 四棵树下所有栏目，列表取全、每篇取详情。
其余（homePage、about、activity 及前端代码里写死的新闻栏目）只取列表，不取详情 —— 那里是公园新闻、
活动、信息公开，取列表是为了日后查「某景点暂停开放 / 修缮」这类公告。

**产出**：`beihai_site_data.json`（入仓库，勿手改）—— 接口返回的原始字段逐字照录，**这里不做任何解析**，
解析与取舍在 `beihai_build.py`（境外机离线写）。原始响应缓存在 beihai_raw/（gitignore，重跑读盘、不再打扰官网）；
样本与报告在 beihai_samples/（入仓库）。

纪律同 wmhg_site_scrape.py（请求、缓存、限速、人机验证即停都直接复用它的 Fetcher）：
· 先读 robots.txt；有 Crawl-delay 照办，没有也至少隔 1.5 秒。
· **碰到人机验证、登录墙或限流就停**，不绕。只调上面三个只读接口和取访客令牌的接口。
· 结构对不上（栏目树里没有 explore-jdjs、列表条数与 total 不符、详情 id 对不上）一律退出码 5，报告里写明看到了什么。
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse

import wmhg_site_scrape as W
from wmhg_site_scrape import Blocked, CertError, Report, Unreachable, _txt, _write

BASE = "https://www.beihaipark.com.cn"
API = "/api"
HERE = pathlib.Path(__file__).resolve().parent
ALLOWED_HOSTS = {"www.beihaipark.com.cn", "beihaipark.com.cn"}

SITE_ZH = "b91a543a5c3c48488c8cf7e86d0b4700"
SITE_EN = "5a4edcbec072478ea6009131d7578f5e"
# 前端各页面调 queryBySiteIdAndDataCode 时传的 dataCode（2026-09-19 版前端代码）
DATA_CODES = ("homePage", "explore", "culture", "guide", "about", "activity", "yingwen")
# 这几棵树下的栏目：列表取全、每篇取详情
DETAIL_PREFIX = ("explore", "culture", "guide", "yingwen")
# 前端代码里写死、可能不在栏目树里的栏目 id（取自哪个页面的组件）。只取列表
KNOWN_COLUMNS = {
    "04888d60432f49bbb9968c5c34425517": "公园动态（/index/parkNews）",
    "7eeb980b41a346c88dab83e4b71d4f51": "活动资讯（/index/activityNews、/activity）",
    "ec1ad17befde4f66bc841c4fadad5ce4": "活动（/activity）",
    "8d236ef4bd0e4cb1adb92a23132a725e": "科普知识（/index/category、探索页科普）",
    "8589478f692e4184901c0f775bc3aee8": "科普·全部（探索页）",
    "12f51ff09679485e91dd3502389154d1": "科普活动（探索页）",
    "4c5391c4e0974e10a2c9ce488a867c71": "研学（探索页）",
    "f949dcc802b84bd7b429707bd8a3552a": "探索页 gardenCity 组件",
    "fa4c521ad4624f5092feddb4aa2101ad": "太液旧影（探索页 taiyejiuying 组件）",
    "fda9014a60804d8ca3a328f573cb0620": "文化页列表组件",
    "9ae99dc74cda4e25ab3c558ca4bd5bae": "关于·游览（/about/tour）",
}
PAGE_SIZE = 50
DETAIL_CAP = 400          # 单个内容栏目超过这么多篇就停下来问 —— 多半是把新闻类栏目当成了内容栏目
LIST_PAGE_CAP = 40        # 只取列表的栏目最多翻这么多页（50 × 40 = 2000 条），超出如实标 truncated


class Incomplete(Exception):
    """没抓完。不写数据文件。"""


class BhFetcher(W.Fetcher):
    """wmhg 的 Fetcher 加三样：主机白名单；访客令牌（X-Access-Token）；前端也会带的 realPath 头。"""

    def __init__(self, *a, extra_host: str | None = None, **kw):
        super().__init__(*a, **kw)
        self.allowed = ALLOWED_HOSTS | ({extra_host} if extra_host else set())
        self.token: str | None = None
        self.page = BASE + "/"

    def check_host(self, url: str) -> None:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host not in self.allowed:
            sys.exit(f"[fatal] {host} 不在白名单 ALLOWED_HOSTS 里：{url}")

    def get(self, url: str, **kw) -> tuple[int, str]:
        self.check_host(url)
        return super().get(url, **kw)

    def _live(self, url: str, ajax: bool, referer: str | None) -> tuple[int, str]:
        # 父类只认 User-Agent / X-Requested-With / Referer。这里换成前端 axios 实际带的头
        import time
        import urllib.request
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": W.UA, "Accept": "application/json, text/plain, */*"}
        if ajax:
            headers["realPath"] = urllib.parse.quote(self.page, safe=":/?#=&")
            if self.token:
                headers["X-Access-Token"] = self.token
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        return self._send(req, url)

    def _send(self, req, url: str) -> tuple[int, str]:
        import socket
        import ssl
        import time
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ctx) as r:
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

    def fetch_token(self, base: str, r: Report) -> None:
        """访客令牌每次现取，不进缓存、不进样本（它是凭据，换台机器也没用）。"""
        import urllib.request
        url = f"{base}{API}/jeecg-summary/userUtil/NoLoginToken"
        self.check_host(url)
        req = urllib.request.Request(url, headers={"User-Agent": W.UA,
                                                   "Accept": "application/json, text/plain, */*"})
        st, text = self._send(req, url)
        js = _json(text)
        if st != 200 or not js or not js.get("success") or not isinstance(js.get("result"), str):
            raise SystemExit(f"取访客令牌失败：HTTP {st}，{text[:200]!r}")
        self.token = js["result"]
        r.say(f"访客令牌：取到（{len(self.token)} 字符，不落盘）")


# ---------------------------------------------------------------- 小工具
def _json(text: str):
    try:
        return json.loads(text.lstrip("﻿"))
    except ValueError:
        return None


def _is_html(text: str) -> bool:
    return text.lstrip()[:15].lower().startswith(("<!doctype", "<html", "<!--"))


def _token_problem(st: int, js) -> bool:
    msg = str((js or {}).get("message") or "")
    return st == 401 or (js is not None and not js.get("success") and "Token" in msg)


def api(f: BhFetcher, base: str, path: str, params: dict | None, r: Report, *,
        page: str = "/#/index", sample: str | None = None) -> dict:
    """GET /api<path> -> 解析后的 JSON。令牌失效时重取一次令牌、绕开缓存重请求；仍不行就退出码 5。"""
    q = urllib.parse.urlencode(params or {})
    url = f"{base}{API}{path}" + ("?" + q if q else "")
    f.page = base + page
    st, text = f.get(url, ajax=True, referer=base + "/", sample=sample)
    js = _json(text) if not _is_html(text) else None
    if _token_problem(st, js):
        r.say(f"  令牌失效（HTTP {st}，{(js or {}).get('message')!r}），重取令牌后重请求一次")
        f.fetch_token(base, r)
        old, f.refresh = f.refresh, True
        try:
            st, text = f.get(url, ajax=True, referer=base + "/", sample=sample)
        finally:
            f.refresh = old
        js = _json(text) if not _is_html(text) else None
    if st != 200 or js is None or not js.get("success"):
        raise SystemExit(f"{path} {params}: HTTP {st}，"
                         f"{'success=False，message=' + repr(js.get('message')) if js else '不是 JSON：' + repr(text[:200])}")
    return js


def probe_robots(f: BhFetcher, base: str, r: Report) -> None:
    import urllib.robotparser
    host = urllib.parse.urlsplit(base).netloc
    r.say(f"\n## robots.txt（{host}）")
    st, text = f.get(base + "/robots.txt", sample="robots.txt")
    rp = urllib.robotparser.RobotFileParser()
    if st == 200 and _is_html(text):
        rp.parse([])
        r.say(f"HTTP {st}，但返回的是 HTML —— 单页应用的兜底页，按「没有 robots」处理")
    else:
        rp.parse(text.splitlines() if st == 200 else [])
        r.say(f"HTTP {st}，Crawl-delay={rp.crawl_delay(W.UA)}")
        if st == 200:
            for line in text.splitlines()[:40]:
                r.say("    " + line)
    f.robots[host] = rp
    f.delay = max(f.delay, float(rp.crawl_delay(W.UA) or 0))
    r.say(f"实际间隔 {f.delay}s")
    for p in (API + "/smart-bhpark/modules/busSecurityArticle/list",
              API + "/smart-bhpark/index/busSecurityIndex/queryById/x"):
        r.say(f"  {p}: {'允许' if rp.can_fetch(W.UA, base + p) else '⚠ 禁止'}")


def _title_split(t: str) -> tuple[str, str]:
    """前端的拆法：开头一串汉字是中文名，其余是英文名。只用于报告。"""
    t = (t or "").strip()
    m = re.match(r"^([一-鿿]+)\s*(.*)$", t)
    return (m.group(1), m.group(2).strip()) if m else (t, "")


def _col_id(info: dict) -> str | None:
    for k in ("id", "fdColumnId"):
        if info.get(k):
            return str(info[k])
    return None


def trees(f: BhFetcher, base: str, r: Report) -> dict[str, dict]:
    """七棵栏目树 -> {dataCode: result}。"""
    out = {}
    for code in DATA_CODES:
        site = SITE_EN if code == "yingwen" else SITE_ZH
        js = api(f, base, "/smart-bhpark/modules/busSecurityColumn/queryBySiteIdAndDataCode",
                 dict(siteId=site, dataCode=code), r, page=f"/#/{'english' if code == 'yingwen' else code}",
                 sample=f"tree_{code}.json")
        res = js.get("result")
        if not isinstance(res, dict) or not res:
            raise SystemExit(f"栏目树 {code} 的 result 不是非空 dict：{str(res)[:200]!r}")
        out[code] = res
        r.say(f"\n## 栏目树 {code}（{len(res)} 个栏目）")
        for k, v in res.items():
            info = (v or {}).get("columnInfo") or {}
            al = info.get("articleList") or []
            r.say(f"  {k:<16} id={_col_id(info)} 名称={info.get('fdColumnName')!r} "
                  f"articleList={len(al)} 篇 extendInfo={'有' if info.get('fdExtendInfo') else '无'}")
    if "explore-jdjs" not in out["explore"]:
        raise SystemExit(f"explore 树里没有 explore-jdjs（景点介绍）：{list(out['explore'])}")
    if "yingwen-jdjs" not in out["yingwen"]:
        raise SystemExit(f"yingwen 树里没有 yingwen-jdjs（英文景点）：{list(out['yingwen'])}")
    return out


def columns_of(tr: dict[str, dict]) -> dict[str, dict]:
    """栏目树里出现的全部栏目 + 前端写死的栏目 -> {栏目 id: {code, name, detail}}。"""
    cols: dict[str, dict] = {}
    for code, res in tr.items():
        for k, v in res.items():
            info = (v or {}).get("columnInfo") or {}
            cid = _col_id(info)
            if not cid:
                continue
            cols.setdefault(cid, dict(code=k, name=info.get("fdColumnName"),
                                      detail=k.startswith(DETAIL_PREFIX), tree=code))
    for cid, name in KNOWN_COLUMNS.items():
        cols.setdefault(cid, dict(code=None, name=name, detail=False, tree=None))
    return cols


def list_column(f: BhFetcher, base: str, cid: str, col: dict, r: Report, *, max_pages: int,
                sample: str | None = None) -> dict:
    rows, total, page = [], None, 1
    truncated = False
    while True:
        js = api(f, base, "/smart-bhpark/modules/busSecurityArticle/list",
                 dict(fdColumnId=cid, pageNo=page, pageSize=PAGE_SIZE), r,
                 sample=sample if page == 1 else None)
        res = js.get("result") or {}
        t = int(res.get("total") or 0)
        if total is not None and t != total:
            raise SystemExit(f"栏目 {col['name']}（{cid}）翻页途中 total 变了：{total} -> {t}（官网在更新，稍后重跑）")
        total = t
        recs = res.get("records") or []
        rows += recs
        if len(rows) >= total or not recs:
            break
        if page >= max_pages:
            truncated = True
            break
        page += 1
    ids = [str(x.get("id")) for x in rows]
    dup = [i for i, c in collections.Counter(ids).items() if c > 1]
    if dup or (not truncated and len(rows) != total):
        raise SystemExit(f"栏目 {col['name']}（{cid}）：取到 {len(rows)} 条，total={total}，重复 id {dup[:10]}")
    return dict(column_id=cid, code=col["code"], name=col["name"], tree=col["tree"],
                total=total, truncated=truncated, records=rows)


def detail(f: BhFetcher, base: str, aid: str, r: Report, sample: str | None = None) -> dict:
    js = api(f, base, f"/smart-bhpark/index/busSecurityIndex/queryById/{aid}", None, r,
             page=f"/#/detail/{aid}", sample=sample)
    res = js.get("result")
    if not isinstance(res, dict) or str(res.get("id")) != aid:
        raise SystemExit(f"详情 {aid} 的 id 对不上：{str(res)[:200]!r}")
    return res


# ---------------------------------------------------------------- 探路
def probe(f: BhFetcher, base: str, r: Report) -> None:
    r.say(f"# 北海公园官网探路 {dt.datetime.now().isoformat(timespec='seconds')}")
    r.say(f"base = {base}")
    probe_robots(f, base, r)
    st, home = f.get(base + "/", sample="home.html")
    m = re.search(r'baseUrl"\]\s*=\s*"([^"]+)', home)
    r.say(f"\n首页 HTTP {st}，{len(home)} 字符；baseUrl 写的是 {m.group(1) if m else '?'!r}")
    f.fetch_token(base, r)
    tr = trees(f, base, r)
    cols = columns_of(tr)
    r.say(f"\n# 每个栏目第 1 页 + 第 1 篇详情（共 {len(cols)} 个栏目）")
    for cid, col in cols.items():
        lst = list_column(f, base, cid, col, r, max_pages=1, sample=f"list_{col['code'] or cid}.json")
        recs = lst["records"]
        r.say(f"\n## {col['code'] or '(写死)'} {col['name']!r} id={cid}：total={lst['total']}"
              f"{'，只取了第 1 页' if lst['truncated'] else ''}")
        for x in recs[:5]:
            r.say(f"    {x.get('id')} {x.get('fdPublishTime') or ''} {x.get('fdTitle')!r}"
                  f"{' [外链 ' + str(x.get('fdExternalLinksUrl')) + ']' if x.get('fdIsExternalLinks') == '2' else ''}")
        if recs:
            d = detail(f, base, str(recs[0]["id"]), r, sample=f"detail_{col['code'] or cid}.json")
            r.say(f"    详情字段：{sorted(d)}")
            r.say(f"    正文 {len(_txt(d.get('fdContent') or ''))} 字，简介 {len(_txt(d.get('fdSynopsis') or ''))} 字，"
                  f"图片 {len([p for p in (d.get('fdPicture') or '').split(',') if p])} 张")


# ---------------------------------------------------------------- 正式抓取
def scrape(f: BhFetcher, base: str, r: Report, out: pathlib.Path) -> None:
    r.say(f"# 北海公园官网正式抓取 {dt.datetime.now().isoformat(timespec='seconds')}")
    r.say(f"base = {base}")
    probe_robots(f, base, r)
    f.fetch_token(base, r)
    tr = trees(f, base, r)
    cols = columns_of(tr)

    lists: dict[str, dict] = {}
    details: dict[str, dict] = {}
    for cid, col in cols.items():
        lst = list_column(f, base, cid, col, r, max_pages=(10 ** 6 if col["detail"] else LIST_PAGE_CAP))
        lists[cid] = lst
        tag = "列表+详情" if col["detail"] else "只取列表"
        r.say(f"  {col['code'] or '(写死)':<16} {str(col['name'])[:24]:<24} total={lst['total']:<5} "
              f"{tag}{'（只取了前 ' + str(LIST_PAGE_CAP) + ' 页）' if lst['truncated'] else ''}")
        if not col["detail"]:
            continue
        if lst["total"] > DETAIL_CAP:
            raise SystemExit(f"内容栏目 {col['code']} 有 {lst['total']} 篇，超过 DETAIL_CAP={DETAIL_CAP} —— "
                             f"多半是新闻类栏目，先停下来看报告")
        for x in lst["records"]:
            aid = str(x["id"])
            if aid not in details:
                details[aid] = detail(f, base, aid, r)

    # 栏目树里 articleList 带出来、但不在任何栏目列表里的文章（栏目 id 缺失时会这样），也取详情
    for code, res in tr.items():
        if not code.startswith(DETAIL_PREFIX):
            continue
        for k, v in res.items():
            for x in ((v or {}).get("columnInfo") or {}).get("articleList") or []:
                aid = str(x.get("id"))
                if aid and aid not in details:
                    r.say(f"  补详情：{k} 的 articleList 里有 {aid}，不在栏目列表中")
                    details[aid] = detail(f, base, aid, r)

    _health(tr, lists, details, r)

    days = sorted({f.manifest[u]["fetched_at"][:10] for u in f.used if u in f.manifest})
    when = days[0] if len(days) == 1 else f"{days[0]} 至 {days[-1]}" if days else "?"
    doc = {
        "_note": "北海公园官网接口的原始返回，字段逐字照录。由 beihai_site_scrape.py --scrape 生成，勿手工编辑；"
                 "解析与取舍在 beihai_build.py。",
        "source": f"{base}{API}",
        "fetched": when,
        "trees": tr,
        "lists": lists,
        "details": details,
    }
    path = out / "beihai_site_data.json"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    r.say(f"\n写出：{path.name}（栏目树 {len(tr)}、栏目列表 {len(lists)}、详情 {len(details)} 篇）")


def _health(tr: dict, lists: dict, details: dict, r: Report) -> None:
    r.say("\n## 体检（只进报告）")
    jd = tr["explore"]["explore-jdjs"]["columnInfo"]
    cid = _col_id(jd)
    recs = lists.get(cid, {}).get("records") if cid else None
    recs = recs if recs is not None else jd.get("articleList") or []
    r.say(f"景点介绍（explore-jdjs）{len(recs)} 篇：")
    for x in recs:
        d = details.get(str(x.get("id"))) or {}
        zh, en = _title_split(x.get("fdTitle") or "")
        ext = " [外链 " + str(x.get("fdExternalLinksUrl")) + "]" if x.get("fdIsExternalLinks") == "2" else ""
        r.say(f"  {x.get('id')} {zh} | {en} | 简介 {len(_txt(x.get('fdSynopsis') or ''))} 字 | "
              f"正文 {len(_txt(d.get('fdContent') or ''))} 字{ext}")
    ye = tr["yingwen"]["yingwen-jdjs"]["columnInfo"]
    ycid = _col_id(ye)
    yrecs = lists.get(ycid, {}).get("records") if ycid else None
    yrecs = yrecs if yrecs is not None else ye.get("articleList") or []
    r.say(f"英文景点（yingwen-jdjs）{len(yrecs)} 篇：")
    for x in yrecs:
        d = details.get(str(x.get("id"))) or {}
        r.say(f"  {x.get('id')} {x.get('fdTitle')!r} | 正文 {len(_txt(d.get('fdContent') or ''))} 字")
    n_ext = sum(1 for d in details.values() if d.get("fdIsExternalLinks") == "2")
    n_empty = sum(1 for d in details.values() if not _txt(d.get("fdContent") or ""))
    r.say(f"详情共 {len(details)} 篇：外链 {n_ext} 篇，正文为空 {n_empty} 篇")


# ---------------------------------------------------------------- 入口
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")        # 中文 Windows 控制台默认 GBK
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--probe", action="store_true", help="探路：栏目树、每栏目第 1 页与 1 篇详情")
    ap.add_argument("--scrape", action="store_true", help="正式抓取，写出 beihai_site_data.json")
    ap.add_argument("--base", default=BASE, help="只在离线自测时改（本机假服务器）")
    ap.add_argument("--out", default=str(HERE), help="beihai_raw/ 与 beihai_samples/ 的上级目录")
    ap.add_argument("--refresh", action="store_true", help="不读本地缓存，全部重新请求")
    args = ap.parse_args()
    if args.probe + args.scrape != 1:
        ap.error("--probe / --scrape 二选一")
    out = pathlib.Path(args.out)
    base = args.base.rstrip("/")
    run, report_name = ((probe, "probe_report.txt") if args.probe else
                        (lambda f_, b_, r_: scrape(f_, b_, r_, out), "scrape_report.txt"))
    f = BhFetcher(out / "beihai_raw", out / "beihai_samples", args.refresh,
                  extra_host=urllib.parse.urlsplit(base).hostname)
    f.check_host(base)
    r = Report()
    code = 0
    try:
        run(f, base, r)
    except SystemExit as e:
        r.say(f"\n[stop] {e.code if isinstance(e.code, str) else '结构对不上，看上面的报告与样本'}")
        code = e.code if isinstance(e.code, int) else 5
    except CertError as e:
        r.say(f"\n[fatal] 证书校验失败：{e}")
        r.say("连上了，是对方证书的问题，不是出口问题。停下来问用户，不要绕。")
        code = 4
    except Unreachable as e:
        r.say(f"\n[fatal] 连不上：{e}")
        if f.n_live:
            r.say("前面的请求是通的，中途被拒 —— 多半是限流。已抓到的在缓存里，隔一阵再跑会接着来；"
                  "连续被拒就停下来问用户。")
        else:
            r.say("境外出口连官网一律超时（2026-10-08 实测），换国内网络再跑。")
        code = 2
    except Blocked as e:
        r.say(f"\n[stop] 碰到人机验证或限流：{e}")
        r.say("不绕。已抓到的留在缓存里，停下来问用户。")
        code = 3
    finally:
        r.say(f"\n本次实际请求 {f.n_live} 次，其余命中本地缓存（{f.raw}）")
        _write(f.samples / report_name, "\n".join(r.lines) + "\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
