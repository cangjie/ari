"""Build the WNE source-passage content-audit request. No model calls.

Same method as boston_area_audit_build.py: each row becomes an item carrying its English name, English
description and address, plus passages cut from the captured page text (1200-character steps, 200 characters
of lead-in, 1400-character window). Prompt and schema are reused from the Boston audit.
Output: wne_audit_request.json and wne_audit_manifest.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import wne_list as inventory
from boston_area_audit_build import SCHEMA, SYSTEM

HERE = Path(__file__).resolve().parent
CAPTURE = HERE / "wne_source_capture.json"
REQUEST = HERE / "wne_audit_request.json"
MANIFEST = HERE / "wne_audit_manifest.json"
CHUNK = 1200
LEAD_IN = 200
WINDOW = 1400


def main() -> None:
    capture = json.loads(CAPTURE.read_text("utf-8"))
    by_url = {source["url"]: source for source in capture["sources"]}
    items, skipped = [], []
    for seq, row in enumerate(inventory.rows, 1):
        source = by_url.get(row["source"])
        if not source or source["status"] != "ok" or not source.get("source_text"):
            skipped.append({"seq": seq, "id": row["id"], "url": row["source"], "reason": "来源未采集到正文，未送审"})
            continue
        text = source["source_text"]
        passages = [{"id": f"{seq}-{offset}", "url": row["source"],
                     "text": text[max(0, offset - LEAD_IN):offset + WINDOW]}
                    for offset in range(0, len(text), CHUNK)]
        items.append({"seq": seq, "id": row["id"], "name": row["en"], "description": row["en_desc"],
                      "address": row["address"], "source_text_sha256": source["text_sha256"],
                      "passages": passages})
    REQUEST.write_text(json.dumps({"system": SYSTEM, "items": items}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    manifest = {
        "state": "审计输入已生成；尚未调用任何模型",
        "inventory_sha256": hashlib.sha256((HERE / "wne_list.py").read_bytes()).hexdigest(),
        "capture_sha256": hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
        "request_sha256": hashlib.sha256(REQUEST.read_bytes()).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode("utf-8")).hexdigest(),
        "rows": len(inventory.rows),
        "items_in_request": len(items),
        "passages_in_request": sum(len(item["passages"]) for item in items),
        "skipped": skipped,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"rows {manifest['rows']} | in request {manifest['items_in_request']} | "
          f"passages {manifest['passages_in_request']} | skipped {len(skipped)}")


if __name__ == "__main__":
    main()
