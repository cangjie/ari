#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段二「单件组合批」的 A/B：合批问会不会改变结果。

    python3 stage2_singleton_ab.py --museum pem --stage1 run11/tier_pem/pem_stage1.jsonl \\
        --model gpt-5.6-luna --k 20 --out-dir run11/stage2_ab

**为什么要做。** PEM 全馆 467 件经 luna 阶段一后分成 354 个 peer group，其中 287 个
是单件组（81%）。阶段二逐组发请求要 354 次调用，而单件组根本没有组内对象可比
（STAGE2_SYSTEM：「D 按『本馆此类唯一』判断」）—— 每次都只为一件东西付一份
约 7k token 的 agent 脚手架。合批能把 287 次压到十几次。

**为什么不能直接合。** 「分批只是调度，绝不能进入算法」（AGENTS.md 第 10 条，
用户 2026-09-05 当场否过一次）。合批的风险是**同一次收到的几件互相影响**。

**判据（2026-09-22 跑之前写死，不许事后调）。** 早先说的「逐字节一致」做不到：
模型输出本身不确定，同一个单件组逐组问两遍都未必相同 —— 拿一个连对照组自己都
过不了的标准去卡实验组，结论只能是「永远不通过」，等于没有判据。改为量噪声底：

    臂      做法                                          调用
    逐组    K 个单件组各问一次（正式跑本就要问，提示词与正式跑逐字节相同，结果直接复用）  K
    合批×2  同样 K 件合成一次问，问两遍（第二遍 refresh 绕过缓存）            2

    通过 ⇔ 对 Q、D、G 每一项：
      ① |平均(合批 − 逐组)| ≤ 0.25                    —— 没有系统性抬高或压低
      ② 平均|合批 − 逐组| ≤ 1.5 × max(平均|合批 − 合批|, 0.25)  —— 差异不超出模型自身波动
    （② 的下限 0.25：0–10 分制上平均差不到 0.375 分，实质就是取整噪声；
      不设下限的话，两遍合批碰巧完全一致就会让任何差异都判失败。）

**计量缺口**：第二遍合批与第一遍的缓存键相同，`llm_call` 的写入是
`ON DUPLICATE KEY UPDATE id = id`，所以第二遍的答案与 token **不会落进 llm_call**。
两遍的答案都存在 `<out-dir>/ab.json` 里。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import tier_v3 as T

COMP = ("Q", "D", "G")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", default="pem")
    ap.add_argument("--stage1", required=True, help="阶段一 JSONL（取 peer_group 与已评维度）")
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--k", type=int, default=20, help="取多少个单件组做实验")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()

    import audit_meta as A
    import codex_cli
    if not codex_cli.available():
        sys.exit("找不到 codex")
    # 与 tier_v3 main 的 codex_cli 分支完全相同的设置 —— 逐组那一臂的缓存键
    # 必须与正式跑一致，否则「结果直接复用」就是一句空话
    efforts = {st: A.norm_effort(T.STAGE_EFFORT[st]) for st in T.STAGE_EFFORT}
    T.CODEX_CLI = (a.model, efforts)

    m = T.MUSEUMS[a.museum]
    items = T.load_items(m, Path(__file__).resolve().parent, None)
    by_seq = {it["seq"]: it for it in items}
    s1 = {}
    for line in open(a.stage1, encoding="utf-8"):
        r = json.loads(line)
        s1[r["seq"]] = r
    evidence = T.load_evidence(m.key)

    groups = {}
    for seq, r in s1.items():
        groups.setdefault(r["peer_group"], []).append(seq)
    singles = sorted(((g, v[0]) for g, v in groups.items() if len(v) == 1),
                     key=lambda x: x[1])
    pairs = singles[:a.k]
    print(f"单件组 {len(singles)} 个，取 seq 最小的 {len(pairs)} 个做实验")
    want = {s for _, s in pairs}

    # —— 逐组 ——
    single = {}
    for i, (g, s) in enumerate(pairs, 1):
        d = T.ask(None, T.STAGE2_SYSTEM, T.stage2_user(m, g, [s], by_seq, s1, evidence),
                  T.STAGE2_SCHEMA, stage="tier_stage2", museum_key=m.key,
                  scope=f"{g}（1 件）", seqs=[s],
                  validate=lambda d, s=s: s in {r["seq"] for r in d["results"]})
        single[s] = next(r for r in d["results"] if r["seq"] == s)
        print(f"  逐组 {i}/{len(pairs)}")

    # —— 合批 × 2 ——
    user = T.stage2_user_merged(m, pairs, by_seq, s1, evidence)
    val = lambda d: want <= {r["seq"] for r in d["results"]}      # noqa: E731
    merged = []
    for rep in (False, True):
        d = T.ask(None, T.STAGE2_SYSTEM, user, T.STAGE2_SCHEMA, stage="tier_stage2",
                  museum_key=m.key, scope=f"A/B 合批 {len(pairs)} 件"
                  + ("（第二遍）" if rep else ""), seqs=sorted(want),
                  validate=val, refresh=rep)
        merged.append({r["seq"]: r for r in d["results"] if r["seq"] in want})
        print(f"  合批第 {'二' if rep else '一'}遍 完成")

    # —— 判定 ——
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ab.json").write_text(json.dumps(
        {"pairs": pairs, "single": single, "merged1": merged[0], "merged2": merged[1]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    S = [s for _, s in pairs]
    f = lambda d, s, c: float(d[s][c])                               # noqa: E731
    ok_all = True
    print(f"\n{'':4}{'合批−逐组 平均':>14}{'合批−逐组 平均绝对':>18}{'合批−合批 平均绝对':>18}{'②阈值':>8}  判定")
    for c in COMP:
        dm = [f(merged[0], s, c) - f(single, s, c) for s in S]
        nn = [abs(f(merged[0], s, c) - f(merged[1], s, c)) for s in S]
        bias, mad, noise = statistics.mean(dm), statistics.mean(abs(x) for x in dm), statistics.mean(nn)
        thr = 1.5 * max(noise, 0.25)
        ok = abs(bias) <= 0.25 and mad <= thr
        ok_all &= ok
        print(f"  {c}{bias:>+14.2f}{mad:>18.2f}{noise:>18.2f}{thr:>8.2f}  {'通过' if ok else '不通过'}")
    cr = lambda d, s: 0.5 * f(d, s, "Q") + 0.3 * f(d, s, "D") + 0.2 * f(d, s, "G")  # noqa: E731
    dcr = [cr(merged[0], s) - cr(single, s) for s in S]
    ncr = [abs(cr(merged[0], s) - cr(merged[1], s)) for s in S]
    print(f"\n  CR（真正进 Core 的那个数）：合批−逐组 平均 {statistics.mean(dcr):+.2f}、"
          f"平均绝对 {statistics.mean(abs(x) for x in dcr):.2f}；合批−合批 平均绝对 {statistics.mean(ncr):.2f}")
    print(f"  CR 在 Core 里的权重是 0.10，所以 CR 差 1 分 = Core 差 0.1 分")
    print(f"\n结论：{'✅ 通过 —— 单件组可以合批' if ok_all else '❌ 不通过 —— 单件组仍逐组发请求'}")
    print(f"逐件结果存于 {out / 'ab.json'}")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
