#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把一个馆院区范围内的 OpenStreetMap 几何取回来，存成 <馆>_osm_data.json（入仓库）。

    python3 tour_osm_fetch.py --museum wmhg            # 已有文件就只体检、打印统计
    python3 tour_osm_fetch.py --museum wmhg --refresh  # 重新取

手机导览页的地图是照这份几何画的，「在不在景区范围内」也按其中的院区边界判定，
所以原始响应必须落进仓库：Overpass 的数据会变，下次取回来的未必是同一份。

范围、院区边界取自 <馆>_tour_data.py，路线各站引用的 OSM 要素取自 <馆>_route_data.py。
两处引用的要素**必须都在取回的结果里**，且路线数据里记的坐标要与 OSM 现在的坐标对得上
（差 5 米以上就报错）—— 路线数据是 2026-10-09 手抄的编号与坐标，这里是它的非循环校验。

数据 © OpenStreetMap contributors，ODbL。导览页的地图角落有署名。
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib
import json
import math
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

from tls import ssl_ctx

HERE = pathlib.Path(__file__).resolve().parent

# 按顺序试，前一个失败才换下一个。2026-10-10 实测主站报「server is probably too busy」，
# kumi.systems 的镜像可用（它的数据比主站旧几个月，时间记在输出文件里）
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
UA = "ari-tour-osm/1.0"       # 不带 User-Agent 主站直接回 406
TIMEOUT = 120
COORD_TOLERANCE_M = 5


def out_path(mk: str) -> pathlib.Path:
    return HERE / f"{mk}_osm_data.json"


def load_modules(mk: str):
    try:
        tour = importlib.import_module(f"{mk}_tour_data")
        route = importlib.import_module(f"{mk}_route_data")
    except ModuleNotFoundError as e:
        sys.exit(f"缺 {e.name}.py —— 这个馆还没有导览配置或路线数据")
    return tour, route


def referenced(tour, route) -> dict[str, str]:
    """{要素: 谁引用了它}。"""
    refs = {tour.BOUNDARY: "院区边界"}
    for key, p in route.POINTS.items():
        refs.setdefault(p[2], f"POINTS[{key!r}]")
    for el, zh, _ in tour.LANDMARKS:
        refs.setdefault(el, f"LANDMARKS {zh}")
    return refs


def build_query(tour, refs) -> str:
    s, w, n, e = tour.OSM_BBOX
    box = f"{s},{w},{n},{e}"
    by_type = collections.defaultdict(list)
    for el in refs:
        t, i = el.split("/")
        by_type[t].append(i)
    # 关系只要建筑与多边形：范围里还压着地铁线、行政区划这类关系，
    # 带几何取回来有几 MB，而地图用不上
    parts = [f"way({box});",
             f'relation["building"]({box});',
             f'relation["type"="multipolygon"]({box});']
    for t in ("node", "way", "relation"):
        if by_type[t]:
            parts.append(f"{t}(id:{','.join(sorted(by_type[t], key=int))});")
    return "[out:json][timeout:90];(" + "".join(parts) + ");out geom;"


def fetch(query: str):
    body = urllib.parse.urlencode({"data": query}).encode()
    ctx = ssl_ctx()
    for ep in ENDPOINTS:
        req = urllib.request.Request(ep, data=body, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                raw = r.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  ✗ {ep}：{type(e).__name__} {str(e)[:120]}")
            continue
        try:
            j = json.loads(raw)
        except ValueError:
            # 忙的时候回的是一页 HTML，状态码却是 200
            tail = raw[-300:].decode("utf-8", "replace").replace("\n", " ")
            print(f"  ✗ {ep}：回的不是 JSON —— …{tail}")
            continue
        if not j.get("elements"):
            print(f"  ✗ {ep}：elements 为空")
            continue
        print(f"  ✓ {ep}：{len(j['elements'])} 个要素")
        return ep, j
    sys.exit("所有 Overpass 端点都没取到，没有写任何文件")


# ---------------------------------------------------------------- 体检
def rings(el) -> list[list[tuple[float, float]]]:
    """要素的全部折线，[(纬度, 经度), ...]。节点没有折线。"""
    if el["type"] == "way":
        return [[(p["lat"], p["lon"]) for p in el.get("geometry", [])]]
    if el["type"] == "relation":
        return [[(p["lat"], p["lon"]) for p in m["geometry"]]
                for m in el.get("members", []) if m.get("geometry")]
    return []


def center(el) -> tuple[float, float]:
    """外接矩形的中心 —— 与 Overpass `out center` 同一口径，路线数据里的坐标就是这么来的。"""
    if el["type"] == "node":
        return el["lat"], el["lon"]
    pts = [p for r in rings(el) for p in r]
    las, los = [p[0] for p in pts], [p[1] for p in pts]
    return (min(las) + max(las)) / 2, (min(los) + max(los)) / 2


def meters(a, b) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def check(data, tour, route, refs) -> None:
    by_id = {f"{e['type']}/{e['id']}": e for e in data["elements"]}
    missing = {el: who for el, who in refs.items() if el not in by_id}
    if missing:
        sys.exit("这些被引用的 OSM 要素不在取回的结果里（编号写错了，或要素已被删改）：\n  "
                 + "\n  ".join(f"{el}  ← {who}" for el, who in missing.items()))
    b = by_id[tour.BOUNDARY]
    ring = rings(b)[0]
    if len(ring) < 4 or ring[0] != ring[-1]:
        sys.exit(f"院区边界 {tour.BOUNDARY} 不是闭合的面（{len(ring)} 个点）")

    bad = []
    for key, p in route.POINTS.items():
        d = meters(center(by_id[p[2]]), p[:2])
        if d > COORD_TOLERANCE_M:
            bad.append(f"POINTS[{key!r}] 记的是 {p[0]},{p[1]}，OSM {p[2]} 的中心是 "
                       f"{center(by_id[p[2]])[0]:.5f},{center(by_id[p[2]])[1]:.5f}，差 {d:.0f} 米")
    if bad:
        sys.exit("路线数据里的坐标与 OSM 对不上：\n  " + "\n  ".join(bad))

    kinds = collections.Counter()
    for e in data["elements"]:
        t = e.get("tags", {})
        kinds[next((f"{k}={t[k]}" for k in ("building", "leisure", "landuse", "natural",
                                             "highway", "barrier", "tourism", "railway",
                                             "waterway", "amenity") if k in t), "（无主标签）")] += 1
    print(f"{out_path(data['museum']).name}：{len(data['elements'])} 个要素，"
          f"OSM 数据时间 {data['osm_base']}，取自 {data['endpoint']}（{data['fetched']}）")
    print("  " + "、".join(f"{k}×{c}" for k, c in kinds.most_common()))
    print(f"  被引用的 {len(refs)} 个要素都在；路线数据的 {len(route.POINTS)} 个坐标与 OSM "
          f"相差均不超过 {COORD_TOLERANCE_M} 米；院区边界 {len(ring) - 1} 个顶点")


def dump(data, path: pathlib.Path) -> None:
    """一行一个要素：整个文件能逐行 diff，又不至于缩进成几万行。"""
    head = {k: v for k, v in data.items() if k != "elements"}
    lines = [json.dumps(e, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
             for e in data["elements"]]
    text = json.dumps(head, ensure_ascii=False, indent=1)[:-2] \
        + ',\n "elements": [\n  ' + ",\n  ".join(lines) + "\n ]\n}\n"
    json.loads(text)                      # 手拼的 JSON，写盘前自己先读一遍
    path.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--museum", required=True, help="museum.key_name")
    ap.add_argument("--refresh", action="store_true", help="重新向 Overpass 取，覆盖现有文件")
    args = ap.parse_args()

    tour, route = load_modules(args.museum)
    refs = referenced(tour, route)
    path = out_path(args.museum)

    if path.exists() and not args.refresh:
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        query = build_query(tour, refs)
        print("向 Overpass 取数：")
        ep, j = fetch(query)
        order = {"node": 0, "way": 1, "relation": 2}
        data = {
            "museum": args.museum,
            "license": "© OpenStreetMap contributors, ODbL 1.0",
            "endpoint": ep,
            "fetched": dt.date.today().isoformat(),
            "osm_base": j.get("osm3s", {}).get("timestamp_osm_base"),
            "bbox": list(tour.OSM_BBOX),
            "query": query,
            "elements": sorted(j["elements"], key=lambda e: (order[e["type"]], e["id"])),
        }
        check(data, tour, route, refs)     # 体检不过就不落盘，不留一份坏文件
        dump(data, path)
        print(f"-> {path}")
        return
    check(data, tour, route, refs)


if __name__ == "__main__":
    main()
