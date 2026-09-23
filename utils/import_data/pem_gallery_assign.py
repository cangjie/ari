#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「按官网栏目推断出来的展厅」写进 `artwork_meta`。**零 API。**

    python3 pem_gallery_assign.py --dry-run
    python3 pem_gallery_assign.py

**这个脚本写的不是事实，是推断。** 由「这件东西登在官网哪个栏目页上」推出
「它在哪个展厅」—— 栏目说的是**门类**，展厅是**房间**。用户 2026-09-21 知情后
授权批量做，条件是单独成列、标明未证实。所以：

  · 只写 `artwork_meta` 的 `gallery_inferred` 键，`source_key='pem_section'`，
    由 `source_rules` 定为 Tier 4 / INFERENCE / weak；
  · **绝不写 `artwork.gallery_id`** —— 那一列只装有出处的归属
    （在展原句直接点名、或展览页写明「Located in the X.」，都已由导入器写好）；
  · 展品**已经有**带出处的 `gallery_id` 时，这里一条都不写。有证据就不必猜，
    而把猜的和查的并排放着，下一个读的人分不清哪个是哪个。

反例就在数据里：`korean-art` 栏目按门类指向俞吉濬展厅，可该栏目里每一条有在展
原文的记录写的都是「Salem Stories」或「Garden Atrium」—— 馆方自己的陈述与栏目
推断打架。这正是两者必须分开存放的理由。

判据全部在 `pem_gallery_data.SECTION_MAP`：17 个栏目逐个登记，能映射的只有 5 个，
其余显式写 None。**没登记的栏目会抛 KeyError** —— 官网加了新栏目要被发现。
"""

from __future__ import annotations

import argparse
import sys

import meta_lib as M
import pem_ext_data as E
import pem_gallery_data as G
from source_rules import SOURCE_RULES, quality_of

KEY = "gallery_inferred"
SOURCE_KEY = "pem_section"
MUSEUM = "pem"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写库")
    args = ap.parse_args()

    tier, etype, _why = SOURCE_RULES[SOURCE_KEY]
    quality = quality_of(tier)
    if etype != "INFERENCE":
        sys.exit(f"[fatal] {SOURCE_KEY} 在 source_rules 里登记成了 {etype}。"
                 f"这一列是推断，登记成 FACT 会让它被当证据读。")

    conn = M.connect()
    cur = conn.cursor()

    # 哪些展品已经有带出处的展厅 —— 这些一条都不碰
    cur.execute("""SELECT a.source_seq FROM artwork a
                   JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
                   WHERE a.gallery_id IS NOT NULL""", (MUSEUM,))
    has_sourced = {r[0] for r in cur.fetchall()}

    todo, skipped_have, skipped_nomap = [], 0, 0
    for r in E.ITEMS:
        sec = r.get("section")
        if not sec:                       # Wikidata 来源的行没有栏目
            continue
        dest = G.SECTION_MAP[sec]         # 没登记就抛，由上面的 docstring 解释为什么
        if dest is None:
            skipped_nomap += 1
            continue
        if r["seq"] in has_sourced:
            skipped_have += 1
            continue
        todo.append((r["seq"], sec, dest))

    print(f"新增展品里有栏目的：{sum(1 for r in E.ITEMS if r.get('section'))} 件")
    print(f"  栏目指不到具体展厅，跳过      {skipped_nomap}")
    print(f"  已有带出处的展厅，不覆盖      {skipped_have}")
    print(f"  写入 {KEY}（推断）            {len(todo)}")
    if todo:
        import collections
        for g, n in collections.Counter(d for _, _, d in todo).most_common():
            print(f"      {n:>3}  {g}")

    if args.dry_run:
        print("\n--dry-run，未写库")
        return
    if not todo:
        print("\n没有可写的行")
        return

    zh_of = {g["name_en"]: g["name_zh"] for g in G.GALLERIES}
    M.ensure_key(cur, KEY, "推断展厅（未证实）", "Inferred gallery (unverified)",
                 note="由官网栏目归属推断，非馆方陈述；有出处的展厅在 artwork.gallery_id")
    n = 0
    for seq, sec, dest in todo:
        n += M.set_meta(
            cur, MUSEUM, seq, KEY, [(zh_of[dest], dest)],
            source_key=SOURCE_KEY,
            source=f"https://www.pem.org/the-pem-collection/{sec}",
            confidence="low", filled_by="rule",
            evidence_type=etype, source_quality=quality)
    conn.commit()
    print(f"\n已写入 {n} 行（{KEY} / {SOURCE_KEY} / {etype} / {quality} / confidence=low）")
    print("记得重跑 evidence_score.py --museum pem —— best_source_tier 按库里实际来源重算")


if __name__ == "__main__":
    main()
