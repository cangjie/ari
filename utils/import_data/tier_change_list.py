#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
写库之前的「旧件变档清单」：新一轮评级会让哪些现有展品换档、为什么。

    python3 tier_change_list.py --museum pem --new run11/tier_pem --out run11/tier_changes_pem.csv

用户 2026-09-21 定：接受旧件变档，**但写库前要出清单给人看过**。

「旧」取库里现存的 `artwork_tier_v3`（即当前线上的结论），「新」取 --new 目录的
三个阶段产物。两边的档位都由 `tier_v3_load.grade()` 算 —— 与写库同一个函数，
所以清单上说的就是写进库的。

**主因推断**（只对换档的展品）：构造一个反事实 —— 新的阶段一分数 + 旧的 CR：
  · 反事实已经等于新档位   → 主因是**阶段一换了打分者**（维度分变了）
  · 反事实仍等于旧档位     → 主因是**阶段二**（重新分组 / 组里进了新成员 / 组内比较）
  · 都不等                 → 两者共同作用
这是推断不是证明：两个阶段的变化并非严格可加，阶段三（S-ness）也会参与。
所以列名写的是「主因推断」，并把各维度的分差一并列出，让读的人自己看。
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import meta_lib as M
from tier_v3_load import grade, read_jsonl

ORDER = ["S", "A", "B", "C"]
DIMS = ("HS", "IU", "VI", "VA", "CE")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", default="pem")
    ap.add_argument("--new", required=True, help="新一轮 tier_v3 的 out-dir")
    ap.add_argument("--excel-rows", type=int, default=196,
                    help="源 Excel 的件数；seq 大于它的是本轮新增展品，没有「旧档」")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    mk, new = a.museum, Path(a.new)
    n1, n2, n3 = (read_jsonl(new / f"{mk}_stage{i}.jsonl") for i in (1, 2, 3))
    miss = set(n1) - set(n2)
    if miss:
        sys.exit(f"新一轮阶段二还缺 {len(miss)} 件（如 {sorted(miss)[:5]}），先跑完再出清单")

    cur = M.connect().cursor()
    cur.execute("""SELECT v.source_seq, v.tier, v.core, v.cr, v.peer_group,
                          v.HS, v.IU, v.VI, v.VA, v.CE, v.scored_by, tn.text
                   FROM artwork_tier_v3 v
                   JOIN museum m ON m.key_name = v.museum_key
                   JOIN artwork a ON a.museum_id = m.id AND a.source_seq = v.source_seq
                   JOIN content_text tn ON tn.content_id = a.name_cid AND tn.lang = 'en'
                   WHERE v.museum_key = %s""", (mk,))
    old = {r[0]: dict(zip(("tier", "core", "cr", "pg", *DIMS, "by", "name"), r[1:]))
           for r in cur.fetchall()}
    cur.execute("""SELECT a.source_seq, tn.text FROM artwork a
                   JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
                   JOIN content_text tn ON tn.content_id = a.name_cid AND tn.lang = 'en'""", (mk,))
    names = dict(cur.fetchall())

    # 新组里有没有本轮新增的展品 —— 判断「组里进了新成员」的客观依据
    members = {}
    for s, r in n1.items():
        members.setdefault(r["peer_group"], []).append(s)

    rows, moves, cause = [], Counter(), Counter()
    for s in sorted(n1):
        t_new, _, cr_new, core_new = grade(n1[s], n2[s], n3.get(s))
        o = old.get(s)
        grp = members[n1[s]["peer_group"]]
        has_new = any(x > a.excel_rows for x in grp)
        row = {
            "seq": s, "名称": names.get(s, ""),
            "旧档": o["tier"] if o else "（新增）", "新档": t_new,
            "旧 Core": round(float(o["core"]), 2) if o else "",
            "新 Core": round(core_new, 2),
            "ΔCR": round(cr_new - float(o["cr"]), 2) if o else "",
            **{f"Δ{d}": round(float(n1[s][d]) - float(o[d]), 1) if o else "" for d in DIMS},
            "旧组": o["pg"] if o else "", "新组": n1[s]["peer_group"],
            "新组件数": len(grp), "新组含新增展品": "是" if has_new else "",
            "主因推断": "",
        }
        if o:
            moves[(o["tier"], t_new)] += 1
            if o["tier"] != t_new:
                # 反事实：新阶段一 + 旧 CR。旧 CR 由旧 Q/D/G 算出，这里直接用库里存的 cr，
                # 为此构造一个 Q=D=G=旧 cr 的阶段二行 —— CR 公式对它恒等于旧 cr。
                cr_old = float(o["cr"])
                fake = {"Q": cr_old, "D": cr_old, "G": cr_old}
                t_cf = grade(n1[s], fake, n3.get(s))[0]
                if t_cf == t_new:
                    why = "阶段一换了打分者"
                elif t_cf == o["tier"]:
                    why = "阶段二：重新分组" + ("、组里进了新成员" if has_new else "")
                else:
                    why = "两者共同作用"
                row["主因推断"] = why
                cause[why] += 1
        rows.append(row)

    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        # 换档的排前面（降档在前），其余按 seq
        key = lambda r: (r["旧档"] == r["新档"] or r["旧档"] == "（新增）",  # noqa: E731
                         -(ORDER.index(r["新档"]) - ORDER.index(r["旧档"]))
                         if r["旧档"] in ORDER else 0, r["seq"])
        for r in sorted(rows, key=key):
            w.writerow(r)

    olds = [r for r in rows if r["旧档"] in ORDER]
    down = sum(1 for r in olds if ORDER.index(r["新档"]) > ORDER.index(r["旧档"]))
    up = sum(1 for r in olds if ORDER.index(r["新档"]) < ORDER.index(r["旧档"]))
    print(f"原有 {len(olds)} 件：降档 {down}、升档 {up}、不变 {len(olds) - down - up}")
    print("档位移动（旧 → 新）：")
    for (o_, n_), c in sorted(moves.items(), key=lambda x: (ORDER.index(x[0][0]), ORDER.index(x[0][1]))):
        print(f"   {o_} → {n_} {c:>4}{'' if o_ == n_ else ('  ↓' if ORDER.index(n_) > ORDER.index(o_) else '  ↑')}")
    print("换档主因推断：", dict(cause))
    print("新增展品的档位分布：",
          dict(Counter(r["新档"] for r in rows if r["旧档"] == "（新增）")))
    print("全馆新档位分布：", dict(Counter(r["新档"] for r in rows)))
    print(f"\n清单 -> {a.out}（换档的排在最前）")


if __name__ == "__main__":
    main()
