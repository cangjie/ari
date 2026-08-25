#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻译故宫的 976 段评级理由。

这些理由不是自由散文，而是由分号连接的原子短语拼成的：

    常规展品；同名同型第2件，去重降分 20
    「罗汉像」族第5件，降分 13

按原子翻译再拼回去，比逐段翻译好在三点：
  1. 976 段只需 423 个翻译单位 —— 其中 630 个原子实例落在两个纯数字模板里，
     613 个只用了 45 个族名
  2. 同一个原子在任何一段里译法都一样，不会出现「常规展品」被译成两种说法
  3. 新增展品带来的新组合会自动拼出译文，只有真正的新原子才需要人补

用法：
  python translate_reasons.py --atoms atoms.tsv        # 直接写回 translations_artwork_text.csv
  python translate_reasons.py --atoms atoms.tsv --dry-run

atoms.tsv 每行 `原子<TAB>译文`，另需 families.tsv 给族名译法。
两个词表都随仓库走，见 reason_atoms.tsv / reason_families.tsv。
"""

import argparse
import csv
import os
import re

ATOMS_FILE = "reason_atoms.tsv"
FAMILIES_FILE = "reason_families.tsv"
TARGET_CSV = "translations_artwork_text.csv"
KIND = "artwork_tier_reason"

SPLIT = re.compile(r"[；;]")
# 同名同型第 N 件，去重降分 M
T_DUP = re.compile(r"^同名同型第(\d+)件，去重降分\s*([\d.]+)$")
# 「族名」族第 N 件，降分 M
T_FAM = re.compile(r"^「(.+?)」族第(\d+)件，降分\s*([\d.]+)$")


def ordinal(n):
    n = int(n)
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def load_tsv(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            k, _, v = ln.partition("\t")
            if v:
                out[k.strip()] = v.strip()
    return out


def translate_atom(a, atoms, families):
    """一个原子短语 -> 英文；译不出返回 None。"""
    m = T_DUP.match(a)
    if m:
        return (f"{ordinal(m.group(1))} of an identical type; "
                f"deduplication penalty {m.group(2)}")
    m = T_FAM.match(a)
    if m:
        fam = families.get(m.group(1))
        if not fam:
            return None
        return (f"{ordinal(m.group(2))} in the {fam} family; "
                f"penalty {m.group(3)}")
    return atoms.get(a)


def translate(text, atoms, families):
    parts = []
    for a in SPLIT.split(text):
        a = a.strip()
        if not a:
            continue
        en = translate_atom(a, atoms, families)
        if en is None:
            return None                 # 有一个原子译不出就整段交给人工，不半译
        parts.append(en)
    return "; ".join(parts) + "." if parts else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=TARGET_CSV)
    ap.add_argument("--atoms", default=ATOMS_FILE)
    ap.add_argument("--families", default=FAMILIES_FILE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    atoms = load_tsv(args.atoms)
    families = load_tsv(args.families)
    print(f"词表：原子 {len(atoms)} 条，族名 {len(families)} 条")

    lines = open(args.csv, encoding="utf-8").readlines()
    banner = [l for l in lines if l.lstrip().startswith("#")]
    rows = list(csv.reader([l for l in lines if not l.lstrip().startswith("#")]))
    header, rows = rows[0], rows[1:]

    done = missing = 0
    unknown = set()
    for r in rows:
        if r[0] != KIND:
            continue
        en = translate(r[1], atoms, families)
        if en is None:
            missing += 1
            for a in SPLIT.split(r[1]):
                a = a.strip()
                if a and translate_atom(a, atoms, families) is None:
                    unknown.add(a)
            continue
        if not args.dry_run:
            r[3], r[4] = en, "AI"
        done += 1

    print(f"拼出译文 {done} 段，{missing} 段因有未登记原子而跳过")
    if unknown:
        print(f"  未登记原子 {len(unknown)} 个：{sorted(unknown)[:5]}")

    if args.dry_run:
        return
    with open(args.csv, "w", encoding="utf-8", newline="") as f:
        f.writelines(banner)
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    left = sum(1 for r in rows if not r[2] or not r[3])
    print(f"{args.csv} 仍缺译 {left} 条")


if __name__ == "__main__":
    main()
