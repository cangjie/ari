#!/usr/bin/env python3
"""合并版 MFA 工作簿的路径解析。

**为什么需要它（2026-09-16）**

同一个文件在仓库里有三种写法：`merge_mfa_xlsx.py` 写 `exports/zh-CN/`，
四个在展/展厅脚本读 `export/`（单数），而实际落盘的那份在 `exports/`（根下）。
三者互不相等，且 `export/` 与 `exports/` 都被 gitignore 挡着不随仓库走 ——
**换一台机器，路径就对不上，而脚本要到 `load_workbook` 才炸。**

2026-09-15 写好的 `gallery_grounded.py` 因此一次都没跑成：它在调 API 之前
就死在 FileNotFoundError 上，于是「重新搜索展厅」这件事从未真正发生过，
而现象看起来只是「展厅列还是空的」。

规矩同仓库其余部分：**取不到就喊**，把找过的位置全部打印出来，不猜、不新建。
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).parent
NAME = "展品_波士顿美术馆_合并.xlsx"

# 找过的位置，按优先级。三个都是历史上真实出现过的落点。
CANDIDATES = (
    HERE / "export" / NAME,
    HERE / "exports" / NAME,
    HERE / "exports" / "zh-CN" / NAME,
)


def merged_xlsx() -> pathlib.Path:
    """返回合并版工作簿的实际路径；找不到就退出并列出找过的地方。"""
    found = [p for p in CANDIDATES if p.exists()]
    if not found:
        lines = "\n".join(f"  · {p}" for p in CANDIDATES)
        sys.exit(f"找不到合并版工作簿「{NAME}」。找过这些位置：\n{lines}\n"
                 f"它由 merge_mfa_xlsx.py 生成，且被 .gitignore 挡着不随仓库走。")
    if len(found) > 1:
        # 两份副本必然分叉，改哪一份都是赌。宁可停下来让人删掉一份。
        lines = "\n".join(f"  · {p}  ({p.stat().st_size} 字节)" for p in found)
        sys.exit(f"发现 {len(found)} 份合并版工作簿，无法判断该改哪一份：\n{lines}\n"
                 f"请只保留一份再跑。")
    return found[0]
