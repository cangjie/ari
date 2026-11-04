#!/usr/bin/env python3
"""Capture OSM road geometry and source-bound coordinates for Summer Street."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import httpx

import boston_summer_st_list as inventory


HERE = Path(__file__).resolve().parent
KEY = "boston_summer_st"
BBOX = [42.3430, -71.0750, 42.3680, -71.0250]  # south, west, north, east
OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}
CURATED_OSM = {
    "T02": ("way", 29718019), "T03": ("way", 240317867), "T05": ("way", 29551954),
    "T06": ("node", 7613081520), "T07": ("way", 240319309), "T08": ("node", 367781324),
    "T09": ("way", 29608515), "T10": ("node", 632018853), "T11": ("way", 29551702),
    "P05": ("way", 29835286), "P10": ("node", 358275870), "P11": ("way", 29660099),
    "P13": ("node", 367781329), "P15": ("way", 117888922), "P16": ("way", 349363809),
    "P17": ("way", 94482797), "P18": ("node", 4394182202), "P20": ("way", 827967422),
    "S13": ("node", 7644634278), "S15": ("node", 2939948841), "S20": ("way", 29618668),
}


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_osm(client: httpx.Client) -> None:
    raw_path = HERE / f"{KEY}_osm_overpass_raw.json"
    normalized_path = HERE / f"{KEY}_osm.json"
    if raw_path.exists() and normalized_path.exists():
        print(f"OSM: reuse {normalized_path.name}", flush=True)
        return
    south, west, north, east = BBOX
    query = f"""[out:json][timeout:120][bbox:{south},{west},{north},{east}];
(
  way[highway];
  way[building][name];
  way[leisure=park];
  way[natural=water];
  node[name];
);
out body geom;
>;
out skel qt;
"""
    response = client.post(OVERPASS, content=query, headers={"Content-Type": "text/plain"}, timeout=180)
    response.raise_for_status()
    raw_path.write_bytes(response.content)
    raw = response.json()
    merged = {}
    for element in raw["elements"]:
        key = (element["type"], element["id"])
        current = merged.setdefault(key, {"type": element["type"], "id": element["id"]})
        for field in ("lat", "lon", "nodes", "geometry", "tags", "members"):
            if field in element:
                current[field] = element[field]
    normalized = {
        "bbox": BBOX,
        "raw_file": raw_path.name,
        "raw_sha256": sha(raw_path),
        "source": OVERPASS,
        "query": query,
        "elements": list(merged.values()),
    }
    dump(normalized_path, normalized)
    print(f"OSM: {len(normalized['elements'])} elements", flush=True)


def query_for(row: dict) -> str:
    overrides = {
        "F00": "Boston Common, Boston, Massachusetts",
        "T01": "Boston Common, Boston, Massachusetts",
        "T03": "Park Street Church, Boston, Massachusetts",
        "T05": "Kings Chapel, Boston, Massachusetts",
        "T06": "Boston Latin School Site, School Street, Boston, Massachusetts",
        "T07": "Old Corner Bookstore, Boston, Massachusetts",
        "T10": "Boston Massacre Site, Boston, Massachusetts",
        "P01": "Downtown Crossing, Boston, Massachusetts",
        "P02": "10 Summer Street, Boston, Massachusetts",
        "P04": "Boston Irish Famine Memorial, Boston, Massachusetts",
        "P06": "Dewey Square, Boston, Massachusetts",
        "P08": "Fort Point, Boston, Massachusetts",
        "P09": "263 Summer Street, Boston, Massachusetts",
        "P14": "Fan Pier Park, Boston, Massachusetts",
        "P19": "400 Summer Street, Boston, Massachusetts",
        "P20": "Harbor Way, Boston, Massachusetts",
    }
    return overrides.get(row["id"], f'{row["en"]}, {row["address"]}, Boston, Massachusetts')


def geocode(client: httpx.Client) -> list[dict]:
    progress_path = HERE / f"{KEY}_geocode_progress.json"
    result = json.loads(progress_path.read_text("utf-8"))["items"] if progress_path.exists() else []
    done = {item["seq"] for item in result}
    for seq, row in enumerate(inventory.rows, 1):
        if seq in done:
            continue
        queries = [query_for(row), f'{row["address"]}, Boston, Massachusetts']
        found = None
        attempts = []
        for query in dict.fromkeys(queries):
            for retry in range(3):
                response = client.get(NOMINATIM, params={"q": query, "format": "jsonv2", "limit": 5, "addressdetails": 1}, timeout=30)
                if response.status_code < 500:
                    break
                if retry == 2:
                    response.raise_for_status()
                time.sleep(2.5 * (retry + 1))
            response.raise_for_status()
            values = response.json()
            attempts.append({"query": query, "response": values})
            for candidate in values:
                lat, lon = float(candidate["lat"]), float(candidate["lon"])
                if BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]:
                    found = candidate
                    break
            if found:
                break
            time.sleep(1.05)
        if not found:
            raise ValueError(f'No in-corridor OSM geocode for {seq} {row["en"]}')
        osm_type = {"N": "node", "W": "way", "R": "relation"}.get(found.get("osm_type", "").upper()[:1], found.get("osm_type"))
        result.append({
            "seq": seq,
            "identity_key": row["id"].lower(),
            "name": row["en"],
            "query": attempts[-1]["query"],
            "lat": float(found["lat"]),
            "lon": float(found["lon"]),
            "osm": [osm_type, int(found["osm_id"])],
            "display_name": found["display_name"],
            "source_url": f'https://www.openstreetmap.org/{osm_type}/{found["osm_id"]}',
            "attempts": attempts,
        })
        dump(progress_path, {"items": result})
        print(f'{seq:02d} {row["id"]}: {found["display_name"]}', flush=True)
        time.sleep(1.05)
    return result


def apply_curated_osm(items: list[dict]) -> list[dict]:
    osm = json.loads((HERE / f"{KEY}_osm.json").read_text("utf-8"))
    elements = {(row["type"], row["id"]): row for row in osm["elements"]}
    by_id = {row["id"]: row for row in inventory.rows}
    for item in items:
        inventory_id = inventory.rows[item["seq"] - 1]["id"]
        wanted = CURATED_OSM.get(inventory_id)
        if not wanted:
            continue
        element = elements[wanted]
        if element["type"] == "node":
            lat, lon = element["lat"], element["lon"]
        else:
            geometry = element.get("geometry", [])
            lat = (min(point["lat"] for point in geometry) + max(point["lat"] for point in geometry)) / 2
            lon = (min(point["lon"] for point in geometry) + max(point["lon"] for point in geometry)) / 2
        name = element.get("tags", {}).get("name", by_id[inventory_id]["en"])
        item.update(lat=lat, lon=lon, osm=list(wanted), display_name=name,
                    source_url=f"https://www.openstreetmap.org/{wanted[0]}/{wanted[1]}",
                    curated_from_saved_osm=True)
    return items


def main() -> None:
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        fetch_osm(client)
        geocodes = apply_curated_osm(geocode(client))
    dump(HERE / f"{KEY}_geocode_capture.json", {"captured_on": "2026-11-03", "provider": NOMINATIM, "items": geocodes})
    positions = [{
        "seq": item["seq"], "identity_key": item["identity_key"], "basis": "sourced-point",
        "lat": item["lat"], "lon": item["lon"], "osm": item["osm"], "osm_name": item["display_name"],
        "source": {"title": f'OpenStreetMap · {item["name"]}', "url": item["source_url"]},
        "min_zoom": 0.35 if item["seq"] not in {2, 19, 27, 52} else 0,
    } for item in geocodes]
    media = {
        "osm_file": f"{KEY}_osm.json",
        "raw_file": f"{KEY}_osm_overpass_raw.json",
        "osm_sha256": sha(HERE / f"{KEY}_osm.json"),
        "water_relations": [],
        "positions": positions,
        "labels": [],
        "photo_manifest": f"{KEY}_photos.json",
        "cover_seq": 2,
    }
    dump(HERE / f"{KEY}_tour_media.json", media)
    print(f"media manifest: {len(positions)} positions", flush=True)


if __name__ == "__main__":
    main()
