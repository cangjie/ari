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


def norm_effort(s: str | None) -> str | None:
    return EFFORT_ALIASES.get(s.strip().lower(), s.strip()) if s else None


def ask(client, model: str, system: str, user: str, name: str, schema: dict,
        effort: str | None = None) -> dict:
    """一次结构化输出调用。strict 模式保证返回的是合法且合规的 JSON。

    刻意不传 temperature / max_tokens：型号由 --model 决定，而不同代际的模型对这
    两个参数的支持并不一致（有的推理型号直接拒收 temperature，有的把 max_tokens
    换成了 max_completion_tokens）。全部走服务端默认值，换型号时不必改代码。
    reasoning_effort 只在显式传了 --effort 时才带上，同样不替型号做假设。
    """
    kw = {}
    if effort:
        kw["reasoning_effort"] = effort
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_schema",
                         "json_schema": {"name": name, "strict": True, "schema": schema}},
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        **kw,
    )
    msg = resp.choices[0].message
    if getattr(msg, "refusal", None):
        raise RuntimeError(f"模型拒答：{msg.refusal}")
    return json.loads(msg.content)


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

【关于 PEM 这批数据你必须知道的实情】
PEM 官方藏品门户 explore-art.pem.org 已停服，196 件里官方页面链接 0 条。
除少数几件在 pem.org 藏品栏目页或 Wikidata 上核实过，其余的「资料」实际上只有
一段来路不明的简介。所以低完备度是**如实的结论**，不是你没审好。
看到一件只有名称和一句套话简介的东西，就该判低完备度、低可信度、写明缺什么。"""

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

【三】Potential Tier Range：给出 potential_low 与 potential_high

  含义是：**结合现有证据与未知信息，这件对象合理的潜在 Tier 范围**。
  low 是下界（最差可能是几级），high 是上界（最好可能到几级），
  用 S/A/B/C 表示，且 low 不得优于 high（S 最优，C 最差）。
  资料已经充分时，两者相同（如 A 和 A）。
  资料严重不足、且有合理线索指向更高等级时，区间就该拉开（如 B 和 S）。
  拉开区间不是猜测，是承认「我们不知道」。

【四】Missing Evidence：真正影响 Tier 判断的缺失资料

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

以及 review_flag（true / false）。以下情形之一为真时置 true 并写明 review_reason：
  · 当前 Tier 明显缺乏证据支撑
  · 新资料有可能导致跨 Tier
  · 现有资料自相矛盾
  · 以往可能因 description 不完整而被低估
  · 以往可能因宣传性 description 而被高估
  · 发现明显的事实错误
不满足就置 false，review_reason 给 null。**不要为了显得认真而滥标。**"""


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
                            "properties": {"zh": {"type": "string"}, "en": {"type": "string"}},
                            "required": ["zh", "en"],
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
    for m in rec["missing"]:
        if len(m["zh"]) < 6 or "更多资料" in m["zh"] or "信息不足" in m["zh"]:
            raise RuntimeError(f"seq {rec['seq']} 的缺失证据太空泛：{m['zh']}")


def stage1(client, model, effort, ctx, items, out: Path, batch: int) -> dict:
    done = read_done(out)
    todo = [it for it in items if it["seq"] not in done]
    if not todo:
        print(f"  阶段一：{len(done)} 件已完成，跳过")
        return done
    print(f"  阶段一：待审 {len(todo)} 件（已完成 {len(done)}），每批 {batch}")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        user = (f"博物馆语境：\n{ctx}\n\n"
                f"请逐件审计以下 {len(chunk)} 件对象：\n\n"
                + "\n\n".join(fmt_item(it) for it in chunk))
        data = ask(client, model, STAGE1_SYSTEM, user, "audit_stage1", STAGE1_SCHEMA, effort)
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

你可以在本阶段修正阶段一的 tier_confidence 与潜在区间 —— 深审后看法变了是正常的，
按你现在的判断给出。但仍然**不得给出新的 Tier**。"""

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
                    "tier_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "potential_low": {"type": "string", "enum": TIERS},
                    "potential_high": {"type": "string", "enum": TIERS},
                    "review_flag": {"type": "boolean"},
                    "review_reason_zh": _nullable("string"),
                    "review_reason_en": _nullable("string"),
                },
                "required": ["seq", "answers", "inference_only_survives", "tier_confidence",
                             "potential_low", "potential_high", "review_flag",
                             "review_reason_zh", "review_reason_en"],
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
    if TIER_IDX[rec["potential_low"]] < TIER_IDX[rec["potential_high"]]:
        raise RuntimeError(f"seq {rec['seq']} 区间方向反了")
    if rec["review_flag"] and not rec["review_reason_zh"]:
        raise RuntimeError(f"seq {rec['seq']} 标了 review_flag 却没写原因")
    q6 = next(a for a in rec["answers"] if a["q"] == "q6_survives")
    if (q6["verdict"] == "yes") != rec["inference_only_survives"]:
        raise RuntimeError(f"seq {rec['seq']} 的 q6 结论与 inference_only_survives 不一致")


def stage2(client, model, effort, ctx, items, s1: dict, out: Path, batch: int) -> dict:
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
        user = (f"博物馆语境：\n{ctx}\n\n"
                f"请对以下 {len(chunk)} 件 S/A 对象逐件做六问深审：\n\n"
                + "\n\n".join(blocks))
        data = ask(client, model, STAGE2_SYSTEM, user, "audit_stage2", STAGE2_SCHEMA, effort)
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


def stage3(client, model, effort, ctx, items, claims, out: Path, batch: int) -> dict:
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
        user = (f"博物馆语境：\n{ctx}\n\n"
                f"请逐条判定以下 {len(chunk)} 条取值：\n\n" + "\n\n".join(lines))
        data = ask(client, model, STAGE3_SYSTEM, user, "audit_stage3", STAGE3_SCHEMA, effort)
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
            low = r2.get("potential_low", r1["potential_low"])
            high = r2.get("potential_high", r1["potential_high"])
            core = it["v3"]["core"] if it["v3"] else None
            w.writerow([
                it["seq"], it["name_en"], it["name_zh"], it["tier"],
                f"{core:.3f}" if core is not None else "",
                f"{comp:.1f}",
                r2.get("tier_confidence", r1["tier_confidence"]),
                f"{low}–{high}" if low != high else low,
                f"{priority_of(comp, low, high, core):.2f}",
                "是" if (r2.get("review_flag") or r1["review_flag"]) else "",
                r2.get("review_reason_zh") or r1["review_reason_zh"] or "",
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
    ap.add_argument("--limit", type=int, help="只审前 N 件，用于冒烟")
    ap.add_argument("--model", default=os.environ.get("OPENAI_MODEL", ""),
                    help="OpenAI 型号；不传则取环境变量 OPENAI_MODEL")
    ap.add_argument("--effort", default=os.environ.get("OPENAI_EFFORT", ""),
                    help="推理强度，如 xhigh / high / medium / low，也认「extra high」"
                         "「超高」这类叫法；不传则不带该参数，走服务端默认")
    ap.add_argument("--key-file", default="~/.openai_key",
                    help="OpenAI key 文件（权限须为 600）；OPENAI_API_KEY 存在时优先用它")
    args = ap.parse_args()

    if not args.model:
        sys.exit("没指定型号：用 --model，或设环境变量 OPENAI_MODEL")
    effort = norm_effort(args.effort)
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

    scored = sum(1 for it in items if it["v3"])
    dist = collections.Counter(it["tier"] or "无" for it in items)
    print(f"{mk.upper()}：{len(items)} 件"
          + ("（--limit 截断）" if args.limit else "")
          + f"，其中 {scored} 件有 V3.0 评分")
    print(f"当前 Tier 分布：{dict(sorted(dist.items(), key=lambda x: TIERS.index(x[0]) if x[0] in TIER_IDX else 9))}")
    print(f"待逐条判定的 Evidence Packet 取值：{len(claims)} 条")

    # 审计者身份落盘，audit_load.py 默认从这里读，写进 artwork_evidence.audited_by。
    # 与 artwork_tier_v3.scored_by 对照，事后一眼能看出审计者与打分者是否同源。
    tag = args.model + (f" effort={effort}" if effort else "")
    (out_dir / f"{mk}.model").write_text(tag, encoding="utf-8")
    print(f"审计者：{tag}")

    client = LazyClient(args.key_file)
    p1 = out_dir / f"{mk}_audit1.jsonl"
    p2 = out_dir / f"{mk}_audit2.jsonl"
    p3 = out_dir / f"{mk}_audit3.jsonl"

    s1 = read_done(p1)
    s2 = read_done(p2)
    if args.stage in ("all", "1"):
        s1 = stage1(client, args.model, effort, ctx, items, p1, args.batch)
    if args.stage in ("all", "2"):
        s2 = stage2(client, args.model, effort, ctx, items, s1, p2, max(1, args.batch // 2))
    if args.stage in ("all", "3"):
        stage3(client, args.model, effort, ctx, items, claims, p3, args.batch)

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
