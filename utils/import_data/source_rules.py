#!/usr/bin/env python3
"""每个 source_key 的来源性质与等级。提案第 3、4 节。

单独成模块，因为有两个消费者且必须一致：`evidence_score.py` 拿它重算
`best_source_tier`，`audit_load.py` 拿它回填 `artwork_meta` 的
`evidence_type` / `source_quality`。放在任一方都会造成循环 import
（`audit_load` → `audit_meta` → `evidence_score`）。

**判 FACT 是说「它陈述的是一件事实」，不是说「这件事一定对」。**
对不对由 `confidence` 与来源等级表达，两件事不要混。譬如 seq 15 费克肖像的
馆藏号，PEM 官方是 `100183`、Wikidata 是 `M11043` —— 两条都是 FACT，
一条 tier 1 一条 tier 3，谁对谁错交给读取方判断。

来源等级（提案第 4 节）：
  1  博物馆官方藏品页/藏品库、UNESCO、国家文物机构、官方图录
  2  展览图录、学术论文、权威考古报告
  3  重要拍卖行、专业艺术数据库、可靠文化机构
  4  Wikipedia 及一般网络资料 —— **不足以单独支撑 S**
"""
from __future__ import annotations

# source_key -> (来源等级, evidence_type, 这么定的理由)
SOURCE_RULES = {
    # www.pem.org/the-pem-collection/<栏目> 的栏目页。2026-08-31 逐页核实过：
    # 每件都带馆藏号、材质、年代与「Gift of …, <年>」，是馆方自己发布的编目数据，
    # 不是宣传文案。故为 Tier 1。
    "pem_official":     (1, "FACT", "PEM 官网藏品栏目页，馆方发布的逐件编目数据"),
    # 结构化，但社群维护、无馆方背书
    "wikidata":         (3, "FACT", "Wikidata 结构化条目，社群维护"),
    # PEM 关联的商品站，有藏品图与年代，但不是藏品数据库
    "pem_customprints": (3, "FACT", "PEM 关联站点 customprints，非官方藏品库"),
    # 行业媒体文章
    "incollect":        (4, "FACT", "incollect 行业媒体文章，一般网络资料"),
    # 源工作表的 Category 列。是事实陈述，但这份 Excel 本身不是馆方权威发布
    "source_file":      (4, "FACT", "源工作表 Category 列，非馆方权威发布"),
    # 从展品名与英文简介解析而来。解析规则可靠，但被解析的那段文字不可靠
    "rule":             (4, "FACT", "由名称与简介解析得出，来源仍是那段简介"),
    # Evidence Packet 里的 sig_* 判断。**默认是推断**，逐条由 audit_meta.py
    # 阶段三复核：能指认出真实外部来源的才可以改判 FACT。
    "evidence":         (4, "INFERENCE", "Evidence Packet 的 significance 判断，默认为推断"),
}

# 等级 -> 来源质量。审计导出里用这三档，比 1–4 更好读。
TIER_QUALITY = {1: "strong", 2: "strong", 3: "moderate", 4: "weak"}


def quality_of(tier: int | None) -> str:
    """拿不准的一律算 weak —— 来源质量存疑时高估比低估危险。"""
    return TIER_QUALITY.get(tier, "weak")
