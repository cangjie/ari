#!/usr/bin/env python3
"""给审计产出的中文自由文本批量补英译。**补完才能交给 audit_load.py 写库。**

**为什么拆成两步（用户 2026-09-09 定）**

审计原先要模型同时出中英两版。实测 432 件的可见输出里英文占 74.7% 的字符，
而且是**重写不是翻译** —— 每条 missing 中文平均 57 字符、英文 165 字符。
审计要的是判断力，翻译要的是语言能力；让同一次昂贵的推理调用兼做两件事，
等于用审计的单价买翻译。而且恢复双语后实测出现过单次调用超 600 秒的情况。

拆开之后审计只出中文，补译走这里 —— 默认 OpenAI，翻译是廉价任务，
用什么模型都不影响审计结论（判断已经做完了，这一步只换语言）。

**⚠ 这一步不是可选的。** `audit_load.py` 有中英成对的硬校验（`pair()`），
缺一边直接报错退出。那个校验存在的理由是：审计自由文本**不走 `content` 表**
（审计轨迹逐轮重写，灌进内容表既删不掉又要新增 kind），所以导出时的
「零回落」CJK 扫描照不到这几列，只能在写入口拦。

用法：
    python3 audit_translate.py --out-dir run7/h1 --dump            # 看缺多少
    python3 audit_translate.py --out-dir run7/h1 --model <型号>     # 补译并回写

就地改写 JSONL：给每条 missing 补 `en`、给记录补 `top_missing_en` /
`error_note_en`。**已有 en 的一律跳过**，所以可反复跑、可中断续跑。
每批落盘一次，中断了已译的部分不白费。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

SYS = """把博物馆元数据审计的判语从中文译成英文。这是内部工作记录，不是展陈文案。

- **逐条对应**：一条中文出一条英文，不要合并、不要拆分、不要增补原文没有的信息。
- **保持同等篇幅**：原文一句，译文也一句。原文没有展开论证，译文也不要展开。
- 文物术语按行业习惯：「馆藏号」= accession number、「断代」= dating、
  「流传」= provenance、「著录」= catalogue entry、「归属」= attribution、
  「传」= attributed to、「款」= signed。
- 朝代按通行译法：「金代」= Jin dynasty、「北宋」= Northern Song、
  「12 世纪初」= early 12th century。
- 人名、机构名、藏品编号用通行原文拼写；**认不出是谁就保留中文原文** ——
  造一个不存在的拼写比留着中文更糟。

只返回译文，不要加解释。"""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, "en": {"type": "string"}},
        "required": ["i", "en"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}


def collect(recs: list[dict]) -> list[tuple]:
    """收集还缺 en 的中文串 -> [(记录下标, 字段路径, 中文)]。

    字段路径用元组表示，回写时不必再猜结构：
      ("missing", i) / ("top_missing_en",) / ("error_note_en",)
    """
    todo = []
    for ri, r in enumerate(recs):
        for mi, m in enumerate(r.get("missing") or []):
            if m.get("zh") and not m.get("en"):
                todo.append((ri, ("missing", mi), m["zh"]))
        if r.get("top_missing_zh") and not r.get("top_missing_en"):
            todo.append((ri, ("top_missing_en",), r["top_missing_zh"]))
        if r.get("error_note_zh") and not r.get("error_note_en"):
            todo.append((ri, ("error_note_en",), r["error_note_zh"]))
    return todo


def apply_one(rec: dict, path: tuple, en: str) -> None:
    if path[0] == "missing":
        rec["missing"][path[1]]["en"] = en
    else:
        rec[path[0]] = en


def save(path: pathlib.Path, recs: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, help="审计产物目录（可给多个，用逗号分隔）")
    ap.add_argument("--museum", default="mfa_boston_ext")
    ap.add_argument("--provider", choices=["openai", "gemini", "claude_cli"],
                    default="openai", help="默认 openai —— 翻译是廉价任务")
    ap.add_argument("--model", default="", help="OpenAI 型号；不给则取 OPENAI_MODEL")
    ap.add_argument("--key-file", default="~/.openai_key")
    ap.add_argument("--size", type=int, default=40, help="每次请求译多少条")
    ap.add_argument("--dump", action="store_true", help="只报告缺多少，不调 API")
    args = ap.parse_args()

    dirs = [pathlib.Path(d.strip()) for d in args.out_dir.split(",")]
    files = [d / f"{args.museum}_audit1_slim.jsonl" for d in dirs]
    for f in files:
        if not f.exists():
            sys.exit(f"找不到 {f}")

    total = 0
    for f in files:
        recs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        n = len(collect(recs))
        total += n
        print(f"  {f}：{len(recs)} 条记录，待译 {n} 段")
    print(f"合计待译 {total} 段")
    if args.dump or not total:
        return

    import audit_meta as A
    import os
    if args.provider == "gemini":
        import gemini_api
        A.GEMINI = args.model or gemini_api.DEFAULT_MODEL
    elif args.provider == "claude_cli":
        import claude_cli
        A.CLAUDE_CLI = args.model or claude_cli.DEFAULT_MODEL
    model = args.model or os.environ.get("OPENAI_MODEL", "")
    if args.provider == "openai" and not model:
        sys.exit("走 OpenAI 需要 --model，或设环境变量 OPENAI_MODEL")
    client = A.LazyClient(args.key_file)

    for f in files:
        recs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        todo = collect(recs)
        if not todo:
            print(f"{f}：无需补译"); continue
        print(f"{f}：补译 {len(todo)} 段")
        for i in range(0, len(todo), args.size):
            chunk = todo[i:i + args.size]
            # 用序号对齐而不是让模型回抄原文：回抄既费 token，又容易被改动一两个字
            # 而对不上（translate_artwork.py 踩过同样的坑）。
            user = ("逐条译成英文，共 %d 条：\n" % len(chunk)
                    + "\n".join(f"[{j}] {zh}" for j, (_, _, zh) in enumerate(chunk)))
            want = set(range(len(chunk)))
            data = A.ask(client, model, SYS, user, "audit_trans", SCHEMA, None,
                         museum_key=args.museum,
                         scope=f"{f.parent.name} trans {i + 1}-{i + len(chunk)}",
                         validate=lambda d, w=want: w <= {x["i"] for x in d["items"]})
            got = {d["i"]: d["en"] for d in data["items"]}
            for j, (ri, fp, _) in enumerate(chunk):
                apply_one(recs[ri], fp, got[j])
            save(f, recs)          # 每批落盘，中断不白费
            print(f"    {min(i + args.size, len(todo))}/{len(todo)}")
        left = collect(recs)
        print(f"  -> {'仍缺 %d 段' % len(left) if left else '中英已成对'}")

    print("\n补译完成。可以交给 audit_load.py 写库了。")


if __name__ == "__main__":
    main()
