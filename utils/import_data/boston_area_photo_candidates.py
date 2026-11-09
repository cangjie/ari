#!/usr/bin/env python3
"""Search Wikimedia Commons for candidate photos of the Greater Boston route stops. No downloads.

Output: boston_area_photo_candidates.json, one list of candidates per stop, each with the Commons
title, licence short name, licence URL, artist text, description, and original size. A human then
chooses files and records the choice in boston_area_photo_manifest.json; this script never selects.
Commons rules: at most one request per two seconds; a generic User-Agent, not a personal address.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "boston_area_photo_candidates.json"
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}
LIMIT = 8

# Commons search text per inventory id (route stops only). The search is by name, so the list is
# a starting point; visual and licence checks are done by a person afterwards.
QUERIES = {
    "boston_common": "Boston Common",
    "public_garden": "Boston Public Garden",
    "massachusetts_state_house": "Massachusetts State House",
    "freedom_trail": "Freedom Trail Boston",
    "black_heritage_trail": "African Meeting House Boston",
    "union_oyster_house": "Union Oyster House",
    "mikes_pastry": "Mike's Pastry Boston",
    "regina_pizzeria_north_end": "Regina Pizzeria Boston",
    "rose_kennedy_greenway": "Rose Kennedy Greenway",
    "boston_tea_party_ships": "Boston Tea Party Ships Museum",
    "ica_boston": "Institute of Contemporary Art Boston",
    "sowa": "SoWa Boston Harrison Avenue",
    "chinatown_theater_district": "Boston Opera House Washington Street",
    "mission_hill_basilica": "Basilica of Our Lady of Perpetual Hope Boston",
    "mission_hill_triangle_historic_district": "Mission Hill Boston",
    "trinity_church": "Trinity Church Boston Copley Square",
    "mfa_boston": "Museum of Fine Arts Boston",
    "gardner_museum": "Isabella Stewart Gardner Museum",
    "back_bay_fens": "Back Bay Fens",
    "fenway_park": "Fenway Park",
    "harvard_square": "Harvard Square Cambridge",
    "harvard_university": "Harvard Yard",
    "harvard_art_museums": "Harvard Art Museums Cambridge",
    "longfellow_house": "Longfellow House Washington's Headquarters",
    "mit_campus": "MIT Massachusetts Institute of Technology campus Cambridge",
    "oleana": "Oleana restaurant Cambridge",
    "pem": "Peabody Essex Museum",
    "house_of_seven_gables": "House of the Seven Gables Salem",
    "salem_maritime": "Salem Maritime National Historic Site",
    "salem_witch_museum": "Salem Witch Museum",
    "nubian_square": "Nubian Square Roxbury",
    "franklin_park": "Franklin Park Boston",
    "franklin_park_zoo": "Franklin Park Zoo",
}


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def candidates(client: httpx.Client, query: str) -> list[dict]:
    params = {
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": LIMIT, "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime", "format": "json", "formatversion": 2,
    }
    response = client.get(API, params=params)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", [])
    found = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        found.append({
            "title": page["title"],
            "page_url": f"https://commons.wikimedia.org/wiki/{page['title'].replace(' ', '_')}",
            "licence": meta.get("LicenseShortName", {}).get("value", ""),
            "licence_url": meta.get("LicenseUrl", {}).get("value", ""),
            "artist": strip_tags(meta.get("Artist", {}).get("value", "")),
            "credit": strip_tags(meta.get("Credit", {}).get("value", "")),
            "description": strip_tags(meta.get("ImageDescription", {}).get("value", ""))[:300],
            "width": info.get("width"),
            "height": info.get("height"),
            "original_url": info.get("url"),
            "mime": info.get("mime"),
        })
    return found


def main() -> None:
    out = {}
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=45) as client:
        for index, (key, query) in enumerate(QUERIES.items()):
            if index:
                time.sleep(2.0)
            out[key] = {"query": query, "candidates": candidates(client, query)}
            print(f"{key}: {len(out[key]['candidates'])} candidates", flush=True)
    OUT.write_text(json.dumps({
        "captured_on": date.today().isoformat(),
        "provider": "Wikimedia Commons search (generator=search, imageinfo extmetadata)",
        "items": out,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
