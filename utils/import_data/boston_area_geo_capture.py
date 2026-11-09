#!/usr/bin/env python3
"""Capture coordinates for the route stops of the Greater Boston guide.

Source: OpenStreetMap Nominatim search (one request per second, as its usage policy asks).
Each stop is searched with an explicit query built from the inventory address or the place name.
The result is a coordinate estimate for walking-time calculation only. It is not an entrance,
it is not verified against the operator, and it must be read together with the inventory row.
Output: boston_area_geo_capture.json (overwritten on every run; keep the file under version control).
"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "boston_area_geo_capture.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}

# Query per inventory id. Explicit street addresses come from the inventory row or the captured
# first-party page; area-only names are anchors and are marked as such in the route data.
QUERIES = {
    "boston_common": "Boston Common, Boston, MA",
    "public_garden": "Boston Public Garden, Boston, MA",
    "massachusetts_state_house": "Massachusetts State House, 24 Beacon St, Boston, MA",
    "freedom_trail": "Faneuil Hall, Boston, MA",
    "black_heritage_trail": "African Meeting House, Smith Court, Boston, MA",
    "union_oyster_house": "41 Union Street, Boston, MA",
    "mikes_pastry": "Mike's Pastry, Hanover Street, Boston, MA",
    "regina_pizzeria_north_end": "Regina Pizzeria, North End, Boston, MA",
    "rose_kennedy_greenway": "Rose Kennedy Greenway, Boston, MA",
    "boston_tea_party_ships": "306 Congress Street, Boston, MA",
    "boston_harborwalk": "Harborwalk, Seaport District, Boston, MA",
    "ica_boston": "25 Harbor Shore Drive, Boston, MA",
    "sowa": "530 Harrison Avenue, Boston, MA",
    "chinatown_theater_district": "Paramount Center, Washington Street, Boston, MA",
    "mission_hill_basilica": "1545 Tremont Street, Boston, MA",
    "mission_hill_triangle_historic_district": "Smith Street, Mission Hill, Boston, MA",
    "trinity_church": "206 Clarendon Street, Boston, MA",
    "mfa_boston": "465 Huntington Avenue, Boston, MA",
    "gardner_museum": "25 Evans Way, Boston, MA",
    "back_bay_fens": "Back Bay Fens, Boston, MA",
    "fenway_park": "4 Jersey Street, Boston, MA",
    "harvard_square": "Harvard Square, Cambridge, MA",
    "harvard_university": "Harvard Yard, Cambridge, MA",
    "harvard_art_museums": "32 Quincy Street, Cambridge, MA",
    "longfellow_house": "105 Brattle Street, Cambridge, MA",
    "mit_campus": "77 Massachusetts Avenue, Cambridge, MA",
    "oleana": "134 Hampshire Street, Cambridge, MA",
    "pem": "161 Essex Street, Salem, MA",
    "house_of_seven_gables": "115 Derby Street, Salem, MA",
    "salem_maritime": "Salem Maritime National Historic Site, Salem, MA",
    "salem_witch_museum": "19 1/2 North Washington Square, Salem, MA",
    "nubian_square": "Nubian Square, Roxbury, Boston, MA",
    "franklin_park": "1 Franklin Park Road, Boston, MA",
    "franklin_park_zoo": "Franklin Park Zoo, Boston, MA",
}


def search(client: httpx.Client, query: str) -> dict | None:
    response = client.get(NOMINATIM, params={"q": query, "format": "jsonv2", "limit": 1})
    response.raise_for_status()
    hits = response.json()
    if not hits:
        return None
    hit = hits[0]
    return {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "display_name": hit["display_name"],
        "osm_type": hit["osm_type"],
        "osm_id": hit["osm_id"],
        "osm_class": hit.get("class"),
        "osm_category": hit.get("type"),
    }


def main() -> None:
    items = {}
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for index, (key, query) in enumerate(QUERIES.items()):
            if index:
                time.sleep(1.1)
            result = search(client, query)
            items[key] = {"query": query, "result": result}
            status = "none" if result is None else f"{result['lat']:.5f},{result['lon']:.5f} {result['display_name'][:70]}"
            print(f"{key}: {status}", flush=True)
    OUT.write_text(json.dumps({
        "captured_on": date.today().isoformat(),
        "provider": "OpenStreetMap Nominatim (search, limit 1)",
        "note": "Coordinate estimates for walking-time calculation; not entrances; verify against the inventory row.",
        "items": items,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
