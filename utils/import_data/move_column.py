#!/usr/bin/env python3
"""把工作簿某个 sheet 里的一列整体挪到另一列前面。按列名操作，不按列号。

用法：
    python3 move_column.py --xlsx A.xlsx --sheet 去重后总表 --col 官方展厅 --before 展厅

**为什么按列名**：合并表有 106 列，列号会随任何一次增删整体平移；
仓库里其它脚本也一律 `hdr.index("列名")` 取列。按列号挪，下次就对不上了。

**行序绝对不能变** —— 在展/展厅那几个脚本按 xlsx 行号定位（`序号` 在合并表里不唯一），
行序一乱，A 件的答案就会落到 B 件的行上且不报错。故逐行按原顺序重写，
写完断言行列数与原表一致，不一致就中止且不落盘。
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

import openpyxl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--col", required=True, help="要挪动的列名")
    ap.add_argument("--before", required=True, help="挪到这一列的前面")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = pathlib.Path(args.xlsx)
    if not path.exists():
        sys.exit(f"文件不存在：{path}")

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if args.sheet not in wb.sheetnames:
        sys.exit(f"没有 sheet「{args.sheet}」，现有：{wb.sheetnames}")
    ws = wb[args.sheet]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    for n in (args.col, args.before):
        if n not in hdr:
            sys.exit(f"表头里没有列「{n}」")
    src, dst = hdr.index(args.col), hdr.index(args.before)
    if src == dst:
        sys.exit("两个列名相同")

    order = [i for i in range(len(hdr)) if i != src]
    order.insert(order.index(dst), src)          # 插到目标列之前
    print(f"「{args.col}」第 {src+1} 列 → 挪到「{args.before}」(第 {dst+1} 列) 之前")
    print("挪动后前 8 列：", [hdr[i] for i in order[:8]])
    if args.dry_run:
        return

    out = openpyxl.Workbook()
    nws = out.active
    nws.title = args.sheet
    nws.append([hdr[i] for i in order])
    n_rows = 1
    for row in it:
        row = list(row) + [None] * (len(hdr) - len(row))
        nws.append([row[i] for i in order])
        n_rows += 1
    nws.freeze_panes = "A2"

    if (n_rows, len(hdr)) != (ws.max_row, ws.max_column):
        sys.exit(f"维度对不上：原 {ws.max_row}×{ws.max_column}，新 {n_rows}×{len(hdr)} —— 已中止，未落盘")

    bak = path.with_suffix(".xlsx.bak_movecol")
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f"改动前已备份到 {bak.name}")
    out.save(path)
    print(f"已写回 {path.name}：{n_rows} 行 × {len(hdr)} 列，行序不变")


if __name__ == "__main__":
    main()
