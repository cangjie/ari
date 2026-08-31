#!/usr/bin/env python3
"""计算 Metadata Completeness 与 Research Priority，写入 artwork_evidence。

依据 docs/Metadata Enrichment Pipeline 提案.md 第 2、5、6 节。

**Completeness（提案第 2 节）**
八个权重桶，按桶内字段的填充比例加权求和，满分 100。它回答的不是「这件东西
重不重要」，而是「我知不知道它是否重要」—— 20/100 的含义是后者。

**Research Priority（提案第 6 节，公式已改）**
原式为 Potential Importance × Missing Information × Probability of Tier Change。
第三项有循环：研究结果尚未发生，无从知道 tier 会不会变，而这正是要用它来决定
的事。且三项连乘，任一项为 0 即整体归零。改用：

    Research Priority = Ceiling × (1 − Completeness/100) × BoundaryFactor × 10

  Ceiling         现有证据支持的最高可能等级（S=1.0 A=0.75 B=0.45 C=0.2），
                  表达「最多能到哪」，而非「会不会变」
  1 − Completeness 缺得越多越值得查
  BoundaryFactor  Core 距最近门槛越近越值得查。实测 PEM 有 28 件距门槛 0.2 以内，
                  猎巫审判手稿差 0.003 落在 A —— 这批的 research ROI 最高

三项都能从现有数据直接算出，不需要先知道研究结果。

**本脚本量的是填充率，不是完备度。** 它只看 key 在不在 artwork_meta 里，不看
取值质量，也不认「这一项对该对象不适用」。PEM 实测中位 1.1/100 —— 那个数字的
含义是「196 件里绝大多数只有 object_form 一个键」，不是「这批东西没有价值」。
真正的完备度判定在 audit_meta.py：12 项逐项判 full/partial/none/na，na 从分母剔除。

**已审计的行本脚本一律跳过。** completeness / potential_ceiling / research_priority
/ is_preliminary 四列由两个脚本共写，靠 completeness_src 分辨所有权：
audit 口径的行归 audit_load.py，本脚本不碰。这不是洁癖 —— 早先本脚本用先删后插，
把 evidence_fill.py 刚写的可信度与缺失证据一并冲成 NULL 且不报错，
下次查询时才发现全变 NULL。同一张表多个写入者，职责必须互斥。

用法：
    python3 evidence_score.py --museum pem --dry-run
    python3 evidence_score.py --museum pem
"""
from __future__ import annotations

import argparse
import collections

import meta_lib as M
from source_rules import SOURCE_RULES

# 提案第 2 节的八个桶 -> 库中对应的 meta_key。权重合计 100。
BUCKETS = [
    ("基本身份/年代/作者", 10, ["object_form", "period", "date_text", "artist", "maker",
                                "material", "dimensions", "accession_no", "origin_place"]),
    ("Historical significance",    15, ["sig_historical"]),
    ("Art/Cultural significance",  15, ["sig_art_historical", "sig_cultural"]),
    ("Rarity / Uniqueness",        15, ["sig_rarity"]),
    ("Provenance",                 10, ["provenance", "sig_provenance", "acquisition"]),
    ("Institutional significance", 15, ["sig_institutional"]),
    ("Category context",           10, ["sig_category"]),
    ("Visitor/visual",             10, ["sig_visual", "sig_relations"]),
]
assert sum(w for _, w, _ in BUCKETS) == 100, "权重合计必须为 100"

CEILING = {"S": 1.0, "A": 0.75, "B": 0.45, "C": 0.2}
THRESHOLDS = (8.5, 7.2, 5.5)


def boundary_factor(core: float | None) -> tuple[float, float | None]:
    """离最近门槛越近，越值得研究。返回 (系数, 距离)。

    距离 0 -> 1.0；距离 >= 1.0 -> 0.2。中间线性。没有 Core 的对象按中性 0.5。
    """
    if core is None:
        return 0.5, None
    d = min(abs(core - t) for t in THRESHOLDS)
    return (max(0.2, 1.0 - 0.8 * min(d, 1.0)), d)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--museum", default="pem")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = M.connect()
    cur = conn.cursor()
    mk = args.museum

    cur.execute("SELECT source_seq FROM artwork a JOIN museum m ON m.id=a.museum_id"
                " WHERE m.key_name=%s", (mk,))
    seqs = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT source_seq, key_name, source_key FROM artwork_meta"
                " WHERE museum_key=%s", (mk,))
    have = collections.defaultdict(set)
    src_tier = {}
    for s, k, sk in cur.fetchall():
        have[s].add(k)
        t = SOURCE_RULES.get(sk, (4, "", ""))[0]
        src_tier[s] = min(src_tier.get(s, 9), t)     # 等级数字越小越权威

    # 当前 tier 与 Core 来自 V3.0 评分表；没跑过评分的馆两列为空，按中性处理
    cur.execute("SELECT source_seq, tier, core FROM artwork_tier_v3 WHERE museum_key=%s", (mk,))
    scored = {r[0]: (r[1], float(r[2])) for r in cur.fetchall()}

    # 已被 audit_meta.py 审过的行，这四列归 audit_load.py，本脚本不碰
    cur.execute("SELECT source_seq FROM artwork_evidence"
                " WHERE museum_key=%s AND completeness_src='audit'", (mk,))
    audited = {r[0] for r in cur.fetchall()}

    rows, dist = [], collections.Counter()
    for s in seqs:
        if s in audited:
            continue
        comp = sum(w * (sum(1 for k in keys if k in have[s]) / len(keys))
                   for _, w, keys in BUCKETS)
        tier, core = scored.get(s, (None, None))
        bf, bd = boundary_factor(core)
        # 尚未做 significance 研究时，用当前 tier 作为 ceiling 的下限估计：
        # 证据不足只可能低估，不会高估，故 ceiling 至少等于当前 tier。
        ceiling = tier
        prio = CEILING.get(ceiling, 0.45) * (1 - comp / 100) * bf * 10
        # V3.0 第十二节：证据不足者一律先记为 Preliminary。
        #
        # 【来源等级闸门暂不生效 —— 2026-08-30 用户决定】
        # 提案第 4 节规定 Tier 4 来源（Wikipedia 及一般网络资料、未经核实的汇编）
        # 不足以单独支撑 S。PEM 全部 196 件目前只能标 Tier 4：官方藏品门户
        # explore-art.pem.org 已停服，official_url 为 0/196，外部可核实的仅 3 件。
        # 若此刻就执行闸门，196 件会被一刀切成 Preliminary，本轮实验将测不出
        # 「是算法的问题还是 metadata 的问题」—— 而那正是做这轮实验的目的。
        # 故 best_source_tier 只记录不阻断；等拿到 Tier 1–2 来源后再启用。
        # 启用方式：把下面这行改成
        #     prelim = comp < 60 or (best_source_tier or 4) >= 4
        prelim = comp < 60
        dist[int(comp // 10) * 10] += 1
        rows.append((mk, s, round(comp, 2), ceiling,
                     round(bd, 3) if bd is not None else None,
                     round(prio, 2), prelim))

    print(f"{mk.upper()} {len(rows)} 件按规则计分"
          + (f"，{len(audited)} 件已审计（归 audit_load.py，跳过）" if audited else ""))
    if not rows:
        # 全馆都审过时这里没有可算的行，不是出错。硬往下走会在 comps[0] 上 IndexError，
        # 报出来的还是个跟真实原因毫无关系的错。
        print("没有需要按规则计分的行，退出。")
        conn.close()
        return

    print(f"\nCompleteness 分布：")
    for b in sorted(dist):
        print(f"  {b:3d}–{b+9:3d} 分  {dist[b]:4d} 件  {'█' * int(dist[b] / 4)}")
    comps = sorted(r[2] for r in rows)
    print(f"  最低 {comps[0]:.1f} / 中位 {comps[len(comps)//2]:.1f} / 最高 {comps[-1]:.1f}")

    top = sorted(rows, key=lambda r: -r[5])[:15]
    print(f"\nResearch Priority 最高的 15 件（最该先查的）：")
    cur.execute("""SELECT a.source_seq, t.text FROM artwork a
        JOIN museum m ON m.id=a.museum_id AND m.key_name=%s
        JOIN content_text t ON t.content_id=a.name_cid AND t.lang='zh-CN'""", (mk,))
    names = dict(cur.fetchall())
    print(f"  {'prio':>5s} {'完备度':>6s} {'tier':>4s} {'距门槛':>6s}  名称")
    for _, s, comp, tier, bd, prio, _p in top:
        print(f"  {prio:5.2f} {comp:6.1f} {str(tier):>4s} "
              f"{(f'{bd:.3f}' if bd is not None else '—'):>6s}  {names.get(s,'')[:34]}")

    # 只更新本脚本负责的列，不能 DELETE+INSERT。
    # artwork_evidence 由两个脚本分工写：本脚本算 completeness / priority / ceiling，
    # evidence_fill.py 写逐维度可信度、missing_evidence、best_source_tier。
    # 早先这里用的是先删后插，结果把 evidence_fill 刚写的那几列一并冲掉，
    # 且不报错 —— 只是下次查询时它们全变成 NULL。
    cur.executemany(
        "INSERT INTO artwork_evidence (museum_key, source_seq, completeness,"
        " potential_ceiling, boundary_prox, research_priority, is_preliminary, generated_by)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,'rule')"
        " ON DUPLICATE KEY UPDATE completeness=VALUES(completeness),"
        " potential_ceiling=VALUES(potential_ceiling), boundary_prox=VALUES(boundary_prox),"
        " research_priority=VALUES(research_priority), is_preliminary=VALUES(is_preliminary)",
        rows)
    print(f"\nartwork_evidence 写入 {len(rows)} 行")

    # best_source_tier：按库里**实际存在**的来源重算，只升不降。
    #
    # 这一列原本只由 evidence_fill.py 从 evidence_data_pem.py 里写死的 source_tier 填。
    # 那批数字是写 packet 那天的判断，后来抓到 PEM 官网栏目页（Tier 1）之后没人回头改
    # —— 2026-08-31 实测 seq 2/5/6/7/9 明明有 pem_official 的官网编目字段，
    # best_source_tier 却还停在 4 或 3。审计读这一列，等于被喂了过时的输入。
    #
    # 用 LEAST 只升不降：若 packet 里记的来源比 artwork_meta 里能看到的更权威
    # （譬如查过纸质图录，没落成 metadata 取值），不该被这里冲掉。
    if src_tier:
        cur.executemany(
            "UPDATE artwork_evidence SET best_source_tier ="
            " LEAST(COALESCE(best_source_tier, 9), %s)"
            " WHERE museum_key=%s AND source_seq=%s",
            [(t, mk, s) for s, t in sorted(src_tier.items())])
        cur.execute("SELECT best_source_tier, COUNT(*) FROM artwork_evidence"
                    " WHERE museum_key=%s GROUP BY best_source_tier"
                    " ORDER BY best_source_tier", (mk,))
        dist_t = cur.fetchall()
        print("best_source_tier 重算后：" + "  ".join(
            f"Tier {t if t is not None else '—'}: {n} 件" for t, n in dist_t))

    if args.dry_run:
        conn.rollback(); print("--dry-run：未写库")
    else:
        conn.commit(); print("已提交")
    conn.close()


if __name__ == "__main__":
    main()
