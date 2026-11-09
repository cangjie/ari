"""Run the WNE source-passage content audit with Claude (same method as boston_area_audit_run.py).

Resumable: results are written after every batch; a changed request file refuses to resume.
A passage id that does not exist in the item's passages is marked unsupported.
Default model is claude-haiku-5-5 at medium effort, the model the Boston final audit used.
Run with --dry-run to print the batch layout without calling any model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import claude_cli
from boston_area_audit_build import SCHEMA, SYSTEM

HERE = Path(__file__).resolve().parent
REQUEST = HERE / "wne_audit_request.json"
DEFAULT_RESULTS = HERE / "wne_audit_results.json"
DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "medium"
BATCH = 5


def payload_of(batch: list[dict]) -> list[dict]:
    return [{"seq": x["seq"], "name": x["name"], "description": x["description"],
             "address": x["address"], "passages": x["passages"]} for x in batch]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--max-batches", type=int, default=0)
    args = parser.parse_args()
    results_path = Path(args.results)

    raw = REQUEST.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    items = json.loads(raw)["items"]
    if results_path.exists():
        saved = json.loads(results_path.read_text("utf-8"))
        if saved["request_sha256"] != digest:
            raise ValueError("审计输入已变化，旧结果不能续用")
        if saved["model"] != args.model or saved["effort"] != args.effort:
            raise ValueError("结果文件的型号或档位与参数不一致")
    else:
        saved = {"request_sha256": digest, "model": args.model, "effort": args.effort, "batch": BATCH,
                 "items": [], "calls": [], "complete": False}
    done = {x["seq"] for x in saved["items"]}
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
    pending = [b for b in batches if not {x["seq"] for x in b} <= done]
    if args.max_batches:
        pending = pending[:args.max_batches]
    print(f"items {len(items)} | batches {len(batches)} | pending {len(pending)} | "
          f"model {args.model} effort={args.effort} | results {results_path.name}", flush=True)
    if args.dry_run:
        for b in pending:
            print("  seqs", [x["seq"] for x in b], "passages", sum(len(x["passages"]) for x in b), flush=True)
        return

    for batch in pending:
        by_seq = {x["seq"]: x for x in batch}
        answer, usage = claude_cli.ask(SYSTEM, json.dumps(payload_of(batch), ensure_ascii=False), SCHEMA,
                                       model=args.model, effort=args.effort)
        got = sorted(x["seq"] for x in answer["items"])
        if got != sorted(by_seq):
            raise ValueError(f"模型返回的覆盖不完整：应为 {sorted(by_seq)}，实得 {got}")
        for item in answer["items"]:
            source = by_seq[item["seq"]]
            valid = {p["id"] for p in source["passages"]}
            verdict_says_yes = item["supported"] or item["address_supported"]
            if item["passage_ids"] and any(p not in valid for p in item["passage_ids"]):
                item.update(supported=False, address_supported=False,
                            reason="引用了不存在的原文片段。 " + item["reason"])
            elif verdict_says_yes and not item["passage_ids"]:
                item.update(supported=False, address_supported=False,
                            reason="判为支持但未引用原文。 " + item["reason"])
            saved["items"].append({**item, "id": source["id"]})
            done.add(item["seq"])
        saved["calls"].append({"seqs": sorted(by_seq), "usage": usage})
        saved["complete"] = len(saved["items"]) == len(items)
        results_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"checked {len(saved['items'])}/{len(items)}", flush=True)


if __name__ == "__main__":
    main()
