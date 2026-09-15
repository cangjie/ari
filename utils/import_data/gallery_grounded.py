#!/usr/bin/env python3
"""开 Google 搜索工具，逐件查具体展厅号，**只写有出处的**。

用法：
    python3 gallery_grounded.py --dry-run          # 只看选中哪些行、不调 API
    python3 gallery_grounded.py --limit 2          # 先跑 2 件
    python3 gallery_grounded.py                    # S 级在展且没查到展厅的全部

**为什么有这个脚本（2026-09-15）**

`fill_onview_gemini.py` 走的是裸 `generateContent`，**没开任何工具**，模型只能凭记忆答。
实测同一个问题（Homer《The Fog Warning》在哪个展厅）：

  · 不开搜索 → `Gallery 222`，并自称「根据波士顿美术馆的官方馆藏记录」（它没查过任何记录）
  · 开搜索（用户在 Gemini App 里）→ `Gallery 234`

**两个数字不一样，而不开搜索的那个还伪造了出处。** 所以那个脚本的提示词写死「记不准
展厅号就留空」——挡住的正是 `Gallery 222` 这类东西，代价是展厅列大片为空。

本脚本换一条路：**给它检索能力，然后要求出处**。规则只有一条硬的 ——

    **没有 groundingChunks（检索来源）就不写。** 模型凭记忆答出来的一律丢弃。

这跟仓库里反复踩的「取不到就退而求其次」是反着来的：取不到就留空并喊出来。

**结构化输出与搜索工具不能同时用**（responseSchema 会和 tools 冲突），故改为让模型
以 `GALLERY: xxx` 结尾，正则取值；取不到就算失败，不猜。

**证据落仓库**：每次调用的答案原文、解析结果、来源 URL、实际搜索词全部写进
`gallery_grounded.jsonl` —— 抓回来的东西要落进仓库，不能只落进 Excel。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

import openpyxl

HERE = pathlib.Path(__file__).parent
XLSX = HERE / "export" / "展品_波士顿美术馆_合并.xlsx"
OUT = HERE / "gallery_grounded.jsonl"
SHEET = "去重后总表"

MODEL = "gemini-3.5-flash"
ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent")
KEY_FILE = "~/.gemini_key"
MIN_GAP = 8.0          # 秒；带搜索的调用更贵，放慢一点

DEPT_MARK = "部门级"
GALLERY_RE = re.compile(r"GALLERY:\s*(.+?)\s*$", re.I | re.M)
# 只认真正的定位：Gallery + 数字，或 MFA 的命名空间
SPECIFIC_RE = re.compile(
    r"(Gallery\s*\d+[A-Za-z]?)"
    r"|(Sargent\s+(?:Colonnade|Rotunda))"
    r"|(Huntington\s+Avenue\s+Plaza)", re.I)

PROMPT = """请查询波士顿美术馆（Museum of Fine Arts, Boston）这件藏品当前陈列在哪个展厅。

藏品：{name}
{acc}

要求：
1. 用搜索查证，优先采信 mfa.org / collections.mfa.org 的页面。
2. 只有查到**具体展厅**（如 "Gallery 234"）才算数。
   「美洲艺术翼」「古埃及展区」这类是**区域不是展厅**，不算。
3. 查不到具体展厅号就如实说查不到 —— 不要凭印象给一个号。
   给错展厅号的后果是游客走过去扑空，比留空严重得多。

最后另起一行，严格用这个格式收尾（二选一）：
GALLERY: Gallery 234
GALLERY: NONE"""


def source_label(sources: list[dict]) -> str:
    """给来源起个短标签写进单元格。

    ⚠ Gemini 的 groundingChunks.uri 多半是重定向地址
    （vertexaisearch.cloud.google.com/grounding-api-redirect/…），解析主机名得到的
    是 Google 的域名而不是真正的出处。真域名通常在 `title` 里，故优先取 title。
    官方源排在前面，让单元格里一眼看得出可信度。
    """
    titles = [str(s.get("title") or "").strip() for s in sources]
    titles = [t for t in titles if t]
    for t in titles:                       # 官方源优先
        if "mfa.org" in t.lower():
            return t
    if titles:
        return titles[0]
    m = re.search(r"//([^/]+)", sources[0]["uri"])
    return re.sub(r"^www\.", "", m.group(1)) if m else "未知来源"


def key() -> str:
    p = pathlib.Path(KEY_FILE).expanduser()
    if not p.exists():
        sys.exit(f"找不到 {p}")
    return p.read_text().strip()


def ask(name: str, acc, model: str, api_key: str) -> dict:
    """一次带搜索的调用。返回 {text, gallery, sources, queries}。"""
    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT.format(
            name=name,
            acc=f"馆藏号：{acc}" if acc else "（无馆藏号）")}]}],
        "tools": [{"google_search": {}}],
    }
    req = urllib.request.Request(
        ENDPOINT.format(model=model), data=json.dumps(body).encode(),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.load(r)

    cand = resp["candidates"][0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    gm = cand.get("groundingMetadata") or {}
    sources = []
    for c in (gm.get("groundingChunks") or []):
        w = c.get("web") or {}
        if w.get("uri"):
            sources.append({"title": w.get("title"), "uri": w["uri"]})
    m = GALLERY_RE.search(text)
    raw = m.group(1).strip() if m else ""
    sm = SPECIFIC_RE.search(raw)
    return {
        "text": text,
        "gallery_raw": raw,
        "gallery": sm.group(0) if sm else None,
        "sources": sources,
        "queries": gm.get("webSearchQueries") or [],
        "usage": resp.get("usageMetadata"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="S")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(XLSX)
    ws = wb[SHEET]
    hdr = [c.value for c in ws[1]]
    for n in ("Tier", "陈列状态", "展厅", "展品名称", "馆藏号"):
        if n not in hdr:
            sys.exit(f"表头缺列「{n}」")
    c_t, c_s = hdr.index("Tier") + 1, hdr.index("陈列状态") + 1
    c_g, c_n = hdr.index("展厅") + 1, hdr.index("展品名称") + 1
    c_a = hdr.index("馆藏号") + 1

    tiers = {x.strip() for x in args.tier.split(",") if x.strip()}
    todo = []
    for row in range(2, ws.max_row + 1):
        if ws.cell(row, c_t).value not in tiers:
            continue
        if ws.cell(row, c_s).value != "在展":
            continue
        g = str(ws.cell(row, c_g).value or "")
        if g and DEPT_MARK not in g:          # 已有具体展厅的不动
            continue
        todo.append({"row": row, "name": str(ws.cell(row, c_n).value),
                     "acc": ws.cell(row, c_a).value, "cur": g})
    if args.limit:
        todo = todo[:args.limit]

    print(f"待查 {len(todo)} 行（Tier {args.tier}，在展，且未查到具体展厅）")
    for t in todo:
        print(f"  行{t['row']:<6} {t['name'][:46]:<48} 现值={t['cur'][:18] or '空'}")
    if args.dry_run or not todo:
        return

    api_key = key()
    written, nosrc, nogal, failed = [], [], [], []
    last = 0.0
    for t in todo:
        gap = MIN_GAP - (time.time() - last)
        if gap > 0:
            time.sleep(gap)
        last = time.time()
        try:
            r = ask(t["name"], t["acc"], args.model, api_key)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:160]
            print(f"  行{t['row']} 调用失败 HTTP {e.code} {msg}")
            failed.append(t["row"])
            continue
        except Exception as e:
            print(f"  行{t['row']} 调用失败 {type(e).__name__} {str(e)[:120]}")
            failed.append(t["row"])
            continue

        rec = {"row": t["row"], "name": t["name"], "acc": str(t["acc"]),
               "model": args.model, **r}
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        if not r["gallery"]:
            print(f"  行{t['row']} 未查到具体展厅（原文 {r['gallery_raw']!r}）")
            nogal.append(t["row"])
            continue
        if not r["sources"]:
            # 硬规则：没出处就不写，哪怕它给了一个号
            print(f"  行{t['row']} ⚠ 给了 {r['gallery']} 但**没有检索来源**，丢弃")
            nosrc.append(t["row"])
            continue

        ws.cell(t["row"], c_g).value = f"{r['gallery']}（来源：{source_label(r['sources'])}）"
        written.append((t["row"], r["gallery"], len(r["sources"]), t["name"][:34]))
        print(f"  行{t['row']} ✓ {r['gallery']}  来源 {len(r['sources'])} 条")

    print(f"\n写入 {len(written)}｜未查到 {len(nogal)}｜有号无出处丢弃 {len(nosrc)}｜失败 {len(failed)}")
    for row, g, n, nm in written:
        print(f"  行{row:<6} {g:<14} 来源{n}条  {nm}")
    # 只在真有记录时才说写了 —— 全部调用失败时 JSONL 里一条也没有，
    # 这时候打印「证据已写入」就是在报告一件没发生的事。
    if len(written) + len(nogal) + len(nosrc):
        print(f"\n逐条证据已写入 {OUT.name}")

    if not written:
        print("没有任何行被写入，不重存文件。")
        return
    bak = XLSX.with_suffix(".xlsx.bak4")
    if not bak.exists():
        shutil.copy2(XLSX, bak)
        print(f"改动前已备份到 {bak.name}")
    wb.save(XLSX)
    print(f"已写回 {XLSX.name}")


if __name__ == "__main__":
    main()
