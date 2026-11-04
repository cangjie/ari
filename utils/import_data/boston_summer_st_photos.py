#!/usr/bin/env python3
"""Download, normalize and bind route-node photos for Boston Summer Street."""
from __future__ import annotations

import hashlib
import argparse
import html
import io
import json
import re
import time
from pathlib import Path

import httpx
from PIL import Image, ImageOps

import boston_summer_st_list as inventory


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEY = "boston_summer_st"
OUT = ROOT / "web_api" / "tour" / "img" / KEY
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}

COMMONS = {
    2: "File:Boston Common November 2016 003.jpg",
    3: "Massachusetts State House",
    4: "File:2024 Park Street Church - Boston 01.jpg",
    5: "Granary Burying Ground",
    6: "King's Chapel Boston",
    7: "Benjamin Franklin statue Old City Hall Boston",
    8: "Old Corner Bookstore Boston",
    9: "Old South Meeting House Boston",
    10: "File:Old State House, Boston.jpg",
    11: "File:2005 BostonMassacre site 24164572.jpg",
    12: "Faneuil Hall Boston",
    19: "Boston South Station facade",
    20: "File:A Street from Summer Street, Boston, June 2025.jpg",
    21: "File:Melcher Street at Summer Street, Boston, July 2013.JPG",
    22: "Boston Tea Party Ships Museum",
    24: "File:Martin's Park P1030201.jpg",
    27: "Institute of Contemporary Art Boston building",
    52: "File:Harpoon Brewery, Boston MA.jpg",
}

DIRECT = {
    21: {
        "image": "https://263summerst.com/wp-content/uploads/2026/02/boston-wharf-industrial-real-estate-sign.jpg",
        "page": "https://263summerst.com/history/", "title": "Boston Wharf Company rooftop sign",
    },
    31: {
        "image": "https://assets.wsdevelopment.com/wp-content/uploads/2021/01/Vanderwarker-pdv_1609-1289x1200.jpg",
        "page": "https://www.wsdevelopment.com/our-properties/400-summer-street/", "title": "400 Summer Street and public steps",
    },
    32: {
        "image": "https://assets.wsdevelopment.com/wp-content/uploads/2021/10/01-90683358-boston-park.jpg",
        "page": "https://www.wsdevelopment.com/news/how-to-humanize-a-22-billion-neighborhood-built-from-scratch/", "title": "Harbor Way public space",
    },
    36: {
        "image": "https://www.downtownboston.org/wp-content/uploads/2024/11/Untitled-24.jpg",
        "page": "https://www.downtownboston.org/business/tatte-bakery-125-summer-street/", "title": "Tatte Bakery at 125 Summer Street",
    },
    45: {
        "image": "https://www.highstreetplace.com/wp-content/uploads/2021/09/LIPBN_FH-03_Main-Entry-1a_200828-1024x682.jpg",
        "page": "https://www.highstreetplace.com/", "title": "High Street Place main entry",
    },
    46: {
        "image": "https://media.bizj.us/view/img/11043044/unknown-2%2A900xx4032-2268-0-378.jpg",
        "page": "https://www.bizjournals.com/boston/news/2018/09/12/food-fight-flour-bakery-sues-fort-point-landlord.html", "title": "Flour Bakery Fort Point storefront",
    },
    47: {
        "image": "https://images.getbento.com/accounts/0458dfcde69e52599298b5a6f7714c1d/media/images/35028Row34-July2021-AGL-173.jpg?w=1600&auto=compress,format&cs=origin",
        "page": "https://www.row34.com/location/row34-seaport/", "title": "Row 34 Seaport",
    },
    50: {
        "image": "https://images.getbento.com/accounts/4cdf4d8d02f9f9ca81a9ddfb59ad39b7/media/images/51211Main_Dining_Room_1_-_Coquette_Boston_-_Ryan_Fischer_-_Hi_Res-1.jpg?w=1600&auto=compress,format&cs=origin",
        "page": "https://www.coquetteboston.com/location/coquette/", "title": "Coquette Boston dining room",
    },
    52: {
        "image": "https://harpoonbrewery.com/wp-content/uploads/2025/04/boston-featured-image.png",
        "page": "https://harpoonbrewery.com/boston-brewery/", "title": "Harpoon Boston Brewery",
    },
}


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def commons_candidate(client: httpx.Client, query: str) -> dict:
    params = {"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime|mediatype",
              "iiurlwidth": 1800, "format": "json", "formatversion": 2}
    if query.startswith("File:"):
        params["titles"] = query
    else:
        params.update(generator="search", gsrsearch=query, gsrnamespace=6, gsrlimit=20)
    response = client.get(API, params=params, timeout=45)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", [])
    accepted = []
    tokens = {token.lower() for token in re.findall(r"[A-Za-z]+", query) if token.lower() not in {"boston", "building", "facade", "park"}}
    for page in pages:
        info = page.get("imageinfo", [{}])[0]
        meta = info.get("extmetadata", {})
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        if not any(name in license_name.lower() for name in ("cc", "public domain", "pdm")):
            continue
        if info.get("mediatype") != "BITMAP" or info.get("mime") not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        if info.get("width", 0) < 900 or info.get("height", 0) < 500:
            continue
        title = page["title"].lower()
        score = sum(2 for token in tokens if token in title)
        score += 2 if all(word not in title for word in ("diagram", "map", "logo", "catalogue", ".pdf", ".djvu")) else -8
        accepted.append((score, page, info, meta))
    if not accepted:
        raise ValueError(f"No licensed Commons photo for {query}")
    _, page, info, meta = max(accepted, key=lambda item: (item[0], item[2].get("width", 0)))
    return {
        "bytes_url": info.get("thumburl") or info["url"],
        "page": info["descriptionurl"],
        "title": page["title"].removeprefix("File:"),
        "author": strip_tags(meta.get("Artist", {}).get("value", "Wikimedia Commons contributor")),
        "license": meta.get("LicenseShortName", {}).get("value", ""),
        "license_url": meta.get("LicenseUrl", {}).get("value", ""),
        "photographed_on": strip_tags(meta.get("DateTimeOriginal", {}).get("value", "")) or None,
        "provider": "Wikimedia Commons",
    }


def normalize_image(content: bytes, path: Path) -> tuple[int, int]:
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
    if image.width < 900:
        scale = 900 / image.width
        image = image.resize((900, round(image.height * scale)), Image.Resampling.LANCZOS)
    image.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
    image.save(path, "JPEG", quality=88, optimize=True, progressive=True)
    return image.size


def get(client: httpx.Client, url: str, referer: str | None = None) -> bytes:
    for attempt in range(3):
        response = client.get(url, headers={"Referer": referer} if referer else None, timeout=60)
        if response.status_code < 500:
            response.raise_for_status()
            return response.content
        time.sleep(2 * (attempt + 1))
    response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--commons-only', action='store_true', help='Generate an unreviewed licensed candidate set')
    parser.add_argument('--seq', type=int, action='append', help='Only fetch specific candidates')
    args = parser.parse_args()
    if DIRECT and not args.commons_only:
        raise ValueError("Direct-source images lack verified reuse licenses; replace them before publication")
    OUT.mkdir(parents=True, exist_ok=True)
    checkpoint = HERE / f"{KEY}_commons_photo_candidates.json"
    prior = json.loads(checkpoint.read_text('utf-8')) if args.commons_only and checkpoint.exists() else {}
    entries = prior.get('photos', [])
    raw_capture = prior.get('source_capture', [])
    completed = {p['seq'] for p in entries if (ROOT/'web_api'/'tour'/p['path']).is_file()}
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        targets = set(COMMONS) if args.commons_only else set(COMMONS) | set(DIRECT)
        if args.seq:
            targets &= set(args.seq)
            entries = [p for p in entries if p['seq'] not in targets]
            raw_capture = [p for p in raw_capture if p['seq'] not in targets]
            completed -= targets
        for seq in sorted(targets):
            if seq in completed:
                continue
            row = inventory.rows[seq - 1]
            if seq in COMMONS:
                try:
                    source = commons_candidate(client, COMMONS[seq])
                except (ValueError, httpx.HTTPError) as exc:
                    print(f'{seq:02d} candidate unavailable: {exc}', flush=True)
                    continue
            else:
                direct = DIRECT[seq]
                source = {
                    "bytes_url": direct["image"], "page": direct["page"], "title": direct["title"],
                    "author": row["source_name"],
                    "license": "Source-page image; rights not stated; source attribution retained",
                    "license_url": direct["page"], "photographed_on": None, "provider": row["source_name"],
                }
            content = get(client, source["bytes_url"], source["page"] if seq in DIRECT else None)
            raw_capture.append({"seq": seq, "identity_key": row["id"].lower(), **source,
                                "download_sha256": hashlib.sha256(content).hexdigest()})
            output = OUT / f"{seq}.jpg"
            width, height = normalize_image(content, output)
            entry = {
                "seq": seq, "identity_key": row["id"].lower(), "path": f"img/{KEY}/{seq}.jpg",
                "caption": {"zh": row["zh"], "en": row["en"]},
                "source": {"title": source["title"], "url": source["page"], "image_url": source["bytes_url"],
                           "author": source["author"], "license": source["license"], "license_url": source["license_url"]},
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "photographed_on": source["photographed_on"], "width": width, "height": height,
            }
            entries.append(entry)
            print(f"{seq:02d} {row['id']} {width}x{height} {source['title']}", flush=True)
            if args.commons_only:
                (HERE / f"{KEY}_commons_photo_candidates.json").write_text(
                    json.dumps({"state":"unreviewed", "photos":entries, "source_capture":raw_capture}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if not args.commons_only:
        (HERE / f"{KEY}_photo_source_capture.json").write_text(json.dumps({"captured_on": "2026-11-03", "items": raw_capture}, ensure_ascii=False, indent=2) + "\n", "utf-8")
        (HERE / f"{KEY}_photos.json").write_text(json.dumps({"photos": entries, "supplementary_photos": []}, ensure_ascii=False, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
