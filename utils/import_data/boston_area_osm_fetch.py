#!/usr/bin/env python3
"""Fetch the OpenStreetMap pedestrian network for the Greater Boston route areas.

Two bounding boxes are needed: the Boston–Cambridge–Roxbury area, and Salem. The raw Overpass JSON is
large (the Boston box is about 40 MB), so it is written to a path given on the command line, normally
outside the repository. boston_area_walk.py reads these files.

Run: python3 boston_area_osm_fetch.py boston /path/to/out/boston_area_overpass_raw.json
     python3 boston_area_osm_fetch.py salem  /path/to/out/boston_area_salem_overpass_raw.json
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}
BBOX = {
    "boston": (42.29, -71.14, 42.385, -71.03),
    "salem": (42.505, -70.93, 42.545, -70.86),
}
HIGHWAYS = ("footway|path|pedestrian|steps|residential|living_street|service|tertiary|tertiary_link|"
            "secondary|secondary_link|primary|primary_link|unclassified|track|cycleway")


def query(bbox):
    south, west, north, east = bbox
    return (f'[out:json][timeout:240];\n(way["highway"~"^({HIGHWAYS})$"]({south},{west},{north},{east}););\n'
            "out body; >; out skel qt;")


ENDPOINTS = [OVERPASS, "https://overpass.kumi.systems/api/interpreter"]


def main():
    name, out = sys.argv[1], Path(sys.argv[2])
    last = None
    for attempt in range(6):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            with httpx.Client(headers=HEADERS, timeout=300) as client:
                response = client.post(url, data={"data": query(BBOX[name])})
            if response.status_code == 200 and response.content[:1] == b"{":
                out.write_bytes(response.content)
                print(url, out, len(response.content))
                return
            last = f"{url} -> HTTP {response.status_code}, starts {response.content[:20]!r}"
        except httpx.HTTPError as exc:
            last = f"{url} -> {type(exc).__name__}"
        print("retry:", last, flush=True)
        time.sleep(30)
    raise SystemExit(f"Overpass unavailable after retries: {last}")


if __name__ == "__main__":
    main()
