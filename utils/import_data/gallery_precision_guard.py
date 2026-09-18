#!/usr/bin/env python3
"""对照基准工作簿，把展厅列里**被改粗**的行还原。零 API，幂等。

用法：
    python3 gallery_precision_guard.py \
        --baseline "exports/展品_波士顿美术馆_合并.xlsx" \
        --target   "exports/展品_波士顿美术馆_展厅检索.xlsx" --dry-run
    （去掉 --dry-run 才写盘）

**为什么需要它（2026-09-16）**

那一轮让模型补展厅时，选行条件从「状态为空/未知」改成了「展厅不够具体就选」，
于是三百多行**已经有值**的行也被卷了进来；而写入侧仍是无条件覆盖。结果：

  · 73 行从空填上（其中 63 行只到部门级、仅 1 行含展厅号，且全部无出处）
  · **58 行原有值被改写，34 行变差、0 行变好**
    `Level LG, Gallery LG33 — Pre-Columbian Gold` → `Art of the Americas Wing`（丢了真展厅号）
    `Level 1 — Mummies 木乃伊展厅` → `Ancient Egypt`
    `Art of Europe 欧洲艺术（英国绘画）` → `Europe`

**判据是 `gallery_text.precision()` 的四级，不是字符串长度。**
早先我拿「新值比原值短」当变差的判据，那是又一次「拿一列代理另一件事」——
`Gallery 252` 比 `Art of Asia 亚洲艺术（中国绘画）` 短得多，却精确得多。

**行怎么对齐**：按 `(来源表, 来源行)`，不按行号。实测这个键在两份文件里
都是 4537 个、零重复、零缺失。行号在两份文件里目前恰好一致，但那是巧合不是保证 ——
`copy_sheet.py` 的文件头已记：按行号对齐一旦错位，A 件的值会写进 B 件的行且不报错。

**只动展厅列**。陈列状态那一列不在本脚本职责内 —— 它的新旧差异是模型两轮判断不同，
不存在「粒度」可比，该不该回滚是另一个问题。
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

import openpyxl

from gallery_text import precision

SHEET = "去重后总表"
KEY_COLS = ("来源表", "来源行")
COL = "展厅"


def read_rows(path: pathlib.Path) -> dict[tuple, str]:
    """(来源表, 来源行) → 展厅值。键不唯一或缺失就退出，不猜。"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if SHEET not in wb.sheetnames:
        sys.exit(f"{path.name} 里没有 sheet「{SHEET}」")
    ws = wb[SHEET]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    for n in KEY_COLS + (COL,):
        if n not in hdr:
            sys.exit(f"{path.name} 的表头里没有列「{n}」")
    ia, ib, ig = hdr.index(KEY_COLS[0]), hdr.index(KEY_COLS[1]), hdr.index(COL)
    out: dict[tuple, str] = {}
    for n, row in enumerate(it, start=2):
        k = (row[ia], row[ib])
        if k[0] is None or k[1] is None:
            sys.exit(f"{path.name} 第 {n} 行缺少 {KEY_COLS} —— 无法对齐，已中止")
        if k in out:
            sys.exit(f"{path.name} 的键 {k} 重复 —— 无法对齐，已中止")
        out[k] = str(row[ig] or "").strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="原值来源，只读")
    ap.add_argument("--target", required=True, help="要还原的工作簿")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base_p, tgt_p = pathlib.Path(args.baseline), pathlib.Path(args.target)
    base = read_rows(base_p)
    tgt = read_rows(tgt_p)
    only = set(base) ^ set(tgt)
    if only:
        sys.exit(f"两份文件的行键对不上，差异 {len(only)} 个，例：{list(only)[:3]} —— 已中止")

    revert, kept_better, unchanged = [], 0, 0
    for k, old in base.items():
        new = tgt[k]
        if new == old:
            unchanged += 1
            continue
        if precision(new) > precision(old):
            kept_better += 1
        else:
            revert.append((k, old, new))

    print(f"对齐 {len(base)} 行：未变 {unchanged}｜新值更具体（保留新值）{kept_better}｜"
          f"**新值不更具体，应还原** {len(revert)}")
    for k, old, new in revert[:20]:
        print(f"  {k[0]}表第{k[1]}行  p{precision(new)} {new[:26]!r}"
              f"  →还原→  p{precision(old)} {old[:40]!r}")
    if len(revert) > 20:
        print(f"  …… 其余 {len(revert) - 20} 行")
    if args.dry_run or not revert:
        if not revert:
            print("没有需要还原的行。")
        return

    # 写盘：按键定位目标行，不按行号
    wb = openpyxl.load_workbook(tgt_p)
    ws = wb[SHEET]
    hdr = [c.value for c in ws[1]]
    ia, ib, ig = (hdr.index(KEY_COLS[0]) + 1, hdr.index(KEY_COLS[1]) + 1, hdr.index(COL) + 1)
    want = {k: old for k, old, _ in revert}
    done = 0
    for r in range(2, ws.max_row + 1):
        k = (ws.cell(r, ia).value, ws.cell(r, ib).value)
        if k in want:
            ws.cell(r, ig).value = want[k] or None
            done += 1
    if done != len(revert):
        sys.exit(f"只定位到 {done}/{len(revert)} 行 —— 已中止，未写盘")

    bak = tgt_p.with_suffix(".xlsx.bak_precision")
    if not bak.exists():
        shutil.copy2(tgt_p, bak)
        print(f"改动前已备份到 {bak.name}")
    wb.save(tgt_p)
    print(f"已还原 {done} 行并写回 {tgt_p.name}")


if __name__ == "__main__":
    main()
