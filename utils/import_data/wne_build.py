#!/usr/bin/env python3
"""Publish the WNE campus list as a collection-mode scenic area, without ratings.

Scope: only rows whose captured source passed the passage audit (wne_audit_results.json, supported and
address_supported both true). Rating fields are left empty; the page shows 未评级. Photos are the three
Commons photos in wne_photo_manifest.json, each with its licence and author. There are no routes for this
campus: the list is the product, as the campus is small and the official pages describe buildings, not walks.

Run: python3 wne_build.py            # writes web_api/tour/data/wne_campus.json and the catalog entry
     python3 wne_build.py --check    # validates the output without writing
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from PIL import Image

import wne_list as inventory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOUR = ROOT / "web_api" / "tour"
KEY = "wne_campus"
OUT = TOUR / "data" / f"{KEY}.json"
CATALOG = TOUR / "catalog.json"
AUDIT = HERE / "wne_audit_results.json"
PHOTOS = HERE / "wne_photo_manifest.json"
CAPTURE = HERE / "wne_source_capture.json"

ZONE_ZH = {"Campus core": "校园中心"}
ADDRESS_NOTE = {
    "wne_welcome_center": "1215 Wilbraham Road, Springfield, MA 01119（校区地址）",
}
PHOTO_CAPTION = {
    "wne_campus": ("西新英格兰大学校园一角（资料图）", "Campus courtyard (reference photo)"),
    "wne_golden_bear_stadium": ("校园足球场看台（资料图）", "Campus football field seating (reference photo)"),
    "wne_ahlc": ("体育馆内的篮球场（资料图）", "Basketball court inside the alumni athletics building (reference photo)"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def passed_rows() -> list[tuple[int, dict]]:
    audit = json.loads(AUDIT.read_text("utf-8"))["items"]
    passed = {x["id"] for x in audit if x["supported"] and x["address_supported"]}
    return [(seq, row) for seq, row in enumerate(inventory.rows, 1) if row["id"] in passed]


def photo_for(stop_id: str, photos: dict):
    rec = photos.get(stop_id)
    if not rec:
        return None, None
    path = TOUR / rec["file"]
    if not path.exists():
        raise SystemExit(f"photo listed but missing: {rec['file']}")
    with Image.open(path) as img:
        width, height = img.size
    zh, en = PHOTO_CAPTION[stop_id]
    info = {
        "caption": {"zh": zh, "en": en},
        "source": {"title": "Wikimedia Commons", "url": rec["commons_page"], "author": rec["artist"],
                   "license": rec["licence"], "license_url": rec["licence_url"],
                   "changes": "已缩放为1200像素以内的JPEG，未作其他修改"},
        "sha256": rec["sha256"], "photographed_on": None, "width": width, "height": height,
    }
    return rec["file"], info


def build() -> dict:
    photos = {r["stop"]: r for r in json.loads(PHOTOS.read_text("utf-8"))["photos"]}
    rows = passed_rows()
    if not rows:
        raise SystemExit("no passed rows")
    places, stops = [], {}
    for seq, row in rows:
        stop_id = row["id"]
        photo_file, photo_info = photo_for(stop_id, photos)
        address = ADDRESS_NOTE.get(stop_id, row["address"])
        places.append({"id": stop_id, "name": {"zh": row["zh"], "en": row["en"]}, "stops": [seq],
                       "photo": photo_file, **({"photo_info": photo_info} if photo_info else {})})
        stops[str(seq)] = {
            "seq": seq, "place": stop_id, "name": {"zh": row["zh"], "en": row["en"]}, "aliases": [],
            "tier": "", "core": None, "kind": "culture",
            "area": {"zh": ZONE_ZH.get(row["zone"], row["zone"]), "en": row["zone"]},
            "related": None, "dwell": None,
            "status": {"zh": "以现场为准", "en": "Check on site"},
            "intro": [row["zh_desc"]], "intro_en": row["en_desc"],
            "source": {"zh": "依据学校官方页面整理（AI整理），逐条出处见下方",
                       "en": "Summarised from the university's official pages; sources below"},
            "sources": [{"title": row["source_name"], "url": row["source"]}],
            "borrowed": {"zh": "访问：" + row["access"], "en": ""},
            "address": {"zh": address, "en": address},
            "specialty": {"zh": "", "en": ""}, "shop_kind": {"zh": "", "en": ""},
            "platform": {"zh": "", "en": ""},
            "photo": photo_file, "photo_info": photo_info, "objects": [], "review": None,
        }
        if photo_info is None:
            stops[str(seq)].pop("photo_info")
    planning_zh = ("本页为清单模式，收录学校官方页面可核实的校园地点，不构成路线。校园为 215 英亩的步行校区；"
                   "“校园地图第 N 号”的编号以学校官方校园地图为准，本页地址统一为校区地址。"
                   "本页暂未公布评级，待评分与独立审计完成后另行发布。")
    planning_en = ("List mode: campus places verified against the university's official pages; not a route. "
                   "Building numbers follow the official campus map; addresses are the campus address. Ratings are not yet published.")
    data = {
        "key": KEY, "mode": "collection", "generated": date.today().isoformat(),
        "name": {"zh": "西新英格兰大学校园", "en": "Western New England University"},
        "card": {
            "city": {"zh": "斯普林菲尔德", "en": "Springfield"},
            "district": {"zh": "Wilbraham Road 校区", "en": "Wilbraham Road campus"},
            "type": {"zh": "校园建筑 · 图书馆 · 艺术 · 餐饮 · 体育", "en": "Campus buildings, library, art, dining, athletics"},
            "short": {"zh": "西新英格兰大学", "en": "Western New England University"},
            "desc": {"zh": f"收录学校官方页面可核实的{len(places)}处校园地点，涵盖教学楼、图书馆、艺术画廊、餐饮与体育设施；暂未公布评级。",
                     "en": f"{len(places)} campus places verified against the university's official pages; ratings not yet published."},
            "hours": "校园开放与各场所时间请以学校公告为准",
            "hours_note": {"zh": "查看介绍与来源", "en": "Browse introductions and sources"},
            "cover": "img/wne_campus/wne_campus.jpg",
        },
        "opening": {"zh": "各场所开放、展览、比赛、餐厅营业及访客安排请出行前以学校公告为准；资料来自抓取时的官方页面，不代表今日状态。",
                    "en": "Check opening hours, exhibitions, events, dining and visitor arrangements with the university before visiting; sources are snapshots."},
        "planning": {"zh": planning_zh, "en": planning_en},
        "places": places, "stops": stops, "routes": [], "default_route": "none",
        "provenance": {
            "inventory": "wne_list.py", "inventory_sha256": sha(HERE / "wne_list.py"),
            "audit": AUDIT.name, "audit_sha256": sha(AUDIT),
            "capture": CAPTURE.name, "capture_sha256": sha(CAPTURE),
            "photos": PHOTOS.name, "photos_sha256": sha(PHOTOS),
            "rating": "not published", "checked_on": date.today().isoformat(),
            "business_database_written": False,
        },
        "map_mode": "none",
        "canvas": {"w": 1000, "h": 1000, "north": 0, "px_per_m": 1},
        "proj": {"lat0": 42.12, "lon0": -72.53, "mlat": 111000, "mlon": 82000, "a": 1, "b": 0, "c": 0, "d": 1, "tx": 0, "ty": 0},
        "map": {"roads": [], "paths": [], "water": [], "woods": [], "walls": [], "track": [], "blocks": []},
        "labels": [],
        "entrance": {"x": 500, "y": 500, "name": {"zh": "校园", "en": "Campus"}},
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
    if check:
        print(f"ok: {len(data['places'])} places, {len(data['stops'])} stops, not written")
        update_catalog(True)
        return
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    update_catalog(False)
    print(OUT, len(data["places"]), "places")


if __name__ == "__main__":
    main()
