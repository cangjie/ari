#!/usr/bin/env python3
"""Capture first-party source pages referenced by the Greater Boston inventory."""
from __future__ import annotations

import hashlib
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import httpx

import boston_area_list as inventory


HERE = Path(__file__).resolve().parent
OUT = HERE / "boston_area_v3_source_capture.json"
HEADERS = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}
MAX_SOURCE_CHARS = 50000


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True
        if tag in {"script", "style", "svg", "noscript", "template"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in {"script", "style", "svg", "noscript", "template"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if not self.hidden_depth:
            self.parts.append(text)


def source_id(index: int) -> str:
    return f"source_{index:03d}"


def capture_one(job: tuple[int, tuple[str, list[dict]]]) -> dict:
    index, (url, bound_rows) = job
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20) as client:
            response = client.get(url)
    except httpx.RequestError as exc:
        return {
            "id": source_id(index),
            "status": "unavailable",
            "url": url,
            "final_url": None,
            "http_status": None,
            "content_type": None,
            "title": None,
            "retrieval_method": "http_request_error",
            "extracted_char_count": 0,
            "raw_sha256": None,
            "text_sha256": None,
            "source_text": None,
            "error": f"{type(exc).__name__}: {exc}",
            "bound_inventory_ids": [row["id"] for row in bound_rows],
        }

    content_type = response.headers.get("content-type", "")
    parser = TextExtractor()
    if "html" in content_type.lower() or response.content.lstrip().startswith(b"<"):
        parser.feed(response.content.decode(response.encoding or "utf-8", "replace"))
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    text = text[:MAX_SOURCE_CHARS]
    return {
        "id": source_id(index),
        "status": "ok" if response.status_code == 200 and text else "unavailable",
        "url": url,
        "final_url": str(response.url),
        "http_status": response.status_code,
        "content_type": content_type,
        "title": " ".join(parser.title_parts).strip() or None,
        "retrieval_method": "http_html_text" if text else "http_no_extractable_text",
        "extracted_char_count": len(text),
        "raw_sha256": hashlib.sha256(response.content).hexdigest(),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        "source_text": text or None,
        "error": None,
        "bound_inventory_ids": [row["id"] for row in bound_rows],
    }


def main() -> None:
    by_url: dict[str, list[dict]] = {}
    for row in inventory.rows:
        by_url.setdefault(row["source"], []).append(row)
    jobs = list(enumerate(by_url.items(), 1))
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(capture_one, jobs))
    result = {
        "captured_on": date.today().isoformat(),
        "inventory_file": "boston_area_list.py",
        "inventory_ids": [row["id"] for row in inventory.rows],
        "sources": sources,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    available = sum(source["status"] == "ok" for source in sources)
    print(f"{available}/{len(sources)} source pages captured; {len(inventory.rows)} inventory rows")
    print(OUT)
    for source in sources:
        if source["status"] != "ok":
            print(f"UNAVAILABLE {source['http_status']!r} {source['url']} {source['error'] or ''}")


if __name__ == "__main__":
    main()
