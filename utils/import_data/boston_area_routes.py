#!/usr/bin/env python3
"""Recommended day routes for the Greater Boston guide: route definitions and a checked builder.

Each stop refers to an inventory id in boston_area_list.py. Coordinates come from
boston_area_geo_capture.json (Nominatim estimates). Dwell times are estimates written by hand.
Walking legs use the route_plan convention: straight-line distance x 1.4, at 60 m per minute.
Legs longer than WALK_LIMIT_M are marked for public transit; no transit minutes are invented.

Run: python3 boston_area_routes.py            # rebuild boston_area_routes.json and .md
     python3 boston_area_routes.py --check    # validate ids and coordinates, write nothing
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import boston_area_list as inventory

HERE = Path(__file__).resolve().parent
GEO = HERE / "boston_area_geo_capture.json"
OUT_JSON = HERE / "boston_area_routes.json"
OUT_MD = HERE / "boston_area_routes.md"
WALK_FACTOR = 1.4
WALK_SPEED_M_PER_MIN = 60
WALK_LIMIT_M = 1500

# Display addresses that replace an English inventory placeholder, or add the verification status.
# Restaurant addresses are marked with where they came from; nothing here is verified beyond that.
OVERRIDES = {
    "union_oyster_house": "41 Union Street, Boston（官网页面）",
    "regina_pizzeria_north_end": "11½ Thacher St, Boston（Frommer's 等二手来源；官网未载，待核）",
    "mikes_pastry": "300 Hanover St, Boston（多家列表一致；官网地址页未取得，待核）",
    "oleana": "134 Hampshire Street, Cambridge（官网页面）",
    "salem_maritime": "塞勒姆海滨（门牌待核）",
    "nubian_square": "罗克斯伯里努比亚广场（广场，无单一门牌）",
    "back_bay_fens": "芬威一带（公园，无单一门牌）",
    "chinatown_theater_district": "华盛顿街剧院区（路线点取 Paramount 一带，门牌待核）",
}

ROUTE_NOTES = {
    "boston_4d_core": [
        "第四天（塞勒姆）未排午餐：Turner's Seafood 官网抓取被拒（403），地址未能核实，暂不入路线。",
        "雷吉娜披萨与 Mike's Pastry 的北端门店地址来自二手来源，须对官网或门店信息再核一次。",
        "Mike's Pastry 无可确认的门店照片（已剔除：拍摄地点无法对上北端店），这一站暂无图。",
        "芬威球场比赛需票，此处只列外观；加德纳博物馆需按馆方要求提前预约。",
        "停留与步行时间为估计；公共交通段（剑桥至塞勒姆等）须现场查 MBTA 时刻。",
    ],
    "boston_2d_harbor_north": [
        "备选二日路线，与四日主路线第一天有重叠，适合时间少的游客。",
        "波士顿倾茶船与博物馆需购票或预约，时段另核。",
        "雷吉娜披萨与 Mike's Pastry 地址待官网核实，同主路线。",
    ],
    "boston_2d_south_community": [
        "不含餐厅：此路线的候选餐厅尚未核实地址，不列入。",
        "米申教堂（大殿）与弥撒及参观规定以教区为准，只列外观。",
        "富兰克林公园动物园需购票，季节开放另核。",
        "努比亚广场为广场性质，无单一门牌与开放时间。",
    ],
}

# (inventory id, dwell minutes estimate, role)  role: 景点 / 餐饮 / 步道 / 路线段
ROUTES = [
    {
        "id": "boston_4d_core",
        "title": "四日：波士顿、剑桥与塞勒姆（含餐厅）",
        "summary": "主路线。第一天市中心与北端，第二天后湾与芬威，第三天剑桥，第四天塞勒姆。",
        "days": [
            {"title": "第一天：市中心、北端与美食", "stops": [
                ("boston_common", 40, "景点"),
                ("public_garden", 30, "景点"),
                ("black_heritage_trail", 60, "步道"),
                ("freedom_trail", 60, "路线段"),
                ("union_oyster_house", 60, "餐饮"),
                ("regina_pizzeria_north_end", 60, "餐饮"),
                ("mikes_pastry", 20, "餐饮"),
            ]},
            {"title": "第二天：后湾与芬威博物馆区", "stops": [
                ("trinity_church", 30, "景点"),
                ("mfa_boston", 180, "景点"),
                ("gardner_museum", 120, "景点"),
                ("back_bay_fens", 40, "景点"),
                ("fenway_park", 20, "景点"),
            ]},
            {"title": "第三天：剑桥", "stops": [
                ("harvard_art_museums", 120, "景点"),
                ("longfellow_house", 40, "景点"),
                ("mit_campus", 90, "景点"),
                ("oleana", 90, "餐饮"),
            ]},
            {"title": "第四天：塞勒姆", "stops": [
                ("pem", 150, "景点"),
                ("house_of_seven_gables", 60, "景点"),
                ("salem_maritime", 60, "景点"),
                ("salem_witch_museum", 50, "景点"),
            ]},
        ],
    },
    {
        "id": "boston_2d_harbor_north",
        "title": "两日：市中心、海港与北端（含餐厅）",
        "summary": "备选二日。第一天市中心与自由之路，第二天海港与北端美食。",
        "days": [
            {"title": "第一天：市中心与自由之路", "stops": [
                ("boston_common", 40, "景点"),
                ("public_garden", 30, "景点"),
                ("black_heritage_trail", 60, "步道"),
                ("freedom_trail", 60, "路线段"),
                ("union_oyster_house", 60, "餐饮"),
            ]},
            {"title": "第二天：海港与北端", "stops": [
                ("boston_tea_party_ships", 90, "景点"),
                ("ica_boston", 60, "景点"),
                ("regina_pizzeria_north_end", 60, "餐饮"),
                ("mikes_pastry", 20, "餐饮"),
            ]},
        ],
    },
    {
        "id": "boston_2d_south_community",
        "title": "两日：南端、唐人街与罗克斯伯里（不含餐厅）",
        "summary": "备选二日，以社区与公园为主，不要求餐厅。覆盖南端、剧院区、米申山与罗克斯伯里。",
        "days": [
            {"title": "第一天：南端、剧院区与米申山", "stops": [
                ("sowa", 40, "景点"),
                ("chinatown_theater_district", 30, "景点"),
                ("mission_hill_basilica", 30, "景点"),
                ("mission_hill_triangle_historic_district", 30, "景点"),
            ]},
            {"title": "第二天：罗克斯伯里与富兰克林公园", "stops": [
                ("nubian_square", 40, "景点"),
                ("franklin_park", 120, "景点"),
                ("franklin_park_zoo", 150, "景点"),
            ]},
        ],
    },
]


WALK_LEGS = HERE / "boston_area_walk_legs.json"
LEG_KIND = {"walk": "walk", "transit": "transit", "straight_no_path": "straight", "straight_unsnapped": "straight"}
LEG_NOTE = {
    "walk": "步行（道路网，估计）",
    "transit": "公共交通（现场查 MBTA，不估算时间）",
    "straight_no_path": "道路网未连通，按直线估算（现场确认路线）",
    "straight_unsnapped": "不在已取道路范围，按直线估算（现场确认路线）",
}


def load_legs() -> dict:
    """Walk legs computed on the OSM network by boston_area_walk.py, keyed by (route, day, from, to)."""
    if not WALK_LEGS.exists():
        return {}
    data = json.loads(WALK_LEGS.read_text("utf-8"))
    return {(x["route"], x["day"], x["from"], x["to"]): x for x in data["legs"]}


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def load() -> tuple[dict, dict]:
    rows = {row["id"]: row for row in inventory.rows}
    geo = json.loads(GEO.read_text("utf-8"))["items"]
    return rows, geo


def check(rows: dict, geo: dict) -> list[str]:
    problems = []
    for route in ROUTES:
        for day in route["days"]:
            for stop_id, _, _ in day["stops"]:
                if stop_id not in rows:
                    problems.append(f"{route['id']}: unknown inventory id {stop_id}")
                    continue
                hit = geo.get(stop_id, {}).get("result")
                if not hit:
                    problems.append(f"{route['id']}: no coordinates for {stop_id}")
    return problems


def build_route(route: dict, rows: dict, geo: dict) -> dict:
    days_out, total_dwell, total_walk, total_legs_transit, total_straight = [], 0, 0, 0, 0
    legs = load_legs()
    for day_index, day in enumerate(route["days"], 1):
        stops = []
        for index, (stop_id, dwell, role) in enumerate(day["stops"]):
            hit = geo[stop_id]["result"]
            stop = {
                "order": index + 1,
                "id": stop_id,
                "name_en": rows[stop_id]["en"],
                "name_zh": rows[stop_id]["zh"],
                "role": role,
                "dwell_min_estimate": dwell,
                "lat": hit["lat"],
                "lon": hit["lon"],
                "address": OVERRIDES.get(stop_id, rows[stop_id]["address"]),
                "access": rows[stop_id]["access"],
                "source_url": rows[stop_id]["source"],
                "photo": f"img/boston_area/{stop_id}.jpg" if (HERE.parents[1] / "web_api/tour/img/boston_area" / f"{stop_id}.jpg").exists() else None,
                "leg_to_next": None,
            }
            total_dwell += dwell
            stops.append(stop)
        for current, following in zip(stops, stops[1:]):
            leg = legs.get((route["id"], day_index, current["id"], following["id"]))
            if leg is None:
                raise ValueError(f"no walk leg computed for {route['id']} day {day_index}: {current['id']}->{following['id']}")
            kind = LEG_KIND[leg["mode"]] if leg["mode"] in LEG_KIND else leg["mode"]
            if kind == "straight" and leg["straight_m"] > 1500:
                # An unconnected straight line this long is not presented as a walk.
                kind = "transit"
                leg = dict(leg, mode="transit")
            if kind == "walk":
                distance, minutes = leg["road_m"], leg["minutes_estimate"]
                total_walk += minutes
            elif kind == "straight":
                distance = leg["straight_m"]
                minutes = round(distance * WALK_FACTOR / WALK_SPEED_M_PER_MIN)
                total_straight += minutes
            else:
                distance, minutes = leg["straight_m"], None
                total_legs_transit += 1
            current["leg_to_next"] = {"kind": kind, "mode": LEG_NOTE[leg["mode"]], "distance_m": distance,
                                      "minutes_estimate": minutes}
        days_out.append({"title": day["title"], "stops": stops})
    return {
        "id": route["id"],
        "title": route["title"],
        "summary": route["summary"],
        "days": days_out,
        "notes": ROUTE_NOTES.get(route["id"], []),
        "totals": {
            "days": len(route["days"]),
            "stops": sum(len(d["stops"]) for d in route["days"]),
            "dwell_min_estimate": total_dwell,
            "walk_min_estimate": total_walk,
            "straight_min_estimate": total_straight,
            "transit_legs": total_legs_transit,
        },
    }


def markdown(built: list[dict]) -> str:
    lines = [
        "# 大波士顿推荐路线（草案）",
        "",
        f"生成日期：{date.today().isoformat()}。停留时间为人工估计，步行时间按直线距离×1.4、每分钟60米估计，",
        "不是实测。公共交通段只写距离，时间须现场查 MBTA 实时信息。地址来自清单，未另行核实的门店以“待核”标示。",
        "",
    ]
    for route in built:
        t = route["totals"]
        lines += [
            f"## {route['title']}",
            "",
            route["summary"],
            "",
            f"共 {t['days']} 天、{t['stops']} 站；停留合计约 {t['dwell_min_estimate']} 分钟，"
            f"步行段合计约 {t['walk_min_estimate']} 分钟（估计），公共交通段 {t['transit_legs']} 段。",
            "",
        ]
        if route["notes"]:
            lines += ["**注意**", ""] + [f"- {note}" for note in route["notes"]] + [""]
        for day in route["days"]:
            lines += [f"### {day['title']}", ""]
            for stop in day["stops"]:
                leg = stop["leg_to_next"]
                nxt = ""
                if leg:
                    if leg["kind"] == "walk":
                        nxt = f"→ 步行约 {leg['minutes_estimate']} 分钟（道路 {leg['distance_m']} 米，估计）"
                    elif leg["kind"] == "straight":
                        nxt = f"→ 道路未连通，直线 {leg['distance_m']} 米，按直线估算步行约 {leg['minutes_estimate']} 分钟（现场确认）"
                    else:
                        nxt = f"→ 公共交通（直线 {leg['distance_m']} 米，现场查）"
                lines.append(f"{stop['order']}. **{stop['name_zh']}**（{stop['role']}，停留约 {stop['dwell_min_estimate']} 分钟） {nxt}")
                lines.append(f"   - 地址/位置：{stop['address']}")
                if stop["access"]:
                    lines.append(f"   - 访问：{stop['access']}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    rows, geo_doc = load()
    geo = geo_doc
    problems = check(rows, geo)
    if problems:
        raise SystemExit("\n".join(problems))
    if "--check" in sys.argv:
        print("ok: all stops resolve to inventory rows and coordinates")
        return
    built = [build_route(route, rows, geo) for route in ROUTES]
    OUT_JSON.write_text(json.dumps({"captured_on": date.today().isoformat(), "routes": built},
                                   ensure_ascii=False, indent=2) + "\n", "utf-8")
    OUT_MD.write_text(markdown(built), "utf-8")
    print(OUT_JSON)
    print(OUT_MD)


if __name__ == "__main__":
    main()
