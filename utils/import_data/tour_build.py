#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成手机导览页的数据文件 web_api/tour/data/<馆>.json（入仓库，勿手改）。

    python3 tour_build.py --museum wmhg            # 生成
    python3 tour_build.py --museum wmhg --check    # 只比对现有文件，不写；不一致退出码 1

三个来源合成一份，读库只读、不写任何表：

- 库：名称、评级、Core、在展状态、介绍原文、复核标记（经 route_plan.load_items 与一条补充查询）
- <馆>_route_data.py：参观顺序、坐标、停留时间、现状说明；路线由 route_plan.Planner 现算，
  与 route_plan.py 导出的 Excel 是同一段代码、同一组数字
- <馆>_osm_data.json + <馆>_tour_data.py：地图几何与画布摆法

**热区是「地点」不是「站」。** 路线上的一站是库里的一个节点；地图上的一个热区是一个
实际能走到的位置。怀远楼和楼上的御纹章展是两站、一个地点。归并规则：

- 坐标点相同的站归到同一个地点；
- 坐标是**借用**的站（路线数据里写了借用说明的）不单独成点，归到它所借的那个地点，
  并把借用说明带给页面 —— 页面不能在一个没有出处的位置上画标记、更不能在那里触发到站提醒。

**对不上一律报错退出，不猜**：地点没登记名称、登记了却没有站、站点落在景区范围之外、
站点没有中文介绍、院区里有认不出类别的 OSM 要素（后者只打印，不退出）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import math
import pathlib
import re
import sys

import meta_lib
import route_plan as RP
from export_excel import EN, ZH

HERE = pathlib.Path(__file__).resolve().parent
TOUR_DIR = HERE.parent.parent / "web_api" / "tour"

M_PER_DEG_LAT = 110574.0
R_MIN_M, R_MAX_M, R_PAD_M = 15, 45, 10        # 热区半径：轮廓等效半径 + 10 米，限制在 15–45 米
ROAD_KINDS = {"primary", "secondary", "tertiary", "residential", "unclassified"}
PATH_KINDS = {"footway", "service", "path", "pedestrian", "steps"}
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def L2(pair):
    return {"zh": pair[0], "en": pair[1]}


def nm(by_lang):
    """route_plan 里按 export_excel 的语种标签（zh-CN / en）存的名称，换成页面用的键。"""
    return {"zh": by_lang[ZH], "en": by_lang[EN]}


# ---------------------------------------------------------------- 几何
class Projection:
    """经纬度 → 画布像素。相似变换（旋转 + 等比缩放），所以画布上的距离除以比例就是米。"""

    def __init__(self, T):
        self.lat0, self.lon0 = T.ORIGIN
        self.mlon = 111320.0 * math.cos(math.radians(self.lat0))
        r, s = math.radians(T.ROTATE_DEG), T.PX_PER_M
        # 东 → (cos r, sin r)，北 → (sin r, -cos r)；画布 y 轴朝下
        self.a, self.b = s * math.cos(r), s * math.sin(r)
        self.c, self.d = s * math.sin(r), -s * math.cos(r)
        self.tx = self.ty = 0.0

    def enu(self, lat, lon):
        return (lon - self.lon0) * self.mlon, (lat - self.lat0) * M_PER_DEG_LAT

    def xy(self, lat, lon):
        e, n = self.enu(lat, lon)
        return self.a * e + self.b * n + self.tx, self.c * e + self.d * n + self.ty

    def as_json(self):
        return {"lat0": self.lat0, "lon0": self.lon0, "mlat": M_PER_DEG_LAT,
                "mlon": round(self.mlon, 3),
                "a": round(self.a, 6), "b": round(self.b, 6),
                "c": round(self.c, 6), "d": round(self.d, 6),
                "tx": round(self.tx, 2), "ty": round(self.ty, 2)}


def el_rings(el):
    """[(闭合?, [(lat, lon), ...])]。关系按成员各出一条，洞与外环不区分（画的时候用 evenodd）。"""
    if el["type"] == "way":
        g = [(p["lat"], p["lon"]) for p in el.get("geometry", [])]
        return [g] if g else []
    if el["type"] == "relation":
        return [[(p["lat"], p["lon"]) for p in m["geometry"]]
                for m in el.get("members", []) if m.get("geometry")]
    return []


def el_center(el):
    """外接矩形中心，与 Overpass `out center` 同口径（路线数据里的坐标也是这个口径）。"""
    if el["type"] == "node":
        return el["lat"], el["lon"]
    pts = [p for r in el_rings(el) for p in r]
    las, los = [p[0] for p in pts], [p[1] for p in pts]
    return (min(las) + max(las)) / 2, (min(los) + max(los)) / 2


def poly_area(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:]))) / 2


def in_poly(pt, poly):
    x, y = pt
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def dist_poly(pt, poly):
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        t = 0 if l2 == 0 else max(0, min(1, ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / l2))
        best = min(best, math.hypot(pt[0] - x1 - t * dx, pt[1] - y1 - t * dy))
    return best


def clip_segment(p, q, w, h, pad):
    """Liang–Barsky：把线段裁到画布（四边各放宽 pad）。整段在外返回 None。"""
    x0, y0, x1, y1 = p[0], p[1], q[0], q[1]
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 + pad), (dx, w + pad - x0), (-dy, y0 + pad), (dy, h + pad - y0)):
        if pp == 0:
            if qq < 0:
                return None
            continue
        t = qq / pp
        if pp < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def clip_line(pts, w, h, pad=20):
    """折线裁到画布，返回若干段折线。"""
    out, cur = [], []
    for p, q in zip(pts, pts[1:]):
        seg = clip_segment(p, q, w, h, pad)
        if seg is None:
            if len(cur) > 1:
                out.append(cur)
            cur = []
            continue
        a, b = seg
        if cur and math.hypot(cur[-1][0] - a[0], cur[-1][1] - a[1]) < 0.01:
            cur.append(b)
        else:
            if len(cur) > 1:
                out.append(cur)
            cur = [a, b]
    if len(cur) > 1:
        out.append(cur)
    return out


def f1(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def path_d(pts, close=False):
    return "M" + " L".join(f"{f1(x)} {f1(y)}" for x, y in pts) + ("Z" if close else "")


# ---------------------------------------------------------------- 取数
def load_extras(conn, mk):
    """route_plan.load_items 没取的几列：介绍、图片地址、展厅名。"""
    cur = conn.cursor()
    cur.execute("""
        SELECT a.source_seq, dz.text, a.image_url, a.official_url, gz.text, ge.text
        FROM artwork a
        JOIN museum m ON m.id = a.museum_id
        LEFT JOIN content_text dz ON dz.content_id = a.description_cid AND dz.lang = 'zh-CN'
        LEFT JOIN gallery g ON g.id = a.gallery_id
        LEFT JOIN content_text gz ON gz.content_id = g.name_cid AND gz.lang = 'zh-CN'
        LEFT JOIN content_text ge ON ge.content_id = g.name_cid AND ge.lang = 'en'
        WHERE m.key_name = %s""", (mk,))
    return {seq: dict(intro=intro, image_url=img, official_url=url, gallery={ZH: gz, EN: ge})
            for seq, intro, img, url, gz, ge in cur.fetchall()}


def museum_name(conn, mk):
    cur = conn.cursor()
    cur.execute("SELECT zh.text, en.text FROM museum m"
                " JOIN content_text zh ON zh.content_id = m.name_cid AND zh.lang = 'zh-CN'"
                " JOIN content_text en ON en.content_id = m.name_cid AND en.lang = 'en'"
                " WHERE m.key_name = %s", (mk,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"库里没有馆 {mk}，或它缺中英文名称")
    return {"zh": row[0], "en": row[1]}


def intro_source(seq, url, T):
    """这段介绍取自官网哪一类页面。认不出就报错，不拿「地点出处」顶替。"""
    for frag, zh, en in T.INTRO_SOURCES:
        if url and frag in url:
            return {"zh": zh, "en": en}
    sys.exit(f"seq {seq} 的 official_url {url!r} 不匹配 INTRO_SOURCES 里任何一条")


def photo_of(mk, seq):
    """这个序号已经下载到仓库里的图片的相对路径；没有就是 None。"""
    d = TOUR_DIR / "img" / mk
    for ext in IMG_EXTS:
        if (d / f"{seq}{ext}").is_file():
            return f"img/{mk}/{seq}{ext}"
    return None


# ---------------------------------------------------------------- 地点
def group_places(D, T):
    """{地点键: [站序号]}，以及 {站序号: 借用说明或 None}。"""
    anchor_of_osm = {}
    for key in T.PLACES:
        if key not in D.POINTS:
            sys.exit(f"PLACES 登记了 POINTS 里没有的坐标点 {key!r}")
        if D.POINTS[key][3]:
            sys.exit(f"PLACES[{key!r}] 的坐标是借用的，不能当地点")
        osm = D.POINTS[key][2]
        if osm in anchor_of_osm:
            sys.exit(f"PLACES 里 {anchor_of_osm[osm]!r} 与 {key!r} 指向同一个 OSM 要素 {osm}")
        anchor_of_osm[osm] = key

    stops_of = {key: [] for key in T.PLACES}
    borrowed = {}
    for st in D.STOPS:
        seq, point = st[0], st[1]
        p = D.POINTS[point]
        if p[3]:
            key = anchor_of_osm.get(p[2])
            if key is None:
                sys.exit(f"seq {seq} 的坐标借自 {p[2]}，但没有哪个登记过的地点在那里")
            borrowed[seq] = (p[3], p[4])
        else:
            key = point
            if key not in stops_of:
                sys.exit(f"seq {seq} 的坐标点 {point!r} 没在 PLACES 里登记名称")
            borrowed[seq] = None
        stops_of[key].append(seq)
    empty = [k for k, v in stops_of.items() if not v]
    if empty:
        sys.exit(f"PLACES 里这些地点一站都没有：{empty}")
    return stops_of, borrowed


def place_name(spec, items, extras):
    kind, seq = spec
    if seq not in items:
        sys.exit(f"PLACES 引用的序号 {seq} 库里没有")
    if kind == "node":
        return nm(items[seq]["name"])
    if kind == "gallery":
        g = extras[seq]["gallery"]
        if not g[ZH] or not g[EN]:
            sys.exit(f"seq {seq} 的展厅缺{'中文' if not g[ZH] else '英文'}名称")
        return {"zh": g[ZH], "en": g[EN]}
    sys.exit(f"PLACES 的名称来源只能是 node 或 gallery，不是 {kind!r}")


# ---------------------------------------------------------------- 地图
def building_bearing(elements, proj):
    """建筑边的主方位角（相对正北、折到 0–90 度、按边长加权），取权重最大的 1 度格。"""
    hist = {}
    for el in elements:
        if "building" not in el.get("tags", {}):
            continue
        for ring in el_rings(el):
            pts = [proj.enu(*p) for p in ring]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                ln = math.hypot(x2 - x1, y2 - y1)
                if ln >= 4:
                    k = round(math.degrees(math.atan2(x2 - x1, y2 - y1)) % 90 * 2) / 2
                    hist[k] = hist.get(k, 0) + ln
    return max(hist, key=hist.get)


def build_map(osm, T, proj, area_xy, w, h):
    """把 OSM 要素分到原型的几个图层里，返回 ({图层: path}, 没认出来的要素清单)。"""
    buf_px = T.AREA_BUFFER_M * T.PX_PER_M
    layers = {k: [] for k in ("woods", "water", "blocks", "track", "paths", "roads")}
    road_pieces, unknown = {}, []
    member_ways = {m["ref"] for el in osm["elements"] if el["type"] == "relation"
                   for m in el.get("members", []) if m["type"] == "way"}

    def near_area(pts):
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        return in_poly((cx, cy), area_xy) or dist_poly((cx, cy), area_xy) <= buf_px

    for el in osm["elements"]:
        tags = el.get("tags", {})
        ident = f"{el['type']}/{el['id']}"
        if ident == T.BOUNDARY or el["type"] == "node":
            continue
        rings = [[proj.xy(*p) for p in r] for r in el_rings(el)]
        rings = [r for r in rings if len(r) > 1]
        if not rings:
            continue
        hw = tags.get("highway")
        if hw in ROAD_KINDS:
            for r in rings:
                for piece in clip_line(r, w, h):
                    layers["roads"].append(path_d(piece))
                    road_pieces.setdefault(tags.get("name"), []).append(piece)
            continue
        if "railway" in tags or "boundary" in tags or tags.get("type") in ("route", "boundary"):
            continue                                   # 轨道线、行政区划界线与地图无关
        if not near_area([p for r in rings for p in r]):
            continue                                   # 院外的建筑、绿地不画
        closed = all(r[0] == r[-1] for r in rings)
        if hw in PATH_KINDS:
            layers["paths"] += [path_d(r) for r in rings]
        elif "building" in tags and closed:
            layers["blocks"].append("".join(path_d(r[:-1], close=True) for r in rings))
        elif tags.get("leisure") == "track" or "man_made" in tags:
            layers["track"] += [path_d(r) for r in rings]      # 跑道、鸟居这类细线勾出来的东西
        elif (tags.get("leisure") in ("garden", "park") or tags.get("landuse") in ("forest", "grass")) \
                and closed:
            layers["woods"] += [path_d(r[:-1], close=True) for r in rings]
        elif (tags.get("leisure") == "swimming_pool" or tags.get("natural") == "water") and closed:
            layers["water"] += [path_d(r[:-1], close=True) for r in rings]
        elif not tags and el["type"] == "way" and el["id"] in member_ways:
            continue                                   # 关系的成员环，已随关系画过
        else:
            unknown.append(f"{ident} {tags}")
    return {k: " ".join(v) for k, v in layers.items()}, road_pieces, unknown


# ---------------------------------------------------------------- 组装
def build(mk):
    try:
        D = importlib.import_module(f"{mk}_route_data")
        T = importlib.import_module(f"{mk}_tour_data")
    except ModuleNotFoundError as e:
        sys.exit(f"缺 {e.name}.py —— 这个馆还没有路线数据或导览配置")
    osm_path = HERE / f"{mk}_osm_data.json"
    if not osm_path.exists():
        sys.exit(f"缺 {osm_path.name} —— 先跑 tour_osm_fetch.py --museum {mk}")
    osm = json.loads(osm_path.read_text(encoding="utf-8"))
    by_id = {f"{e['type']}/{e['id']}": e for e in osm["elements"]}

    conn = meta_lib.connect()
    items = RP.load_items(conn, mk)
    extras = load_extras(conn, mk)
    name = museum_name(conn, mk)
    conn.close()

    RP.check_registry(items, D)
    hls = RP.highlights(items, D)
    P = RP.Planner(items, D)
    report = []

    # —— 画布 ——
    proj = Projection(T)
    if T.BOUNDARY not in by_id:
        sys.exit(f"OSM 数据里没有院区边界 {T.BOUNDARY}")
    ring = el_rings(by_id[T.BOUNDARY])[0]
    raw = [proj.xy(*p) for p in ring]
    pad = T.AREA_BUFFER_M * T.PX_PER_M + T.CANVAS_MARGIN_PX
    proj.tx = pad - min(p[0] for p in raw)
    proj.ty = pad - min(p[1] for p in raw)
    area_xy = [proj.xy(*p) for p in ring]
    w = math.ceil(max(p[0] for p in area_xy) + pad)
    h = math.ceil(max(p[1] for p in area_xy) + pad)
    buf_px = T.AREA_BUFFER_M * T.PX_PER_M

    bearing = building_bearing(osm["elements"], proj)
    # 主方位角 b 的那组边转到画布上是竖的，当且仅当 ROTATE_DEG ≡ 180 - b（模 90）
    off = ((T.ROTATE_DEG + bearing) % 90 + 45) % 90 - 45
    report.append(f"画布 {w}×{h} 像素，{1 / T.PX_PER_M:.2f} 米/像素；建筑主方位角 {bearing} 度，"
                  f"按 ROTATE_DEG={T.ROTATE_DEG} 摆正后偏 {off:+.1f} 度")
    if abs(off) > 3:
        sys.exit(f"ROTATE_DEG={T.ROTATE_DEG} 与建筑主方位角 {bearing} 度对不上（偏 {off:+.1f} 度），"
                 "地图会是歪的")

    def in_area(xy):
        return in_poly(xy, area_xy) or dist_poly(xy, area_xy) <= buf_px

    # —— 地点 ——
    stops_of, borrowed = group_places(D, T)
    stop_def = {s[0]: s for s in D.STOPS}
    order = [s[0] for s in D.STOPS]
    place_of = {seq: key for key, seqs in stops_of.items() for seq in seqs}
    places, outside = [], []
    for key in sorted(stops_of, key=lambda k: min(order.index(s) for s in stops_of[k])):
        lat, lon, osm_id = D.POINTS[key][:3]
        el = by_id.get(osm_id)
        if el is None:
            sys.exit(f"POINTS[{key!r}] 的 {osm_id} 不在 OSM 数据里 —— 先跑 tour_osm_fetch.py --refresh")
        rings_m = [[proj.enu(*p) for p in r] for r in el_rings(el)]
        area_m2 = max((poly_area(r) for r in rings_m if len(r) > 3 and r[0] == r[-1]), default=0)
        r_m = max(R_MIN_M, min(R_MAX_M, math.sqrt(area_m2 / math.pi) + R_PAD_M))
        x, y = proj.xy(lat, lon)
        if not in_area((x, y)):
            outside.append(f"{key} ({lat},{lon})")
        spec, lp = T.PLACES[key]
        if lp not in "btrl":
            sys.exit(f"PLACES[{key!r}] 的标签朝向 {lp!r} 不是 b/t/r/l 之一")
        photo = next((ph for s in stops_of[key] if (ph := photo_of(mk, s))), None)
        places.append({"id": key, "name": place_name(spec, items, extras),
                       "lat": lat, "lon": lon, "x": round(x, 1), "y": round(y, 1),
                       "r": round(r_m * T.PX_PER_M, 1), "r_m": round(r_m),
                       "lp": lp, "osm": osm_id, "photo": photo, "stops": stops_of[key]})
    ent = D.POINTS[D.ENTRANCE]
    ex, ey = proj.xy(*ent[:2])
    if not in_area((ex, ey)):
        outside.append(f"入口 {D.ENTRANCE}")
    if outside:
        sys.exit("这些点落在景区范围（院区边界外扩 "
                 f"{T.AREA_BUFFER_M} 米）之外：\n  " + "\n  ".join(outside))

    # —— 站 ——
    stops, flagged = {}, []
    for seq in order:
        st, it = stop_def[seq], items[seq]
        intro = extras[seq]["intro"]
        if not intro or not intro.strip():
            sys.exit(f"seq {seq} {it['name'][ZH]} 没有中文介绍")
        note = None
        if borrowed[seq]:
            if seq not in T.BORROWED_NOTE:
                sys.exit(f"seq {seq} {it['name'][ZH]} 的坐标是借用的，但 BORROWED_NOTE 里没有给游客看的说明")
            note = L2(T.BORROWED_NOTE[seq])
        objs = []
        for o in hls.get(seq, []):
            rr = o["review_reason"][ZH] if o["review"] else None
            if o["review"]:
                flagged.append(o["seq"])
            objs.append({"seq": o["seq"], "name": nm(o["name"]), "tier": o["tier"],
                         "photo": photo_of(mk, o["seq"]), "review": rr})
        if it["review"]:
            flagged.append(seq)
        stops[str(seq)] = {
            "seq": seq, "place": place_of[seq], "name": nm(it["name"]), "tier": it["tier"],
            "dwell": st[2],
            "status": {"zh": RP.status_text(P, seq, ZH), "en": RP.status_text(P, seq, EN)},
            "intro": [p.strip() for p in re.split(r"[\r\n]+", intro) if p.strip()],
            "source": intro_source(seq, extras[seq]["official_url"], T),
            "borrowed": note,
            "photo": photo_of(mk, seq),
            "objects": objs,
            "review": it["review_reason"][ZH] if it["review"] else None,
        }

    stale = sorted(set(T.BORROWED_NOTE) - {s for s, b in borrowed.items() if b})
    if stale:
        sys.exit(f"BORROWED_NOTE 里这些序号的坐标并不是借用的（路线数据改过了？）：{stale}")

    # —— 路线 ——
    routes, seen = [], {}
    for key, budget, lab_zh, lab_en in D.BUDGETS:
        plans = {rule: P.plan(budget, rule)[0] for rule in RP.RULES}
        same = len({frozenset(s) for s in plans.values()}) == 1
        short = (re.sub(r"（.*?）", "", lab_zh).strip(), re.sub(r"\s*\(.*?\)", "", lab_en).strip())
        for rule, sel in plans.items():
            if same and rule != next(iter(RP.RULES)):
                continue
            dwell = sum(P.dwell(s) for s in sel)
            legs = P.legs(sel)
            walk = sum(m for _, _, m in legs)
            rid = key if same else f"{key}-{rule}"
            label = L2(short) if same else {
                "zh": f"{short[0]} · {RP.RULE_SHORT[rule][0]}",
                "en": f"{short[1]} · {RP.RULE_SHORT[rule][1]}"}
            routes.append({"id": rid, "label": label, "budget": budget,
                           "total": RP.fmt(dwell + walk), "stay": dwell, "walk": RP.fmt(walk),
                           "stops": [s for s in order if s in sel]})
            seen[key, rule] = rid
            if same:
                for other in RP.RULES:
                    seen[key, other] = rid
    default_route = seen.get(tuple(T.DEFAULT_ROUTE))
    if default_route is None:
        sys.exit(f"DEFAULT_ROUTE={T.DEFAULT_ROUTE} 不是一条存在的路线")

    # —— 地图 ——
    layers, road_pieces, unknown = build_map(osm, T, proj, area_xy, w, h)
    labels = []
    for osm_id, zh, en in T.LANDMARKS:
        if osm_id not in by_id:
            sys.exit(f"LANDMARKS 的 {osm_id}（{zh}）不在 OSM 数据里")
        x, y = proj.xy(*el_center(by_id[osm_id]))
        labels.append({"kind": "gate", "x": round(x, 1), "y": round(y, 1), "t": {"zh": zh, "en": en}})
    for zh, en in T.ROADS:
        pieces = road_pieces.get(zh)
        if not pieces:
            sys.exit(f"ROADS 的「{zh}」在画布范围内没有路段")
        best = max(pieces, key=lambda pc: sum(math.hypot(b[0] - a[0], b[1] - a[1])
                                              for a, b in zip(pc, pc[1:])))
        mid = best[len(best) // 2] if len(best) > 2 else \
            ((best[0][0] + best[1][0]) / 2, (best[0][1] + best[1][1]) / 2)
        x = max(30, min(w - 30, mid[0]))
        y = max(20, min(h - 20, mid[1]))
        labels.append({"kind": "road", "x": round(x, 1), "y": round(y, 1), "t": {"zh": zh, "en": en}})

    data = {
        "key": mk,
        "generated": dt.date.today().isoformat(),
        "name": name,
        "card": {**{k: L2(T.CARD[k]) for k in ("city", "district", "type", "short", "desc",
                                               "hours_note")},
                 "hours": T.CARD["hours"], "cover": photo_of(mk, T.CARD["cover_seq"])},
        "opening": L2(D.OPENING),
        "canvas": {"w": w, "h": h, "north": T.ROTATE_DEG, "px_per_m": T.PX_PER_M},
        "proj": proj.as_json(),
        "area": {"poly": [[round(x, 1), round(y, 1)] for x, y in area_xy],
                 "buffer": round(buf_px, 1), "osm": T.BOUNDARY},
        "walk": {"detour": RP.DETOUR, "m_per_min": RP.WALK_M_PER_MIN},
        "entrance": {"name": L2(D.ENTRANCE_NAME), "lat": ent[0], "lon": ent[1],
                     "x": round(ex, 1), "y": round(ey, 1)},
        "map": {"walls": path_d(area_xy[:-1], close=True), **layers},
        "labels": labels,
        "places": places,
        "stops": stops,
        "routes": routes,
        "default_route": default_route,
        "attribution": {"zh": "地图数据 © OpenStreetMap 贡献者", "en": "Map data © OpenStreetMap contributors",
                        "osm_base": osm.get("osm_base")},
    }

    # —— 体检输出 ——
    n_borrowed = sum(1 for v in borrowed.values() if v)
    report.append(f"{len(places)} 个地点、{len(stops)} 站（其中 {n_borrowed} 站坐标借用、并入所借地点），"
                  f"不进路线 {len(D.MERGED)} 个并入 + {len(D.UNPLACED)} 个位置不明")
    for p in places:
        names = "、".join(f"{s}{'*' if borrowed[s] else ''}" for s in p["stops"])
        report.append(f"   {p['id']:12s} {p['name']['zh']:<14s} 半径 {p['r_m']:2d} 米  站 {names}"
                      f"{'  有照片' if p['photo'] else ''}")
    for r in routes:
        report.append(f"   路线 {r['id']:12s} {r['label']['zh']:<12s} {len(r['stops']):2d} 站  "
                      f"合计 {r['total']}（停留 {r['stay']} + 步行 {r['walk']}）")
    n_photo = sum(1 for s in stops.values() if s["photo"])
    report.append(f"照片：{n_photo}/{len(stops)} 站有图，卡片封面{'有' if data['card']['cover'] else '无'}")
    report.append(f"带复核标记而会展示的条目：{len(flagged)} 件" + (f" {sorted(set(flagged))}" if flagged else ""))
    if unknown:
        report.append(f"院区内有 {len(unknown)} 个 OSM 要素没认出类别，没有画：")
        report += [f"   {u}" for u in unknown]
    return data, report


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--museum", required=True, help="museum.key_name")
    ap.add_argument("--check", action="store_true", help="只比对现有文件，不写")
    args = ap.parse_args()

    data, report = build(args.museum)
    print("\n".join(report))
    out = TOUR_DIR / "data" / f"{args.museum}.json"

    if args.check:
        if not out.exists():
            sys.exit(f"{out} 不存在")
        old = json.loads(out.read_text(encoding="utf-8"))
        old["generated"] = data["generated"]          # 生成日期不算差异
        if old != data:
            diff = [k for k in data if old.get(k) != data[k]]
            print(f"\n✗ 现有文件与重新生成的不一致，不同的顶层键：{diff}")
            sys.exit(1)
        print(f"\n✓ {out.name} 与重新生成的一致")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(data), encoding="utf-8")
    print(f"-> {out}（{out.stat().st_size // 1024} KB）")


if __name__ == "__main__":
    main()
