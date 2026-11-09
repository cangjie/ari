#!/usr/bin/env python3
"""Capture the first-party WNE pages cited by wne_list.py, keeping the page text for the passage audit.

Reuses capture_one from boston_area_source_capture (same extraction, same hashes, same record shape).
Output: wne_source_capture.json. A page that does not return 200 with text is recorded as unavailable.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import boston_area_source_capture as capture
import wne_list as inventory

HERE = Path(__file__).resolve().parent
OUT = HERE / "wne_source_capture.json"


def main() -> None:
    by_url: dict[str, list[dict]] = {}
    for row in inventory.rows:
        by_url.setdefault(row["source"], []).append(row)
    jobs = list(enumerate(by_url.items(), 1))
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(capture.capture_one, jobs))
    OUT.write_text(json.dumps({
        "captured_on": date.today().isoformat(),
        "inventory_file": "wne_list.py",
        "inventory_ids": [row["id"] for row in inventory.rows],
        "sources": sources,
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    ok = sum(s["status"] == "ok" for s in sources)
    print(f"{ok}/{len(sources)} WNE source pages captured; {len(inventory.rows)} rows")
    for s in sources:
        print(s["status"], s["http_status"], s["extracted_char_count"], s["url"])


if __name__ == "__main__":
    main()
