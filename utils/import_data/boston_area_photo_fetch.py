#!/usr/bin/env python3
"""Download the chosen Commons photos for the Greater Boston route stops and record their licences.

Choices live in SELECTION below (stop id -> a unique substring of the Commons title, as printed by
boston_area_photo_candidates.py). The script refuses to continue if a substring matches zero or
several candidates. Each photo is downloaded at 1200 px, re-encoded as an RGB JPEG without metadata,
and recorded with its Commons page, licence, licence URL, author text, original size and SHA-256.
Subject checks are a separate, human step; this script does not judge whether a photo shows the place.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx
from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATES = HERE / "boston_area_photo_candidates.json"
MANIFEST = HERE / "boston_area_photo_manifest.json"
OUT = ROOT / "web_api" / "tour" / "img" / "boston_area"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}
WIDTH = 1200
ALLOWED = ("CC0", "Public domain", "CC BY ", "CC BY-SA", "No restriction")

SELECTION = {
    "boston_common": "Boston Common November 2016 002.jpg",
    "public_garden": "Boston Public Garden November 2016 001.jpg",
    "massachusetts_state_house": "Massachusetts State House 2022.jpg",
    "freedom_trail": "Freedom Trail Sign Boston 1974.jpg",
    "black_heritage_trail": "Exterior of the African Meeting House (0e4c6a56",
    "union_oyster_house": "Union-oyster-house-1.jpg",
    "regina_pizzeria_north_end": "Pizzeria Regina, Boston MA.jpg",
    "rose_kennedy_greenway": "Rose Kennedy Greenway - Boston, MA - 20141226 105944.jpg",
    "boston_tea_party_ships": "Tea Wharf at the Boston Tea Party Ships & Museum.jpg",
    "ica_boston": "Institute of Contemporary Art, Boston, and Harborwalk.JPG",
    "sowa": "2009 HarrisonAve Boston 3388079514.jpg",
    "chinatown_theater_district": "Washington Street, Boston (53828903528).jpg",
    "mission_hill_triangle_historic_district": "Mission Hill Boston entrance.jpg",
    "trinity_church": "Outside Trinity Church in Copley Square, Boston.jpg",
    "mfa_boston": "Museum of Fine Arts, Boston in November 2021.jpg",
    "gardner_museum": "Isabella Stewart Gardner Museum Boston November 2016 001.jpg",
    "back_bay_fens": "Back Bay Fens Boston November 2016 001.jpg",
    "fenway_park": "Fenway Park01.jpg",
    "harvard_square": "Harvard Square, Cambridge MA.jpg",
    "harvard_university": "Harvard Yard im Sommer.jpg",
    "harvard_art_museums": "Harvard Art Museums, February 2022.jpg",
    "longfellow_house": "Cambridge - Longfellow House",
    "mit_campus": "MIT Dome night1 Edit.jpg",
    "pem": "Peabody Essex Museum.JPG",
    "house_of_seven_gables": "House of the Seven Gables (front angle)",
    "salem_maritime": "Salem Maritime National Historic Site.JPG",
    "salem_witch_museum": "Salem Witch Museum 1.jpg",
    "franklin_park": "Path and tree in Franklin Park, October 2013.jpg",
    "franklin_park_zoo": "Franklin Farm, Franklin Park Zoo, Dorchester MA.jpg",
}


def resolve(candidates: dict) -> dict:
    chosen = {}
    for stop, needle in SELECTION.items():
        pool = candidates[stop]["candidates"]
        hits = [c for c in pool if needle in c["title"]]
        if len(hits) != 1:
            raise SystemExit(f"{stop}: '{needle}' matched {len(hits)} candidates")
        photo = hits[0]
        if not any(photo["licence"].startswith(allowed) for allowed in ALLOWED):
            raise SystemExit(f"{stop}: licence '{photo['licence']}' is not in the allowed list")
        chosen[stop] = photo
    return chosen


def normalise(data: bytes) -> bytes:
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    image.thumbnail((WIDTH, WIDTH))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def main() -> None:
    candidates = json.loads(CANDIDATES.read_text("utf-8"))["items"]
    chosen = resolve(candidates)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60) as client:
        for index, (stop, photo) in enumerate(chosen.items()):
            if index:
                time.sleep(2.0)
            name = photo["title"][len("File:"):]
            url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(name)}?width={WIDTH}"
            response = client.get(url)
            response.raise_for_status()
            jpeg = normalise(response.content)
            target = OUT / f"{stop}.jpg"
            target.write_bytes(jpeg)
            records.append({
                "stop": stop,
                "file": f"img/boston_area/{stop}.jpg",
                "bytes": len(jpeg),
                "sha256": hashlib.sha256(jpeg).hexdigest(),
                "commons_title": photo["title"],
                "commons_page": photo["page_url"],
                "licence": photo["licence"],
                "licence_url": photo["licence_url"],
                "artist": photo["artist"],
                "original_size": [photo["width"], photo["height"]],
                "retrieved_on": date.today().isoformat(),
                "subject_check": "pending",
            })
            print(f"{stop}: {len(jpeg)} bytes  {photo['licence']}  {photo['artist'][:40]}", flush=True)
    MANIFEST.write_text(json.dumps({
        "captured_on": date.today().isoformat(),
        "note": "Downloaded Commons photos; subject_check must be set to 'ok' after a visual check.",
        "photos": records,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(MANIFEST)


if __name__ == "__main__":
    main()
