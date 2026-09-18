#!/usr/bin/env python3
"""给「作者没解析出来」的行补作者与年代。haiku-4.5，约 9 次调用。

用法：
    python3 dedupe_extract.py --dry-run
    python3 dedupe_extract.py

**为什么需要**：去重按「作者 + 时期」分组（用户 2026-09-17 定：
重复只可能发生在同一作者同一时期的作品之间），作者缺失的行进不了任何组。

实测作者未知的 600 行里：
  · 348 行是**真佚名**（Wikidata 给的是匿名创作者节点，或根本没有作者属性）→ 不用抽
  · 150 行原清单、102 行官网 —— **简介里其实写着作者**：
    `和服女子`「莫奈绘妻子身穿日本和服…」、`九龙图卷`「南宋陈容《九龙图》…」。
    规则抽取漏掉它们，是因为防误判要求中文名 ≥3 字，而**莫奈、陈容都是两个字**。
    放宽长度会撞上音译人名（AGENTS.md：子串匹配撞上音译人名就是灾难），
    所以这 252 行交给模型读。

模型只负责**读出**作者名，**不负责判断**是不是同一个人 ——
读出的名字仍要落到 Wikidata 创作者 QID 上才算数（见 dedupe_recall.build）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import dedupe_llm as LLM
import dedupe_recall as R

HERE = pathlib.Path(__file__).parent
FACTS = HERE / "dedupe_facts.json"
OUT = HERE / "dedupe_extract.json"
BATCH = 30

SYS = """从博物馆藏品记录里读出**创作者**与**年代**。

每条给出：名称、简介，有时还有英文名。逐条回答：
  · author_en：创作者的**英文通行全名**（如 Claude Monet、Chen Rong、Paul Revere、
    Emperor Huizong of Song）。只写**具名的个人**。
    佚名、某文化/某作坊/某国工匠、「古埃及雕刻家」这类，一律填空字符串 ""。
  · author_zh：创作者的中文名（没有就填 ""）。
  · date_text：记录里写到的年代原文（如「1885 年」「南宋」「12 世纪初」「古王国第四王朝」），
    没写就填 ""。**不要自己推断年代。**

只读记录里写了的，不要凭常识补。例如名称是「睡莲」但简介没提作者，就填 ""。"""

SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {
        "row": {"type": "integer"},
        "author_en": {"type": "string"},
        "author_zh": {"type": "string"},
        "date_text": {"type": "string"}},
    "required": ["row", "author_en", "author_zh", "date_text"],
    "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="exports/展品_波士顿美术馆_展厅检索.xlsx")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    raw = {r["_row"]: r for r in R.load_rows(args.xlsx)}
    items = R.build(list(raw.values()), facts, R.load_en_bridge())
    todo = [i for i in items if not i["creator_qid"] and i["sub"] in ("原清单", "ext·官网")]
    print(f"待抽作者：{len(todo)} 行（原清单 {sum(1 for i in todo if i['sub']=='原清单')}，"
          f"官网 {sum(1 for i in todo if i['sub']=='ext·官网')}）→ {-(-len(todo)//BATCH)} 次调用，"
          f"模型 {LLM.MODEL}")

    def line(i):
        r = raw[i["row"]]
        en = [x for x in i["en_raw"] if x != i["name"]]
        return (f"[{i['row']}] 名称：{i['name'][:120]}\n"
                + (f"      英文名：{en[0][:100]}\n" if en else "")
                + f"      简介：{str(r.get('展品简介') or '')[:160]}")

    if args.dry_run:
        print("\n样例：\n" + "\n".join(line(i) for i in todo[:4]))
        return

    out, hit = {}, 0
    for k in range(0, len(todo), BATCH):
        chunk = todo[k:k + BATCH]
        want = {i["row"] for i in chunk}
        user = "逐条读出下列记录的创作者与年代：\n\n" + "\n".join(line(i) for i in chunk)
        r, cached = LLM.ask(SYS, user, SCHEMA, stage="dedupe_extract",
                            scope=f"rows {k}-{k+len(chunk)-1}",
                            validate=lambda d, w=want: w <= {x["row"] for x in d["items"]})
        hit += cached
        for x in r["items"]:
            if x["row"] in want:
                out[x["row"]] = x
        print(f"  {min(k + BATCH, len(todo))}/{len(todo)}" + ("（缓存）" if cached else ""))

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    named = sum(1 for x in out.values() if x["author_en"] or x["author_zh"])
    dated = sum(1 for x in out.values() if x["date_text"])
    print(f"\n已写出 {OUT.name}：{len(out)} 行，读出作者 {named}，读出年代 {dated}"
          f"（缓存命中 {hit} 批）")


if __name__ == "__main__":
    main()
