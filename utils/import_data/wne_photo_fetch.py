"""Download the three WNE photos chosen from Wikimedia Commons and record licence and author.

Titles are fixed here after a visual check; the script refuses a title whose Commons licence is not in
the allowed list. Photos go to web_api/tour/img/wne_campus/ at 1200 px, RGB JPEG without metadata.
Output: wne_photo_manifest.json (subject_check is set to pending; the visual check is done separately).
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
OUT = ROOT / "web_api" / "tour" / "img" / "wne_campus"
MANIFEST = HERE / "wne_photo_manifest.json"
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}
ALLOWED = ("CC0", "Public domain", "CC BY ", "CC BY-SA", "No restriction")
WIDTH = 1200
CHOICES = {
    "wne_campus": "File:Western New England College campus 07.jpg",
    "wne_golden_bear_stadium": "File:WNECFootball22.jpg",
    "wne_ahlc": "File:WNECAHLC22.jpg",
}


def strip_tags(value: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    titles = list(CHOICES.values())
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60) as client:
        response = client.get(API, params={"action": "query", "titles": "|".join(titles), "prop": "imageinfo",
                                           "iiprop": "url|extmetadata|size", "format": "json", "formatversion": 2})
        response.raise_for_status()
        pages = {p["title"]: p for p in response.json()["query"]["pages"]}
        records = []
        for index, (key, title) in enumerate(CHOICES.items()):
            if index:
                time.sleep(2.0)
            info = pages[title]["imageinfo"][0]
            meta = info["extmetadata"]
            licence = meta.get("LicenseShortName", {}).get("value", "")
            if not any(licence.startswith(a) for a in ALLOWED):
                raise SystemExit(f"{key}: licence '{licence}' not allowed")
            name = title[len("File:"):]
            raw = client.get(f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(name)}?width={WIDTH}")
            raw.raise_for_status()
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw.content))).convert("RGB")
            image.thumbnail((WIDTH, WIDTH))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=85, optimize=True)
            jpeg = buffer.getvalue()
            (OUT / f"{key}.jpg").write_bytes(jpeg)
            records.append({
                "stop": key, "file": f"img/wne_campus/{key}.jpg", "bytes": len(jpeg),
                "sha256": hashlib.sha256(jpeg).hexdigest(), "width": image.size[0], "height": image.size[1],
                "commons_title": title, "commons_page": f"https://commons.wikimedia.org/wiki/{quote(title.replace(' ', '_'))}",
                "licence": licence, "licence_url": meta.get("LicenseUrl", {}).get("value", ""),
                "artist": strip_tags(meta.get("Artist", {}).get("value", "")),
                "original_size": [info.get("width"), info.get("height")],
                "retrieved_on": date.today().isoformat(), "subject_check": "pending",
            })
            print(key, len(jpeg), licence, records[-1]["artist"][:40], flush=True)
    MANIFEST.write_text(json.dumps({"captured_on": date.today().isoformat(),
                                    "note": "Commons photos for the WNE list; subject_check must be ok after a visual check.",
                                    "photos": records}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(MANIFEST)


if __name__ == "__main__":
    main()
