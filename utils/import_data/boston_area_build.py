#!/usr/bin/env python3
"""Publish the Greater Boston guide as a collection-mode scenic area, without ratings.

Scope: only inventory rows whose captured source page passed the final passage audit
(boston_area_v3_audit_results_haiku55.json, supported and address_supported both true). Rows without a
captured page, or whose address did not pass, are not published. Ratings are not published: tier and core
are left empty, and the page shows 未评级 until a V3 scoring and an independent audit exist (see
boston_area_rate.py and the later audit step). Routes are published as text in the planning note, from
boston_area_routes.json; the walking times there are OpenStreetMap estimates, not timed walks.

Run: python3 boston_area_build.py            # writes web_api/tour/data/boston_area.json and catalog entry
     python3 boston_area_build.py --check    # validates the output without writing
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from PIL import Image

import boston_area_list as inventory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOUR = ROOT / "web_api" / "tour"
KEY = "boston_area"
OUT = TOUR / "data" / f"{KEY}.json"
CATALOG = TOUR / "catalog.json"
AUDIT = HERE / "boston_area_v3_audit_results_haiku55.json"
ROUTES = HERE / "boston_area_routes.json"
PHOTOS = HERE / "boston_area_photo_manifest.json"
CAPTURE = HERE / "boston_area_v3_source_capture.json"

ZONE_ZH = {
    "Harvard Square / Cambridge": "剑桥", "Kendall Square / Cambridge": "剑桥", "Cambridge": "剑桥",
    "Salem": "萨勒姆", "Lexington": "莱克星顿", "Concord": "康科德", "Cambridge / Watertown": "剑桥",
    "Quincy": "昆西", "Lexington / Lincoln / Concord": "莱克星顿·康科德",
    "Boston Common": "波士顿公园区", "Back Bay": "后湾", "Downtown": "市中心", "Beacon Hill": "灯塔山",
    "Fenway–Kenmore": "芬威—肯莫尔", "Jamaica Plain": "牙买加平原", "South End": "南端",
    "South Boston": "南波士顿", "Seaport": "海港区", "East Boston": "东波士顿", "Mattapan": "马塔潘",
    "West Roxbury": "西罗克斯伯里", "Brighton": "布莱顿", "Dorchester": "多切斯特", "Roxbury": "罗克斯伯里",
    "Charlestown": "查尔斯敦", "West End": "西端", "Allston": "奥尔斯顿", "Hyde Park": "海德公园",
    "Mission Hill": "米申山", "Chinatown / Theatre District": "唐人街·剧院区", "Roslindale": "罗斯林代尔",
    "North End": "北端", "North End / Downtown": "北端·市中心", "Downtown / North End / Charlestown": "市中心·北端·查尔斯敦",
    "Downtown / Waterfront": "市中心·海滨", "Waterfront / Seaport / East Boston": "海滨·海港·东波士顿",
    "Roxbury / Dorchester / Jamaica Plain": "罗克斯伯里·多切斯特·牙买加平原",
    "Roxbury / Dorchester": "罗克斯伯里·多切斯特", "South Boston Waterfront": "南波士顿海滨",
    "South End / Boston": "南端",
}
ACCESS_OVERRIDE_ADDRESS = {
    "union_oyster_house": "41 Union Street, Boston（官网页面）",
    "regina_pizzeria_north_end": "北端店（门牌以官网为准，待核）",
    "mikes_pastry": "北端 Hanover Street（门牌以官网为准，待核）",
    "oleana": "134 Hampshire Street, Cambridge（官网页面）",
    "salem_maritime": "塞勒姆海滨（门牌待核）",
    "nubian_square": "罗克斯伯里努比亚广场",
    "back_bay_fens": "芬威一带",
    "chinatown_theater_district": "华盛顿街剧院区",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def passed_rows() -> list[tuple[int, dict]]:
    audit = json.loads(AUDIT.read_text("utf-8"))["items"]
    passed = {x["id"] for x in audit if x["supported"] and x["address_supported"]}
    return [(seq, row) for seq, row in enumerate(inventory.rows, 1) if row["id"] in passed]


def photo_record(stop_id: str, photos: dict):
    rec = photos.get(stop_id)
    if not rec:
        return None, None
    path = TOUR / rec["file"]
    if not path.exists():
        raise SystemExit(f"photo listed but missing: {rec['file']}")
    with Image.open(path) as img:
        width, height = img.size
    info = {
        "caption": {"zh": "", "en": ""},
        "source": {
            "title": "Wikimedia Commons",
            "url": rec["commons_page"],
            "author": rec["artist"],
            "license": rec["licence"],
            "license_url": rec["licence_url"],
            "changes": "已缩放为1200像素以内的JPEG，未作其他修改",
        },
        "sha256": rec["sha256"],
        "photographed_on": None,
        "width": width,
        "height": height,
    }
    return rec["file"], info


def build() -> dict:
    routes = json.loads(ROUTES.read_text("utf-8"))["routes"]
    photos = {r["stop"]: r for r in json.loads(PHOTOS.read_text("utf-8"))["photos"]}
    rows = passed_rows()
    if not rows:
        raise SystemExit("no passed rows")
    places, stops = [], {}
    for seq, row in rows:
        stop_id = row["id"]
        photo_file, photo_info = photo_record(stop_id, photos)
        if photo_info:
            photo_info["caption"] = {"zh": row["zh"] + "（资料图）", "en": row["en"] + " (reference photo)"}
        zone_zh = ZONE_ZH.get(row["zone"], row["zone"])
        address = ACCESS_OVERRIDE_ADDRESS.get(stop_id, row["address"])
        places.append({"id": stop_id, "name": {"zh": row["zh"], "en": row["en"]}, "stops": [seq],
                       "photo": photo_file})
        stops[str(seq)] = {
            "seq": seq, "place": stop_id, "name": {"zh": row["zh"], "en": row["en"]}, "aliases": [],
            "tier": "", "core": None, "kind": "culture",
            "area": {"zh": zone_zh, "en": row["zone"]}, "related": None, "dwell": None,
            "status": {"zh": "以现场为准", "en": "Check on site"},
            "intro": [row["zh_desc"]], "intro_en": row["en_desc"],
            "source": {"zh": "依据来源机构页面整理（AI整理），逐条出处见下方",
                       "en": "Summarised from the source organisation's page; sources below"},
            "sources": [{"title": row["source_name"], "url": row["source"]}],
            "borrowed": {"zh": "访问：" + row["access"], "en": ""},
            "address": {"zh": address, "en": address},
            "specialty": {"zh": "", "en": ""}, "shop_kind": {"zh": "", "en": ""},
            "platform": {"zh": "", "en": ""},
            "photo": photo_file, "photo_info": photo_info, "objects": [], "review": None,
        }
        if photo_file:
            places[-1]["photo_info"] = photo_info
    route_lines = []
    for route in routes:
        days = "；".join(day["title"] for day in route["days"])
        route_lines.append(f"{route['title']}：{days}")
    planning_zh = (
        "本页为清单模式，收录已通过原文审计的地点，不构成路线。参考路线（停留时间为估计，步行时间按OSM道路估计）："
        + " ".join(route_lines) + " 本页暂未公布评级，待评分与独立审计完成后另行发布。"
    )
    planning_en = ("List mode: places whose captured sources passed the passage audit; not a route. "
                   "Three reference routes are described in the Chinese text. Ratings are not yet published.")
    data = {
        "key": KEY, "mode": "collection",
        "generated": date.today().isoformat(),
        "name": {"zh": "大波士顿", "en": "Greater Boston"},
        "card": {
            "city": {"zh": "波士顿", "en": "Boston"},
            "district": {"zh": "波士顿及周边", "en": "Boston area"},
            "type": {"zh": "文化参观 · 餐厅", "en": "Culture and dining"},
            "short": {"zh": "大波士顿", "en": "Greater Boston"},
            "desc": {"zh": f"收录已通过原文审计的{len(places)}个地点，覆盖波士顿市区、剑桥与萨勒姆，附参考路线；暂未公布评级。",
                     "en": f"{len(places)} sourced places across Boston, Cambridge and Salem, with reference routes; ratings not yet published."},
            "hours": "各场所开放及餐厅营业时间请出行前核实",
            "hours_note": {"zh": "查看介绍与来源", "en": "Browse introductions and sources"},
            "cover": places[0]["photo"] if places[0]["photo"] else None,
        },
        "opening": {"zh": "各场所开放、预约、收费及餐厅营业时间请出行前核实；资料来自抓取时的官方页面，不代表今日状态。",
                    "en": "Check access, reservations, admission and restaurant hours before visiting; sources are snapshots, not live information."},
        "planning": {"zh": planning_zh, "en": planning_en},
        "places": places, "stops": stops, "routes": [], "default_route": "none",
        "provenance": {
            "inventory": "boston_area_list.py", "inventory_sha256": sha(HERE / "boston_area_list.py"),
            "audit": AUDIT.name, "audit_sha256": sha(AUDIT),
            "capture": CAPTURE.name, "capture_sha256": sha(CAPTURE),
            "routes": ROUTES.name, "routes_sha256": sha(ROUTES),
            "photos": PHOTOS.name, "photos_sha256": sha(PHOTOS),
            "rating": "not published", "checked_on": date.today().isoformat(),
            "business_database_written": False,
        },
        "map_mode": "none",
        "canvas": {"w": 1000, "h": 1000, "north": 0, "px_per_m": 1},
        "proj": {"lat0": 42.36, "lon0": -71.06, "mlat": 111000, "mlon": 82000, "a": 1, "b": 0, "c": 0, "d": 1, "tx": 0, "ty": 0},
        "map": {"roads": [], "paths": [], "water": [], "woods": [], "walls": [], "track": [], "blocks": []},
        "labels": [],
        "entrance": {"x": 500, "y": 500, "name": {"zh": "波士顿", "en": "Boston"}},
        "attribution": {"zh": "无底图（清单模式）", "en": "No base map (list mode)"},
        "shop_label_policy": "分类只描述经营类别，不代表餐饮口味、质量或价格。",
    }
    return data


def update_catalog(check: bool) -> None:
    catalog = json.loads(CATALOG.read_text("utf-8"))
    if KEY in catalog["museums"]:
        return
    if check:
        print("catalog would add", KEY)
        return
    catalog["museums"].append(KEY)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> None:
    check = "--check" in sys.argv
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if check:
        print(f"ok: {len(data['places'])} places, {len(data['stops'])} stops, not written")
        update_catalog(True)
        return
    OUT.write_text(text, "utf-8")
    update_catalog(False)
    print(OUT, len(data["places"]), "places")


if __name__ == "__main__":
    main()
