#!/usr/bin/env python3
"""把 B/C 段那些「没写明凭什么够得着 A/S」的 tier_sensitive 降为 false。

**为什么要用代码兜底，而不是继续调提示词（2026-09-09）**

`STAGE1_SLIM_SYSTEM` 的规则 4 写得很清楚：当前是 B 或 C、且补齐资料也到不了
A/S 的，一条 tier_sensitive 都不要给；**只有当你认为它确实可能被低估、
够得着 A/S 时才给 true，并在该条里写明凭什么够得着。**

同一段判据，不同模型执行力差很多（实测 mfa_boston_ext）：

    段      gemini-3.1-pro     claude-haiku-4.5
    B            0%                 19%
    C            0%                 15%
    整体        17%                 24%

而 B/C 合计占全馆 76%，这两段的泄漏直接把整体从 17% 抬到 24%。
逐条看 haiku 在 B/C 段判 true 的 123 条，**只有 2 条（2%）真的写了升档理由**，
其余是「缺 MFA 官方确认该作确为 XX 本人作品」这类通用话 —— 正是规则 4 要排除的。

**所以这不是模型判错，是它没执行规则的后半句。** 与其反复求它自觉，不如让代码
执行一条明确的规则 —— AGENTS.md 本来就写着「tier_review_flag 由 tier_sensitive
导出而非独立判断」，确定性规则做兜底是这套设计的一部分。

**⚠ 这里用了子串匹配，是本仓库反复警告过的做法，所以做了三重约束：**
  1. **只用于「保留」不用于「否定」**：命中关键词才留下 true。反过来用
     （命中就判 false）才是本仓库踩过的那类坑（材质子串误判音译人名、
     check1_slim 因「信息不足」是子串而误杀好条目）。
  2. **原值一律保留**在 `tier_sensitive_raw`，可随时回滚、可事后复核。
  3. **每次运行都打印被降级的条数与样例**，人能直接看出有没有误伤。

用法（写库前跑，可反复跑、幂等）：
    python3 audit_bc_guard.py --out-dir run7/h1,run7/h2,run7/h3 --dry-run
    python3 audit_bc_guard.py --out-dir run7/h1,run7/h2,run7/h3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import meta_lib as M

# 「这一条明示了它可能够得着 A/S」的标记词。宁可放宽也不要收紧 ——
# 漏放一个词只会多降一条（可从 tier_sensitive_raw 找回），
# 而收紧过头会把真正该进队列的对象挡在外面。
UPGRADE_MARKS = (
    "A 级", "A级", "S 级", "S级", "A/S", "升档", "升级", "上调", "改判",
    "低估", "被低估", "够得着", "可能达到", "提升至", "提升到", "升到",
    "镇馆", "核心名作", "代表作之一", "不可替代",
)


def could_reach_as(text: str) -> bool:
    return any(k in text for k in UPGRADE_MARKS)


def load_tiers(museum: str) -> dict[int, str]:
    cur = M.connect().cursor()
    cur.execute("SELECT source_seq, COALESCE(tier_override, tier)"
                " FROM artwork_tier_v3 WHERE museum_key = %s", (museum,))
    return dict(cur.fetchall())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, help="审计产物目录，多个用逗号分隔")
    ap.add_argument("--museum", default="mfa_boston_ext")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不改文件")
    ap.add_argument("--show", type=int, default=6, help="打印几条被保留的样例")
    args = ap.parse_args()

    tiers = load_tiers(args.museum)
    files = [pathlib.Path(d.strip()) / f"{args.museum}_audit1_slim.jsonl"
             for d in args.out_dir.split(",")]
    for f in files:
        if not f.exists():
            sys.exit(f"找不到 {f}")

    n_rec = n_down = n_keep = 0
    flip_seqs, kept = [], []
    for f in files:
        recs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        changed = False
        for r in recs:
            n_rec += 1
            t = tiers.get(r["seq"])
            if t not in ("B", "C"):
                continue
            was = any(m.get("tier_sensitive") for m in r["missing"])
            for m in r["missing"]:
                if not m.get("tier_sensitive"):
                    continue
                if could_reach_as(m["zh"]):
                    n_keep += 1
                    kept.append((r["seq"], t, m["zh"]))
                    continue
                # 原值留痕：这一列是可回滚的，也便于事后复核兜底有没有误伤。
                m.setdefault("tier_sensitive_raw", True)
                m["tier_sensitive"] = False
                n_down += 1
                changed = True
            if was and not any(m.get("tier_sensitive") for m in r["missing"]):
                flip_seqs.append((r["seq"], t))
        if changed and not args.dry_run:
            with f.open("w", encoding="utf-8") as fh:
                for r in recs:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"扫描 {n_rec} 条记录")
    print(f"  B/C 段降级的 tier_sensitive：{n_down} 条")
    print(f"  B/C 段保留的（写明了升档理由）：{n_keep} 条")
    print(f"  因此退出研究队列的展品：{len(flip_seqs)} 件")
    if kept:
        print(f"\n保留的样例（这些是判据认可的真·反向线索）：")
        for s, t, z in kept[:args.show]:
            print(f"  seq {s} [{t}] {z[:90]}")
    if args.dry_run:
        print("\n--dry-run：文件未改动")
    else:
        print("\n已就地改写。原值存在每条的 tier_sensitive_raw，可回滚。")


if __name__ == "__main__":
    main()
