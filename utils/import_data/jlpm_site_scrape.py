#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓吉林省博物院官网（www.jlmuseum.net）的展览与藏品，产出提交进仓库的数据模块。

    python3 jlpm_site_scrape.py --probe          # 阶段 1：探路 —— 先弄清有哪些展厅、接口长什么样
    python3 jlpm_site_scrape.py --probe-extra    # 补探：「博物中国」本馆藏品、国家文物局名录查询页
    python3 jlpm_site_scrape.py --probe2         # 第二轮：展览全列与展品清单、镇馆之宝、藏品数据库、「博物中国」
    （--scrape 等探路样本回来、看清接口之后再写，现在写等于猜）

**必须在国内网络下跑。** 2026-09-26 实测：境外出口（美国 IP）连 www.jlmuseum.net 一律超时，
WebFetch 同样被拒 —— 与伪满皇宫同一种情况（AGENTS.md 第 16 条）。证书没问题：crt.sh 上
新网 OV 证书 2026-09-10 签发、2027-03-28 到期，**不需要** --allow-expired-cert。

**⚠ jlmuseum.org 已经不是博物院了。** 那个旧域名被人占用，2024 年起是盗版影视站
（「汤姆影视」），而 Wikidata 上本馆（Q18111051）的官网属性 P856 仍指向它。
本脚本按白名单只访问 ALLOWED_HOSTS，碰到 jlmuseum.org 直接退出。

**已知的站点结构**（来自 Wayback 存档的 app.js，2025-09 那一版；以现场 --probe 为准）：

    Vue 单页应用，哈希路由（#/collect/detail?id=<32 位十六进制>）。页面本身没有内容，
    数据全部由 axios 从 /api 取：baseURL 是 "/api"，get(url, params) 发查询串，
    post(url, data) 发 JSON；响应拦截器只取 body，形如 {success, data|result, message}。
    各页面的组件拆在按需加载的分块里：首页用 <link href=js/chunk-….js rel=prefetch>
    （属性值不带引号）列出，app.js 里另有一张「分块名 → 哈希」表。
    **接口路径写在这些分块里，而存档没有收录它们**，所以只能现场抽。

    路由                          页面          分块（2025-09 版，重新构建后哈希会变）
    /exhibition                   陈列展览      chunk-86a5a7d8
    /exhibition/detail            展览详情      chunk-bae64e4c
    /collect                      院藏精品      chunk-7ecb0319
    /collect/detail               藏品详情      chunk-a7541110（+ 公共分块 chunk-0c0c7beb）
    /collect/collectionDatabase   藏品数据库    chunk-33942d5b（+ chunk-0c0c7beb）

**探路做四件事**，不解析字段、不产出数据模块：
  1. robots.txt（单页应用常把任何路径都回成首页，那样就按「没有 robots」处理，并写进报告）；
  2. 首页 → app.js → 全部分块，逐个存盘；从中抽出所有 $http.get / post 调用：
     接口路径、在哪个分块、调用处前后的原文（参数长什么样就看这里）；
  3. 按 app.js 的路由表把「路由 → 分块 → 接口」对上；
  4. 对陈列展览、院藏精品、藏品数据库、首页、概况、参观这几个页面用到的**只读**接口，
     按调用处能看出来的参数各试一次（第 1 页、每页 10 条），存样本；从列表里取第 1 条的 id
     去试详情接口。

**只读保证**：只调 READ_ROUTES 这几个页面的分块里出现的接口；路径里带写操作字样的
（WRITE_PAT：新增、保存、登录、留言、报名、点赞……）一概不调；POST 只调路径看得出是
查询的（READ_POST_PAT）。其余只列在报告里。

纪律同 wmhg_site_scrape.py（请求、缓存、限速、人机验证即停都直接复用它的 Fetcher）：
· 原始响应存 jlpm_raw/（gitignore，重跑读盘、不再打扰官网）；样本存 jlpm_samples/（入仓库，
  写解析器的机器连不上官网，全靠它）；报告同时写进 jlpm_samples/probe_report.txt。
· 先读 robots.txt；有 Crawl-delay 照办，没有也至少隔 1.5 秒。
· **碰到人机验证、登录墙或限流就停**，不绕。
· 整趟约 60–90 次请求（分块约 40 个 + 接口 20–40 次）。
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
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

import wmhg_site_scrape as W
from wmhg_site_scrape import Blocked, CertError, Report, Unreachable, _abs, _read, _title, _txt, _write

BASE = "https://www.jlmuseum.net"
HERE = pathlib.Path(__file__).resolve().parent

# 只许访问这些主机（外加 --base 指定的主机，离线自测时是 web.archive.org）
MC_BASE = "https://www.museumschina.cn"
NCHA_APP = "http://app.gjzwfw.gov.cn/jmopen/webapp/html5/gjwwjqggcwwmlcx/index.html"
ALLOWED_HOSTS = {"www.jlmuseum.net", "jlmuseum.net", "www.museumschina.cn",
                 "app.gjzwfw.gov.cn", "gl.ncha.gov.cn"}
# 旧域名，现为盗版影视站。任何情况下都不请求
DENIED_HOSTS = ("jlmuseum.org",)

# 「博物中国」上本馆介绍页的 id（2026-09-26 WebSearch：「吉林省博物院博物馆详情 - 博物中国」）。
# 列表筛选用的 museums= 是另一套 14 位编号，要从介绍页上现场找（同伪满皇宫）
MC_MUSEUM_PAGE = "202208231954172117"
MC_NAME = "吉林省博物院"

# 要试接口的页面。其余页面（留言、志愿者、登录、文创……）的接口只列不调
READ_ROUTES = ("/home", "/exhibition", "/exhibition/detail", "/collect", "/collect/detail",
               "/collect/collectionDatabase", "/overview", "/overview/detail", "/visit", "/search")
WRITE_PAT = re.compile(r"add|save|insert|update|edit|delete|remove|submit|login|logout|regist|"
                       r"upload|leave|word|volunteer|apply|sign|vote|praise|like|favou?r|follow|"
                       r"comment|order|pay|wx|user|reserv|book", re.I)
READ_POST_PAT = re.compile(r"list|page|query|search|detail|info|get|tree|type|categor|find|select",
                           re.I)
PAGE_KEY = re.compile(r"^(page|pageNo|pageNum|pageIndex|current|currentPage|curPage|p)$", re.I)
SIZE_KEY = re.compile(r"(size|limit|rows|count)$", re.I)
ID_KEY = re.compile(r"^(id|uuid|\w+Id|\w+_id)$")
TOTAL_KEYS = ("total", "totalCount", "totalNum", "totalRecord", "totalElements", "totalSize", "count")


class JlFetcher(W.Fetcher):
    """wmhg 的 Fetcher 加两样：主机白名单；POST JSON（缓存键带请求体）。"""

    def __init__(self, *a, extra_host: str | None = None, **kw):
        super().__init__(*a, **kw)
        self.allowed = ALLOWED_HOSTS | ({extra_host} if extra_host else set())

    def _check_host(self, url: str) -> None:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if any(host == d or host.endswith("." + d) for d in DENIED_HOSTS):
            sys.exit(f"[fatal] 拒绝访问 {host}：jlmuseum.org 已是盗版影视站，不是博物院（见文件头）")
        if host not in self.allowed:
            sys.exit(f"[fatal] {host} 不在白名单 ALLOWED_HOSTS 里：{url}")

    def get(self, url: str, **kw) -> tuple[int, str]:
        self._check_host(url)
        return super().get(url, **kw)

    def post_json(self, url: str, payload: dict, *, referer: str | None = None,
                  sample: str | None = None) -> tuple[int, str]:
        self._check_host(url)
        rp = self.robots.get(urllib.parse.urlsplit(url).netloc)
        if rp is not None and not rp.can_fetch(W.UA, url):
            return 0, ""
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        key = f"POST {url} {body}"
        self.used.add(key)
        ent = self.manifest.get(key)
        if ent and not self.refresh and (self.raw / ent["file"]).exists():
            status, text = ent["status"], _read(self.raw / ent["file"])
        else:
            status, text = self._post_live(url, body.encode("utf-8"), referer)
            fname = W._fname(url)[:-len(".html")] + "__POST_" + \
                hashlib.sha1(body.encode("utf-8")).hexdigest()[:10] + ".json"
            _write(self.raw / fname, text)
            self.manifest[key] = dict(file=fname, status=status, bytes=len(text.encode("utf-8")),
                                      fetched_at=dt.datetime.now().isoformat(timespec="seconds"))
            self.mf_path.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=1), "utf-8")
        if status in W.BLOCK_STATUS or (len(text) < 5000 and W.BLOCK_PAT.search(text)):
            raise Blocked(f"POST {url} -> HTTP {status}，{len(text)} 字节：{_txt(text)[:200]!r}")
        if sample:
            _write(self.samples / sample, text)
        return status, text

    def _post_live(self, url: str, body: bytes, referer: str | None) -> tuple[int, str]:
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": W.UA, "Content-Type": "application/json;charset=UTF-8",
                   "Accept": "application/json, text/plain, */*"}
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ctx) as r:
                status, raw, ctype = r.status, r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            status, raw, ctype = e.code, e.read(), e.headers.get("Content-Type", "")
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
        return status, raw.decode(m.group(1) if m else "utf-8", "replace")


# ---------------------------------------------------------------- 小工具
def _is_html(text: str) -> bool:
    return text.lstrip()[:15].lower().startswith(("<!doctype", "<html"))


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:80] or "root"


def _json(text: str):
    try:
        return json.loads(text.lstrip("﻿"))
    except ValueError:
        return None


def _find_list(obj) -> tuple[str | None, list | None]:
    """广度优先找第一个「元素是 dict」的非空列表 -> (路径, 列表)。"""
    q = collections.deque([("", obj)])
    while q:
        p, o = q.popleft()
        if isinstance(o, list) and o and all(isinstance(x, dict) for x in o[:3]):
            return p, o
        if isinstance(o, dict):
            q.extend((f"{p}.{k}" if p else k, v) for k, v in o.items())
        elif isinstance(o, list):
            q.extend((f"{p}[{i}]", v) for i, v in enumerate(o[:3]))
    return None, None


def _find_total(obj, depth: int = 0) -> list[str]:
    out = []
    if isinstance(obj, dict) and depth <= 3:
        for k, v in obj.items():
            if k in TOTAL_KEYS and isinstance(v, (int, str)) and str(v).isdigit():
                out.append(f"{k}={v}")
            out += _find_total(v, depth + 1)
    return out


def _item_id(item: dict):
    for k in ("id", "uuid"):
        if item.get(k) not in (None, ""):
            return item[k]
    for k, v in item.items():
        if ID_KEY.match(k) and isinstance(v, (str, int)) and v != "":
            return v
    return None


def _preview(v, n: int = 70) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    flat = _txt(s) if "<" in s else s
    return f"{flat[:n]!r}" + (f"…（共 {len(s)} 字符）" if len(s) > n else "")


# ---------------------------------------------------------------- robots
def probe_robots(f: JlFetcher, base: str, r: Report, paths: tuple[str, ...]) -> None:
    host = urllib.parse.urlsplit(base).netloc
    r.say(f"\n## robots.txt（{host}）")
    st, text = f.get(base + "/robots.txt", sample=f"robots_{_slug(host)}.txt")
    rp = urllib.robotparser.RobotFileParser()
    if st == 200 and _is_html(text):
        # 单页应用把任何路径都回成首页：等于没有 robots，按全部允许处理
        rp.parse([])
        r.say(f"HTTP {st}，但返回的是 HTML（{_title(text)!r}）—— 单页应用的兜底页，按「没有 robots」处理")
    else:
        rp.parse(text.splitlines() if st == 200 else [])
        r.say(f"HTTP {st}，Crawl-delay={rp.crawl_delay(W.UA)}")
        if st == 200:
            for line in text.splitlines()[:40]:
                r.say("    " + line)
    f.robots[host] = rp
    f.delay = max(f.delay, float(rp.crawl_delay(W.UA) or 0))
    r.say(f"实际间隔 {f.delay}s")
    for p in paths:
        r.say(f"  {p}: {'允许' if rp.can_fetch(W.UA, base + p) else '⚠ 禁止'}")


# ---------------------------------------------------------------- 阶段 1：探路
JS_LINK = re.compile(r'(?:src|href)\s*=\s*["\']?([^"\'\s>]+\.js)\b', re.I)
CHUNK_MAP = re.compile(r'\w\.p\+"js/"\+\((\{[^{}]*\})\[\w\]\|\|\w\)\+"\."\+(\{[^{}]*\})\[\w\]\+"\.js"')
ROUTE = re.compile(r'path:"([^"]*)"[^{}]*?component:function\(\)\{return ([^{}]*?)\}')
# $http.get("/x", {...}) / this.$http.post("/x", ...) / 其他别名的 .get("/x" …)
CALL = re.compile(r'(?:\$http|\b\w{1,3})\.(get|post|base|request)\(\s*(["\'`])(/[^"\'`]{1,120})\2(\s*\+)?')
URL_OBJ = re.compile(r'url:\s*(["\'`])(/[A-Za-z][^"\'`]{1,120})\1')


def _js_obj(lit: str) -> dict[str, str]:
    """JS 对象字面量（不含嵌套）-> {键: 值原文}。"""
    out = {}
    for m in re.finditer(r'(["\']?)([\w$]+)\1\s*:\s*("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^,]+)', lit):
        out[m.group(2)] = m.group(3).strip()
    return out


def _params(raw: dict[str, str]) -> tuple[dict, list[str], list[str]]:
    """调用处的参数原文 -> (能用的参数, 需要 id 的键, 丢掉的键)。字面量照用；
    表达式按键名猜：页码 1、每页 10、id 类留给详情；其余丢掉（报告里写明）。"""
    use, need_id, drop = {}, [], []
    for k, v in raw.items():
        if re.fullmatch(r'"[^"]*"|\'[^\']*\'', v):
            use[k] = v[1:-1]
        elif re.fullmatch(r"-?\d+", v):
            use[k] = int(v)
        elif v in ("!0", "!1", "true", "false"):
            use[k] = v in ("!0", "true")
        elif PAGE_KEY.match(k):
            use[k] = 1
        elif SIZE_KEY.search(k):
            use[k] = 10
        elif ID_KEY.match(k):
            need_id.append(k)
        else:
            drop.append(f"{k}={v[:30]}")
    return use, need_id, drop


def discover(f: JlFetcher, base: str, r: Report) -> tuple[dict, dict]:
    """-> (路由 -> 分块列表, 分块 -> 接口调用列表)"""
    r.say("\n## 首页与脚本")
    st, index = f.get(base + "/", sample="index.html")
    r.say(f"HTTP {st}，{len(index)} 字节，<title> {_title(index)!r}")
    links = list(dict.fromkeys(JS_LINK.findall(index)))
    app = [u for u in links if re.search(r"(^|/)app\.[0-9a-f]+\.js$", u)]
    r.say(f"页面引用的 js {len(links)} 个，其中 app：{app}")
    if not app:
        raise SystemExit(5)
    st, app_js = f.get(_abs(base, app[0].lstrip("./")), sample="app.js")
    r.say(f"app.js：HTTP {st}，{len(app_js)} 字节")
    base_url = re.findall(r'baseURL\s*:\s*["\']([^"\']*)["\']', app_js)
    r.say(f"axios baseURL：{base_url}")
    api_prefix = base_url[0] if base_url else "/api"

    chunks: dict[str, str] = {}             # 分块名 -> 文件路径 js/<名>.<哈希>.js
    m = CHUNK_MAP.search(app_js)
    if m:
        names = dict(re.findall(r'"?([\w-]+)"?\s*:\s*"([\w-]+)"', m.group(1)))
        for name, h in re.findall(r'"?([\w-]+)"?\s*:\s*"([0-9a-f]+)"', m.group(2)):
            chunks[name] = f"js/{names.get(name, name)}.{h}.js"
    for u in links:
        mm = re.search(r"js/([\w-]+)\.[0-9a-f]+\.js$", u)
        if mm and mm.group(1) not in ("app", "chunk-vendors"):
            chunks.setdefault(mm.group(1), u.lstrip("./"))
    r.say(f"分块 {len(chunks)} 个（app.js 分块表 {'有' if m else '⚠ 没找到'}；首页 prefetch 链接补充）")

    routes: dict[str, list[str]] = {}
    for path, body in ROUTE.findall(app_js):
        routes.setdefault(path, list(dict.fromkeys(re.findall(r'\w\.e\("([^"]+)"\)', body))))
    r.say(f"路由 {len(routes)} 条：")
    for p, cs in routes.items():
        r.say(f"    {p:<32} {cs}")
    if not routes:
        r.say("⚠ app.js 里没认出路由表 —— 构建方式变了，看样本 app.js")

    calls: dict[str, list[dict]] = {"app": _calls(app_js, set(routes))}
    labels: dict[str, list[dict]] = {}
    want = {c for p in READ_ROUTES for c in routes.get(p, [])}
    bad: dict[int, list[str]] = collections.defaultdict(list)
    for name, rel in chunks.items():
        sample = f"js_{name}.js" if name in want else None
        st, code = f.get(_abs(base, rel), sample=sample)
        if st != 200:
            bad[st].append(name)
            if sample:
                (f.samples / sample).unlink(missing_ok=True)
            continue
        calls[name] = _calls(code, set(routes))
        if name in want:
            labels[name] = _labels_in(code, name, r)
    for st, names in bad.items():
        r.say(f"  ⚠ 分块取不到（HTTP {st}）{len(names)} 个：{names}")
    r.say(f"\n## 接口调用（axios 前缀 {api_prefix}）")
    for name, cs in calls.items():
        used_by = [p for p, c in routes.items() if name in c] or (["（全站）"] if name == "app" else [])
        for c in cs:
            r.say(f"  [{name}] {used_by} {c['method'].upper()} {c['path']}{' +拼接' if c['concat'] else ''}")
            r.say(f"        上下文：{c['ctx']}")
    return routes, calls, dict(prefix=api_prefix, labels=labels)


def _calls(code: str, route_paths: set[str]) -> list[dict]:
    """分块源码 -> 接口调用。route_paths 用来剔除菜单里的 {name:"首页",url:"/home"} ——
    那是前端路由，不是接口；只按「与某条路由同名」剔，/collect/list 这类真接口不受影响。"""
    out, seen = [], set()
    for m in CALL.finditer(code):
        path = m.group(3)
        if re.search(r"\.(js|css|png|jpe?g|gif|svg|ico|html?)$", path) or path.startswith("//"):
            continue
        key = (m.group(1), path)
        if key in seen:
            continue
        seen.add(key)
        after = code[m.end():m.end() + 400]
        lit = re.match(r"\s*,\s*(\{[^{}]*\})", after)
        out.append(dict(method=m.group(1), path=path, concat=bool(m.group(4)),
                        raw=_js_obj(lit.group(1)[1:-1]) if lit else {},
                        ctx=code[max(0, m.start() - 80):m.end() + 220].replace("\n", " ")))
    for m in URL_OBJ.finditer(code):
        near = code[max(0, m.start() - 200):m.end() + 200]
        meth = re.search(r'method:\s*["\'](\w+)["\']', near)
        key = ((meth.group(1).lower() if meth else "get"), m.group(2))
        if key not in seen and m.group(2).split("?")[0] not in route_paths:
            seen.add(key)
            out.append(dict(method=key[0], path=m.group(2), concat=False, raw={},
                            ctx=near.replace("\n", " ")))
    return out


def _labels_in(code: str, name: str, r: Report) -> list[dict]:
    """分块里带中文的小对象（标签页、类目、筛选项），常常就是展览/藏品分类的取值表，
    如 {name:"基本陈列",type:"1"}。-> 各对象解析后的 {键: 值原文}"""
    objs = list(dict.fromkeys(re.findall(r"\{[^{}]{0,160}[一-鿿][^{}]{0,160}\}", code)))
    if objs:
        r.say(f"  [{name}] 带中文的小对象 {len(objs)} 个（前 30）：")
        for o in objs[:30]:
            r.say(f"      {o[:240]}")
    return [_js_obj(o[1:-1]) for o in objs]


def _tab_values(labels: list[dict], key: str) -> list[tuple[str, str]]:
    """调用处丢掉的参数 key，若同一分块的中文小对象里有同名键且是字面量，
    就拿这些取值各试一次。-> [(取值, 对应的中文标签)]"""
    out = []
    for o in labels:
        v = o.get(key, "")
        if re.fullmatch(r'"[^"]*"|\'[^\']*\'|-?\d+', v):
            tag = next((x[1:-1] for x in o.values() if re.search(r"[一-鿿]", x)), "")
            out.append((v.strip("\"'"), tag))
    return list(dict.fromkeys(out))


def try_calls(f: JlFetcher, base: str, r: Report, routes: dict, calls: dict, meta: dict) -> None:
    api = base + meta["prefix"]
    r.say(f"\n## 试调只读接口（{api}）")
    # 路由 -> 该页列表里取到的 id。按路由分开记：/collect 的列表可能是类目，
    # 拿类目 id 去查藏品详情没有意义，所以详情接口对同一家族的每个列表页各试一个
    ids: dict[str, list] = collections.defaultdict(list)
    detail_todo: list[tuple[str, dict]] = []
    done: set[tuple] = set()

    def call(c: dict, params: dict, tag: str, ref: str) -> None:
        path = c["path"]
        url = api + path
        k = (c["method"], path, json.dumps(params, sort_keys=True))
        if k in done:
            return
        done.add(k)
        sample = f"api_{_slug(path)}{tag}.json"
        if c["method"] == "post":
            st, text = f.post_json(url, params, referer=ref, sample=sample)
        else:
            q = urllib.parse.urlencode(params)
            st, text = f.get(url + ("?" + q if q else ""), ajax=True, referer=ref, sample=sample)
        r.say(f"  {c['method'].upper()} {path} {params}: HTTP {st}，{len(text)} 字节")
        if st == 0:
            r.say("      robots 不许，没有发请求")
            return
        if _is_html(text):
            r.say(f"      ⚠ 返回的是 HTML（{_title(text)!r}）—— 多半是单页应用兜底，接口路径或前缀不对")
            return
        js = _json(text)
        if js is None:
            r.say(f"      ⚠ 不是 JSON：{text[:200]!r}")
            return
        if isinstance(js, dict):
            r.say(f"      顶层键 {list(js)[:12]}；success={js.get('success')!r} "
                  f"code={js.get('code')!r} message={str(js.get('message') or js.get('msg') or '')[:80]!r}")
            if re.search(r"登录|login|token|权限|unauthori", json.dumps(js, ensure_ascii=False)[:500], re.I):
                r.say("      ⚠ 响应提到登录/权限 —— 若确是登录墙，停下来问用户，不绕")
        lp, lst = _find_list(js)
        total = _find_total(js)
        if lst:
            r.say(f"      列表在 {lp}，本页 {len(lst)} 条；总数字段 {total or '无'}")
            first = lst[0]
            r.say(f"      第 1 条的字段（{len(first)} 个）：")
            for kk, vv in list(first.items())[:40]:
                r.say(f"          {kk}: {_preview(vv)}")
            names = [str(x.get("title") or x.get("name") or x.get("exhibitionName") or
                         x.get("collectName") or "")[:30] for x in lst]
            r.say(f"      本页标题：{names}")
            src = ref.split("#", 1)[1] if "#" in ref else ""
            for x in lst[:3]:
                if (i := _item_id(x)) is not None:
                    ids[src].append(i)
            if total and any(int(t.split("=")[1]) > len(lst) for t in total):
                big = {kk: (100 if SIZE_KEY.search(kk) else vv) for kk, vv in params.items()}
                if big != params:
                    call(c, big, "_size100", ref)
        elif isinstance(js, dict):
            data = js.get("data", js.get("result"))
            r.say(f"      没有列表；data/result：{_preview(data, 300)}")

    for route in READ_ROUTES:
        ref = f"{base}/#{route}"
        for chunk in routes.get(route, []):
            for c in calls.get(chunk, []):
                if WRITE_PAT.search(c["path"]):
                    continue
                if c["method"] == "post" and not READ_POST_PAT.search(c["path"]):
                    r.say(f"  未试：POST {c['path']}（看不出是只读查询）")
                    continue
                use, need_id, drop = _params(c["raw"])
                if drop:
                    r.say(f"  {c['path']}：丢掉的参数 {drop}")
                if need_id or c["concat"] or route.endswith("/detail"):
                    detail_todo.append((route, dict(c, use=use, need_id=need_id)))
                    continue
                call(c, use, "", ref)
                # 丢掉的参数若在本分块的标签页取值表里（如 type: 基本陈列 1 / 临时展览 2），逐个取值再试
                for k in (d.split("=")[0] for d in drop):
                    for v, tag in _tab_values(meta["labels"].get(chunk, []), k):
                        r.say(f"  —— {k}={v}（{tag}）")
                        call(c, dict(use, **{k: v}), f"_{k}{_slug(v)}", ref)
    for c in calls.get("app", []):
        if not WRITE_PAT.search(c["path"]) and c["method"] == "get":
            call(c, _params(c["raw"])[0], "", f"{base}/#/home")

    r.say("\n## 试调详情接口（用同一家族各列表页的第 1 个 id）")
    for route, c in detail_todo:
        fam = route.split("/")[1]
        cands = {src: v[0] for src, v in ids.items() if src.split("/")[1:2] == [fam] and v}
        for src, i in cands.items():
            r.say(f"  {c['path']}（{route}）用 {src} 列表的 id {i!r}：")
            if c["concat"]:
                call(dict(c, path=c["path"] + str(i)), c["use"], "", f"{base}/#{route}")
            else:
                p = dict(c["use"], **{k: i for k in (c["need_id"] or ["id"])})
                call(c, p, f"_{_slug(str(i))[:12]}", f"{base}/#{route}")
        if not cands:
            r.say(f"  未试：{c['method'].upper()} {c['path']}（{route}）—— 家族 {fam} 的列表没取到 id")


def probe(f: JlFetcher, base: str, r: Report) -> None:
    r.say(f"# 吉林省博物院官网探路 {dt.datetime.now().isoformat(timespec='seconds')}")
    r.say(f"base = {base}")
    probe_robots(f, base, r, ("/", "/api/", "/js/"))
    routes, calls, meta = discover(f, base, r)
    try_calls(f, base, r, routes, calls, meta)


# ---------------------------------------------------------------- 补探（--probe-extra）
def probe_mc(f: JlFetcher, r: Report) -> None:
    """「博物中国」上的本馆藏品：件数、分级筛选、详情页带哪些字段。结构同伪满皇宫那次。"""
    r.say("\n# 博物中国 museumschina.cn（国家文物局数据中心）")
    probe_robots(f, MC_BASE, r, ("/Collection", "/collection/details", "/museums/details"))
    st, page = f.get(f"{MC_BASE}/museums/details?id={MC_MUSEUM_PAGE}", sample="mc_museum.html")
    r.say(f"本馆介绍页：HTTP {st}，<title> {_title(page)!r}")
    r.say(f"  摘录：{W._excerpt(page, '藏品', 300)}")
    # 介绍页上唯一的 museums= 是介绍页自己的 id（18 位），**不是**列表筛选用的 14 位编号 ——
    # 2026-09-26 第一轮拿它去筛，五个级别全是 0 件。只认 14 位的
    mids = collections.Counter(m for m in re.findall(r"museums=(\d+)", page) if len(m) == 14)
    r.say(f"  页面上出现的 14 位 museums= 取值：{mids.most_common(5)}")
    mid = mids.most_common(1)[0][0] if mids else None
    if not mid:
        # 退路：拿官网镇馆之宝的名称去搜（名录里的写法），结果里「收藏单位」链接的 museums= 就是本馆编号
        for i, kw in enumerate(("文姬归汉图", "洞庭春色", "丙午神钩", "契丹文八角铜镜", "吉林省博物院"), 1):
            st, pg = f.get(f"{MC_BASE}/Collection?" + urllib.parse.urlencode({"searchkey": kw}),
                           sample=f"mc_search_{i}.html")
            units = collections.Counter((re.search(r"museums=(\d+)", h).group(1), t)
                                        for h, t in W._links(pg) if "museums=" in h and t)
            hit = [m for (m, t) in units if MC_NAME in t]
            r.say(f"  搜「{kw}」：HTTP {st}，{'本馆编号 ' + hit[0] if hit else '结果里没有本馆'}；"
                  f"结果里的收藏单位 {units.most_common(5)}")
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
    units = collections.Counter(_txt(u) for u in re.findall(
        r'class="ex_info_address">\s*<a[^>]*>(.*?)</a>', pg, re.S))
    r.say(f"museums={mid}：HTTP {st}，本页 {len(det)} 件，翻页最大页码 {maxp}（每页 20）；"
          f"收藏单位 {units.most_common(3)}")
    levels = {t: re.search(r"level=(\d+)", h).group(1) for h, t in W._links(pg)
              if "level=" in h and t in ("一级", "二级", "三级", "一般", "未定级")}
    r.say(f"  级别筛选码：{levels}")
    for name, code in levels.items():
        st, _, d, mp = lst(dict(level=code, pages=1, size=20))
        r.say(f"    {name}：HTTP {st}，第 1 页 {len(d)} 件，翻页最大页码 {mp}")
    for i, href in enumerate(det[:2], 1):
        st, dp = f.get(MC_BASE + href, sample=f"mc_detail_{i}.html")
        r.say(f"  详情 {href}：HTTP {st}，<title> {_title(dp)!r}")
        r.say(f"      摘录：{W._excerpt(dp, '收藏单位', 400)}")


def probe_ncha(f: JlFetcher, r: Report) -> None:
    """国家文物局「全国馆藏文物名录」查询页（Wikidata 那 11947 条的出处）。
    只看它的页面与脚本里有哪些接口、要不要登录，**不调查询接口** —— 政务平台，先看清再说。"""
    r.say(f"\n# 全国馆藏文物名录查询页 {NCHA_APP}")
    st, page = f.get(NCHA_APP, sample="ncha_index.html")
    r.say(f"HTTP {st}，{len(page)} 字节，<title> {_title(page)!r}")
    js = list(dict.fromkeys(JS_LINK.findall(page)))
    r.say(f"引用的 js：{js[:10]}")
    found: collections.Counter = collections.Counter()
    for src in js[:6]:
        u = urllib.parse.urljoin(NCHA_APP, src)
        if urllib.parse.urlsplit(u).hostname not in ALLOWED_HOSTS:
            r.say(f"  跳过站外脚本 {u}")
            continue
        _, code = f.get(u, sample=f"ncha_{_slug(src)[-60:]}.js")
        for m in re.finditer(r'["\'](https?://[\w.:-]+/[\w/.-]*|/[\w-]+(?:/[\w.-]+){1,6})["\']', code):
            if not re.search(r"\.(css|png|jpe?g|gif|svg|js)$", m.group(1)):
                found[m.group(1)] += 1
        for kw in ("级别", "等级", "文物名称", "收藏单位", "登录", "token", "sign"):
            if kw in code:
                found[f"（脚本含「{kw}」）"] += 1
    r.say(f"脚本里出现的路径与字样（前 40）：")
    for k, n in found.most_common(40):
        r.say(f"    {n:>3}  {k}")


def probe_extra(f: JlFetcher, base: str, r: Report) -> None:
    r.say(f"# 吉林省博物院补探 {dt.datetime.now().isoformat(timespec='seconds')}")
    for name, fn in (("「博物中国」", probe_mc), ("名录查询页", probe_ncha)):
        try:
            fn(f, r)
        except (Unreachable, CertError) as e:
            # 两处互不依赖，一处取不到不妨碍另一处
            r.say(f"⚠ {name}取不到：{e}")


# ---------------------------------------------------------------- 第二轮探路（--probe2）
# 第一轮（2026-09-26）摸清的接口，全在 /api 下，GET，响应 {success, message, data, total}：
#   /exhibition/list      page, size, type（必填：1 基本陈列 2 临时展览 3 虚拟展厅 4 H5 展览）
#                         每条带 exhibitionFlag（前端：2 即将展出、1 展出中、0 已结束）、place、exhibitionTime
#   /exhibition/detail    id
#   /exhibition/collect   id    —— 该展的展品清单（展览详情页「展品」标签）
#   /collect/list         page, size, isTreasure=1 —— 镇馆之宝，第一轮 17 件，带级别、尺寸、介绍、exhibitionList
#   /collect/detail       id（镇馆之宝的数字 id）
#   /collectdb/list.do    page, size, s_yearType, s_type, s_name —— 藏品数据库，第一轮 total=17709，
#                         列表每条只有 id（32 位十六进制）、name、typeName、yearTypeName、mainImgUrl、threedUrl
#   /collectdb/detail     id（32 位十六进制）；前端显示 content、levelName、size、texture 等
# 第一轮的详情都没试成：拿去试的 id 是字典条目的（282），不是展品的。这一轮全部按接口定点请求。
EXHIB_TYPES = (("1", "基本陈列"), ("2", "临时展览"), ("3", "虚拟展厅"))
FLAG = {"0": "已结束", "1": "展出中", "2": "即将展出"}
# 名录里的镇馆之宝（jlpm_wikidata_catalog.json 的写法），用来试藏品数据库的按名搜索
DB_PROBE_NAMES = ("文姬归汉", "洞庭春色", "丙午神钩", "百花图", "契丹文八角铜镜", "松风清节")


def _api(f: JlFetcher, base: str, path: str, params: dict, r: Report, sample: str | None = None,
         ref: str = "/#/home"):
    """GET /api<path>，-> 解析后的 JSON（success 为假时照样返回，由调用方报告）或 None。"""
    q = urllib.parse.urlencode(params)
    st, text = f.get(f"{base}/api{path}" + ("?" + q if q else ""), ajax=True,
                     referer=base + ref, sample=sample)
    js = _json(text) if st == 200 and not _is_html(text) else None
    if js is None:
        r.say(f"  ⚠ {path} {params}: HTTP {st}，不是 JSON：{text[:160]!r}")
    elif not js.get("success"):
        r.say(f"  ⚠ {path} {params}: success=False，message={js.get('message')!r}")
    return js


def _fields(item: dict, n: int = 50) -> list[str]:
    return [f"{k}={_preview(v, 40)}" for k, v in list(item.items())[:n]]


def probe2(f: JlFetcher, base: str, r: Report) -> None:
    r.say(f"# 吉林省博物院第二轮探路 {dt.datetime.now().isoformat(timespec='seconds')}")
    r.say(f"base = {base}")
    probe_robots(f, base, r, ("/api/",))

    # ---- 展览：三类全列，展出中/即将展出的与全部基本陈列再取详情与展品清单
    r.say("\n# 展览")
    exhibs: list[dict] = []
    for t, tname in EXHIB_TYPES:
        js = _api(f, base, "/exhibition/list", dict(page=1, size=100, type=t), r,
                  sample=f"p2_exhibition_list_type{t}.json", ref=f"/#/exhibition?type={t}")
        data = (js or {}).get("data") or []
        r.say(f"\n## {tname}（type={t}）：{len(data)} 个，total={(js or {}).get('total')}")
        if js and len(data) < int(js.get("total") or 0):
            r.say(f"  ⚠ 一页没取完（{len(data)}/{js.get('total')}），正式抓取要翻页")
        for e in data:
            flag = FLAG.get(str(e.get("exhibitionFlag")), f"flag={e.get('exhibitionFlag')!r}")
            r.say(f"  {e.get('id'):>5}  [{flag}]  {e.get('name')}  | 地点：{e.get('place')}"
                  f"  | 时间：{e.get('exhibitionTime')}")
            exhibs.append(dict(e, _type=t))
    if exhibs:
        r.say(f"\n展览条目的字段：{list(exhibs[0])}")
    pick = [e for e in exhibs if e["_type"] == "1" or str(e.get("exhibitionFlag")) in ("1", "2")]
    r.say(f"\n## 取详情与展品清单：基本陈列全部 + 其余展出中/即将展出的，共 {len(pick)} 个")
    for e in pick:
        i = e.get("id")
        js = _api(f, base, "/exhibition/detail", dict(id=i), r, sample=f"p2_exhibition_detail_{i}.json",
                  ref=f"/#/exhibition/detail?id={i}")
        d = (js or {}).get("data") or {}
        body = _txt(str(d.get("content") or ""))
        r.say(f"\n  {i} {e.get('name')}")
        r.say(f"      详情字段 {list(d)[:30]}")
        r.say(f"      地点：{d.get('place')!r}；时间：{d.get('exhibitionTime')!r}；介绍 {len(body)} 字："
              f"{body[:160]!r}")
        # 介绍里点到展厅、楼层、单元的句子，另列出来 —— 展厅清单主要靠它和 place
        hits = list(dict.fromkeys(re.findall(r"[^。；！？]{0,40}(?:展厅|展区|楼|单元|部分)[^。；！？]{0,40}", body)))
        for h in hits[:8]:
            r.say(f"      · {h.strip()}")
        js = _api(f, base, "/exhibition/collect", dict(id=i), r, sample=f"p2_exhibition_collect_{i}.json",
                  ref=f"/#/exhibition/detail?id={i}")
        items = (js or {}).get("data") or []
        r.say(f"      展品清单 {len(items) if isinstance(items, list) else type(items).__name__} 件"
              f"（total={(js or {}).get('total')}）")
        if isinstance(items, list) and items:
            r.say(f"      展品字段 {_fields(items[0])}")
            r.say(f"      展品名 {[str(x.get('name'))[:24] for x in items[:40]]}")

    # ---- 镇馆之宝
    r.say("\n# 镇馆之宝 /collect/list?isTreasure=1")
    js = _api(f, base, "/collect/list", dict(page=1, size=100, isTreasure=1), r,
              sample="p2_collect_list_treasure.json", ref="/#/collect")
    tre = (js or {}).get("data") or []
    r.say(f"{len(tre)} 件，total={(js or {}).get('total')}")
    for x in tre:
        r.say(f"  {x.get('id'):>4}  {x.get('name')}  | {x.get('levelName')} · {x.get('yearTypeName')} · "
              f"{x.get('typeName')} · {x.get('size')}  | 曾经展出 {len(x.get('exhibitionList') or [])} 个"
              f"  | 介绍 {len(_txt(str(x.get('content') or '')))} 字")
    for x in tre[:2]:
        i = x.get("id")
        js = _api(f, base, "/collect/detail", dict(id=i), r, sample=f"p2_collect_detail_{i}.json",
                  ref=f"/#/collect/detail?id={i}")
        d = (js or {}).get("data") or {}
        r.say(f"  详情 {i}：字段 {list(d)}")
        for ex in (d.get("exhibitionList") or [])[:5]:
            r.say(f"      曾经展出：{ {k: ex.get(k) for k in ('id', 'name', 'place', 'exhibitionFlag')} }")

    # ---- 藏品数据库
    r.say("\n# 藏品数据库 /collectdb/list.do")
    q = dict(page=1, size=100, s_yearType="", s_type="", s_name="")
    js = _api(f, base, "/collectdb/list.do", q, r, sample="p2_collectdb_list_size100.json", ref="/#/collect")
    lst = (js or {}).get("data") or []
    r.say(f"size=100：本页 {len(lst)} 条，total={(js or {}).get('total')}"
          f"{'（服务器限了每页条数）' if js and len(lst) < 100 else ''}")
    ids = [x.get("id") for x in lst[:2]]
    for kw in DB_PROBE_NAMES:
        js = _api(f, base, "/collectdb/list.do", dict(q, size=20, s_name=kw), r, ref="/#/collect")
        got = (js or {}).get("data") or []
        r.say(f"  按名搜「{kw}」：{len(got)} 条 {[(x.get('name'), x.get('yearTypeName')) for x in got[:5]]}")
        if got:
            ids.append(got[0].get("id"))
    for i in list(dict.fromkeys(ids))[:6]:
        js = _api(f, base, "/collectdb/detail", dict(id=i), r, sample=f"p2_collectdb_detail_{i}.json",
                  ref=f"/#/collect/collectionDatabase?id={i}")
        d = (js or {}).get("data") or {}
        r.say(f"  详情 {i} {d.get('name')!r}：{d.get('levelName')!r} · {d.get('yearTypeName')!r} · "
              f"{d.get('typeName')!r} · 尺寸 {d.get('size')!r} · 质地 {d.get('texture')!r} · "
              f"介绍 {len(_txt(str(d.get('content') or '')))} 字 · 图 {len(d.get('imgList') or [])} 张")
        r.say(f"      字段 {_fields(d)}")

    # ---- 博物中国：第一轮拿错了筛选编号，这轮按名称搜
    try:
        probe_mc(f, r)
    except (Unreachable, CertError) as e:
        r.say(f"⚠ 「博物中国」取不到：{e}")


# ---------------------------------------------------------------- 入口
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")        # 中文 Windows 控制台默认 GBK
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--probe", action="store_true", help="阶段 1：探路，只存原始响应与样本")
    ap.add_argument("--probe-extra", action="store_true",
                    help="补探：「博物中国」本馆藏品、国家文物局名录查询页")
    ap.add_argument("--probe2", action="store_true",
                    help="第二轮探路：展览全列（含展品清单）、镇馆之宝、藏品数据库的规模与详情、「博物中国」")
    ap.add_argument("--base", default=BASE,
                    help="只在离线自测时改，例如 Wayback 存档："
                         "http://web.archive.org/web/20250912052641id_/https://jlmuseum.net")
    ap.add_argument("--out", default=str(HERE), help="jlpm_raw/ 与 jlpm_samples/ 的上级目录")
    ap.add_argument("--refresh", action="store_true", help="不读本地缓存，全部重新请求")
    ap.add_argument("--allow-expired-cert", action="store_true",
                    help="「博物中国」证书 2026-04-21 已过期（伪满皇宫那次用户同意过这个域名）："
                         "只对 wmhg_site_scrape.EXPIRED_CERT_HOSTS 登记的域名跳过有效期，"
                         "证书链与域名照常校验。官网 jlmuseum.net 的证书有效，用不着")
    args = ap.parse_args()
    if args.probe + args.probe_extra + args.probe2 != 1:
        ap.error("--probe / --probe-extra / --probe2 三选一")
    out = pathlib.Path(args.out)
    base = args.base.rstrip("/")
    run, report_name = ((probe, "probe_report.txt") if args.probe
                        else (probe_extra, "probe_extra_report.txt") if args.probe_extra
                        else (probe2, "probe2_report.txt"))

    f = JlFetcher(out / "jlpm_raw", out / "jlpm_samples", args.refresh,
                  allow_expired=args.allow_expired_cert,
                  extra_host=urllib.parse.urlsplit(base).hostname)
    f._check_host(base)
    r = Report()
    if args.allow_expired_cert:
        r.say(f"⚠ 本次对 {'、'.join(W.EXPIRED_CERT_HOSTS)} 跳过了证书有效期检查，证书链与域名照常校验")
    code = 0
    try:
        run(f, base, r)
    except SystemExit as e:
        # 结构对不上（首页里找不到 app.js 等）或白名单拒绝。报告照样写出来
        r.say(f"\n[stop] {e.code if isinstance(e.code, str) else '结构对不上，看上面的报告与样本'}")
        code = e.code if isinstance(e.code, int) else 5
    except CertError as e:
        r.say(f"\n[fatal] 证书校验失败：{e}")
        r.say("连上了，是对方证书的问题，不是出口问题。官网证书按 crt.sh 应当有效，停下来问用户，不要绕。")
        code = 4
    except Unreachable as e:
        r.say(f"\n[fatal] 连不上：{e}")
        if f.n_live or len(f.manifest) > 1:
            r.say("前面的请求是通的，中途被拒 —— 多半是限流。已抓到的在缓存里，隔一阵再跑会从断点接着来；"
                  "连续被拒就停下来问用户。")
        else:
            r.say("境外出口连官网一律超时（2026-09-26 实测），换国内网络再跑。")
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
