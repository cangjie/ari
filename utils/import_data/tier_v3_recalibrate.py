#!/usr/bin/env python3
"""一次性脚本：把 PEM 试点的评分换算到 tier_v3.py 新增的分档锚点上。

**为什么存在这个脚本**

2026-08-28 的 PEM 试点在 `tier_v3.py` 尚未写入分档锚点时完成。那一轮的
**序关系**是逐个 Peer Group 横向比较得出的，并通过了 D 跨度检验（68 个多件组
中 55 组跨度 ≥2.0），这部分可信；出问题的是**序关系到分值的换算**：当时把
「良好精品」记作 6.5，而锚点规定该水位是 7，整条标尺在中段被压低了约半分。

后果是实测出来的：全维度统一 +0.75，「132/196 件要改」变成「24/196 件要改」。
换句话说，未加锚点时得到的「V3.0 与原表大幅分歧」这个结论，测的是标尺位置，
不是算法分歧。

**本脚本做什么，不做什么**

做：按下表把旧分值单调映射到锚点刻度。映射保序，因此 Peer Group 内部的相对
    关系（尤其是 D 的拉开程度）原样保留。
不做：不重新判断任何一件展品。它不是重评，是换算。

**其余五馆不该用这个脚本。** 它们应当直接对着 `tier_v3.py` 里的锚点评分。
本脚本只为让试点数据与新锚点对齐，跑过一次即完成使命。

用法：
    python3 tier_v3_recalibrate.py --out-dir ./tier_v3_out --museum pem
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

# 旧分值 -> 锚点分值。中段抬升最多（+0.5），两端收窄：
# 顶端本就贴着「世界级顶点」，底端本就贴着「残件/量产品」，都不需要挪。
#
# 下段必须一路铺到 0：D 在「同名同型第 2 件」这类重复件上会低到 2.0，
# 若曲线止于 4.0，这些值会被钳平，防重复机制刚拉开的差距当场消失
# （首次实现就踩了这个坑，保序检查报出 2621 处序关系翻转）。
CURVE = [
    (0.0, 0.0),
    (2.0, 2.0),
    (3.0, 3.0),
    (4.0, 4.0),
    (4.5, 4.6),
    (5.0, 5.3),
    (5.5, 5.9),
    (6.0, 6.5),
    (6.5, 7.0),
    (7.0, 7.5),
    (7.5, 8.0),
    (8.0, 8.5),
    (8.5, 8.9),
    (9.0, 9.2),
    (9.5, 9.6),
    (10.0, 10.0),
]


def remap(v: float) -> float:
    """分段线性插值，保序。超出端点则钳到端点。"""
    if v <= CURVE[0][0]:
        return CURVE[0][1]
    if v >= CURVE[-1][0]:
        return CURVE[-1][1]
    for (x0, y0), (x1, y1) in zip(CURVE, CURVE[1:]):
        if x0 <= v <= x1:
            t = (v - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 2)
    raise AssertionError(f"曲线未覆盖 {v}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="./tier_v3_out")
    ap.add_argument("--museum", default="pem")
    args = ap.parse_args()

    out = Path(args.out_dir)
    # ER 只在 node/site 上有意义，object 恒为 0，映射时必须跳过，
    # 否则 remap(0) 会把它抬成 4.0，凭空给单件展品加上 ER 分。
    fields = {
        "stage1": ["HS", "IU", "VI", "VA", "CE"],
        "stage2": ["Q", "D", "G"],
    }

    for stage, keys in fields.items():
        p = out / f"{args.museum}_{stage}.jsonl"
        if not p.exists():
            raise SystemExit(f"找不到 {p}")
        bak = p.with_suffix(".jsonl.pre_anchor")
        if not bak.exists():
            shutil.copy2(p, bak)          # 原始判断留底，可回溯
        recs = [json.loads(l) for l in bak.open(encoding="utf-8") if l.strip()]
        for r in recs:
            for k in keys:
                r[k] = remap(float(r[k]))
            if stage == "stage1" and r.get("object_type") != "object":
                r["ER"] = remap(float(r["ER"]))
        with p.open("w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{p.name}: {len(recs)} 条已换算（原始留底 {bak.name}）")

    print("\nstage3 是布尔判断，不涉及分值，未改动。")


if __name__ == "__main__":
    main()
