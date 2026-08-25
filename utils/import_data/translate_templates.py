#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻译 tier_reason / change_reason 中的模板串。

这两个字段里 860/960 条不是散文，而是机器生成的定长模板：

    强项:<维度><分数>、<维度><分数>;弱项:<维度><分数>。<可选尾注>

模板串该由程序翻译而不是手译：词汇表只有 11 个维度词 + 5 种尾注，
审一遍这 16 个词就等于审完全部 860 条，且每条译文完全一致，不会出现
同一个维度在不同条目里被译成两种说法。剩下的 100 条散文仍需人工翻译。

用法：
  python translate_templates.py            # 直接写回 translations_text.csv
  python translate_templates.py --tsv out.tsv   # 只导出 TSV，不改 CSV

维度词与 schema.sql 中 dim1-dim6 的列注释一一对应，改这里请同步改那边。
"""

import argparse
import csv
import re

TARGETS = ("tier_reason", "change_reason")

# 与 schema.sql 的 dim1..dim6 注释对齐：前六个是博物馆赛道，后五个是遗址地赛道
DIMENSIONS = {
    "藏品世界唯一性": "Collection Uniqueness",
    "文明叙事完整度": "Narrative Completeness",
    "学术与国际影响力": "Scholarly & International Influence",
    "国际认知指数": "International Recognition Index",
    "展陈与公众体验": "Display & Visitor Experience",
    "规模与保障": "Scale & Resources",
    "原真性与完整性": "Authenticity & Integrity",
    "文明地位(OUV)": "Civilizational Significance (OUV)",
    "现场震撼度": "On-site Impact",
    "阐释与配套": "Interpretation & Facilities",
    "保存状况与可达性": "Conservation & Accessibility",
}

TAILS = {
    "": "",
    "现状:战乱损毁或不可安全参观(总分×0.88)。":
        " Status: damaged by conflict or not safely visitable (total score ×0.88).",
    "现状:准入受限/原件不可见(总分×0.92)。":
        " Status: restricted access / originals not on view (total score ×0.92).",
    "现状:闭馆改造/主体不可见(总分×0.80)。":
        " Status: closed for renovation / main structure not viewable (total score ×0.80).",
    "与同城条目重复,不占 S 级名额。":
        " Duplicates another entry in the same city; does not occupy an S-tier slot.",
    "(按机构层级与榜单信号的默认参数估分)":
        " (scored with default parameters derived from institutional tier and ranking signals)",
}

TEMPLATE = re.compile(r"^强项:(.+?)([\d.]+)、(.+?)([\d.]+);弱项:(.+?)([\d.]+)。(.*)$")


def translate(key):
    """模板串 -> 英文；不是模板串则返回 None。"""
    m = TEMPLATE.match(key)
    if not m:
        return None
    d1, s1, d2, s2, d3, s3, tail = m.groups()
    for d in (d1, d2, d3):
        if d not in DIMENSIONS:
            return None            # 出现没登记的维度词，交给人工，不硬译
    if tail not in TAILS:
        return None                # 出现没登记的尾注，同上
    return (f"Strengths: {DIMENSIONS[d1]} {s1}, {DIMENSIONS[d2]} {s2}; "
            f"Weakness: {DIMENSIONS[d3]} {s3}.{TAILS[tail]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="translations_text.csv")
    ap.add_argument("--tsv", help="只导出 TSV 而不改写 CSV")
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8") as f:
        lines = f.readlines()
    banner = [ln for ln in lines if ln.lstrip().startswith("#")]
    rows = list(csv.reader([ln for ln in lines if not ln.lstrip().startswith("#")]))
    header, rows = rows[0], rows[1:]

    done = skipped = 0
    out = []
    for r in rows:
        kind, key = r[0], r[1]
        if kind not in TARGETS:
            continue
        en = translate(key)
        if en is None:
            skipped += 1
            continue
        out.append((kind, key, en))
        if not args.tsv:
            r[3], r[4] = en, "官方"   # 模板串译文是确定性的，非猜测
        done += 1

    print(f"模板串 {done} 条已翻译，{skipped} 条非模板需人工翻译")

    if args.tsv:
        with open(args.tsv, "w", encoding="utf-8") as f:
            for kind, key, en in out:
                f.write(f"{kind}\t{key}\t{en}\t官方\n")
        print(f"已导出 {args.tsv}")
        return

    with open(args.csv, "w", encoding="utf-8", newline="") as f:
        f.writelines(banner)
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    todo = sum(1 for r in rows if not r[2] or not r[3])
    print(f"{args.csv} 仍缺译 {todo} 条")


if __name__ == "__main__":
    main()
