#!/usr/bin/env python3
"""把人工/模型撰写的 Evidence Packet 写入 artwork_meta 与 artwork_evidence。

依据 docs/Metadata Enrichment Pipeline 提案.md 第 8 节。

数据放在 evidence_data_<museum>.py 里，一个 PACKETS 字典，形如：

    PACKETS = {
      seq: {
        "sig": {"sig_historical": ("中文一句", "English sentence"), ...},
        "conf": {"hs": "high", "iu": "medium", ...},      # 逐维度证据可信度
        "missing": ["还缺什么", ...],                      # 提案第 3 节
        "source_tier": 4,                                  # 提案第 4 节
      }, ...
    }

**source_tier 要如实填。** 提案第 4 节规定 Tier 4（Wikipedia 及一般网络资料，
以及未经核实的汇编）不足以单独支撑 S。填高了等于把这条闸门废掉。

用法：
    python3 evidence_fill.py --museum pem --dry-run
    python3 evidence_fill.py --museum pem
"""
from __future__ import annotations

import argparse
import importlib

import meta_lib as M

CONF_DIMS = ("hs", "iu", "vi", "va", "ce", "cr", "er")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--museum", default="pem")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mod = importlib.import_module(f"evidence_data_{args.museum}")
    packets = mod.PACKETS

    conn = M.connect()
    cur = conn.cursor()
    mk = args.museum

    cur.execute("SELECT source_seq FROM artwork a JOIN museum m ON m.id=a.museum_id"
                " WHERE m.key_name=%s", (mk,))
    valid = {r[0] for r in cur.fetchall()}
    unknown = set(packets) - valid
    if unknown:
        raise SystemExit(f"这些 seq 不在库中：{sorted(unknown)[:20]}")

    cache, n_sig = {}, 0
    for seq, pk in sorted(packets.items()):
        for key, (zh, en) in pk["sig"].items():
            M.set_meta(cur, mk, seq, key, [(zh, en)], source_key="evidence",
                       source=f"Evidence Packet source_tier={pk['source_tier']}",
                       confidence=pk.get("field_conf", "medium"),
                       filled_by="claude-opus-5", cache=cache)
            n_sig += 1
        conf = pk.get("conf", {})
        cur.execute(
            "UPDATE artwork_evidence SET "
            + ", ".join(f"conf_{d}=%s" for d in CONF_DIMS)
            + ", missing_evidence=%s, best_source_tier=%s, generated_by='claude-opus-5'"
              " WHERE museum_key=%s AND source_seq=%s",
            tuple(conf.get(d) for d in CONF_DIMS)
            + ("\n".join(pk.get("missing", [])) or None, pk["source_tier"], mk, seq))

    print(f"{mk.upper()}：{len(packets)} 件 Evidence Packet，写入 significance 取值 {n_sig} 条")
    print(f"  新建值内容 {len(cache)} 段")

    if args.dry_run:
        conn.rollback(); print("--dry-run：未写库")
    else:
        conn.commit(); print("已提交")
    conn.close()


if __name__ == "__main__":
    main()
