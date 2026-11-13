#!/usr/bin/env python3
"""Add the campus map, the classic walking route and the GPS navigation to the WNE list.

Input: an Overpass snapshot of the WNE campus (wne_osm_raw.json, kept outside the repository; it is
about 2.5 MB and is fetched by the query in this module's docstring). Output: the map layers, navigation
block and itinerary written into web_api/tour/data/wne_campus.json.

Method, the same family as boston_area_walk.py and tour_package_build.py:
- The projection is a local equirectangular metric frame: 1 canvas px = 1 metre, north up.
- Map layers are SVG path strings: roads, paths (footways), blocks (buildings), water, woods.
- Each named building is located by its OSM name at the centre of its footprint. That is an approximation:
  it is not the entrance, and places without an OSM feature are listed but not placed on the map.
- The route is a loop from the Welcome Center through the located places in the order of the official
  campus map numbers, joined along the footpath network (shortest path on distance). Legs are walking
  estimates at 60 m per minute. Stay times are hand estimates, not measured.
- Navigation: entrance at the Welcome Center; each located place has a 20 m arrival radius.

Overpass query used for the snapshot (bbox = centre 42.1125825,-72.5147814 +/- 0.0065 lat, +/- 0.0085 lon):
  way["building"], way["highway"~...], way["leisure"], way["landuse"], way["amenity"], way["natural"],
  way["water"], node["name"], way["name"] ... out body geom; >; out skel qt;
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import sys
from datetime import date
from pathlib import Path

from wne_visitor_details import apply as apply_visitor_details

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "web_api" / "tour" / "data" / "wne_campus.json"
DEFAULT_RAW = Path("/private/tmp/claude-501/-Users-cangjie-Projects-ari/623e2602-4e78-4e77-9f4e-8f5ec77589df/scratchpad/wne_osm_raw.json")

LAT0, LON0 = 42.1125825, -72.5147814
MLAT = 111200.0
MLON = 111320.0 * math.cos(math.radians(LAT0))
PAD = 40.0
ARRIVAL_RADIUS_M = 20

WALK_HIGHWAYS = {"footway", "path", "pedestrian", "steps", "service", "residential", "living_street",
                 "unclassified", "tertiary", "secondary", "primary", "cycleway", "track"}
ROAD_HIGHWAYS = {"service", "residential", "living_street", "unclassified", "tertiary", "secondary", "primary"}
PATH_HIGHWAYS = {"footway", "path", "pedestrian", "steps", "cycleway", "track"}

# Places located by OSM name. The campus map numbers are kept for the record.
PLACE_OSM = {
    "wne_welcome_center": ("Kevin S. Delbridge Welcome Center", "访客中心", "Welcome Center"),
    "wne_deliso_hall": ("Joseph J. Deliso Sr. Hall", "Deliso 楼", "Joseph J. Deliso Sr. Hall"),
    "wne_emerson_hall": ("Emerson Hall", "埃默森楼", "Emerson Hall"),
    "wne_herman_hall": ("Herman Hall", "赫尔曼楼", "Herman Hall"),
    "wne_csp": ("Center for the Sciences and Pharmacy", "科学与药学中心", "Center for the Sciences and Pharmacy"),
    "wne_damour_library": ("D’Amour Library", "D'Amour 图书馆", "D'Amour Library"),
    "wne_blake_law_center": ("Western New England College School of Law Library", "Blake 法学中心", "Blake Law Center (Law Library)"),
    "wne_churchill_hall": ("Churchill Hall", "丘吉尔楼", "Churchill Hall"),
    "wne_art_gallery": ("Saint Germain Campus Center", "St. Germain 校园中心（艺术画廊所在）", "St. Germain Campus Center (Art Gallery)"),
    "wne_university_commons": ("University Commons", "大学公共中心", "University Commons"),
    "wne_sleith_hall": ("Sleith Hall", "Sleith 楼", "Sleith Hall"),
    "wne_rivers_memorial_hall": ("Rivers Memorial Hall", "Rivers 纪念楼", "Rivers Memorial Hall"),
    "wne_golden_bear_stadium": ("Golden Bear Multipurpose Turf Stadium", "金熊体育场", "Golden Bear Stadium"),
    "wne_ahlc": ("Anthony S. Caprio Alumni Healthful Living Center", "Caprio 校友健康生活中心", "Caprio Alumni Healthful Living Center"),
}

# Classic loop: campus-map order, from the Welcome Center and back to it.
# (place id, stay minutes as a hand estimate, short visitor note from the official page)
LOOP = [
    ("wne_welcome_center", 5, "从访客中心出发，招生与访客信息都在此。"),
    ("wne_deliso_hall", 5, "行政办公楼，主要在外观上经过。"),
    ("wne_emerson_hall", 10, "1959 年启用的校园第一座建筑，文理学院的教学楼。"),
    ("wne_herman_hall", 10, "数学与写作中心、艺术工作室与多媒体教室所在。"),
    ("wne_csp", 15, "19 间科学实验室与模型药房；二层为健康与福祉中心。"),
    ("wne_damour_library", 20, "研究与社交中心，设 110 多个数据库与 24 小时自习区。"),
    ("wne_churchill_hall", 15, "商学院所在，内有 Cohen 交易室。"),
    ("wne_art_gallery", 15, "校园艺术画廊，展览与讲座时间以学校公告为准。"),
    ("wne_university_commons", 20, "2018 年启用的餐饮与社交中心，可在此用餐休息（不评价口味）。"),
    ("wne_sleith_hall", 15, "工程学院实验楼，生物医学工程套间模拟医院病房。"),
    ("wne_rivers_memorial_hall", 5, "广播电台与戏剧、音乐项目所在，主要在外观上经过。"),
    ("wne_blake_law_center", 15, "法学院所在，法学图书馆与模拟法庭。"),
    ("wne_golden_bear_stadium", 10, "1,500 座体育场，学生在 The Cave 一侧为同学加油。"),
    ("wne_ahlc", 10, "校友健康生活中心，男女篮球等项目使用。"),
    ("wne_welcome_center", 0, "回到访客中心，结束路线。"),
]


def haversine(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def proj_lat_lon(lat, lon):
    """Local metres east (e) and north (n) of the campus centre."""
    return (lon - LON0) * MLON, (lat - LAT0) * MLAT


def load(raw_path: Path):
    data = json.loads(raw_path.read_text("utf-8"))
    return data["elements"]


def centre(el):
    if el["type"] == "node":
        return el["lat"], el["lon"]
    geom = el.get("geometry") or []
    if not geom:
        return None
    lat = sum(p["lat"] for p in geom) / len(geom)
    lon = sum(p["lon"] for p in geom) / len(geom)
    return lat, lon


def path_d(points, closed=False):
    if len(points) < 2:
        return ""
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    return d + (" Z" if closed else "")


def build(raw_path: Path) -> dict:
    elements = load(raw_path)
    by_name = {}
    for el in elements:
        name = (el.get("tags") or {}).get("name")
        if name:
            by_name.setdefault(name, []).append(el)

    # Place centres from OSM names; a name must match exactly one feature.
    located = {}
    for pid, (osm_name, _, _) in PLACE_OSM.items():
        hits = [el for el in by_name.get(osm_name, []) if centre(el)]
        if len(hits) != 1:
            print(f"  not located: {pid} ({len(hits)} OSM matches for '{osm_name}')", file=sys.stderr)
            continue
        located[pid] = {"el": hits[0], "centre": centre(hits[0])}

    # Projection frame from every geometry point, so nothing falls outside the canvas.
    pts = []
    for el in elements:
        for p in el.get("geometry") or []:
            pts.append(proj_lat_lon(p["lat"], p["lon"]))
    min_e = min(p[0] for p in pts)
    max_e = max(p[0] for p in pts)
    max_n = max(p[1] for p in pts)
    min_n = min(p[1] for p in pts)
    tx = PAD - min_e
    ty = PAD + max_n
    width = (max_e - min_e) + 2 * PAD
    height = (max_n - min_n) + 2 * PAD

    def canvas(lat, lon):
        e, n = proj_lat_lon(lat, lon)
        return e + tx, -n + ty

    def ring(el):
        return [canvas(p["lat"], p["lon"]) for p in el.get("geometry") or []]

    layers = {"roads": [], "paths": [], "blocks": [], "water": [], "woods": []}
    for el in elements:
        if el["type"] != "way" or not el.get("geometry"):
            continue
        tags = el.get("tags") or {}
        hw = tags.get("highway")
        if hw in ROAD_HIGHWAYS and tags.get("area") != "yes":
            layers["roads"].append(path_d(ring(el)))
        elif hw in PATH_HIGHWAYS and tags.get("area") != "yes":
            layers["paths"].append(path_d(ring(el)))
        elif "building" in tags:
            layers["blocks"].append(path_d(ring(el), closed=True))
        elif tags.get("natural") == "water" or "water" in tags or tags.get("landuse") == "reservoir":
            layers["water"].append(path_d(ring(el), closed=True))
        elif tags.get("landuse") == "forest" or tags.get("natural") == "wood":
            layers["woods"].append(path_d(ring(el), closed=True))
    layers = {k: " ".join(v) for k, v in layers.items()}

    # Walkable graph for legs.
    adj: dict[int, list[tuple[int, float]]] = {}
    coords: dict[int, tuple[float, float]] = {}
    for el in elements:
        if el["type"] != "way":
            continue
        tags = el.get("tags") or {}
        if tags.get("highway") not in WALK_HIGHWAYS or tags.get("access") in ("private", "no") \
                or tags.get("foot") in ("private", "no") or tags.get("tunnel") == "yes":
            continue
        geom = el.get("geometry") or []
        nodes = el.get("nodes") or []
        if len(geom) != len(nodes) or len(nodes) < 2:
            continue
        for nid, p in zip(nodes, geom):
            coords[nid] = (p["lat"], p["lon"])
        for a, b, pa, pb in zip(nodes, nodes[1:], geom, geom[1:]):
            if a == b:
                continue
            d = haversine((pa["lat"], pa["lon"]), (pb["lat"], pb["lon"]))
            adj.setdefault(a, []).append((b, d))
            adj.setdefault(b, []).append((a, d))

    def snap(point):
        best, best_d = None, float("inf")
        for nid, (la, lo) in coords.items():
            if abs(la - point[0]) > 0.0015 or abs(lo - point[1]) > 0.002:
                continue
            d = haversine(point, (la, lo))
            if d < best_d:
                best, best_d = nid, d
        return best, best_d

    def shortest(src, dst):
        dist = {src: 0.0}
        prev = {}
        heap = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == dst:
                break
            if d > dist.get(u, float("inf")):
                continue
            for v, w in adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
        if dst not in dist:
            return None, None
        path = [dst]
        while path[-1] != src:
            path.append(prev[path[-1]])
        return dist[dst], list(reversed(path))

    snapped = {pid: snap(located[pid]["centre"]) for pid in located}
    for pid, (node, gap) in snapped.items():
        if node is None or gap > 80:
            raise SystemExit(f"{pid}: no walkable node within 80 m (gap {gap:.0f} m)")

    # Loop legs.
    legs, route_pts_xy, route_pts_ll = [], [], []
    walk_total, meters_total = 0.0, 0.0
    order = [pid for pid, _, _ in LOOP]
    for a, b in zip(order, order[1:]):
        na, ga = snapped[a]
        nb, gb = snapped[b]
        if a == b:
            continue
        road, path = shortest(na, nb)
        if road is None:
            raise SystemExit(f"no footpath between {a} and {b}")
        total = road + ga + gb
        seg_ll = [located[a]["centre"]] + [coords[n] for n in path] + [located[b]["centre"]]
        seg_xy = [canvas(la, lo) for la, lo in seg_ll]
        route_pts_ll.extend(seg_ll if not route_pts_ll else seg_ll[1:])
        route_pts_xy.extend(seg_xy if not route_pts_xy else seg_xy[1:])
        minutes = total / 60.0
        walk_total += minutes
        meters_total += total
        legs.append({"start": a, "end": b, "meters": round(total), "minutes": round(minutes, 1),
                     "way_ids": []})

    stay_total = sum(stay for _, stay, _ in LOOP)
    stops_unique = [pid for pid, _, _ in LOOP[:-1]]

    # Map-frame metadata.
    proj = {"lat0": LAT0, "lon0": LON0, "mlat": MLAT, "mlon": MLON, "a": 1, "b": 0, "c": 0, "d": -1,
            "tx": tx, "ty": ty}
    canvas_meta = {"w": round(width), "h": round(height), "north": 0, "px_per_m": 1}

    # Navigation area: the route's bounding box plus a margin, in canvas px (1 px = 1 m).
    xs = [p[0] for p in route_pts_xy]
    ys = [p[1] for p in route_pts_xy]
    margin = 40
    x0, x1, y0, y1 = min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin
    area_poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    la_all = [p[0] for p in route_pts_ll]
    lo_all = [p[1] for p in route_pts_ll]
    bbox = [min(la_all), min(lo_all), max(la_all), max(lo_all)]

    places_nav, places_map = [], {}
    place_items = {}
    for pid, info in located.items():
        x, y = canvas(*info["centre"])
        places_map[pid] = {"x": round(x, 2), "y": round(y, 2), "lat": info["centre"][0], "lon": info["centre"][1]}
        places_nav.append({"id": pid, "name": {"zh": PLACE_OSM[pid][1], "en": PLACE_OSM[pid][2]},
                           "stops": [], "x": round(x, 2), "y": round(y, 2),
                           "lat": info["centre"][0], "lon": info["centre"][1], "r": ARRIVAL_RADIUS_M,
                           "note": "OSM 建筑中心，不是门口；到附近即提醒。"})

    welcome = located["wne_welcome_center"]
    entrance = {"x": places_map["wne_welcome_center"]["x"], "y": places_map["wne_welcome_center"]["y"],
                "lat": places_map["wne_welcome_center"]["lat"], "lon": places_map["wne_welcome_center"]["lon"],
                "name": {"zh": "访客中心", "en": "Welcome Center"}}

    raw_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    nav = {
        "area": {"poly": area_poly, "buffer": 30, "basis": "osm-snapshot-bbox", "bbox": bbox,
                 "source_file": "utils/import_data/wne_route_build.py（Overpass 快照，不入库）",
                 "source_sha256": raw_sha,
                 "note": "校园步道与建筑的外接范围外扩 40 米，用于判断是否在校园范围内；不是学校法定边界。"},
        "entrance": entrance,
        "places": places_nav,
        "radius_m": ARRIVAL_RADIUS_M,
        "policy": ("GPS 导览只在校园范围内判断位置，靠近建筑中心约 20 米时提示“到附近”，不代表已到门口。"
                   "建筑位置来自 OpenStreetMap 轮廓中心；室内开放、讲座与比赛安排以学校公告为准。"),
    }

    variant = {
        "start_station": "welcome", "end_station": "welcome",
        "meters": round(meters_total), "walk_minutes": round(walk_total), "stay_minutes": stay_total,
        "total_minutes": round(walk_total) + stay_total,
        "path": [[round(x, 1), round(y, 1)] for x, y in route_pts_xy],
        "path_wgs84": [[round(la, 7), round(lo, 7)] for la, lo in route_pts_ll],
        "way_ids": [], "legs": legs,
    }

    steps = []
    for seq, (pid, stay, note) in enumerate(LOOP, 1):
        if pid == "wne_welcome_center" and seq != 1:
            continue
        steps.append({"seq": len(steps) + 1, "minutes": stay, "note": note,
                      "name": {"zh": PLACE_OSM[pid][1], "en": PLACE_OSM[pid][2]},
                      "place": pid, "point": [places_map[pid]["lat"], places_map[pid]["lon"]],
                      "streets": [], "related": []})

    theme = {
        "id": "classic", "name": "经典校园路线",
        "default_start": "welcome", "end_station": "welcome",
        "description": "从访客中心出发，依次经过教学楼、图书馆、艺术画廊、大学公共中心、工程学院与体育设施，回到访客中心。",
        "fee": "校园步道与外观免费；礼堂、画廊、图书馆与体育场的开放及活动，以学校公告为准。",
        "access": "步行约 %.1f 公里；停留时间为估计。雨雪天请注意路况，部分室内场所需按学校安排入内。" % (meters_total / 1000),
        "sources": [
            {"title": "Western New England University · 校园地图", "url": "https://wne.edu/become-a-student/visit/campus-map"},
            {"title": "Western New England University · 校园介绍", "url": "https://wne.edu/become-a-student/why-wne/campus"},
            {"title": "Western New England University · 图书馆", "url": "https://wne.edu/libraries/index"},
            {"title": "Western New England University · 艺术画廊", "url": "https://wne.edu/art-gallery/index"},
            {"title": "Western New England University Athletics · 体育设施", "url": "https://wnegoldenbears.com/facilities"},
        ],
        "optional_shops": [],
        "steps": steps,
        "variants": [variant],
    }

    station = {
        "id": "welcome", "name": "访客中心（Welcome Center）", "lines": [], "lines_label": "校园起点",
        "osm_node": None,
        "source": {"title": "Western New England University · 校园地图", "url": "https://wne.edu/become-a-student/visit/campus-map"},
        "position_source": {"title": "OpenStreetMap · Kevin S. Delbridge Welcome Center",
                            "url": "https://www.openstreetmap.org/search?query=Kevin%20S.%20Delbridge%20Welcome%20Center"},
        "point": [places_map["wne_welcome_center"]["lat"], places_map["wne_welcome_center"]["lon"]],
        "street_node": None, "connector_m": 0,
    }

    return {
        "map_mode": "browse",
        "canvas": canvas_meta, "proj": proj,
        "map": {"roads": layers["roads"], "paths": layers["paths"], "water": layers["water"],
                "woods": layers["woods"], "walls": "", "track": "", "blocks": layers["blocks"]},
        "labels": [],
        "entrance": {"x": entrance["x"], "y": entrance["y"], "name": entrance["name"]},
        "attribution": {"zh": "地图数据 © OpenStreetMap 贡献者（ODbL）", "en": "Map data © OpenStreetMap contributors (ODbL)"},
        "itineraries": [theme],
        "itinerary_stations": [station],
        "itinerary_policy": "路线沿校园步道与道路计算，停留与步行时间为估计；起点即访客中心，不设地铁接驳。",
        "itinerary_exit_note": "停留时间未计排队与用餐；室内开放以学校公告为准。",
        "itinerary_spread_markers": False,
        "itinerary_start_label": "校园起点",
        "navigation": nav,
        "_places_map": places_map,
        "_places_located": sorted(located),
        "_legs": legs,
        "_stay_total": stay_total,
        "_walk_total": round(walk_total),
        "_meters_total": round(meters_total),
        "_raw_sha256": raw_sha,
        "_unlocated": sorted(set(PLACE_OSM) - set(located)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    raw_path = Path(args.raw)
    result = build(raw_path)
    located = result.pop("_places_located")
    places_map = result.pop("_places_map")
    legs = result.pop("_legs")
    stay_total = result.pop("_stay_total")
    walk_total = result.pop("_walk_total")
    meters_total = result.pop("_meters_total")
    raw_sha = result.pop("_raw_sha256")
    unlocated = result.pop("_unlocated")
    print(f"located {len(located)} places; not located {unlocated}")
    print(f"loop: {len(legs)} legs, {meters_total} m, walk {walk_total} min (estimate), stay {stay_total} min (estimate)")
    if args.check:
        return

    data = json.loads(DATA.read_text("utf-8"))
    # Places that OSM locates get map positions; the rest stay list-only.
    by_id = {p["id"]: p for p in data["places"]}
    for pid, pos in places_map.items():
        if pid in by_id:
            by_id[pid].update({"x": pos["x"], "y": pos["y"], "lat": pos["lat"], "lon": pos["lon"]})
    data.update(result)
    data["generated"] = date.today().isoformat()
    data["planning"] = {
        "zh": ("本页为清单模式，收录学校官方页面可核实的地点。“经典校园路线”以访客中心为起点与终点，"
               "沿校园步道约 %d 米，步行与停留时间为估计，不含排队与用餐。GPS 导览可在靠近建筑中心约 20 米时提示“到附近”，不代表已到门口。"
               "本页暂未公布评级，待评分与独立审计完成后另行发布。") % meters_total,
        "en": ("List mode with a classic walking route from the Welcome Center. Walking and stay times are estimates. "
               "GPS guidance prompts within about 20 metres of a building centre, not the entrance. Ratings are not yet published."),
    }
    data["card"]["desc"]["zh"] = (f"收录学校官方页面可核实的{len(data['places'])}处校园地点，附一条约 {meters_total//1000:.0f} 公里的经典校园路线与 GPS 导览；暂未公布评级。")
    data["provenance"].update({
        "route_builder": "wne_route_build.py",
        "osm_snapshot_sha256": raw_sha,
        "route_checked_on": date.today().isoformat(),
    })
    apply_visitor_details(data)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(DATA)


if __name__ == "__main__":
    main()
