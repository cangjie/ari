#!/usr/bin/env python3
"""把 tier_v3.py 的评分结果写入 `artwork_tier_v3`，并可选地刷进 `artwork.tier`。

**必须知道的一件事**

`import_artworks.py` 会 `DELETE FROM artwork` 清空重灌。评分本身存在独立表
`artwork_tier_v3` 里，重灌不受影响；但 `artwork.tier` 会退回源文件的原表评级。
因此：

    每次跑完 import_artworks.py，都要再跑一次本脚本的 --apply-tier，
    否则库里的 tier 就不是 V3.0 的结论了。

建表见 `schema_tier_v3.sql`，算法见 `docs/Ariadne文化遗产Tier算法V3.0.txt`。

数据库口令走 `~/.my.cnf`（权限 600），不写进命令行 —— AGENTS.md 硬性约定。

用法：
    # 只写评分表，先不动 artwork.tier
    python3 tier_v3_load.py --museum pem

    # 写评分表并把 tier 刷进 artwork（会覆盖原表评级）
    python3 tier_v3_load.py --museum pem --apply-tier
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pymysql

from tier_v3 import MUSEUMS, DIMS_WITH_ER, core_of, tier_of, load_items

# 打分者的默认值。tier_v3.py 会把本轮实际用的型号写进 <out-dir>/<museum>.model，
# 有那个文件就以它为准 —— 写死一个型号，换了供应商之后库里记的出处就是假的，
# 而 scored_by 是判断「审计者与打分者是否同源」的唯一依据，写错整条追溯链就断了。
SCORED_BY_DEFAULT = "claude-opus-5"


def read_jsonl(p: Path) -> dict:
    if not p.exists():
        raise SystemExit(f"找不到 {p}，请先跑 tier_v3.py")
    return {r["seq"]: r for r in
            (json.loads(l) for l in p.open(encoding="utf-8") if l.strip())}


def grade(r: dict, g: dict, sn: dict | None) -> tuple[str, str, float, float]:
    """
    一件展品的 CR → Core → Tier。返回 (tier, 理由, cr, core)。

    写库（本文件 main）与变档清单（tier_change_list.py）**共用这一个函数** ——
    两边各算各的，清单上告诉用户的就可能和最后写进库的对不上，而且不报错。
    """
    cr = 0.5 * float(g["Q"]) + 0.3 * float(g["D"]) + 0.2 * float(g["G"])
    core = core_of(r, cr)
    tier, why = tier_of(core, r, sn)
    # V3.0 第十二节：低可信度对象不得直接成为正式 S
    if tier == "S" and r["confidence"] == "low":
        tier = "A"
        why += "；证据可信度 low，按第十二节不得直接定 S"
    return tier, why, cr, core


APPLY_SQL = """
    UPDATE artwork a
      JOIN museum m ON m.id = a.museum_id
      JOIN artwork_tier_v3 v
        ON v.museum_key = m.key_name AND v.source_seq = a.source_seq
       SET a.tier = COALESCE(v.tier_override, v.tier)
     WHERE m.key_name = %s
"""


def apply_only(key: str, dry_run: bool) -> None:
    """重灌展品之后，只把 artwork.tier 刷回评分表已有的结论。

    **不读 JSONL、不动 artwork_tier_v3。** 完整的 --apply-tier 会先按 --out-dir 里的
    JSONL 把该馆评分整批删了重写 —— 那些 JSONL 不进仓库，换台机器要么没有、要么是旧的；
    重写时也不带 tier_override，人工改过的评级会被清空。而重灌后要恢复的只是 artwork.tier
    这一列，评分表本身一行没变（2026-09-24 接伪满皇宫、重灌全库时加的）。
    """
    conn = pymysql.connect(read_default_file=os.path.expanduser("~/.my.cnf"),
                           charset="utf8mb4", autocommit=False)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM artwork_tier_v3 WHERE museum_key = %s", (key,))
    scored = cur.fetchone()[0]
    if not scored:
        raise SystemExit(f"artwork_tier_v3 里没有 {key} 的评分，没有可刷回的结论")
    cur.execute("""SELECT COUNT(*) FROM artwork_tier_v3 v
                    WHERE v.museum_key = %s AND NOT EXISTS (
                          SELECT 1 FROM artwork a JOIN museum m ON m.id = a.museum_id
                           WHERE m.key_name = v.museum_key AND a.source_seq = v.source_seq)""", (key,))
    orphan = cur.fetchone()[0]
    if orphan:
        raise SystemExit(f"{key} 有 {orphan} 条评分在 artwork 里找不到对应 source_seq —— 先查重灌是否错位")
    cur.execute(APPLY_SQL, (key,))
    changed = cur.rowcount
    cur.execute("""SELECT COUNT(*) FROM artwork a JOIN museum m ON m.id = a.museum_id
                     JOIN artwork_tier_v3 v ON v.museum_key = m.key_name AND v.source_seq = a.source_seq
                    WHERE m.key_name = %s AND NOT (a.tier <=> COALESCE(v.tier_override, v.tier))""", (key,))
    left = cur.fetchone()[0]
    if left:
        conn.rollback()
        raise SystemExit(f"{key} 刷完仍有 {left} 件不一致，已回滚")
    print(f"{key}：评分 {scored} 件，artwork.tier 改动 {changed} 行，与评分表逐件一致")
    if dry_run:
        conn.rollback()
        print("--dry-run：已回滚，库未改动")
    else:
        conn.commit()
    conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--museum", required=True, choices=sorted(MUSEUMS))
    ap.add_argument("--out-dir", default="./tier_v3_out")
    ap.add_argument("--apply-tier", action="store_true",
                    help="同时把 tier 刷进 artwork.tier（覆盖原表评级）")
    ap.add_argument("--apply-only", action="store_true",
                    help="重灌展品后用：只把 artwork.tier 刷回评分表已有的结论，"
                         "不读 JSONL、不动 artwork_tier_v3")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不提交")
    args = ap.parse_args()
    if args.apply_only:
        apply_only(args.museum, args.dry_run)
        return

    base = Path(__file__).resolve().parent
    out = Path(args.out_dir)
    m = MUSEUMS[args.museum]

    items = {it["seq"]: it for it in load_items(m, base, None)}
    s1 = read_jsonl(out / f"{m.key}_stage1.jsonl")
    s2 = read_jsonl(out / f"{m.key}_stage2.jsonl")
    s3 = read_jsonl(out / f"{m.key}_stage3.jsonl")

    missing = set(items) - set(s1) or set(items) - set(s2)
    if missing:
        raise SystemExit(f"评分不完整，缺 seq={sorted(missing)[:20]}")

    conn = pymysql.connect(read_default_file=os.path.expanduser("~/.my.cnf"),
                           charset="utf8mb4", autocommit=False)
    cur = conn.cursor()

    # 写库前先确认库里确实有这些 source_seq，避免写入一批对不上任何展品的孤儿评分
    cur.execute("SELECT id FROM museum WHERE key_name = %s", (m.key,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"museum 表里没有 key_name={m.key!r}")
    museum_id = row[0]
    cur.execute("SELECT source_seq FROM artwork WHERE museum_id = %s", (museum_id,))
    in_db = {r[0] for r in cur.fetchall()}
    orphan = set(items) - in_db
    if orphan:
        raise SystemExit(f"库中无对应展品的 source_seq={sorted(orphan)[:20]}")
    print(f"{m.label}：评分 {len(items)} 件，库中 {len(in_db)} 件，source_seq 全部对得上")

    mf = out / f"{m.key}.model"
    scored_by = mf.read_text(encoding="utf-8").strip() if mf.exists() else SCORED_BY_DEFAULT
    print(f"打分者：{scored_by}" + ("" if mf.exists() else "（无 .model 文件，用默认值）"))

    rows, dist = [], {}
    for seq in sorted(items):
        r, g = s1[seq], s2[seq]
        tier, why, cr, core = grade(r, g, s3.get(seq))
        dist[tier] = dist.get(tier, 0) + 1
        sn = s3.get(seq)
        rows.append((
            m.key, seq, r["object_type"], r["peer_group"],
            r["HS"], r["IU"], r["VI"], r["VA"], r["CE"], r.get("ER", 0),
            g["Q"], g["D"], g["G"], round(cr, 3), round(core, 3),
            tier, why[:255],
            sn["q1"] if sn else None, sn["q2"] if sn else None, sn["q3"] if sn else None,
            r["confidence"], r.get("evidence"), g.get("cr_reason"),
            sn.get("sness_reason") if sn else None, scored_by,
        ))

    cur.execute("DELETE FROM artwork_tier_v3 WHERE museum_key = %s", (m.key,))
    cur.executemany(
        "INSERT INTO artwork_tier_v3 (museum_key, source_seq, object_type, peer_group,"
        " hs, iu, vi, va, ce, er, q, d, g, cr, core, tier, tier_reason,"
        " sness_q1, sness_q2, sness_q3, confidence, evidence, cr_reason,"
        " sness_reason, scored_by)"
        " VALUES (" + ",".join(["%s"] * 25) + ")", rows)
    print(f"artwork_tier_v3 写入 {cur.rowcount} 行  {dict(sorted(dist.items()))}")

    if args.apply_tier:
        cur.execute(APPLY_SQL, (m.key,))
        print(f"artwork.tier 覆盖 {cur.rowcount} 行")

    if args.dry_run:
        conn.rollback()
        print("\n--dry-run：已回滚，库未改动")
    else:
        conn.commit()
        print("\n已提交")
    conn.close()


if __name__ == "__main__":
    main()
