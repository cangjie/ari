#!/usr/bin/env python3
"""把 audit_meta.py 的三个 JSONL 写进库。**一列 tier 都不改。**

写 artwork_evidence 的审计列，写 artwork_meta 的 evidence_type / source_quality。
不碰 artwork.tier、artwork_tier_v3 的任何一列，也不碰 artwork_meta 的取值本身
（value_cid / confidence / source 一律不动）。

**故意不提供 --apply-tier 之类的开关。** tier_v3_load.py 有那个开关是因为它的
职责就是落地评级；本脚本的职责是评估证据。审计发现证据不足时该做的是标记
tier_review_flag 交给人看，不是自己动手改级 —— 拿不足的证据去改级，改出来的
还是同样不足的证据支撑的结论。写入前后各拍一次 tier 快照，不一致就整体回滚。

【与 evidence_score.py / evidence_fill.py 的分工】
三个脚本写同一张表的不同列，这是有过教训的：evidence_score.py 早先用先删后插，
把 evidence_fill.py 刚写的可信度与缺失证据一并冲成 NULL，且不报错。所以：

  evidence_score.py  completeness(仅 rule 口径) / potential_ceiling / boundary_prox
                     / research_priority / is_preliminary
  evidence_fill.py   conf_hs..conf_er / missing_evidence / best_source_tier
  本脚本             completeness(audit 口径) / completeness_src / completeness_detail
                     / tier_confidence / potential_tier_low / potential_ceiling
                     / research_priority / is_preliminary / tier_review_flag
                     / review_reason(_en) / missing_evidence(_en) / top_missing(_en)
                     / research_question(_en) / inference_only_survives
                     / audit_notes(_en) / audited_by / audit_round / audited_at

completeness 与 research_priority 由本脚本和 evidence_score.py 共写，靠
completeness_src 分辨所有权：本脚本写完置为 'audit'，evidence_score.py 见到
'audit' 就不再覆盖。改任一方前先读 schema_evidence.sql 里那一列的注释。

用法：
    python3 audit_load.py --museum pem --dry-run
    python3 audit_load.py --museum pem
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import meta_lib as M
from audit_meta import (ITEM_KEYS, TIER_IDX, completeness_of, priority_of, read_done)
# 来源分级是 evidence_score.py 与本脚本共用的，抽在 source_rules.py 里，
# 两边各存一份必然分叉（且不报错）。
from source_rules import SOURCE_RULES, quality_of

AUDIT_COLS = [
    "completeness", "completeness_src", "completeness_detail",
    "potential_ceiling", "potential_tier_low", "research_priority", "is_preliminary",
    "tier_confidence", "tier_review_flag", "review_reason", "review_reason_en",
    "missing_evidence", "missing_evidence_en", "top_missing", "top_missing_en",
    "research_question", "research_question_en",
    "inference_only_survives", "audit_notes", "audit_notes_en",
    "audited_by", "audit_round", "audited_at",
]


def tier_snapshot(cur, mk: str):
    """写入前后各拍一次。tier 若被动了，这里必然对不上，整体回滚。"""
    cur.execute("SELECT a.source_seq, a.tier FROM artwork a"
                " JOIN museum m ON m.id=a.museum_id AND m.key_name=%s"
                " ORDER BY a.source_seq", (mk,))
    art = cur.fetchall()
    cur.execute("SELECT source_seq, tier, tier_override, core FROM artwork_tier_v3"
                " WHERE museum_key=%s ORDER BY source_seq", (mk,))
    return art, cur.fetchall()


def pair(zh, en, what: str, seq) -> None:
    """审计文本成对存列，导出的「零回落」检查照不到它们（见 schema_audit.sql 末注）。
    缺一边这里不拦住，就要等英文版 Excel 里漏出中文时才发现。"""
    if bool(zh) != bool(en):
        raise SystemExit(f"seq {seq} 的 {what} 中英不成对：zh={zh!r} en={en!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", default="pem")
    ap.add_argument("--out-dir", default="./audit_out")
    ap.add_argument("--round", default=dt.date.today().isoformat(),
                    help="审计轮次标识，默认今天")
    ap.add_argument("--audited-by", default="",
                    help="审计者型号；不传则从 JSONL 同目录的 .model 文件读，再没有就报错")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mk = args.museum
    out_dir = Path(args.out_dir)
    s1 = read_done(out_dir / f"{mk}_audit1.jsonl")
    s2 = read_done(out_dir / f"{mk}_audit2.jsonl")
    s3 = read_done(out_dir / f"{mk}_audit3.jsonl", key="ck")
    if not s1:
        sys.exit(f"没有阶段一结果：{out_dir / f'{mk}_audit1.jsonl'} 不存在或为空")

    audited_by = args.audited_by
    if not audited_by:
        mf = out_dir / f"{mk}.model"
        if not mf.exists():
            sys.exit("不知道是谁审的：传 --audited-by <型号>。"
                     "审计者型号必须入库，否则事后无法判断它与打分者是否同源")
        audited_by = mf.read_text(encoding="utf-8").strip()

    conn = M.connect()
    cur = conn.cursor()

    cur.execute("SELECT a.source_seq FROM artwork a"
                " JOIN museum m ON m.id=a.museum_id AND m.key_name=%s", (mk,))
    valid = {r[0] for r in cur.fetchall()}
    unknown = set(s1) - valid
    if unknown:
        sys.exit(f"这些 seq 不在库中：{sorted(unknown)[:20]}")

    cur.execute("SELECT source_seq, core FROM artwork_tier_v3 WHERE museum_key=%s", (mk,))
    cores = {r[0]: float(r[1]) for r in cur.fetchall()}

    before = tier_snapshot(cur, mk)

    # ---------------------------------------------------------------- 对象级
    rows, flagged, prelim_n = [], 0, 0
    for seq, r1 in sorted(s1.items()):
        r2 = s2.get(seq, {})
        grades = {x["key"]: x["grade"] for x in r1["items"]}
        if sorted(grades) != sorted(ITEM_KEYS):
            sys.exit(f"seq {seq} 的 12 项判定不全")
        comp = completeness_of(grades)
        detail = "\n".join(f"{x['key']}|{x['grade']}|{x['note']}" for x in r1["items"])

        # 阶段二看得更细，它的结论覆盖阶段一同名字段
        low = r2.get("potential_low", r1["potential_low"])
        high = r2.get("potential_high", r1["potential_high"])
        if TIER_IDX[low] < TIER_IDX[high]:
            sys.exit(f"seq {seq} 潜在区间方向反了：{low}–{high}")
        conf = r2.get("tier_confidence", r1["tier_confidence"])
        flag = bool(r2.get("review_flag") or r1["review_flag"])
        rr_zh = r2.get("review_reason_zh") or r1["review_reason_zh"]
        rr_en = r2.get("review_reason_en") or r1["review_reason_en"]
        if flag and not rr_zh:
            sys.exit(f"seq {seq} 标了需复核却没有原因")
        pair(rr_zh, rr_en, "复核原因", seq)
        pair(r1["top_missing_zh"], r1["top_missing_en"], "最关键缺失证据", seq)
        pair(r1["research_question_zh"], r1["research_question_en"], "研究问题", seq)
        for m in r1["missing"]:
            pair(m["zh"], m["en"], "缺失证据", seq)

        notes_zh = notes_en = None
        if r2:
            notes_zh = "\n".join(f"{a['q']}|{a['verdict']}|{a['note_zh']}"
                                 for a in r2["answers"])
            notes_en = "\n".join(f"{a['q']}|{a['verdict']}|{a['note_en']}"
                                 for a in r2["answers"])

        prio = priority_of(comp, low, high, cores.get(seq))
        # V3.0 第十二节：证据不足者先记为 Preliminary。阈值与来源等级闸门的状态
        # 沿用 evidence_score.py 的决定（闸门暂不生效，理由见那里的注释）。
        # 注意：is_preliminary 只是「不得直接成为正式 S」的准入标记，
        # 它和 tier_confidence 一样，都不触发任何自动降级。
        prelim = comp < 60
        flagged += flag
        prelim_n += prelim
        rows.append((
            mk, seq,
            round(comp, 2), "audit", detail,
            high, low, round(prio, 2), prelim,
            conf, flag, rr_zh, rr_en,
            "\n".join(m["zh"] for m in r1["missing"]) or None,
            "\n".join(m["en"] for m in r1["missing"]) or None,
            r1["top_missing_zh"], r1["top_missing_en"],
            r1["research_question_zh"], r1["research_question_en"],
            r2.get("inference_only_survives"), notes_zh, notes_en,
            audited_by, args.round, dt.datetime.now(),
        ))

    cur.executemany(
        "INSERT INTO artwork_evidence (museum_key, source_seq, "
        + ", ".join(AUDIT_COLS) + ") VALUES (" + ",".join(["%s"] * (2 + len(AUDIT_COLS)))
        + ") ON DUPLICATE KEY UPDATE "
        + ", ".join(f"{c}=VALUES({c})" for c in AUDIT_COLS),
        rows)
    print(f"artwork_evidence：写入 {len(rows)} 行审计结果"
          f"（需复核 {flagged} 件，Preliminary {prelim_n} 件）")

    # ---------------------------------------------------------------- 逐条 claim
    cur.execute("SELECT DISTINCT source_key FROM artwork_meta WHERE museum_key=%s", (mk,))
    keys = {r[0] for r in cur.fetchall()}
    unknown = keys - set(SOURCE_RULES)
    if unknown:
        # 猜一个来源的性质，就是在替读表的人下他自己该下的判断。
        sys.exit(f"遇到未登记的 source_key {sorted(unknown)}；"
                 "先在 SOURCE_RULES 里写明它是 FACT 还是 INFERENCE、来源有多硬，再重跑")

    # 先按来源整体铺一遍（含 evidence：默认 INFERENCE/weak），
    # 再让阶段三的逐条判定覆盖 evidence 那一批。这样即使阶段三没跑完，
    # sig_* 也不会是「未标注」—— 未标注最危险，读表的人会当成事实。
    n_rule = 0
    for skey, (tier, etype, _why) in SOURCE_RULES.items():
        cur.execute("UPDATE artwork_meta SET evidence_type=%s, source_quality=%s"
                    " WHERE museum_key=%s AND source_key=%s",
                    (etype, quality_of(tier), mk, skey))
        n_rule += cur.rowcount

    n_ai, n_fact = 0, 0
    for rec in s3.values():
        if rec["evidence_type"] == "FACT":
            # 提案第 4 节：Evidence Packet 是容器不是来源。判了 FACT 却只能指回
            # 容器本身，等于什么也没指 —— 这种「来源」正是本轮要拆穿的东西。
            src = (rec["real_source"] or "")
            if not src or src.startswith("Evidence Packet"):
                sys.exit(f"{rec['ck']} 判了 FACT 但来源仍是 Evidence Packet 本身：{src!r}")
            n_fact += 1
        cur.execute("UPDATE artwork_meta SET evidence_type=%s, source_quality=%s"
                    " WHERE museum_key=%s AND source_key='evidence'"
                    " AND source_seq=%s AND key_name=%s",
                    (rec["evidence_type"], rec["source_quality"], mk,
                     rec["seq"], rec["key"]))
        n_ai += 1
    # 这里数的是「判定了多少条」，不是 cur.rowcount。MySQL 的 UPDATE rowcount 只数
    # **值真的变了**的行：上面已按来源把 evidence 整批铺成 INFERENCE/weak，
    # 逐条判定与之相同的那些 rowcount 全是 0，累加出来会得到「117 条只判了 2 条」
    # 这种看着像 bug 的数字，而其实一条没漏。
    print(f"artwork_meta：按来源确定性回填 {n_rule} 条，"
          f"逐条判定 {n_ai} 条（其中 FACT {n_fact} 条）")

    if s3:
        cur.execute("SELECT COUNT(*) FROM artwork_meta WHERE museum_key=%s"
                    " AND evidence_type IS NULL", (mk,))
        left = cur.fetchone()[0]
        if left:
            print(f"[warn] 还有 {left} 条没有 evidence_type —— "
                  f"多半是阶段三没跑完，补跑 audit_meta.py --stage 3")

    # ---------------------------------------------------------------- 断言
    after = tier_snapshot(cur, mk)
    if before != after:
        conn.rollback()
        sys.exit("tier 被改动了！已回滚。审计绝不该写 artwork.tier 或 artwork_tier_v3，"
                 "查本次改动引入了哪条 UPDATE")
    print("断言通过：artwork.tier 与 artwork_tier_v3 逐行未变")

    if args.dry_run:
        conn.rollback()
        print("--dry-run：未写库")
    else:
        conn.commit()
        print("已提交")
    conn.close()


if __name__ == "__main__":
    main()
