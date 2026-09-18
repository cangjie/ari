#!/usr/bin/env python3
"""展厅文本的判据：这一格的定位精确到什么程度。

`gallery_grounded.py` 与 `fill_onview_gemini.py` 共用。**两边各存一份必然分叉，
且不报错** —— 同 `museum_context.py` 的道理。

**四级粒度**（`precision()`）：

| 级 | 含义 | 例 |
|---|---|---|
| 3 | 含展厅号 | `Gallery 234`、`252 印象派`、`日本艺术 215`、`Gallery LG33`、`地下层31 日本版画` |
| 2 | 翼楼/部门 + 楼层 | `Art of the Americas Wing, Level 2`、`Level 1 — Ancient Egypt`、`二层 中国艺术` |
| 1 | 只到部门/翼楼 | `Art of the Americas Wing`、`Europe`、`Art of Asia` |
| 0 | 空 | |

**为什么要分级，而不是只判空/非空**（2026-09-16 实测，代价是 34 行数据）：
合并表的展厅列是自由文本、66 种写法。那一轮让模型补展厅时，选行用的是「非空就算有」，
写入却是**无条件覆盖**，于是 58 行原有值被模型的粗答案改写 —— 34 行变差、0 行变好。
`Level LG, Gallery LG33 — Pre-Columbian Gold` 被改成 `Art of the Americas Wing`（丢了真展厅号）、
`Level 1 — Mummies 木乃伊展厅` 被改成 `Ancient Egypt`、
`Art of Europe 欧洲艺术（英国绘画）` 被改成 `Europe`。
换来的 73 行里 63 行只到部门级、仅 1 行含展厅号，且全部无出处 —— **这笔交易是亏的**。

所以写入方一律用：**`precision(新) > precision(原)` 才写，相等或更低保留原值。**
平手时原值赢 —— 原值来自源数据/官网，有出处；模型答案没有。

**楼层里的数字不算展厅号** —— 否则 `Level 2 — Arts of Japan` 会因为那个 2 被判成
已有具体展厅。这是本仓库反复踩的「拿一列代理另一件事」的同一个形状。

**厅号不一定以数字开头**：`Gallery LG33`（Lower Ground 33）就带字母前缀。
早先的 `CELL_NUM_RE` 要求数字开头，漏判了它，正是上面行 50 丢失展厅号的直接原因。
"""
from __future__ import annotations

import re

DEPT_MARK = "部门级"
SUFFIX = "（部门级，未确认具体展厅）"

# 真正的定位：Gallery + 号（数字，或 LG/B 这类字母前缀），以及 MFA 的具名空间
SPECIFIC_RE = re.compile(
    r"(Gallery\s*[A-Za-z]{0,3}\d+[A-Za-z]?)"
    r"|(Sargent\s+(?:Colonnade|Rotunda))"
    r"|(Huntington\s+Avenue\s+Plaza)", re.I)
# 裸写的厅号：`252 印象派`、`日本艺术 215`。必须先扣掉楼层再匹配。
CELL_NUM_RE = re.compile(r"\b\d{2,4}[A-Za-z]?\b")
# 楼层说法。`Level LG` / `Level B1` 也是楼层，不是厅号。
FLOOR_RE = re.compile(
    r"Level\s*(?:\d+|LG|B\d*)\b|^\s*[一二三四]层|地下层|Lower\s+Ground", re.I)


def precision(cell) -> int:
    """定位精度，0–3。见模块文档的四级表。"""
    cell = str(cell or "").strip()
    if not cell:
        return 0
    # 显式标注过「未确认具体展厅」的，按定义够不到 3 级
    marked = DEPT_MARK in cell
    cell = cell.replace(SUFFIX, " ")

    if SPECIFIC_RE.search(cell):
        return 2 if marked else 3
    stripped = FLOOR_RE.sub(" ", cell)
    has_floor = stripped != cell
    if CELL_NUM_RE.search(stripped):
        return 2 if marked else 3
    return 2 if has_floor else 1


def is_specific(cell) -> bool:
    """单元格里有没有能让游客走过去的定位（= 精度 3 级）。"""
    return precision(cell) >= 3


def better(new, old) -> bool:
    """新值该不该覆盖旧值。**相等或更低一律不覆盖** —— 原值有出处，模型答案没有。"""
    return precision(new) > precision(old)
