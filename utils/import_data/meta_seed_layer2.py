#!/usr/bin/env python3
"""灌入 Layer 1 补充字段与 Layer 2（Significance）证据字段的键。

依据 docs/Metadata Enrichment Pipeline 提案.md 第 1 节的三层划分：

    Layer 1  事实字段     —— 尽量来自官方数据库，不让模型「创作」
    Layer 2  significance —— 算法真正要读的资料，本文件的重点
    Layer 3  游客介绍     —— 由前两层生成的 output，不作为评分输入

**Layer 2 的九个字段与 V3.0 七维是一一对应的证据，不是新的打分维度。**
换句话说这不是重新设计 tier 公式，而是给现有公式换掉输入：过去是让模型读一段
500 字 description 凭感觉打分，现在是让它读结构化证据再打分。对应关系写在每个
键的 note 里，改键时务必同步，否则打分环节会找不到证据。

新增键不必改本脚本，直接往 meta_key 插行即可；此处只是这一批的定义。

用法：
    python3 meta_seed_layer2.py --dry-run
    python3 meta_seed_layer2.py
"""
from __future__ import annotations

import argparse

import meta_lib as M

# (key_name, 中文, English, note)
# note 里的「→ XX」标明该证据服务于 V3.0 的哪个维度
LAYER1_EXTRA = [
    ("acquisition",   "入藏方式",   "Acquisition",        "捐赠/购藏/发掘调拨及年份"),
    ("object_id",     "对象编号",   "Object ID",          "馆方内部编号，区别于 accession_no"),
    ("maker",         "制作者/作坊", "Maker",             "非艺术家署名的工匠或作坊"),
]

LAYER2 = [
    ("sig_historical",   "历史意义",       "Historical Significance",
     "→ HS。它在历史事件、制度或文明进程中的位置"),
    ("sig_art_historical", "艺术史地位",   "Art Historical Significance",
     "→ HS。开创性、工艺难度、在艺术史叙述中的位置"),
    ("sig_rarity",       "稀缺性与独特性", "Rarity and Uniqueness",
     "→ IU 与 CR 的 D。存世量、同类比较、是否孤品"),
    ("sig_institutional","本馆身份意义",   "Institutional Significance",
     "→ IU（单件展品权重最高 25%）。失去它本馆身份是否受损"),
    ("sig_category",     "类别代表性",     "Category Importance",
     "→ CR。在本馆同类对象中是否为最值得选出的代表"),
    ("sig_cultural",     "文化与叙事价值", "Cultural Context",
     "→ CE。能否解释一个时代、文明、制度、信仰或事件"),
    ("sig_provenance",   "流传与入藏意义", "Provenance Significance",
     "→ 无直接对应维度，作为 HS/IU 的佐证。递藏链是否本身构成价值"),
    ("sig_visual",       "视觉与现场体验", "Visual and Experiential Features",
     "→ VI 与 VA。尺度、材质观感、现场感染力、对外行的吸引力"),
    ("sig_relations",    "与他物及场地关系", "Relationships to Objects and Site",
     "→ ER。与轴线、地形、仪式路径、成组器物的关系；单件展品常为空"),
]

# 建筑/遗址/景观专用（提案第 7 节）。单件展品用不上，但故宫、颐和园、婆罗浮屠
# 进库时必须有 —— 那类对象不能用 Artist / Material / Dimensions 描述。
LAYER2_SITE = [
    ("site_spatial",     "空间关系",       "Spatial Relationship",     "→ ER"),
    ("site_corridor",    "视线与景观通廊", "Visual Corridor",          "→ ER"),
    ("site_sequence",    "仪式或游览序列", "Processional Sequence",    "→ ER"),
    ("site_human_nature","人与自然的结合", "Human-Nature Integration", "→ ER"),
    ("site_integrity",   "完整性",         "Integrity",                "→ 遗产价值证据与审核字段，不等同于游客吸引力"),
    ("site_authenticity","真实性",         "Authenticity",             "→ 同上"),
    ("site_setting",     "周边环境与背景", "Setting",                  "→ ER"),
    ("site_history",     "建造与改造史",   "Construction History",     "提案新增"),
    ("site_function",    "功能",           "Function",                 "提案新增"),
    ("site_symbolism",   "象征意义",       "Symbolic Meaning",         "提案新增"),
    ("site_viewpoint",   "最佳观景点",     "Best Viewpoint",           "提案新增，供路线生成用"),
    ("site_approach",    "最佳进入序列",   "Best Approach Sequence",   "提案新增，供路线生成用"),
    ("site_parent",      "与母体遗产地的关系", "Relationship to Parent Site", "提案新增"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = M.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM meta_key")
    before = cur.fetchone()[0]

    added = 0
    for group in (LAYER1_EXTRA, LAYER2, LAYER2_SITE):
        for k, zh, en, note in group:
            cur.execute("SELECT 1 FROM meta_key WHERE key_name=%s", (k,))
            if not cur.fetchone():
                added += 1
            M.ensure_key(cur, k, zh, en, note)

    cur.execute("SELECT COUNT(*) FROM meta_key")
    print(f"meta_key: {before} -> {cur.fetchone()[0]}（新增 {added}）")
    print(f"  Layer 1 补充 {len(LAYER1_EXTRA)}，Layer 2 significance {len(LAYER2)}，"
          f"建筑/遗址专用 {len(LAYER2_SITE)}")

    if args.dry_run:
        conn.rollback(); print("--dry-run：已回滚")
    else:
        conn.commit(); print("已提交")
    conn.close()


if __name__ == "__main__":
    main()
