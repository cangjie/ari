#!/usr/bin/env python3
"""逐对确认候选是否同一件实物。走 Claude 订阅账号，不产生 OpenAI 费用。

用法：
    python3 dedupe_confirm.py --limit 8       # 先小批看判得对不对
    python3 dedupe_confirm.py

判据骨架沿用 `merge_confirm.py:24-41`，但**三处必须改**（见 SYS 里的注释）。
所有调用走 `llm_cache.call()`：缓存键含提示词全文，**改一个字就是整批重跑**，
反过来说一字未改就必然命中、不花钱。校验在写缓存之前做 ——
早先有一次模型漏返一个 seq，坏答案照样进了缓存，于是每次重启都命中同一条坏答案。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import audit_meta as A

HERE = pathlib.Path(__file__).parent
CANDS = HERE / "dedupe_cands.json"
HARD = HERE / "dedupe_hard.json"
OUT = HERE / "dedupe_pairs.json"

# 去重用的模型只在 dedupe_llm.MODEL 定义一处（用户 2026-09-17 定：haiku-4.5）
from dedupe_llm import MODEL

SYS = """判断两条博物馆藏品记录是否指向**同一件实物**。

这些记录来自同一个博物馆（波士顿美术馆 MFA）的三批数据，命名风格各不相同：
  · 中文短名，如「雾的警告」「九龙图卷」；
  · 「作者《英文题名》中文题名（年代，材质）」，如「J.M.W. Turner《Slave Ship》奴隶船（1840）」；
  · 「英文题名（作者，ISO 日期，材质）」，如「奴隸船（约瑟夫·马洛德·威廉·透纳，1840-01-01，油彩）」。

**同一件实物在不同批里可能一条是中文名、一条是英文名，两个串没有任何共同字符。**
判断要看的是它指向的实物，不是字面。
例：`Slave Ship` = `奴隸船`；`Red Fuji`（赤富士）= `Fine Wind, Clear Weather`（凯风快晴）——
后者是同一幅北斋版画的两个通行译名。

判 true 的标准：**同一件具体的实物**。作者、题名、年代、材质要能对得上
（允许译名、简繁与格式差异）。

判 false 的情形，**这几类最容易误判，务必分清**：
  · 同一位艺术家的**不同作品**（北斋《神奈川冲浪里》≠ 北斋《凯风快晴（赤富士）》）；
  · 同一题材的**不同件**（两尊不同的观音像、两件不同的青花罐；
    `Untitled`、`Portrait of a Woman`、`Landscape` 这类通用题名尤其危险）；
  · 一件是具体展品、另一件是展厅或专辑（「日本茶室复原空间」不等于任何单件）；
  · 同一作品的**不同版本/摹本**若馆方按两件收藏，也判 false；
  · **作者归属不同即判 false**。两条记录如果给出的作者是不同的人，就算题名与年代一致，
    也判 false，并在 reason 里写明「作者归属存在异说」。

**例外：同一部作品的分件与整体按同一件处理**（用户 2026-09-16 定）。三种都算：
  · 同一套册页/组画的不同分件，例如馆藏号 1986.127.1–.7 的七开册页；
  · **一条指整部作品、另一条指其中某一卷/某一开**，例如
    「平治物语绘卷」与「平治物语绘卷·三条殿夜讨卷」；
  · 同一部作品的不同传本名（「绘巻」与「絵詞」）。
这三种一律判 true，并在 reason 里注明是同组分件或整体/分卷关系。
**这类情形下年代差几十年不构成否决** —— 古代作品的断代本来就有出入
（1275 与 1300 指的可能是同一部 13 世纪绘卷）。

拿不准就判 false —— 误合并会让两件不同的东西的评分与审计数据张冠李戴，
而漏合并只是留下一条重复记录，后者代价小得多。

reason 用中文，一句话说明依据。"""

SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {
        "pair_id": {"type": "integer"},
        "same": {"type": "boolean"},
        "reason": {"type": "string"}},
    "required": ["pair_id", "same", "reason"],
    "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False}


def fmt(pid: int, c: dict) -> str:
    """渲染一对。

    **刻意不把召回分数传给模型**（沿用 `merge_confirm.fmt` 的做法）——
    召回分数不能直接采信：「神奈川冲浪里」会高分召回「赤富士」。
    但**判据本身要给**：作者 QID、年代区间、命中通道，这些是证据不是分数。
    """
    def side(tag):
        nm = c[f"{tag}_name"]
        bits = [f"[{tag}] {nm}"]
        meta = []
        if c.get(f"{tag}_artist"):
            meta.append(f"作者={c[f'{tag}_artist']}")
        if c.get(f"{tag}_creator_qid"):
            meta.append(f"作者QID={c[f'{tag}_creator_qid']}")
        if c.get(f"{tag}_span"):
            lo, hi, ap = c[f"{tag}_span"]
            meta.append(f"年代={'约' if ap else ''}{lo}" + (f"–{hi}" if hi != lo else ""))
        meta.append(f"来源={c[f'{tag}_sub']}")
        if meta:
            bits.append("     " + "，".join(meta))
        return "\n".join(bits)
    ev = c.get("evidence", {})
    return (f"### 对 {pid}\n{side('a')}\n{side('b')}\n"
            f"     命中通道：{'、'.join(c['channels'])}"
            + (f"；年代关系={ev['year']}" if "year" in ev else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--include-review", action="store_true",
                    help="连 ext×ext 那批也送模型（默认只进复核清单）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not CANDS.exists():
        sys.exit(f"缺 {CANDS.name} —— 先跑 dedupe_recall.py")
    cands = json.loads(CANDS.read_text(encoding="utf-8"))
    for n, c in enumerate(cands):
        c["pair_id"] = n
    # ext·wikidata × ext·wikidata **默认不送模型**：两个不同 QID 意味着 Wikidata
    # 认为它们是两个实体；而实测同管线同馆藏号的 38 组里抽查 12/15 是彻底不同的作品
    #（P217 被截断或填错）。这一格价值低、量大（2909 对），送进去是烧钱买噪声。
    # 它们仍然进复核清单，人可以看；只是不由模型下结论。
    n_all = len(cands)
    if not args.include_review:
        cands = [c for c in cands if not c["review_only"]]
        print(f"跳过 ext×ext 只复核的 {n_all - len(cands)} 对（要送模型加 --include-review）")
    if args.limit:
        cands = cands[:args.limit]
    print(f"待确认 {len(cands)} 对（批 {args.batch}，模型 {args.model}）")

    if args.dry_run:
        print("\n--dry-run：提示词样例 —\n")
        print("\n\n".join(fmt(c["pair_id"], c) for c in cands[:3])[:2000])
        return

    # AGENTS.md 硬规矩：审计类一律用 Claude，走本机订阅、不需 API key
    A.CLAUDE_CLI = args.model
    out = []
    for i in range(0, len(cands), args.batch):
        chunk = cands[i:i + args.batch]
        want = {c["pair_id"] for c in chunk}
        user = ("逐对判断下面每一对是否指向同一件实物。\n\n"
                + "\n\n".join(fmt(c["pair_id"], c) for c in chunk))
        d = A.ask(None, args.model, SYS, user, "dedupe_confirm", SCHEMA, None,
                  museum_key="mfa_boston", scope=f"pairs {i}-{i+len(chunk)-1}",
                  validate=lambda r, w=want: w <= {y["pair_id"] for y in r["items"]})
        out += d["items"]
        print(f"  {min(i + args.batch, len(cands))}/{len(cands)}")

    by_id = {c["pair_id"]: c for c in cands}
    pairs = []
    for r in out:
        c = by_id.get(r["pair_id"])
        if not c:
            continue
        pairs.append({**{k: c[k] for k in ("a", "b", "a_row", "b_row", "a_name", "b_name",
                                           "a_sub", "b_sub", "channels", "review_only")},
                      "same": r["same"], "reason": r["reason"]})
    OUT.write_text(json.dumps(pairs, ensure_ascii=False, indent=1), encoding="utf-8")
    yes = sum(1 for p in pairs if p["same"])
    print(f"\n已写出 {OUT.name}：{len(pairs)} 对，判同一件 {yes}，不同 {len(pairs) - yes}")


if __name__ == "__main__":
    main()
