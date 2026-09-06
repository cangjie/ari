#!/usr/bin/env python3
"""Metadata Quality Audit：审「支撑当前 Tier 的证据够不够」，不重新评级。

设计依据：docs/Metadata Enrichment Pipeline 提案.md 第 2、3、4、6、8 节
         docs/Ariadne文化遗产Tier算法V3.0.txt 第十二节

**这一轮一个 tier 都不改。** 脚本只产出对证据本身的判断；artwork.tier 与
artwork_tier_v3 的任何一列都不写，audit_load.py 里有写入前后的快照断言强制这条。
理由见提案第 3 节：第一轮该做的是「说清缺什么」，不是急着改结论 —— 拿不足的
证据去改级，改出来的还是同样不足的证据支撑的结论，只是换了个数字。

三个阶段各自独立跑、各自落 JSONL，跑挂了重跑会跳过已完成的条目：

  阶段一  全量逐件审。12 项完备度判定（含「不适用」）、Tier 可信度、
          潜在 Tier 区间、缺失证据、建议研究问题、是否需复核。
  阶段二  只审 S 与 A。六问深审，核心是最后一问：把全部未经外部资料证实的
          推断删掉之后，它还站得住吗。逐件独立问就够，不需要组内比较。
  阶段三  只审 source_key='evidence' 的 sig_* 取值，逐条判 FACT / INFERENCE
          与来源质量。其余来源（source_file / rule / wikidata / pem_official …）
          按 source_key 确定性回填，不花 API —— 见 audit_load.py。

【为什么用 OpenAI 而不是跟 tier_v3.py 一样用 Anthropic】
V3.0 那批分是 claude-opus-5 打的。审计者若还是同一个模型，「你自己打的分证据够
不够」这个问题的答案先天可疑。换一家的模型评，同源偏差被切断了一部分。
这仍不是独立第三方审计 —— 喂进去的证据本身就是那轮打分的产物 —— 但比同源强。
两个脚本因此落在两家 SDK 上，这是刻意的，不做统一抽象层：抽象只会掩盖
「哪批数据是谁产出的」这条最该显眼的信息。审计者型号写进 artwork_evidence.audited_by，
与 artwork_tier_v3.scored_by 对照即可看清。

用法：
    # 冒烟：只审 12 件，确认链路通
    python3 audit_meta.py --museum pem --limit 12 --stage 1

    # 全量三阶段（可反复重跑，已完成的会跳过）
    python3 audit_meta.py --museum pem

型号不写死：--model 优先，其次环境变量 OPENAI_MODEL，都没有就报错退出。
key 从 ~/.openai_key（权限 600）读，与本仓库 ~/.my.cnf 的做法一致 ——
命令行里不出现 key，也就不会被权限系统写进必须提交的 .claude/settings.json。
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys
from pathlib import Path

import meta_lib as M
from museum_context import CONTEXTS

# boundary_factor / CEILING / THRESHOLDS 直接复用 evidence_score.py，
# 不重新实现：两处若各写一份，改了门槛忘了另一处，Research Priority 会悄悄分叉。
from evidence_score import CEILING, THRESHOLDS, boundary_factor  # noqa: F401


# ---------------------------------------------------------------------------
# 完备度的 12 个检查项
#
# 权重沿用提案第 2 节的八个桶，拆细到审计要求的 12 项：
#   基本身份 10 拆成 身份 4 / 年代 3 / 作者·文化 3
#   Art-Cultural 15 拆成 艺术遗产 8 / 文化教育 7
#   Visitor-visual 10 拆成 视觉体验 6 / 关系空间 4
# 其余四桶（HS 15、稀缺 15、本馆身份 15、类别代表 10、Provenance 10）原样保留。
#
# 【关键差别】这不是「字段在不在」的计数。evidence_score.py 那一套量的是填充率
# （PEM 中位 1.1/100），本表量的是「现有资料够不够支撑对这一项的判断」。
# 一句可靠的简介可以让 historical_significance 判 full，而库里一个 sig_* 都没有。
# ---------------------------------------------------------------------------
ITEMS = [
    ("basic_identification",        4, "基本身份：这到底是什么东西，名称与类别是否明确"),
    ("date_period",                 3, "年代 / 时期"),
    ("maker_culture",               3, "作者 / 制作者 / 所属文化"),
    ("historical_significance",    15, "历史重要性：它在历史、宗教或文明中的位置"),
    ("artistic_significance",       8, "艺术 / 遗产重要性"),
    ("rarity_uniqueness",          15, "稀缺性 / 独特性：同类存世多少，它是否罕见"),
    ("institutional_identity",     15, "本馆身份与地位：失去它本馆身份是否受损"),
    ("category_representativeness",10, "同类代表性：在本馆同类对象中的相对位置"),
    ("cultural_educational",        7, "文化 / 教育 / 叙事价值"),
    ("provenance_acquisition",     10, "来源 / 入藏经过 / 流传"),
    ("visual_experiential",         6, "现场视觉与体验：尺度、观感、展陈"),
    ("relational_spatial",          4, "关系 / 空间：与建筑群、轴线、其他展品的关系（多数单件展品不适用）"),
]
assert sum(w for _, w, _ in ITEMS) == 100, "12 项权重合计必须为 100"
ITEM_KEYS = [k for k, _, _ in ITEMS]
ITEM_WEIGHT = {k: w for k, w, _ in ITEMS}

# full=资料足以支撑判断；partial=有线索但不足以定论；none=完全没有；
# na=这一项对该对象根本不适用（如单件油画的「关系/空间」）。
# **na 从分子分母同时剔除**，不因不适用而扣分 —— 否则每件单件展品都被白扣 4 分，
# 完备度就变成了「对象类型」的函数，而不是「资料多少」的函数。
GRADE_SCORE = {"full": 1.0, "partial": 0.5, "none": 0.0}
GRADES = ["full", "partial", "none", "na"]

TIERS = ["S", "A", "B", "C"]
TIER_IDX = {t: i for i, t in enumerate(TIERS)}


def completeness_of(items: dict[str, str]) -> float:
    """12 项判定 -> 0–100。na 项从分母剔除后归一化。"""
    num = den = 0.0
    for k in ITEM_KEYS:
        g = items[k]
        if g == "na":
            continue
        den += ITEM_WEIGHT[k]
        num += ITEM_WEIGHT[k] * GRADE_SCORE[g]
    return 100.0 * num / den if den else 0.0


def range_span_factor(low: str, high: str) -> float:
    """潜在 Tier 区间跨得越宽，越说明「查一查结论可能不一样」。

    这一项替掉了提案第 6 节原式里的 Probability of Tier Change。原式那一项是循环的
    （研究还没做，无从知道 tier 会不会变，而这正是要用它来决定的事，
    见 evidence_score.py 文件头）。区间不循环：它是从**证据缺口**判出来的，
    不依赖研究结果 —— 「我不知道它是不是本馆最好的大洋洲雕刻」直接给出 B–S。
    """
    d = abs(TIER_IDX[low] - TIER_IDX[high])
    return {0: 0.2, 1: 0.7}.get(d, 1.0)


def priority_of(comp: float, low: str, high: str, core: float | None) -> float:
    """Research Priority 0–10 = Ceiling × 缺得多不多 × 结论可能变不变。"""
    bf, _ = boundary_factor(core)
    change = max(range_span_factor(low, high), bf)
    return max(0.0, min(10.0, 10 * CEILING[high] * (1 - comp / 100) * change))


# ---------------------------------------------------------------------------
# OpenAI 客户端
# ---------------------------------------------------------------------------

def read_key(key_file: str) -> str:
    """环境变量优先，其次 ~/.openai_key。读到的 key 只往 SDK 里传，不打印不落日志。"""
    env = os.environ.get("OPENAI_API_KEY")
    if env:
        return env
    p = Path(os.path.expanduser(key_file))
    if not p.exists():
        sys.exit(f"没有 key：设环境变量 OPENAI_API_KEY，或把 key 写进 {p} 并 chmod 600")
    st = p.stat()
    if st.st_mode & 0o077:
        sys.exit(f"{p} 权限过宽（{oct(st.st_mode & 0o777)}），请 chmod 600 —— "
                 "组内或其他用户可读的密钥文件等于没保护")
    key = p.read_text(encoding="utf-8").strip()
    if not key:
        sys.exit(f"{p} 是空的")
    return key


class LazyClient:
    """用得着才构造真客户端，也才 import openai。

    两个理由。其一同 tier_v3.py：只跑已完成阶段（JSONL 里都有了）时整轮不发请求，
    没有 key 的机器不该在什么都没做之前就报错。其二是 audit_load.py 要 import
    本模块拿 ITEMS 与打分函数，而它一次 API 都不调 —— 若在模块顶层 import openai，
    只装了 pymysql 的机器连写库都做不了。
    """

    def __init__(self, key_file: str) -> None:
        self._c = None
        self._key_file = key_file

    def __getattr__(self, name):
        if self._c is None:
            try:
                from openai import OpenAI
            except ImportError:
                sys.exit("缺少 openai：.venv_local/bin/pip install openai")
            self._c = OpenAI(api_key=read_key(self._key_file))
        return getattr(self._c, name)


# 推理强度的口语叫法 -> API 取值。传不认识的字符串就原样透传，
# 让服务端去报错 —— 本脚本不该假装知道某个型号支持哪几档。
EFFORT_ALIASES = {
    "extra high": "xhigh", "extrahigh": "xhigh", "超高": "xhigh",
    "high": "high", "高": "high",
    "medium": "medium", "中": "medium",
    "low": "low", "低": "low",
}


# 按阶段分配推理强度。依据同 tier_v3.STAGE_EFFORT（2026-09-04 水月观音实测）：
# audit_stage1_slim 从 xhigh 换 medium，推理 1245→424（-66%），是全管线省得最多的
# 一处，而它输出的是「缺什么」的清单不是分数，措辞略简但指向同一件事，可以省。
# 阶段二（六问）实测三问 100% 单一答案，本就该走 --slim 跳过；留 medium 兜底。
# 阶段三逐条判 FACT/INFERENCE，是有明确判据的分类题，medium 够用。
#
# ⚠ effort 参与 llm_cache 的缓存键：改这里等于对应阶段整批重跑。
# 非 None 时审计走 claude CLI 的订阅账号，型号即此字符串。
# 与 tier_v3.CLAUDE_CLI 同一机制，理由见 claude_cli.py 的文件头。
CLAUDE_CLI = None

STAGE_EFFORT = {
    "audit_stage1":      "medium",
    "audit_stage1_slim": "medium",
    "audit_stage2":      "medium",
    "audit_stage3":      "medium",
}


def norm_effort(s: str | None) -> str | None:
    return EFFORT_ALIASES.get(s.strip().lower(), s.strip()) if s else None


def ask(client, model: str, system: str, user: str, name: str, schema: dict,
        effort: str | None = None, museum_key: str | None = None,
        scope: str | None = None, seqs=None, validate=None) -> dict:
    """一次结构化输出调用。strict 模式保证返回的是合法且合规的 JSON。

    刻意不传 temperature / max_tokens：型号由 --model 决定，而不同代际的模型对这
    两个参数的支持并不一致（有的推理型号直接拒收 temperature，有的把 max_tokens
    换成了 max_completion_tokens）。全部走服务端默认值，换型号时不必改代码。
    reasoning_effort 只在显式传了 --effort 时才带上，同样不替型号做假设。

    **走 llm_cache**：键含 system/user/schema 全文，所以提示词没改必然命中（不花钱），
    改了必然不命中（拿不到旧判据的答案）。name 同时用作 stage，供事后分阶段算账。
    """
    if CLAUDE_CLI is not None:
        import claude_cli, llm_cache

        def _do_cli():
            data, usage = claude_cli.ask(system, user, schema, CLAUDE_CLI)
            return data, claude_cli.Usage(usage)

        # effort 记 NULL：CLI 不暴露 reasoning_effort，这条路径没有档位可调。
        return llm_cache.call(_do_cli, provider="anthropic_cli", model=CLAUDE_CLI,
                              effort=None, stage=name, system=system, user=user,
                              schema=schema, museum_key=museum_key, scope=scope,
                              seqs=seqs, validate=validate)

    def _do():
        kw = {}
        if effort:
            kw["reasoning_effort"] = effort
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_schema",
                             "json_schema": {"name": name, "strict": True,
                                             "schema": schema}},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            **kw,
        )
        msg = resp.choices[0].message
        if getattr(msg, "refusal", None):
            raise RuntimeError(f"模型拒答：{msg.refusal}")
        return json.loads(msg.content), getattr(resp, "usage", None)

    import llm_cache
    return llm_cache.call(_do, provider="openai", model=model, effort=effort,
                          stage=name, system=system, user=user, schema=schema,
                          museum_key=museum_key, scope=scope, seqs=seqs,
                          validate=validate)


# ---------------------------------------------------------------------------
# JSONL 断点续跑（与 tier_v3.py 同一套）
# ---------------------------------------------------------------------------

def read_done(path: Path, key: str = "seq") -> dict:
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                out[rec[key]] = rec
    return out


def append(path: Path, rec: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 取数：审的是库里的现状，不是源 Excel
# ---------------------------------------------------------------------------
CONF_DIMS = ("hs", "iu", "vi", "va", "ce", "cr", "er")


def load_items(cur, mk: str, limit: int | None) -> list[dict]:
    cur.execute("""
        SELECT a.source_seq, tn_en.text, tn_zh.text, tg.text,
               td_en.text, tm.text, a.tier
        FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        LEFT JOIN gallery g ON g.id = a.gallery_id
        LEFT JOIN content_text tg    ON tg.content_id    = g.name_cid        AND tg.lang='zh-CN'
        LEFT JOIN content_text tn_en ON tn_en.content_id = a.name_cid        AND tn_en.lang='en'
        LEFT JOIN content_text tn_zh ON tn_zh.content_id = a.name_cid        AND tn_zh.lang='zh-CN'
        LEFT JOIN content_text td_en ON td_en.content_id = a.description_cid AND td_en.lang='en'
        LEFT JOIN content_text tm    ON tm.content_id    = a.medium_cid      AND tm.lang='zh-CN'
        ORDER BY a.source_seq""", (mk,))
    items = {r[0]: {"seq": r[0], "name_en": r[1], "name_zh": r[2], "gallery": r[3],
                    "description": r[4], "category": r[5], "tier": r[6],
                    "v3": None, "meta": [], "conf": {}, "src_tier": None, "missing": None}
             for r in cur.fetchall()}

    cur.execute("""
        SELECT source_seq, object_type, peer_group, hs, iu, vi, va, ce, er, cr, core,
               tier, tier_reason, confidence, evidence, cr_reason, sness_reason
        FROM artwork_tier_v3 WHERE museum_key = %s""", (mk,))
    for r in cur.fetchall():
        if r[0] in items:
            items[r[0]]["v3"] = {
                "object_type": r[1], "peer_group": r[2],
                "HS": float(r[3]), "IU": float(r[4]), "VI": float(r[5]),
                "VA": float(r[6]), "CE": float(r[7]), "ER": float(r[8]),
                "CR": float(r[9]), "core": float(r[10]),
                "tier": r[11], "tier_reason": r[12], "confidence": r[13],
                "evidence": r[14], "cr_reason": r[15], "sness_reason": r[16]}

    # 取值文本用中文版：审计判断在中文语境下做，英文另出一份译文而非另做一次判断
    cur.execute("""
        SELECT am.source_seq, am.key_name, am.source_key, am.source, am.confidence, t.text
        FROM artwork_meta am
        JOIN content_text t ON t.content_id = am.value_cid AND t.lang = 'zh-CN'
        WHERE am.museum_key = %s
        ORDER BY am.source_seq, am.key_name, am.source_key, am.ord""", (mk,))
    for seq, key, skey, src, conf, txt in cur.fetchall():
        if seq in items:
            items[seq]["meta"].append({"key": key, "source_key": skey,
                                       "source": src, "confidence": conf, "text": txt})

    cur.execute("SELECT source_seq, " + ", ".join(f"conf_{d}" for d in CONF_DIMS)
                + ", best_source_tier, missing_evidence"
                  " FROM artwork_evidence WHERE museum_key = %s", (mk,))
    for r in cur.fetchall():
        if r[0] in items:
            items[r[0]]["conf"] = {d: v for d, v in zip(CONF_DIMS, r[1:8]) if v}
            items[r[0]]["src_tier"] = r[8]
            items[r[0]]["missing"] = r[9]

    out = [items[s] for s in sorted(items)]
    return out[:limit] if limit else out


def load_claims(cur, mk: str) -> list[dict]:
    """待逐条判 FACT/INFERENCE 的取值：只有 source_key='evidence' 的需要模型判。

    其余来源（source_file / rule / wikidata / pem_official / pem_customprints /
    incollect）的性质由来源本身就决定了，audit_load.py 里确定性回填，不花 API。
    """
    cur.execute("""
        SELECT am.source_seq, am.key_name, am.source, am.confidence, t.text
        FROM artwork_meta am
        JOIN content_text t ON t.content_id = am.value_cid AND t.lang = 'zh-CN'
        WHERE am.museum_key = %s AND am.source_key = 'evidence'
        ORDER BY am.source_seq, am.key_name""", (mk,))
    return [{"seq": r[0], "key": r[1], "source": r[2], "confidence": r[3], "text": r[4]}
            for r in cur.fetchall()]


def fmt_item(it: dict, with_v3_detail: bool = True) -> str:
    p = [f"[seq {it['seq']}] 当前 Tier: {it['tier'] or '无'}"]
    if it["name_en"]:
        p.append(f"名称(EN): {it['name_en']}")
    if it["name_zh"]:
        p.append(f"名称(CN): {it['name_zh']}")
    if it["gallery"]:
        p.append(f"展厅: {it['gallery']}")
    if it["category"]:
        p.append(f"类别: {it['category']}")
    p.append(f"简介: {it['description'] or '（源数据无简介）'}")

    v = it["v3"]
    if v and with_v3_detail:
        p.append(f"V3.0 评分: HS={v['HS']} IU={v['IU']} VI={v['VI']} VA={v['VA']} "
                 f"CE={v['CE']} ER={v['ER']} CR={v['CR']:.2f} Core={v['core']:.3f}")
        p.append(f"  判定: {v['tier_reason']}｜打分时自评可信度: {v['confidence']}")
        p.append(f"  同类组: {v['peer_group']}（对象类型 {v['object_type']}）")
        if v["evidence"]:
            p.append(f"  打分依据原文: {v['evidence']}")
        if v["cr_reason"]:
            p.append(f"  类别代表性理由: {v['cr_reason']}")
        if v["sness_reason"]:
            p.append(f"  S-ness Test 理由: {v['sness_reason']}")

    if it["meta"]:
        p.append("库中已有的 metadata 取值（来源标识 / 来源 / 该条可信度）：")
        for m in it["meta"]:
            p.append(f"  - {m['key']} = {m['text']}"
                     f"  [{m['source_key']} / {m['source'] or '—'} / {m['confidence']}]")
    else:
        p.append("库中已有的 metadata 取值：无")

    if it["conf"]:
        p.append("已记录的逐维度证据可信度: "
                 + " ".join(f"{d.upper()}={v}" for d, v in it["conf"].items()))
    if it["src_tier"]:
        p.append(f"已记录的最高来源等级: Tier {it['src_tier']}"
                 "（1=馆方官方/UNESCO 2=图录/学术 3=专业数据库/拍卖行 4=一般网络资料）")
    if it["missing"]:
        p.append(f"上一轮记下的缺失证据: {it['missing']}")
    return "\n".join(p)


# ---------------------------------------------------------------------------
# 阶段一：全量逐件审
# ---------------------------------------------------------------------------
COMMON_RULES = """你在执行 Ariadne 的 Metadata Quality Audit（元数据质量审计）。

**审计的问题不是「这件东西该是几级」，而是「支撑它现在这一级的资料够不够」。**

三条纪律，违反任何一条这次审计就白做了：

1. **不重新评级。** 你看得到当前 Tier 和七维分。你的任务是审证据，不是改分。
   即使你认为评错了，也只能标记 review_flag 并说明理由，绝不在输出里给出新等级。

2. **不知道就说不知道。** 严禁用常识、套路或合理推测去补一段听起来像样的内容。
   本轮的目的是**发现知识缺口，不是掩盖知识缺口**。宁可判 none 并写清缺什么，
   也不要判 full 然后自己编一段依据。你补的每一句假内容，都会让后面真正去查资料
   的人少查一处。

3. **区分事实与推断。** 有外部资料（馆方官网、图录、学术出版、权威文化遗产数据库）
   直接支撑的是 FACT；由你或以往的 AI 依据事实作出的判断是 INFERENCE。
   推断可以用于定级，但**绝不能伪装成博物馆或学术来源的事实**。
   注意：喂给你的「简介」和以往的「打分依据原文」本身多半也只是 AI 写的，
   不要把它们当成外部资料 —— 它们证明不了任何事，只能作为线索。

"""


STAGE1_SYSTEM = COMMON_RULES + """

本阶段对每件对象输出五组判断。

【一】完备度 12 项，逐项判 full / partial / none / na

  full     现有资料足以支撑对这一项的判断
  partial  有线索但不足以定论
  none     完全没有可用资料
  na       这一项对该对象根本不适用

  **判 na 要克制，也不要吝啬。** 单件可移动展品（油画、瓷器、家具）的
  「关系/空间」通常判 na —— 它不在建筑群里，没有轴线关系可言，
  不该因为缺这一项而被扣分。但「来源/入藏经过」对任何一件馆藏都是适用的，
  只是不知道而已，那是 none 不是 na。**不适用 ≠ 不知道。**

  判断依据是「资料够不够」，不是「description 长不长」。一段三百字的展厅套话
  什么也没说明，照样判 none；一句「1846 年由 John T. Prince 捐赠」就足以让
  来源那一项判 partial 甚至 full。

  每项附一句依据（note，中文，20 字以内），说明你为什么这么判。

【二】Tier Confidence：high / medium / low

  问的是：**根据目前已有证据，我们对这个对象当前 Tier 的判断有多大信心？**

  **Low Confidence 不等于 Low Tier。** 允许出现「S — Low Confidence」，
  意思是「它可能确实是 S，但我们手上的证据撑不起这个结论」；也允许
  「B — High Confidence」，意思是「资料已经够了，它就是 B」。
  绝对不要因为资料少就往低了判 Tier —— 你根本没在判 Tier。

  **三档的锚点 —— 判的是「不确定性会不会改变 Tier」，不是「资料有多少」**

    high    现有证据足以确定 Tier。进一步研究即使增加知识，也几乎不会改变它。
    medium  存在一个或几个不确定的事实，有可能让 Tier 上下移动一级。
    low     对象身份、归属、或作为定级主要依据的那个论断本身就不确定，
            可能导致 Tier 大幅变化。

  **这一列绝不能由完备度推出来。** 两者测的不是一回事：
  完备度问「我们知道多少」，本列问「不知道的那部分会不会推翻结论」。
  一件资料很少但地位毫无争议的东西，应当是 high；
  一件资料很多但核心论断没有来源的东西，可以是 low。

  **馆方与学界的既成共识本身就是证据。** 一件长期被本馆列为代表作、
  在通行艺术史叙述中位置稳固的对象，即使 provenance 有缺口、
  即使没有 catalogue raisonné 条目，你依然可以对它的 Tier 判 high ——
  因为那些缺口就算永远补不上，也不会改变「游客该不该优先看它」。

  反过来，「还能继续考证」不构成降低信心的理由。任何一件文物都永远有
  可继续研究的问题；若以此为准，这一列会对每件东西都输出 low，
  从而不携带任何信息。**能提出问题 ≠ 结论不可靠。**

【三】Potential Tier Range：给出 potential_low 与 potential_high

  含义是：**结合现有证据与未知信息，这件对象合理的潜在 Tier 范围**。
  low 是下界（最差可能是几级），high 是上界（最好可能到几级），
  用 S/A/B/C 表示，且 low 不得优于 high（S 最优，C 最差）。
  资料已经充分时，两者相同（如 A 和 A）。
  资料严重不足、且有合理线索指向更高等级时，区间就该拉开（如 B 和 S）。
  拉开区间不是猜测，是承认「我们不知道」。

【四】Missing Evidence：真正影响 Tier 判断的缺失资料

  **每条都要回答同一个问题：这条事实如果答案不同，Tier 会不会变？**
  逐条给出 tier_sensitive：
    true   这条不确定直接关系到定级依据。例如：简介称「伦勃朗真迹」但馆方
           只标「伦勃朗工作坊」（可能 A→B/C）；声称「全美唯一一件」却没有
           任何来源，而稀缺性正是它定级的主要理由；或者连作者、年代、馆藏号
           都无法确认的普通小件。
    false  值得研究，但答案如何都不影响 Tier。例如：Liberty Bowl 缺同期
           委托档案 —— 补上了是学术收获，补不上也不改变「到了 MFA 该不该
           看它」；水月观音的具体寺院来源不完整，同样不改变它是不是
           中国艺术板块最不可错过的作品之一。

  **严禁写「需要更多资料」「信息不足」这类空话。** 每条都要具体到可以直接
  派人去查，例如：
    - 缺该作品在艺术家创作生涯中的位置
    - 缺同类作品存世数量与稀缺性资料
    - 缺 PEM 官方对该作品馆藏地位的说明
    - 缺与本馆其他同类对象的比较
    - 缺可靠的 provenance / 入藏记录
    - 缺现场视觉与空间体验信息
  中英各写一份（zh / en），内容对应。资料已经足够时给空列表。
  另给 top_missing：其中最关键的一条（资料足够时给 null）。

【五】research_question：一句可直接执行的研究问题（中英各一份）

  要指名道姓到能去查，例如「PEM 是否在其大洋洲藏品介绍中把这件列为代表作？
  同类库战神像在大都会与大英博物馆各藏几件？」而不是「进一步研究其重要性」。
  没有研究价值时给 null。

以及 review_flag（true / false）—— **它等价于「该不该进人工研究队列」**。

只有一个判据：**至少存在一条 tier_sensitive=true 的缺失证据**，
或者你发现了明显的事实错误、资料自相矛盾。两者都不成立就置 false。

  Research Needed **不等于** 还有东西可以研究，
  Research Needed **等于** 缺的那条事实一旦有了答案，Tier 可能改变。

问自己：「我们缺的哪一条事实，如果答案不同，会导致 Tier 改变？」
答案是「没有」就置 false，哪怕你能列出十个值得研究的学术问题。
一个两百件的馆，真正该进队列的通常是十几到三十件，不会是两百件 ——
**如果你给几乎每件都标了 true，那不是审计结论，是这一列失效了。**"""


# 每个馆的数据实情。**只陈述事实，不预先给结论。**
#
# 这一段原先写死在 COMMON_RULES 里，内容是 PEM 专属的，却被三个阶段、所有馆共用，
# 而且末句直接写着「就该判低完备度、低可信度」—— 等于把答案告诉了审计者。
# 2026-09-01 实测：MFA 与哈佛在这段话下跑出 203/203、204/204 全 low，
# 而那两馆的官网根本没停服、库里也已有馆藏号。指定答案的提示词得到的不是审计结论，
# 是提示词自己的回声。
MUSEUM_NOTE = {
    "pem": "PEM 官方藏品门户 explore-art.pem.org 已停服，196 件的官方页面链接为 0。"
           "已从 pem.org 藏品栏目页核实 15 件、Wikidata 1 件，其余对象的外部来源为零。"
           "另需知道：这批名称多是描述性转写而非编目题名，179/196 件无法与 PEM "
           "官方发布的藏品对应上 —— 对这些对象，「身份可否核验」本身就是未知数。",
    "mfa_boston": "MFA 官网与藏品检索库（collections.mfa.org）均可访问，但本轮未逐件查询。"
                  "已从 Wikidata 核实 20 件，拿到馆藏号、创作年、作者与材质；"
                  "其余 183 件目前只有源文件的名称、类别与一句简介。",
    "mfa_boston_ext": "本清单 4464 件，来源分两类且性质差别很大：135 件出自 MFA 官网"
                      "展厅页/部门页，带馆藏号、断代、材质、入藏基金与展厅位置（Tier 1）；"
                      "其余 4329 件来自 Wikidata，带藏品编号可回官网核对，但源文件自己"
                      "标明「展厅与在展状态未经官网确认」，其 on_view 一律为「未知」。"
                      "判断证据是否充分时，请按每件实际列出的来源等级判断，"
                      "不要因为同属一份清单就一视同仁。",
    "ham": "哈佛艺术博物馆官网与藏品检索库均可访问，另有公开 API（本轮未申请密钥）。"
           "已从 Wikidata 核实 12 件，拿到馆藏号、创作年、作者与材质；"
           "其余 192 件目前只有源文件的名称、类别与一句简介。",
}


def _nullable(t):
    """strict 模式不认 required 之外的可选字段，可空只能靠联合类型表达。"""
    return {"type": [t, "null"]}


STAGE1_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seq": {"type": "integer"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string", "enum": ITEM_KEYS},
                                "grade": {"type": "string", "enum": GRADES},
                                "note": {"type": "string"},
                            },
                            "required": ["key", "grade", "note"],
                            "additionalProperties": False,
                        },
                    },
                    "tier_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "confidence_reason": {"type": "string"},
                    "potential_low": {"type": "string", "enum": TIERS},
                    "potential_high": {"type": "string", "enum": TIERS},
                    "missing": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"zh": {"type": "string"},
                                           "en": {"type": "string"},
                                           "tier_sensitive": {"type": "boolean"}},
                            "required": ["zh", "en", "tier_sensitive"],
                            "additionalProperties": False,
                        },
                    },
                    "top_missing_zh": _nullable("string"),
                    "top_missing_en": _nullable("string"),
                    "research_question_zh": _nullable("string"),
                    "research_question_en": _nullable("string"),
                    "review_flag": {"type": "boolean"},
                    "review_reason_zh": _nullable("string"),
                    "review_reason_en": _nullable("string"),
                },
                "required": ["seq", "items", "tier_confidence", "confidence_reason",
                             "potential_low", "potential_high", "missing",
                             "top_missing_zh", "top_missing_en",
                             "research_question_zh", "research_question_en",
                             "review_flag", "review_reason_zh", "review_reason_en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def check1(rec: dict) -> None:
    """把模型输出的硬性错误挡在 JSONL 之前 —— 落了盘再发现就得手工删行。"""
    got = [i["key"] for i in rec["items"]]
    if sorted(got) != sorted(ITEM_KEYS):
        raise RuntimeError(f"seq {rec['seq']} 的 12 项不全或有重复：{got}")
    if TIER_IDX[rec["potential_low"]] < TIER_IDX[rec["potential_high"]]:
        raise RuntimeError(f"seq {rec['seq']} 区间方向反了："
                           f"{rec['potential_low']}–{rec['potential_high']}")
    if rec["review_flag"] and not rec["review_reason_zh"]:
        raise RuntimeError(f"seq {rec['seq']} 标了 review_flag 却没写原因")
    # review_flag 不再是独立判断，它就是「有没有 tier_sensitive 的缺口」。
    # 留一个例外：发现事实错误或资料矛盾时也该标，那种情况 review_reason 里会写明，
    # 所以只拦「有敏感缺口却没标」这一侧 —— 反向不拦。
    if any(m["tier_sensitive"] for m in rec["missing"]) and not rec["review_flag"]:
        raise RuntimeError(f"seq {rec['seq']} 有 tier_sensitive 的缺失证据却没标 review_flag")
    for m in rec["missing"]:
        if len(m["zh"]) < 6 or "更多资料" in m["zh"] or "信息不足" in m["zh"]:
            raise RuntimeError(f"seq {rec['seq']} 的缺失证据太空泛：{m['zh']}")


def stage1(client, model, effort, ctx, note, items, out: Path, batch: int,
           mk: str) -> dict:
    done = read_done(out)
    todo = [it for it in items if it["seq"] not in done]
    if not todo:
        print(f"  阶段一：{len(done)} 件已完成，跳过")
        return done
    print(f"  阶段一：待审 {len(todo)} 件（已完成 {len(done)}），每批 {batch}")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        user = (f"博物馆语境：\n{ctx}\n\n本馆数据实情：\n{note}\n\n"
                f"请逐件审计以下 {len(chunk)} 件对象：\n\n"
                + "\n\n".join(fmt_item(it) for it in chunk))
        data = ask(client, model, STAGE1_SYSTEM, user, "audit_stage1", STAGE1_SCHEMA,
                   effort, museum_key=mk,
                   scope=f"seq {chunk[0]['seq']}-{chunk[-1]['seq']}",
                   seqs=[it['seq'] for it in chunk])
        got = {r["seq"] for r in data["results"]}
        missing = {it["seq"] for it in chunk} - got
        if missing:
            raise RuntimeError(f"阶段一漏审 seq={sorted(missing)}")
        for r in data["results"]:
            check1(r)
            append(out, r)
            done[r["seq"]] = r
        print(f"    {min(i + batch, len(todo))}/{len(todo)}")
    return done


# ---------------------------------------------------------------------------
# 阶段二：S 与 A 的深审
# ---------------------------------------------------------------------------
STAGE2_QUESTIONS = [
    ("q1_hs",        "支撑 HS（历史/艺术/遗产重要性）的证据充分吗？"),
    ("q2_iu",        "支撑 IU（本馆身份与不可替代性）的证据充分吗？"),
    ("q3_rarity",    "支撑 rarity / uniqueness 的证据充分吗？"),
    ("q4_sness",     "S-ness Test 的结论有事实基础吗？（非 S 对象回答：它离 S 还差什么事实）"),
    ("q5_inference", "是否存在 AI inference 被当作 fact 使用的情况？具体是哪一句？"),
    ("q6_survives",  "如果删除所有未经外部资料验证的推断，它仍然应该是当前这一级吗？"),
]

STAGE2_SYSTEM = COMMON_RULES + """

本阶段只审 S 与 A —— 它们是参观优先级最高的对象，一旦是靠推断堆出来的，
代价最大。请逐件回答下面六问，每问给出 verdict 与一句理由（中英各一份）：

  q1_hs        支撑 HS（历史/艺术/遗产重要性）的证据充分吗？
  q2_iu        支撑 IU（本馆身份与不可替代性）的证据充分吗？
  q3_rarity    支撑 rarity / uniqueness 的证据充分吗？
  q4_sness     S-ness Test 的结论有事实基础吗？（若该件不是 S，回答它离 S 还差什么事实）
  q5_inference 是否存在 AI inference 被当作 fact 使用的情况？具体是哪一句？
  q6_survives  如果删除所有未经外部资料验证的推断，它仍然应该是当前这一级吗？

verdict 取值：yes（充分/是）、partial（部分成立）、no（不充分/否）。

**第六问是本阶段的重点，请当真回答。** 把喂给你的简介、打分依据原文、
以往的 sig_* 判断全部视为「未经验证的推断」剔除，只留下能指认外部来源的事实，
然后问：仅凭这些，它还配得上当前这一级吗？答不上来就是 no。
这一问的答案单独落库为 inference_only_survives（q6 verdict 为 yes 时 true，
partial 或 no 时 false）。

**本阶段不再判 tier_confidence、潜在区间和是否需复核。** 那三项由阶段一按统一的
锚点判定，这里重复判一次只会得到两套判据 —— 而阶段二的结论会覆盖阶段一，
于是全馆 S/A 都按这里的口径走。2026-09-02 实测：阶段一给 MFA 的 S/A 判出
15 高 / 24 中 / 62 低，被本阶段覆盖后变成 101 件全 low，只因为这里当时还在用
旧问法。一列一个判据，判据只放在一个地方。

你在这里只输出两样阶段一给不了的东西：
  · 六问的逐问作答（这是审计轨迹，会原样入库供人复核）
  · inference_only_survives —— 第六问的结论
另加一个窄口子：若你在核对中发现了**明确的事实错误或资料自相矛盾**
（例如简介称「伦勃朗真迹」而馆方标注为「伦勃朗工作坊」、中英文名称的归属不一致），
置 found_factual_error=true 并写明。它只会**追加**一个复核理由，不会改动
阶段一对可信度的判断。没发现就置 false。"""

STAGE2_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seq": {"type": "integer"},
                    "answers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "q": {"type": "string",
                                      "enum": [q for q, _ in STAGE2_QUESTIONS]},
                                "verdict": {"type": "string",
                                            "enum": ["yes", "partial", "no"]},
                                "note_zh": {"type": "string"},
                                "note_en": {"type": "string"},
                            },
                            "required": ["q", "verdict", "note_zh", "note_en"],
                            "additionalProperties": False,
                        },
                    },
                    "inference_only_survives": {"type": "boolean"},
                    "found_factual_error": {"type": "boolean"},
                    "error_note_zh": _nullable("string"),
                    "error_note_en": _nullable("string"),
                },
                "required": ["seq", "answers", "inference_only_survives",
                             "found_factual_error", "error_note_zh", "error_note_en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def check2(rec: dict) -> None:
    got = [a["q"] for a in rec["answers"]]
    want = [q for q, _ in STAGE2_QUESTIONS]
    if sorted(got) != sorted(want):
        raise RuntimeError(f"seq {rec['seq']} 的六问不全：{got}")
    if rec["found_factual_error"] and not rec["error_note_zh"]:
        raise RuntimeError(f"seq {rec['seq']} 说发现事实错误却没写明")
    q6 = next(a for a in rec["answers"] if a["q"] == "q6_survives")
    if (q6["verdict"] == "yes") != rec["inference_only_survives"]:
        raise RuntimeError(f"seq {rec['seq']} 的 q6 结论与 inference_only_survives 不一致")


# ---------------------------------------------------------------------------
# 精简版阶段一（--slim）
#
# 【为什么要有它】2026-09-04 拿三馆 603 件实测了阶段一各列的区分度：
#   · cultural_educational      203/203 全 partial
#   · category_representativeness 198/203
#   · 12 项里有 9 项在 203 件中**一次 full 都没出现过**，而它们合计占 90 分权重
#   · 完备度全馆挤在 16.7–50.0，标准差 7.3
#   · tier_review_flag 92–97% 全 true；potential_tier_low 74–92% 全 C
#   · tier_confidence 对 MFA 镇馆之宝（水月观音）判 low，而判据自己写着
#     「馆方与学界的既成共识本身就是证据……你依然可以判 high」
# 也就是说：那四列在当前输入下要么是常数，要么方向可疑。
#
# 唯一不饱和的是 missing_evidence —— MFA 203 件里 202 条 top_missing 不重复，
# 且逐件具体（版画问版次与复本比较、莫奈问「具体是哪一幅睡莲」）。
# found_factual_error 也不饱和（三馆 27 件）。
#
# 所以精简版只要这两样，并**明确不要求模型判定 Tier 相关的任何结论**。
# 完备度改由 evidence_score.py 的规则口径给（纯填充率，确定性、可复算、零 API）。
# ---------------------------------------------------------------------------

STAGE1_SLIM_SYSTEM = COMMON_RULES + """

本阶段**只做一件事：列出缺什么**。不判完备度、不判 Tier 可信度、不判潜在区间、
不判是否需要复核 —— 那些结论一律由确定性规则从库里算，不问你。

【一】missing —— 真正影响 Tier 判断的缺失资料

  **每条都要回答同一个问题：这条事实如果答案不同，Tier 会不会变？**
  逐条给出 tier_sensitive：
    true   这条不确定直接关系到定级依据。例如：简介称「伦勃朗真迹」但馆方
           只标「伦勃朗工作坊」；声称「全美唯一一件」却没有任何来源，
           而稀缺性正是它定级的主要理由。
    false  值得研究，但答案如何都不影响 Tier。

  **三条硬规则，违反任何一条这一列就失去作用：**

  1. **严禁空话。** 不许写「需要更多资料」「信息不足」。每条都要具体到可以直接
     派人去查，例如「缺该作品在艺术家创作生涯中的位置」「缺同类作品存世数量」。

  2. **并存政权的归属之争一律判 tier_sensitive=false。** 辽/金/北宋在 12 世纪
     并存（山西北部属辽、南部属北宋，1125 后入金），南北朝、五代十国、三国同理。
     这类标签之争在学术上真实存在、也可能永远定不下来，但它**不改变游客该不该
     优先看这件东西**。绝对年代（如「12 世纪初」，尤其有碳十四测年时）无争议，
     不要把它和政权标签混为一谈。

  3. **既成共识不是缺口。** 一件长期被馆方列为展厅核心展品、在通行艺术史叙述中
     位置稳固的对象，即使 provenance 有缺口、即使没有 catalogue raisonné 条目，
     那些缺口也**不是 tier_sensitive** —— 它们就算永远补不上，也不改变定级。
     反过来，「还能继续考证」永远成立，不构成任何一条缺口。

  资料已经足够时**给空列表**，这是允许且常见的结果。

【二】found_factual_error —— 明确的事实错误或资料自相矛盾

  例如简介称「伦勃朗真迹」而馆方标注为「伦勃朗工作坊」、中英文名称的归属不一致、
  或已核实事实与简介直接冲突。**并存政权的不同表述不算矛盾**（见上）。
  没发现就置 false，不要为了显得尽责而硬找。"""

STAGE1_SLIM_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seq": {"type": "integer"},
                    "missing": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "zh": {"type": "string"},
                                "en": {"type": "string"},
                                "tier_sensitive": {"type": "boolean"},
                            },
                            "required": ["zh", "en", "tier_sensitive"],
                            "additionalProperties": False,
                        },
                    },
                    "top_missing_zh": _nullable("string"),
                    "top_missing_en": _nullable("string"),
                    "found_factual_error": {"type": "boolean"},
                    "error_note_zh": _nullable("string"),
                    "error_note_en": _nullable("string"),
                },
                "required": ["seq", "missing", "top_missing_zh", "top_missing_en",
                             "found_factual_error", "error_note_zh", "error_note_en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


# 空话的判定词。**只在整条很短时才据此判空泛** —— 用子串匹配去否定一整句是错的：
# 2026-09-06 实测，「缺可靠艺术史资料说明 Pietro Mera 的身份、活动年代、艺术史地位
# 及该画在其作品中的位置；现有信息不足以支持…」被拒了，只因为句子中段含「信息不足」。
# 那条点名了艺术家、列了四项要查的东西，是这一列里最好的那种写法。
# 同「材质子串规则把音译人名判成材质」是一类错误：子串匹配不能用来做否定判断。
VAGUE_WORDS = ("更多资料", "信息不足", "资料不足", "缺乏资料")
VAGUE_MAXLEN = 30          # 超过这个长度就认为它已经说清了缺什么


def check1_slim(rec: dict) -> None:
    """精简版只剩两条硬检查 —— 其余判定已经不由模型出了。"""
    for m in rec["missing"]:
        zh = m["zh"].strip()
        if len(zh) < 8 or (len(zh) <= VAGUE_MAXLEN
                           and any(w in zh for w in VAGUE_WORDS)):
            raise RuntimeError(f"seq {rec['seq']} 的缺失证据太空泛：{zh}")
    if rec["found_factual_error"] and not rec["error_note_zh"]:
        raise RuntimeError(f"seq {rec['seq']} 说发现事实错误却没写明")


def _slim_ok(data: dict, want: set) -> bool:
    """整批的校验，交给 llm_cache 在**写缓存之前**跑。

    早先 check1_slim 写在拿到 data 之后，于是不合格的答案已经进了缓存，
    重跑必然命中它、必然在同一处再崩 —— 阶段一/二已经各栽过一次。
    """
    if want - {r["seq"] for r in data["results"]}:
        return False
    for r in data["results"]:
        try:
            check1_slim(r)
        except RuntimeError:
            return False
    return True


def stage1_slim(client, model, effort, ctx, note, items, out: Path, batch: int,
                mk: str) -> dict:
    done = read_done(out)
    todo = [it for it in items if it["seq"] not in done]
    if not todo:
        print(f"  阶段一（精简）：{len(done)} 件已完成，跳过")
        return done
    print(f"  阶段一（精简）：待审 {len(todo)} 件（已完成 {len(done)}），每批 {batch}")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        user = (f"博物馆语境：\n{ctx}\n\n本馆数据实情：\n{note}\n\n"
                f"请逐件列出以下 {len(chunk)} 件对象缺什么：\n\n"
                + "\n\n".join(fmt_item(it) for it in chunk))
        want = {it["seq"] for it in chunk}
        data = ask(client, model, STAGE1_SLIM_SYSTEM, user, "audit_stage1_slim",
                   STAGE1_SLIM_SCHEMA, effort, museum_key=mk,
                   scope=f"seq {chunk[0]['seq']}-{chunk[-1]['seq']}",
                   seqs=[it["seq"] for it in chunk],
                   validate=lambda d, w=want: _slim_ok(d, w))
        for r in data["results"]:
            check1_slim(r)          # 这里只剩兜底，正常路径已在 validate 里过了
            append(out, r)
            done[r["seq"]] = r
        print(f"    {min(i + batch, len(todo))}/{len(todo)}")
    return done


def stage2(client, model, effort, ctx, note, items, s1: dict, out: Path, batch: int,
           mk: str) -> dict:
    cands = [it for it in items if it["tier"] in ("S", "A")]
    done = read_done(out)
    todo = [it for it in cands if it["seq"] not in done]
    if not todo:
        print(f"  阶段二：{len(cands)} 件 S/A 已完成，跳过")
        return done
    print(f"  阶段二：{len(cands)} 件 S/A，待深审 {len(todo)}，每批 {batch}")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        blocks = []
        for it in chunk:
            b = fmt_item(it)
            r1 = s1.get(it["seq"])
            if r1:
                # 把阶段一的结论一并交出去，深审是在它之上追问，不是从头再来一遍
                b += (f"\n阶段一审计结论: 完备度 {completeness_of({x['key']: x['grade'] for x in r1['items']}):.1f}"
                      f"｜Tier 可信度 {r1['tier_confidence']}"
                      f"｜潜在区间 {r1['potential_low']}–{r1['potential_high']}")
                if r1["missing"]:
                    b += "\n  阶段一列出的缺失证据: " + "；".join(m["zh"] for m in r1["missing"])
            blocks.append(b)
        user = (f"博物馆语境：\n{ctx}\n\n本馆数据实情：\n{note}\n\n"
                f"请对以下 {len(chunk)} 件 S/A 对象逐件做六问深审：\n\n"
                + "\n\n".join(blocks))
        data = ask(client, model, STAGE2_SYSTEM, user, "audit_stage2", STAGE2_SCHEMA,
                   effort, museum_key=mk,
                   scope=f"S/A seq {chunk[0]['seq']}-{chunk[-1]['seq']}",
                   seqs=[it['seq'] for it in chunk])
        got = {r["seq"] for r in data["results"]}
        miss = {it["seq"] for it in chunk} - got
        if miss:
            raise RuntimeError(f"阶段二漏审 seq={sorted(miss)}")
        for r in data["results"]:
            check2(r)
            append(out, r)
            done[r["seq"]] = r
        print(f"    {min(i + batch, len(todo))}/{len(todo)}")
    return done


# ---------------------------------------------------------------------------
# 阶段三：逐条 claim 判 FACT / INFERENCE
# ---------------------------------------------------------------------------
STAGE3_SYSTEM = COMMON_RULES + """

本阶段审的是一条条 metadata 取值本身，不是对象。这些取值都来自 Evidence Packet
（source_key='evidence'），是以往由模型撰写的 significance 判断。

逐条给出：

  evidence_type   FACT      —— 有外部资料直接支撑，例如馆方官网、展览图录、
                               学术出版、UNESCO、权威文化遗产数据库
                  INFERENCE —— 由 Ariadne / AI 依据事实作出的判断

  source_quality  strong    —— 提案 Tier 1–2：馆方官方发布、UNESCO、国家文物机构、
                               展览图录、学术论文
                  moderate  —— Tier 3：专业艺术数据库、重要拍卖行、可靠文化机构
                  weak      —— Tier 4：一般网络资料；**或该 claim 目前只有原
                               description 与 AI 推断支撑**

  real_source     若判 FACT，必须给出真正的原始来源（机构名 / 出版物 / URL）。
                  **不许编造。** 指不出具体来源就判 INFERENCE 且 source_quality=weak，
                  real_source 给 null。

【必须记住的一条】
「Evidence Packet」只是信息容器，**不是信息来源**。看到来源字段写着
"Evidence Packet source_tier=1" 不构成任何证据 —— 那只是上一轮自己填的标签。
不要因为它写着 tier=1 就判 strong。要问的是：这句话背后到底是谁说的？
如果只有 Ariadne 自己说过，那就是 INFERENCE + weak，如实标注。

预期结果里 INFERENCE 会占绝大多数，这是正常的、也是本轮要暴露的事实。
如果你把大批 sig_* 判成了 FACT，多半是判错了。"""

STAGE3_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seq": {"type": "integer"},
                    "key": {"type": "string"},
                    "evidence_type": {"type": "string", "enum": ["FACT", "INFERENCE"]},
                    "source_quality": {"type": "string",
                                       "enum": ["strong", "moderate", "weak"]},
                    "real_source": _nullable("string"),
                },
                "required": ["seq", "key", "evidence_type", "source_quality", "real_source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def stage3(client, model, effort, ctx, note, items, claims, out: Path, batch: int,
           mk: str) -> dict:
    """键用 "seq|key" —— 一件对象有 9 条 sig_*，光用 seq 会互相覆盖。"""
    done = read_done(out, key="ck")
    todo = [c for c in claims if f"{c['seq']}|{c['key']}" not in done]
    if not todo:
        print(f"  阶段三：{len(done)} 条取值已完成，跳过")
        return done
    by_seq = {it["seq"]: it for it in items}
    print(f"  阶段三：待审 {len(todo)} 条取值（已完成 {len(done)}），每批 {batch}")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        lines = []
        for c in chunk:
            it = by_seq.get(c["seq"], {})
            lines.append(
                f"[seq {c['seq']} / {c['key']}] 对象：{it.get('name_en') or it.get('name_zh') or '—'}"
                f"（当前 Tier {it.get('tier') or '无'}）\n"
                f"  取值: {c['text']}\n"
                f"  当前记录的来源: {c['source'] or '—'}｜可信度: {c['confidence']}")
        user = (f"博物馆语境：\n{ctx}\n\n本馆数据实情：\n{note}\n\n"
                f"请逐条判定以下 {len(chunk)} 条取值：\n\n" + "\n\n".join(lines))
        data = ask(client, model, STAGE3_SYSTEM, user, "audit_stage3", STAGE3_SCHEMA,
                   effort, museum_key=mk, scope=f"{len(chunk)} 条取值",
                   seqs=[c['seq'] for c in chunk])
        got = {f"{r['seq']}|{r['key']}" for r in data["results"]}
        miss = {f"{c['seq']}|{c['key']}" for c in chunk} - got
        if miss:
            raise RuntimeError(f"阶段三漏审 {sorted(miss)}")
        for r in data["results"]:
            if r["evidence_type"] == "FACT" and not r["real_source"]:
                raise RuntimeError(f"{r['seq']}|{r['key']} 判了 FACT 却指不出来源")
            r["ck"] = f"{r['seq']}|{r['key']}"
            append(out, r)
            done[r["ck"]] = r
        print(f"    {min(i + batch, len(todo))}/{len(todo)}")
    return done


# ---------------------------------------------------------------------------
# 审阅 CSV
# ---------------------------------------------------------------------------

def write_review(items, s1, s2, path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "名称EN", "名称CN", "当前Tier", "Core", "完备度",
                    "Tier可信度", "潜在区间", "研究优先级", "需复核", "复核原因",
                    "去推断后仍成立", "最关键缺失证据", "建议研究问题",
                    "缺失证据全部", "12项判定"])
        for it in items:
            r1 = s1.get(it["seq"])
            if not r1:
                continue
            r2 = s2.get(it["seq"], {})
            grades = {x["key"]: x["grade"] for x in r1["items"]}
            comp = completeness_of(grades)
            low, high = r1["potential_low"], r1["potential_high"]
            core = it["v3"]["core"] if it["v3"] else None
            w.writerow([
                it["seq"], it["name_en"], it["name_zh"], it["tier"],
                f"{core:.3f}" if core is not None else "",
                f"{comp:.1f}",
                r1["tier_confidence"],
                f"{low}–{high}" if low != high else low,
                f"{priority_of(comp, low, high, core):.2f}",
                "是" if (r1["review_flag"] or r2.get("found_factual_error")) else "",
                r1["review_reason_zh"] or r2.get("error_note_zh") or "",
                "" if "inference_only_survives" not in r2
                   else ("是" if r2["inference_only_survives"] else "否"),
                r1["top_missing_zh"] or "",
                r1["research_question_zh"] or "",
                "；".join(m["zh"] for m in r1["missing"]),
                " ".join(f"{k}={grades[k]}" for k in ITEM_KEYS),
            ])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", default="pem")
    ap.add_argument("--out-dir", default="./audit_out")
    ap.add_argument("--stage", default="all", choices=["all", "1", "2", "3"])
    ap.add_argument("--batch", type=int, default=12, help="阶段一每批件数")
    ap.add_argument("--provider", choices=["openai", "claude_cli"], default="openai",
                    help="审计走哪条路。默认 openai（需 ~/.openai_key）；"
                         "claude_cli 走本机订阅账号，**但要先确认打分者不是 Anthropic** "
                         "—— 两端同源时审计就成了自评，见文件头")
    ap.add_argument("--only-seq", type=int, action="append",
                    help="只审指定 source_seq（可重复给），用于逐件复核")
    ap.add_argument("--slim", action="store_true",
                    help="精简版：阶段一只输出缺失证据与事实错误，且**跳过阶段二** —— "
                         "实测阶段二六问里三问在 248 件 S/A 上是单一答案，"
                         "而阶段一的四列判定要么饱和要么方向可疑（见 STAGE1_SLIM_SYSTEM）")
    ap.add_argument("--limit", type=int, help="只审前 N 件，用于冒烟")
    ap.add_argument("--model", default=os.environ.get("OPENAI_MODEL", ""),
                    help="OpenAI 型号；不传则取环境变量 OPENAI_MODEL")
    ap.add_argument("--effort", default=os.environ.get("OPENAI_EFFORT", ""),
                    help="推理强度，如 xhigh / high / medium / low，也认「extra high」"
                         "「超高」这类叫法。**不给就按 STAGE_EFFORT 的分阶段推荐值**"
                         "（当前四个阶段都是 medium，依据见该常量注释）。"
                         "注意 effort 参与 llm_cache 的键：改档位 = 对应阶段整批重跑，"
                         "且新旧两批结果不可直接比较"),
    ap.add_argument("--key-file", default="~/.openai_key",
                    help="OpenAI key 文件（权限须为 600）；OPENAI_API_KEY 存在时优先用它")
    args = ap.parse_args()

    # claude_cli 有默认型号（claude_cli.DEFAULT_MODEL），不强制 --model；
    # 走 OpenAI 时仍然必须显式指定 —— 型号写死在代码里会让 audited_by 记错出处。
    if not args.model and args.provider != "claude_cli":
        sys.exit("没指定型号：用 --model，或设环境变量 OPENAI_MODEL")
    global CLAUDE_CLI
    if args.provider == "claude_cli":
        import claude_cli
        if not claude_cli.available():
            sys.exit("找不到 `claude` 命令。装 Claude Code，或用默认的 --provider openai")
        CLAUDE_CLI = args.model or claude_cli.DEFAULT_MODEL
        print(f"[provider] claude CLI（订阅账号）/ {CLAUDE_CLI}；--effort 在此路径下无效")

    # 不给 --effort 就用分阶段推荐值；给了就一次覆盖全部阶段。
    eff = {s: norm_effort(args.effort or STAGE_EFFORT[s]) for s in STAGE_EFFORT}
    effort = eff["audit_stage1"]        # 供下方沿用旧签名的几处调用
    note = MUSEUM_NOTE.get(args.museum)
    if note is None:
        sys.exit(f"MUSEUM_NOTE 里没有 {args.museum} 的数据实情。这一段决定审计者对"
                 "「手上到底有什么」的认识，缺了它只能靠猜 —— 先补上再审")
    ctx = CONTEXTS.get(args.museum)
    if ctx is None:
        sys.exit(f"museum_context.py 里没有 {args.museum} 的馆级语境，先补上再审 —— "
                 "缺语境时 IU 与类别代表性的判断会失去依据")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mk = args.museum

    conn = M.connect()
    cur = conn.cursor()
    items = load_items(cur, mk, args.limit)
    claims = load_claims(cur, mk)
    conn.close()

    if args.only_seq:
        want = set(args.only_seq)
        items = [it for it in items if it["seq"] in want]
        claims = [c for c in claims if c["seq"] in want]
        if (miss := want - {it["seq"] for it in items}):
            sys.exit(f"--only-seq 指定的 {sorted(miss)} 不在本馆展品里")

    scored = sum(1 for it in items if it["v3"])
    dist = collections.Counter(it["tier"] or "无" for it in items)
    print(f"{mk.upper()}：{len(items)} 件"
          + ("（--limit 截断）" if args.limit else "")
          + f"，其中 {scored} 件有 V3.0 评分")
    print(f"当前 Tier 分布：{dict(sorted(dist.items(), key=lambda x: TIERS.index(x[0]) if x[0] in TIER_IDX else 9))}")
    print(f"待逐条判定的 Evidence Packet 取值：{len(claims)} 条")

    # 审计者身份落盘，audit_load.py 默认从这里读，写进 artwork_evidence.audited_by。
    # 与 artwork_tier_v3.scored_by 对照，事后一眼能看出审计者与打分者是否同源。
    # audited_by 是判断「这批审计怎么来的」的唯一依据，分阶段档位必须记全。
    used = ("audit_stage1_slim",) if args.slim else ("audit_stage1", "audit_stage2")
    tag = (f"{CLAUDE_CLI} (claude-cli)" if CLAUDE_CLI
           else args.model + " effort=" + "/".join(eff[s] for s in used))
    (out_dir / f"{mk}.model").write_text(tag, encoding="utf-8")
    print(f"审计者：{tag}")

    client = LazyClient(args.key_file)
    p1 = out_dir / f"{mk}_audit1.jsonl"
    p2 = out_dir / f"{mk}_audit2.jsonl"
    p3 = out_dir / f"{mk}_audit3.jsonl"

    if args.slim:
        # 精简版另落一份 JSONL，不与旧口径的 audit1 混在一起 —— 两套判据的产物
        # 若共用一个文件，断点续跑会把它们当成同一批，而它们的字段根本不同。
        p1s = out_dir / f"{mk}_audit1_slim.jsonl"
        s1s = stage1_slim(client, args.model, eff["audit_stage1_slim"], ctx, note, items, p1s,
                          args.batch, mk)
        if args.stage in ("all", "3"):
            stage3(client, args.model, eff["audit_stage3"], ctx, note, items, claims, p3,
                   args.batch, mk)
        n_sens = sum(1 for r in s1s.values()
                     if any(m["tier_sensitive"] for m in r["missing"]))
        n_err = sum(1 for r in s1s.values() if r["found_factual_error"])
        n_clean = sum(1 for r in s1s.values() if not r["missing"])
        print(f"\n精简审计：{len(s1s)} 件")
        print(f"  有 tier_sensitive 缺口（该进研究队列）：{n_sens} 件"
              f"（{n_sens / len(s1s) * 100:.0f}%）")
        print(f"  资料已足、无缺口：{n_clean} 件")
        print(f"  发现事实错误：{n_err} 件")
        print(f"\n产物：{p1s}")
        print("完备度不在本模式产出 —— 由 evidence_score.py 的规则口径给（零 API）。")
        return

    s1 = read_done(p1)
    s2 = read_done(p2)
    if args.stage in ("all", "1"):
        s1 = stage1(client, args.model, eff["audit_stage1"], ctx, note, items, p1, args.batch, mk)
    if args.stage in ("all", "2"):
        s2 = stage2(client, args.model, eff["audit_stage2"], ctx, note, items, s1, p2,
                    max(1, args.batch // 2), mk)
    if args.stage in ("all", "3"):
        stage3(client, args.model, eff["audit_stage3"], ctx, note, items, claims, p3, args.batch, mk)

    if s1:
        review = out_dir / f"{mk}_audit_review.csv"
        write_review(items, s1, s2, review)
        comps = sorted(completeness_of({x["key"]: x["grade"] for x in r["items"]})
                       for r in s1.values())
        print(f"\n完备度：最低 {comps[0]:.1f} / 中位 {comps[len(comps)//2]:.1f} / "
              f"最高 {comps[-1]:.1f} / 均值 {sum(comps)/len(comps):.1f}")
        cdist = collections.Counter(r["tier_confidence"] for r in s1.values())
        print(f"Tier 可信度：{dict(cdist)}")
        print(f"需复核：{sum(1 for r in s1.values() if r['review_flag'])} 件")
        print(f"\n审阅表：{review}")
        print("确认无误后再跑 audit_load.py 写库。审计不改任何 tier。")


if __name__ == "__main__":
    main()
