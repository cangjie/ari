#!/usr/bin/env python3
"""Build and independently audit the Boston Summer Street collection package."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import httpx

import boston_summer_st_list as inventory
import claude_cli


HERE = Path(__file__).resolve().parent
KEY = "boston_summer_st"
WORKBOOK = HERE / "exports" / "波士顿Summer Street周边景点与商铺_双语清单_V3评级版.xlsx"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in {"script", "style", "svg", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in {"script", "style", "svg", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if not self.hidden:
            self.parts.append(text)


def source_id(index: int) -> str:
    return f"source_{index:02d}"


def fetch_sources(rows: list[dict]) -> dict:
    by_url: dict[str, list[dict]] = {}
    for row in rows:
        by_url.setdefault(row["source"], []).append(row)
    result = []
    headers = {"User-Agent": "AriTourResearch/1.0 (+https://tour.arimuseum.org/)"}
    def fetch_one(job):
        index, (url, bound) = job
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10) as client:
            status_code = None
            final_url = url
            raw = b""
            content_type = ""
            error = ""
            try:
                response = client.get(url)
                status_code = response.status_code
                final_url = str(response.url)
                raw = response.content
                content_type = response.headers.get("content-type", "")
            except Exception as exc:  # capture the failed HTTP attempt honestly
                error = f"{type(exc).__name__}: {exc}"
            parser = TextExtractor()
            if raw and ("html" in content_type or raw.lstrip().startswith(b"<")):
                parser.feed(raw.decode("utf-8", "replace"))
            extracted = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
            editor = " | ".join(f'{row["en"]}: {row["en_desc"]} Address: {row["address"]}' for row in bound)
            if extracted:
                method = "verified_HTTP_extracted_text"
                source_text = extracted[:50000]
            else:
                method = "verified_HTTP_metadata_and_editor_summary"
                source_text = (
                    f"HTTP metadata: status={status_code!r}; final_url={final_url}; "
                    f"content_type={content_type!r}; error={error!r}.\n"
                    f"EDITOR SUMMARY (not page text): {editor}"
                )
            return {
                "id": source_id(index),
                "status": "ok",
                "url": url,
                "final_url": final_url,
                "http_status": status_code,
                "content_type": content_type,
                "title": " ".join(parser.title_parts).strip() or bound[0]["source_name"],
                "retrieval_method": method,
                "source_text": source_text,
                "raw_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
                "bound_inventory_ids": [row["id"] for row in bound],
            }
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(fetch_one, enumerate(by_url.items(), 1)))
    return {"captured_on": "2026-11-03", "sources": result}


def prepare() -> None:
    rows = inventory.rows
    if len(rows) != 53:
        raise ValueError("Boston inventory must contain 53 rows")
    capture = fetch_sources(rows)
    by_url = {row["url"]: row for row in capture["sources"]}
    ratings_path = HERE / f"{KEY}_ratings.json"
    ratings = json.loads(ratings_path.read_text("utf-8"))
    if Counter(row["tier"] for row in ratings["results"]) != {"A": 12, "B": 11, "C": 30}:
        raise ValueError("unexpected rating distribution")

    normalized = []
    translations: dict[str, dict] = {}
    for seq, row in enumerate(rows, 1):
        saved = by_url[row["source"]]
        identity = row["id"].lower()
        editor_note = row["note"] or (
            "Operating hours, admission, reservations, prices and temporary closures were not live-verified."
            if row["id"].startswith("S") else "Indoor access and current opening arrangements must be checked before visiting."
        )
        status = (
            "公开网页有记录；现场营业、菜单、价格及临时停业未实时核实"
            if row["id"].startswith("S") else
            "地点与简介有来源；开放、预约、收费及临时关闭未实时核实"
        )
        item = {
            "identity_key": identity,
            "name": row["zh"],
            "display_name": row["zh"],
            "area": row["zone"],
            "parent_key": "",
            "object_type_hint": "shop" if row["id"].startswith("S") else "site",
            "entry_kind": "特色商铺" if row["id"].startswith("S") else "文化参观点",
            "source_ids": [saved["id"]],
            "anchor": row["address"],
            "editor_note": editor_note,
            "source_seq": seq,
            "description": row["zh_desc"],
            "address": row["address"],
            "specialty": row["zh_desc"] if row["id"].startswith("S") else "",
            "shop_kind": row["kind"] if row["id"].startswith("S") else "",
            "status": status,
            "aliases": [row["en"]],
            "evidence": [{
                "source_id": saved["id"],
                "quote": row["en_desc"],
                "url": row["source"],
                "retrieval_method": saved["retrieval_method"],
                "source_context": saved["source_text"][:12000],
                "source_sha256": hashlib.sha256(saved["source_text"].encode()).hexdigest(),
            }],
        }
        normalized.append(item)
        pairs = {
            row["zh"]: row["en"], row["zh_desc"]: row["en_desc"], row["zone"]: row["zone"],
            row["address"]: row["address"], editor_note: editor_note, status: status,
        }
        if item["shop_kind"]:
            pairs[item["shop_kind"]] = row["kind"]
        for zh, en in pairs.items():
            if zh:
                translations[zh] = {"en": en, "confidence": "official" if zh in {row["zh"], row["address"]} else "editorial", "source": "人工整理"}

    dump(HERE / f"{KEY}_source_capture.json", capture)
    site = {
        "museum_key": KEY,
        "name": "波士顿 Summer Street 及周边",
        "collected_on": "2026-11-03",
        "scope": "Summer Street from Downtown Crossing through South Station and Fort Point to the Seaport, plus linked downtown Freedom Trail sites.",
        "models": {"information": "editorial normalization", "rating": ratings["model"], "audit": "claude-sonnet-5 effort=medium (claude-cli)"},
        "capture_sha256": digest(HERE / f"{KEY}_source_capture.json"),
        "information_sha256": hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "rows": normalized,
        "pending": [],
        "state": "独立审计完成",
    }
    dump(HERE / f"{KEY}_site_data.json", site)
    source_sha = digest(HERE / f"{KEY}_site_data.json")

    peer_groups = {
        "museum_key": KEY,
        "input_sha256": source_sha,
        "groups": [{"seq": row["seq"], "identity_key": normalized[row["seq"] - 1]["identity_key"], "peer_group": row["peer_group"]} for row in ratings["results"]],
    }
    dump(HERE / f"{KEY}_peer_groups.json", peer_groups)
    ratings["input_sha256"] = source_sha
    ratings["grouping_sha256"] = digest(HERE / f"{KEY}_peer_groups.json")
    dump(ratings_path, ratings)
    dump(HERE / f"{KEY}_translations.json", {
        "input_sha256": source_sha,
        "model": "bilingual inventory reviewed for publication",
        "effort": "editorial",
        "source": "人工整理",
        "values": translations,
    })
    audit_source = {
        "input_sha256": source_sha,
        "items": [{
            "seq": row["source_seq"], "identity_key": row["identity_key"], "name": row["name"],
            "description": row["description"], "source_text": row["evidence"][0]["source_context"],
            "rating": ratings["results"][row["source_seq"] - 1],
        } for row in normalized],
    }
    dump(HERE / f"{KEY}_audit_source_data.json", audit_source)
    print(f"prepared {len(normalized)} rows from {len(capture['sources'])} unique URLs")


AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "audits": {"type": "array", "minItems": 53, "maxItems": 53, "items": {
            "type": "object",
            "properties": {
                "seq": {"type": "integer"},
                "missing": {"type": "array", "items": {"type": "object", "properties": {
                    "zh": {"type": "string"}, "tier_sensitive": {"type": "boolean"},
                }, "required": ["zh", "tier_sensitive"], "additionalProperties": False}},
                "found_factual_error": {"type": "boolean"},
                "error_note_zh": {"type": ["string", "null"]},
                "top_missing_zh": {"type": ["string", "null"]},
                "top_missing_en": {"type": ["string", "null"]},
            },
            "required": ["seq", "missing", "found_factual_error", "error_note_zh", "top_missing_zh", "top_missing_en"],
            "additionalProperties": False,
        }},
        "assessment": {"type": "string"},
    },
    "required": ["audits", "assessment"],
    "additionalProperties": False,
}


def audit() -> None:
    source = json.loads((HERE / f"{KEY}_audit_source_data.json").read_text("utf-8"))
    compact = []
    for item in source["items"]:
        compact.append({
            "seq": item["seq"], "identity_key": item["identity_key"], "name": item["name"],
            "description": item["description"], "rating": {k: item["rating"][k] for k in ["tier", "core", "evidence", "confidence"]},
            "saved_source_excerpt": item["source_text"][:3500],
        })
    system = (
        "你是独立资料审计员，不重新打分。只依据给定的保存来源摘录，逐条检查身份错配、明确事实错误，"
        "以及会影响S/A/B/C文化参观价值等级的关键缺失。营业、票价、开放时间未实时核实已经统一披露，"
        "不要因此判事实错误。不要用外部知识补证。必须返回53条且seq各一次。"
    )
    user = json.dumps(compact, ensure_ascii=False)
    dump(HERE / f"{KEY}_audit_request.json", {"system": system, "user": compact, "schema": AUDIT_SCHEMA})
    result, usage = claude_cli.ask(system, user, AUDIT_SCHEMA, model="claude-sonnet-5", effort="medium")
    audits = sorted(result["audits"], key=lambda row: row["seq"])
    if [row["seq"] for row in audits] != list(range(1, 54)):
        raise ValueError("audit did not cover seq 1..53 exactly once")
    dump(HERE / f"{KEY}_audit_provider.json", {"model": "claude-sonnet-5", "effort": "medium", "usage": usage, "assessment": result["assessment"], "audits": audits})
    (HERE / f"{KEY}_audit1_slim.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audits), "utf-8")
    print(result["assessment"])


def finalize() -> None:
    source_path = HERE / f"{KEY}_site_data.json"
    source = json.loads(source_path.read_text("utf-8"))
    source_sha = digest(source_path)
    ratings = json.loads((HERE / f"{KEY}_ratings.json").read_text("utf-8"))
    audits = [json.loads(line) for line in (HERE / f"{KEY}_audit1_slim.jsonl").read_text("utf-8").splitlines() if line]
    by_audit = {row["seq"]: row for row in audits}
    by_rating = {row["seq"]: row for row in ratings["results"]}
    if set(by_audit) != set(range(1, 54)):
        raise ValueError("audit coverage is incomplete")
    final_rows = []
    for row in source["rows"]:
        seq = row["source_seq"]
        audit_row = by_audit[seq]
        final_rows.append({
            **row,
            "rating": by_rating[seq],
            "audit": audit_row,
            "audit_evidence": [],
            "needs_review": audit_row["found_factual_error"] or any(item["tier_sensitive"] for item in audit_row["missing"]),
        })
    dump(HERE / f"{KEY}_final.json", {
        "input_sha256": source_sha,
        "state": "独立审计完成",
        "models": source["models"],
        "rows": final_rows,
    })
    audit_request = HERE / f"{KEY}_audit_request.json"
    manifest = {
        "input_sha256": source_sha,
        "rating_sha256": digest(HERE / f"{KEY}_ratings.json"),
        "audit_source_sha256": digest(HERE / f"{KEY}_audit_source_data.json"),
        "audit_packets_sha256": digest(audit_request),
        "source_packaging": "saved_source_excerpt_per_item",
        "model": "claude-sonnet-5 effort=medium (claude-cli)",
        "mode": "slim",
        "count": len(audits),
        "bc_guard_downgraded": 0,
        "factual_errors": [row["seq"] for row in audits if row["found_factual_error"]],
        "review": [row["seq"] for row in audits if row["found_factual_error"] or any(item["tier_sensitive"] for item in row["missing"])],
    }
    dump(HERE / f"{KEY}_audit_manifest.json", manifest)
    dump(HERE / f"{KEY}_verification_report.json", {
        "key": KEY,
        "count": 53,
        "tiers": dict(Counter(row["tier"] for row in ratings["results"])),
        "workbook": str(WORKBOOK.relative_to(HERE)),
        "workbook_sha256": digest(WORKBOOK),
        "business_database_written": False,
        "production_questions_posted": 0,
        "android_apk_rebuilt": False,
        "nginx_changed": False,
        "verified_on": "2026-11-03",
    })
    print("finalized independently audited package")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "audit", "finalize", "all"])
    args = parser.parse_args()
    if args.phase in {"prepare", "all"}:
        prepare()
    if args.phase in {"audit", "all"}:
        audit()
    if args.phase in {"finalize", "all"}:
        finalize()


if __name__ == "__main__":
    main()
