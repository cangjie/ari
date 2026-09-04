#!/usr/bin/env python3
"""按《Ariadne 文化遗产参观优先级算法 V3.0》重新评定展品 tier。

算法原文见 `docs/Ariadne文化遗产Tier算法V3.0.txt`，本脚本是它的逐条实现。

为什么要分三阶段跑，而不是一次问完：

  阶段一  逐件打 HS/IU/VI/VA/CE 五个维度。这五个维度只依赖对象自身，
          可以独立判断，所以按批并行。同时定对象类型（决定权重表）和
          Peer Group（供阶段二用）。
  阶段二  算 CR。CR = 0.5Q + 0.3D + 0.2G，其中 D 是「相对同类对象的
          独特性」—— 这是**组内比较**，逐件独立问必然得不到正确答案，
          会退化成「每件都挺独特」。必须把整个 Peer Group 一起交给模型。
          算法第五节写明这机制就是用来防「所有宋瓷都升为 A」的。
  阶段三  S-ness Test。只对 Core ≥ 8.5 且至少一维 ≥ 9 的候选跑，
          其余对象结果用不上，不必花钱。

中间结果按阶段写 JSONL，跑挂了重跑会跳过已完成的条目。

用法：
    # 冒烟：只跑 12 件，确认链路通
    python3 tier_v3.py --museum pem --limit 12 --out-dir ./tier_v3_out

    # 全量试点
    python3 tier_v3.py --museum pem --out-dir ./tier_v3_out

产物 `<out-dir>/<museum>_review.csv` 是给人审的：每件的六个维度分、Core、
新旧 tier 对比、评分依据、证据可信度。**确认无误前不要写库。**
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("缺少 openpyxl：pip install openpyxl")

from museum_context import CONTEXTS


MODEL = "claude-opus-5"

# ---------------------------------------------------------------------------
# V3.0 第四节：不同对象类型的权重。三套权重各自归一，改动前先核对总和为 1。
# ---------------------------------------------------------------------------
WEIGHTS = {
    "object": {"HS": .20, "IU": .25, "VI": .15, "VA": .15, "CE": .15, "CR": .10, "ER": .00},
    "node":   {"HS": .15, "IU": .20, "VI": .15, "VA": .15, "CE": .15, "CR": .10, "ER": .10},
    "site":   {"HS": .15, "IU": .20, "VI": .15, "VA": .10, "CE": .15, "CR": .05, "ER": .20},
}
for _t, _w in WEIGHTS.items():
    assert abs(sum(_w.values()) - 1.0) < 1e-9, f"{_t} 权重不等于 1"

DIMS = ["HS", "IU", "VI", "VA", "CE"]  # 阶段一打的五维；CR 走阶段二，ER 见下

# V3.0 第三节把 ER 定义为「与轴线、地形、水体、视线、仪式路径的关系」，
# 明说是为建筑群/园林/遗址设的。单件展品权重 0%，不打分；node/site 才需要。
DIMS_WITH_ER = DIMS + ["ER"]


@dataclass
class Museum:
    """一个馆的源数据在哪、字段怎么取。六馆格式各异，差异全收敛在这里。"""
    key: str
    label: str
    path: str
    sheet: str
    header_row: int          # 表头所在行（0-based）；中文馆第 0 行是大标题
    col_name_en: int | None
    col_name_cn: int | None
    col_gallery: int | None
    col_desc: int | None
    col_category: int | None
    col_tier_old: int        # 入库用的那一列 tier（AGENTS.md 数据库约定第 5 条）
    context: str             # 交给模型的馆级语境，直接影响 IU 与 CR 的判断


MUSEUMS = {
    "pem": Museum(
        key="pem",
        label="Peabody Essex Museum",
        path="artworks/PEM_带tier_c.xlsx",
        sheet="All Tiers",
        header_row=0,
        col_name_en=2, col_name_cn=3, col_gallery=4,
        col_desc=5, col_category=8, col_tier_old=0,
        # 语境已挪进 museum_context.py：audit_meta.py 也要用同一段文字，
        # 两边各存一份改漏了不会报错，只会让评级与审计悄悄用上两套不同的定义。
        context=CONTEXTS["pem"],
    ),
    "mfa_boston": Museum(
        key="mfa_boston",
        label="Museum of Fine Arts, Boston",
        path="artworks/MFA_Ariadne_1300_Artwork_Database.xlsx",
        sheet="Master",
        header_row=0,
        # Master 页 1300 行里只有 203 行有名称，其余是空占位，且从第 30 行起
        # 就开始夹杂 —— load_items 必须按**过滤后**的计数生成 seq，才能与
        # import_artworks.read_museum 的 seq_auto 对齐。
        col_name_en=2, col_name_cn=3, col_gallery=4,
        col_desc=8, col_category=14, col_tier_old=1,
        context=CONTEXTS["mfa_boston"],
    ),
    "ham": Museum(
        key="ham",
        label="Harvard Art Museums",
        path="artworks/ham_带tier_c.xlsx",
        sheet="All Tiers",
        header_row=0,
        # tier 取第 3 列的 Tier，不取第 4 列的 tier_c（AGENTS.md 数据库约定第 5 条：
        # 一律以原表评级列为准，两列在哈佛有 86 条不一致）
        col_name_en=0, col_name_cn=1, col_gallery=2,
        col_desc=5, col_category=8, col_tier_old=3,
        context=CONTEXTS["ham"],
    ),
    "mfa_boston_ext": Museum(
        key="mfa_boston_ext",
        label="Museum of Fine Arts, Boston (Extended List)",
        path="artworks/MFA_展品清单_400_带Tier.xlsx",
        sheet="展品清单",
        # 表头在第 4 行（0 基下标 3），与三个中文馆同构；前三行是大标题与说明。
        header_row=3,
        # 名称与简介都只有中文一列；类别没有独立列（材质写在名称的括号注里，
        # 已由 meta_fill_official_mfa.py 抽成 metadata，走 --evidence 进提示词）。
        col_name_en=None, col_name_cn=2, col_gallery=1,
        col_desc=3, col_category=None, col_tier_old=7,
        # 与 mfa_boston 逐字共用同一段语境 —— 同一个馆若用两套「哪些东西算要紧」
        # 的定义，两份数据的评分不可比，而且不会报错。
        context=CONTEXTS["mfa_boston_ext"],
    ),
    # 故宫、国博、首博待填。故宫需特别注意：1757 件共用 7 段展厅级套话简介，
    # 逐件评分只能依据名称——源文件「评级标准」页自己写明了这一点。
}


# ---------------------------------------------------------------------------
# 读源数据
# ---------------------------------------------------------------------------

def load_items(m: Museum, base: Path, limit: int | None) -> list[dict]:
    wb = openpyxl.load_workbook(base / m.path, read_only=True, data_only=True)
    rows = list(wb[m.sheet].iter_rows(values_only=True))
    wb.close()

    def cell(row, i):
        if i is None or i >= len(row):
            return ""
        v = row[i]
        return "" if v is None else str(v).strip()

    # seq 必须与 import_artworks.read_museum 的 seq_auto 逐条对齐 —— 那边是
    # **过滤之后**才自增的。早先这里用 enumerate 的行号，被跳过的空行照样把计数
    # 推进，于是 MFA（1300 行里 1096 行是空占位，且从第 30 行起就开始夹杂）
    # 每一件的 seq 都会错位，写库时张冠李戴且不报错 —— 名字对不上号也没人拦。
    # PEM 与哈佛没有空行，两种算法碰巧一致，所以这个 bug 一直没暴露。
    items, seq_auto = [], 0
    for row in rows[m.header_row + 1:]:
        name_en = cell(row, m.col_name_en)
        name_cn = cell(row, m.col_name_cn)
        if not (name_en or name_cn):
            continue
        if name_en in ("ArtWorkName_EN", "Name (English)") or name_cn == "展品名称":
            continue                       # MFA Master 页中间混着的表头行
        seq_auto += 1
        items.append({
            "seq": seq_auto,
            "name_en": name_en,
            "name_cn": name_cn,
            "gallery": cell(row, m.col_gallery),
            "description": cell(row, m.col_desc),
            "category": cell(row, m.col_category),
            "tier_old": cell(row, m.col_tier_old),
        })
    return items[:limit] if limit else items


# ---------------------------------------------------------------------------
# JSONL 断点续跑
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


class LazyClient:
    """用得着才构造真客户端。

    三个阶段的中间结果都可以由外部预先填进 JSONL（例如在一次 Claude 会话里
    人工/模型评完再落盘），此时整轮不需要任何 API 调用。若在这种情况下仍
    无条件构造 `anthropic.Anthropic()`，没有凭据的机器会在什么都没做之前
    就直接报错。所以推迟到第一次真要发请求时再构造。
    """

    def __init__(self) -> None:
        self._c = None

    def __getattr__(self, name):
        if self._c is None:
            try:
                import anthropic
            except ImportError:
                sys.exit("缺少 anthropic：pip install anthropic")
            self._c = anthropic.Anthropic()
        return getattr(self._c, name)


# --provider openai 时由 main 填上；为 None 表示走原来的 Anthropic 路径。
# 做成模块级变量而不是层层传参，是因为 ask() 有六个调用点，
# 每个都改签名只会让这次「换供应商」的临时性掩盖在一堆参数里。
OPENAI = None          # (client, model, {stage: effort})
CLAUDE_CLI = None      # 型号字符串；非 None 时走 claude CLI 的订阅账号

# 按阶段分配推理强度。**依据是 2026-09-04 在水月观音上的实测**（同一提示词、
# 只改 effort，输入 token 完全相同 6638，可直接归因）：
#
#   阶段          xhigh→medium 推理降幅   分数变化           结论
#   tier_stage1   262→151  (-42%)        IU -0.4（权重最高） 降太多，用 high
#   tier_stage2   183→107  (-42%)        D  -0.2            单件组无从横比，medium 够
#   tier_stage3   252→231  ( -8%)        三个是非题，无变化   几乎不省钱，保住关卡用 xhigh
#
# 九个维度里八个下降、无一上升 —— 不是随机噪声，medium 会系统性地略保守。
# Core 降了 0.168，而门槛卡在 8.5/7.2/5.5，边界附近的展品会因此改判，
# 所以权重最高的 IU 所在的阶段一不能省。
#
# ⚠ effort 参与 llm_cache 的缓存键：改这里等于让对应阶段整批重跑，
# 且新旧两批不可直接比较。改动前想清楚，并在结论里标明档位。
STAGE_EFFORT = {
    "tier_stage1": "high",
    "tier_stage2": "medium",
    "tier_stage3": "xhigh",
}


def ask(client, system: str, user: str, schema: dict, *,
        stage: str = "tier_v3", museum_key: str | None = None,
        scope: str | None = None, seqs=None) -> dict:
    """一次结构化输出调用。schema 保证返回的第一个 text block 是合法 JSON。

    两条路径（anthropic / openai）都经过 llm_cache：键含提示词全文，
    所以判据没改必然命中、改了必然重跑。stage 供事后分阶段算账 ——
    早先只传死字符串 "tier_v3"，三个阶段的账混在一起分不开。
    """
    if CLAUDE_CLI is not None:
        import claude_cli, llm_cache
        model = CLAUDE_CLI

        def _do():
            data, usage = claude_cli.ask(system, user, schema, model)
            return data, claude_cli.Usage(usage)

        # effort 传 None：CLI 不暴露 reasoning_effort，这条路径没有档位可调，
        # 记 NULL 比记一个想当然的值诚实。
        return llm_cache.call(_do, provider="anthropic_cli", model=model,
                              effort=None, stage=stage, system=system, user=user,
                              schema=schema, museum_key=museum_key, scope=scope,
                              seqs=seqs)

    if OPENAI is not None:
        import audit_meta as A
        oc, model, efforts = OPENAI
        return A.ask(oc, model, system, user, stage, schema, efforts.get(stage),
                     museum_key=museum_key, scope=scope, seqs=seqs)

    def _do():
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": schema},
            },
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"模型拒答：{resp.stop_details}")
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text), getattr(resp, "usage", None)

    import llm_cache
    return llm_cache.call(_do, provider="anthropic", model=MODEL, effort="high",
                          stage=stage, system=system, user=user, schema=schema,
                          museum_key=museum_key, scope=scope, seqs=seqs)


# ---------------------------------------------------------------------------
# 阶段一：五维打分 + 对象类型 + Peer Group
# ---------------------------------------------------------------------------

STAGE1_SYSTEM = """你在执行《Ariadne 文化遗产参观优先级算法 V3.0》的第一阶段评分。

算法目标（务必内化，这决定了全部判断的方向）：
Tier 衡量的**不是**一个对象在世界文化史上的绝对排名，而是**特定游客在特定
博物馆中体验它的优先级**。同一件东西放在不同的馆里，评分可以完全不同。

七个核心维度，均为 0—10 分，本阶段只打前五个：

HS  历史/艺术/遗产重要性 —— 它在历史、艺术、宗教或文明中的位置有多重要？
IU  本馆身份与不可替代性 —— 如果失去它，这个博物馆的身份是否明显受损？
    这是单件展品权重最高的维度（25%）。判断依据是**本馆语境**，不是绝对名气。
VI  视觉/空间冲击力 —— 游客现场感受到的尺度、美感、氛围有多强？
VA  游客体验吸引力 —— 即使不了解背景，普通游客是否仍会觉得惊喜、难忘？
CE  文化/教育/叙事价值 —— 它能否有效解释一个时代、文明、制度、信仰或事件？

**0—10 的分档锚点（必须严格照此换算，否则跨馆不可比）**

算法把 Tier 门槛定死在 8.5 / 7.2 / 5.5，却没有规定分值的含义。锚点缺失时，
同一批判断只要整体挪半分，结论就会天翻地覆 —— 2026-08-28 的 PEM 试点实测：
全维度统一 +0.75，「132/196 件要改」就变成「24/196 件要改」。故锚点必须写死：

  10   世界级顶点，同类中全球屈指可数
  9    本领域公认一流，国家级重要性
  8    很强，在国家或大区层面站得住
  7    良好，明确高于平均水准的精品      ← A 段（强烈推荐）的典型水位
  6    合格，典型的馆藏常规品            ← B 段（值得看但非重点）的典型水位
  5    平常，同类中可被替代
  4    次要：残件、习作、量产品
  3    边缘，仅具登记价值
  0—2  该维度上几乎无价值

对照 Tier 的语义自检：一件「强烈推荐」（A）的展品，各维度应普遍落在 7 上下；
一件「值得看但不是第一次参观重点」（B）的展品，应普遍落在 6 上下。若你给一件
明显值得强烈推荐的东西打出满堂 6.5，说明你把标尺压低了，请上调。

同时判定两件事：

object_type（决定后续权重表）：
  object —— 单件可移动展品：绘画、瓷器、雕像、家具、织物、照片等
  node   —— 建筑或空间节点：整栋建筑、庭院、复原居所、观景点、仪式路径点
  site   —— 遗产地或景观整体

peer_group —— 同类组名称。这是后续算「类别代表性 CR」的分组依据，
  必须是**本馆内部可比较的一类对象**，粒度要能形成竞争关系。
  好的例子：「美国印象派油画」「中国外销瓷」「大洋洲仪式木雕」「白银器皿」。
  坏的例子：「艺术品」（太宽，无法比较）、「梵高1889年自画像」（太窄，组内只有一件）。
  同一批性质相同的对象必须落到**同一个** peer_group 字符串上，用词保持一致。

evidence —— 一句话说明你的评分依据（中文）。
confidence —— 证据可信度：high / medium / low。
  只有名称、无实质简介、且你对该对象没有可靠领域知识时，必须给 low。
  算法第十二节要求低可信度对象不能直接成为正式 S。

评分纪律：
- 不要迎合原有评级。你看不到原评级，也不应猜测它。
- 0—10 分要真正拉开区间。如果一批对象的分数都挤在 6—8，说明你没在区分。
- 宁可给低分并说明理由，也不要给不出依据的高分。
- 简介为空或明显是套话（如整个展厅共用的一段说明）时，据实降低 confidence。"""

STAGE1_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seq": {"type": "integer"},
                    "object_type": {"type": "string", "enum": ["object", "node", "site"]},
                    "peer_group": {"type": "string"},
                    "HS": {"type": "number"}, "IU": {"type": "number"},
                    "VI": {"type": "number"}, "VA": {"type": "number"},
                    "CE": {"type": "number"},
                    "ER": {"type": "number"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["seq", "object_type", "peer_group", "HS", "IU", "VI",
                             "VA", "CE", "ER", "evidence", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def load_evidence(mk: str) -> dict[int, str]:
    """从库里取每件展品已核实的事实，供 --evidence 模式喂进评分。

    **只喂事实，不喂审计的结论。** artwork_meta 的取值（含 FACT/INFERENCE 与来源
    质量）进提示词；完备度、Tier 可信度、缺失证据一律不进。提案第 2 节讲得很清楚：
    完备度低的含义是「我不知道它是否重要」，不是「它不重要」。把「证据不足」交给
    打分者，几乎必然被读成「该压分」—— 那就把「不知道」和「不重要」混成一件事了，
    而这正是整套证据管线要拆开的两件事。

    同理不喂当前 tier 与 Core：算法第一阶段的纪律是「不要迎合原有评级」。
    """
    import meta_lib as M
    conn = M.connect()
    cur = conn.cursor()
    cur.execute("""SELECT am.source_seq, am.key_name, am.source_key, am.source,
                          am.evidence_type, am.source_quality, t.text
                   FROM artwork_meta am
                   JOIN content_text t ON t.content_id = am.value_cid AND t.lang = 'zh-CN'
                   WHERE am.museum_key = %s
                   ORDER BY am.source_seq, am.key_name, am.source_key, am.ord""", (mk,))
    rows = cur.fetchall()
    conn.close()

    out: dict[int, list[str]] = {}
    for seq, key, skey, src, etype, sq, txt in rows:
        tag = f"{etype or '?'}/{sq or '?'}"
        # 来源串一并给出：判断「这条硬不硬」要看它出自哪里，而不是看谁说得笃定
        out.setdefault(seq, []).append(f"  - {key} = {txt}  [{tag} · {skey} · {src or '—'}]")
    return {k: "\n".join(v) for k, v in out.items()}


EVIDENCE_NOTE = """
以上「已核实事实」的读法：
  FACT/strong    馆方官网等一级来源发布的编目数据，可以当事实用
  FACT/moderate  专业数据库或关联站点，基本可信但非馆方权威
  FACT/weak      出自源工作表或由名称解析而来，事实性成立但来源仍弱
  INFERENCE/*    以往 AI 依据描述作出的判断，**不是外部资料**，不得当作事实引用

**没有列出事实，不等于这件东西不重要。** 多数展品只是没人去查过。
遇到资料少的对象，按你对该类对象的领域判断评分，不要因为「资料少」就压低分数
—— 那会把「我们不知道」错记成「它不重要」，是本算法明确要避免的错误。
"""


def fmt_item(it: dict, evidence: dict[int, str] | None = None) -> str:
    parts = [f"[seq {it['seq']}]"]
    if it["name_en"]:
        parts.append(f"名称(EN): {it['name_en']}")
    if it["name_cn"]:
        parts.append(f"名称(CN): {it['name_cn']}")
    if it["gallery"]:
        parts.append(f"展厅: {it['gallery']}")
    if it["category"]:
        parts.append(f"类别: {it['category']}")
    parts.append(f"简介: {it['description'] or '（源数据无简介）'}")
    if evidence and evidence.get(it["seq"]):
        parts.append("已核实事实（来自馆方官网、Wikidata 等外部来源，逐条标了性质与来源质量）：")
        parts.append(evidence[it["seq"]])
    return "\n".join(parts)


def stage1(client, m: Museum, items: list[dict], out: Path, batch: int,
           evidence: dict | None = None) -> dict:
    done = read_done(out)
    todo = [it for it in items if it["seq"] not in done]
    if not todo:
        print(f"  阶段一：{len(done)} 件已完成，跳过")
        return done

    print(f"  阶段一：待评 {len(todo)} 件（已完成 {len(done)}），每批 {batch}")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        user = (
            f"博物馆语境：\n{m.context}\n\n"
            f"请为以下 {len(chunk)} 件对象逐一评分。ER 一栏：object_type 为 object 时"
            f"填 0（单件展品 ER 权重为 0%，不参与计算）；为 node 或 site 时正常评分。\n\n"
            + "\n\n".join(fmt_item(it, evidence) for it in chunk)
                + (EVIDENCE_NOTE if evidence else "")
        )
        data = ask(client, STAGE1_SYSTEM, user, STAGE1_SCHEMA,
                   stage="tier_stage1", museum_key=m.key,
                   scope=f"seq {chunk[0]['seq']}-{chunk[-1]['seq']}",
                   seqs=[it['seq'] for it in chunk])
        got = {r["seq"] for r in data["results"]}
        missing = {it["seq"] for it in chunk} - got
        if missing:
            raise RuntimeError(f"阶段一漏评 seq={sorted(missing)}，未写入，请重跑该批")
        for r in data["results"]:
            append(out, r)
            done[r["seq"]] = r
        print(f"    {min(i + batch, len(todo))}/{len(todo)}")
    return done


# ---------------------------------------------------------------------------
# 阶段二：Peer Group 组内算 CR
# ---------------------------------------------------------------------------

STAGE2_SYSTEM = """你在执行《Ariadne 文化遗产参观优先级算法 V3.0》第五节：类别代表性 CR。

CR = 0.5·Q + 0.3·D + 0.2·G   （Q、D、G 均为 0—10 分）

Q  同类中的品质、历史地位或典范程度。
D  相对同类对象的独特性与非重复性。
   **这一项必须在组内横向比较后给出。** 一组里性质雷同的对象，只有最具
   代表性的那一件该拿高 D，其余按重复程度递降。这正是算法用来防止
   「所有宋瓷都升为 A」「所有古建筑都是 S」评分膨胀的机制。
G  对参观路线或文明叙事的补位价值 —— 它是否填补了本馆叙事中别处没有的一环。

你会一次收到**同一个 Peer Group 内的全部对象**。请先在组内排序，再给分。
组内 D 分必须拉开差距：若一组有 8 件性质接近的对象，不允许 8 件的 D 都在 7—8 分。
若组内只有 1 件对象，D 按「本馆此类唯一」判断，通常偏高，但仍需说明理由。

cr_reason：一句话中文说明，须点出它在组内的相对位置。"""

STAGE2_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seq": {"type": "integer"},
                    "Q": {"type": "number"}, "D": {"type": "number"}, "G": {"type": "number"},
                    "cr_reason": {"type": "string"},
                },
                "required": ["seq", "Q", "D", "G", "cr_reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def stage2(client, m: Museum, items: list[dict], s1: dict, out: Path,
           evidence: dict | None = None) -> dict:
    by_seq = {it["seq"]: it for it in items}
    groups: dict[str, list[int]] = {}
    for seq, r in s1.items():
        groups.setdefault(r["peer_group"], []).append(seq)

    done = read_done(out)
    todo = {g: seqs for g, seqs in groups.items()
            if any(s not in done for s in seqs)}
    if not todo:
        print(f"  阶段二：{len(groups)} 个同类组已完成，跳过")
        return done

    print(f"  阶段二：{len(groups)} 个同类组，待算 {len(todo)} 组")
    for gi, (group, seqs) in enumerate(sorted(todo.items()), 1):
        lines = []
        for s in sorted(seqs):
            it, r = by_seq[s], s1[s]
            lines.append(
                f"[seq {s}] {it['name_en'] or it['name_cn']}"
                f"{' / ' + it['name_cn'] if it['name_en'] and it['name_cn'] else ''}\n"
                f"  类别: {it['category'] or '—'} | 展厅: {it['gallery'] or '—'}\n"
                f"  已评维度: HS={r['HS']} IU={r['IU']} VI={r['VI']} VA={r['VA']} CE={r['CE']}\n"
                f"  简介: {it['description'] or '（无）'}"
                + (f"\n  已核实事实:\n{evidence[s]}"
                   if evidence and evidence.get(s) else "")
            )
        user = (
            f"博物馆语境：\n{m.context}\n\n"
            + (EVIDENCE_NOTE + "\n" if evidence else "")
            + f"Peer Group：{group}\n"
            f"组内共 {len(seqs)} 件对象，请全部给出 Q / D / G：\n\n"
            + "\n\n".join(lines)
        )
        data = ask(client, STAGE2_SYSTEM, user, STAGE2_SCHEMA,
                   stage="tier_stage2", museum_key=m.key,
                   scope=f"{group}（{len(seqs)} 件）", seqs=seqs)
        got = {r["seq"] for r in data["results"]}
        missing = set(seqs) - got
        if missing:
            raise RuntimeError(f"阶段二组「{group}」漏算 seq={sorted(missing)}")
        for r in data["results"]:
            r["peer_group"] = group
            r["peer_size"] = len(seqs)
            append(out, r)
            done[r["seq"]] = r
        print(f"    {gi}/{len(todo)}  {group}（{len(seqs)} 件）")
    return done


# ---------------------------------------------------------------------------
# 阶段三：S-ness Test（只问候选）
# ---------------------------------------------------------------------------

STAGE3_SYSTEM = """你在执行《Ariadne 文化遗产参观优先级算法 V3.0》第七节：S-ness Test。

以下对象的加权 Core 已达到 S 的门槛。每一件请回答三个问题：

q1  如果游客只有两个小时，是否仍应安排它？
q2  如果游客离开而没有看到它，是否明显可惜？
q3  如果它从本馆消失，本馆的身份是否明显受损？

至少两个回答为 true 才能定为 S；否则按算法原则降为 A。

这是一道**收紧**的关卡，不是走过场。Core 高但属于「同类中又一件好东西」的对象，
q3 通常应为 false。请严格作答。"""

STAGE3_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seq": {"type": "integer"},
                    "q1": {"type": "boolean"}, "q2": {"type": "boolean"}, "q3": {"type": "boolean"},
                    "sness_reason": {"type": "string"},
                },
                "required": ["seq", "q1", "q2", "q3", "sness_reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def stage3(client, m: Museum, items: list[dict], cands: list[int],
           s1: dict, cores: dict, out: Path, evidence: dict | None = None) -> dict:
    by_seq = {it["seq"]: it for it in items}
    done = read_done(out)
    todo = [s for s in cands if s not in done]
    if not todo:
        print(f"  阶段三：{len(cands)} 个 S 候选已完成，跳过")
        return done

    print(f"  阶段三：{len(cands)} 个 S 候选，待测 {len(todo)}")
    lines = []
    for s in todo:
        it, r = by_seq[s], s1[s]
        lines.append(
            f"[seq {s}] {it['name_en'] or it['name_cn']}"
            f"{' / ' + it['name_cn'] if it['name_en'] and it['name_cn'] else ''}\n"
            f"  Core={cores[s]:.2f} | HS={r['HS']} IU={r['IU']} VI={r['VI']} "
            f"VA={r['VA']} CE={r['CE']}\n"
            f"  同类组: {r['peer_group']} | 展厅: {it['gallery'] or '—'}\n"
            f"  简介: {it['description'] or '（无）'}"
            + (f"\n  已核实事实:\n{evidence[s]}"
               if evidence and evidence.get(s) else "")
        )
    user = (f"博物馆语境：\n{m.context}\n\n"
            + (EVIDENCE_NOTE + "\n" if evidence else "")
            + f"以下 {len(todo)} 件对象已达 S 门槛，请逐件做 S-ness Test：\n\n"
            + "\n\n".join(lines))
    data = ask(client, STAGE3_SYSTEM, user, STAGE3_SCHEMA,
               stage="tier_stage3", museum_key=m.key,
               scope=f"S 候选 {len(todo)} 件", seqs=todo)
    got = {r["seq"] for r in data["results"]}
    missing = set(todo) - got
    if missing:
        raise RuntimeError(f"阶段三漏测 seq={sorted(missing)}")
    for r in data["results"]:
        append(out, r)
        done[r["seq"]] = r
    return done


# ---------------------------------------------------------------------------
# 定级：V3.0 第六 + 七 + 十二节
# ---------------------------------------------------------------------------

def core_of(s1r: dict, cr: float) -> float:
    w = WEIGHTS[s1r["object_type"]]
    total = sum(float(s1r[d]) * w[d] for d in DIMS) + cr * w["CR"]
    if w["ER"]:
        total += float(s1r.get("ER", 0)) * w["ER"]
    return total


def tier_of(core: float, s1r: dict, sness: dict | None) -> tuple[str, str]:
    """返回 (tier, 判定说明)。S 的三个条件缺一不可，见 V3.0 第六、七节。"""
    if core < 5.5:
        return "C", f"Core {core:.3f} < 5.5"
    if core < 7.2:
        return "B", f"Core {core:.3f} 落在 5.5–7.19"
    if core < 8.5:
        return "A", f"Core {core:.3f} 落在 7.2–8.49"

    # Core 已达 8.5，逐条查 S 的另外两个条件
    peak = max(float(s1r[d]) for d in DIMS_WITH_ER if d in s1r)
    if peak < 9:
        return "A", f"Core {core:.3f} 达标但无维度 ≥9（最高 {peak}），降 A"
    if sness is None:
        return "A", f"Core {core:.3f} 达标但未做 S-ness Test，降 A"
    yes = sum(bool(sness[q]) for q in ("q1", "q2", "q3"))
    if yes < 2:
        return "A", f"Core {core:.3f} 达标但 S-ness 仅 {yes}/3 通过，降 A"
    return "S", f"Core {core:.3f}，峰值 {peak}，S-ness {yes}/3"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", required=True, choices=sorted(MUSEUMS))
    ap.add_argument("--out-dir", default="./tier_v3_out")
    ap.add_argument("--limit", type=int, help="只跑前 N 件，用于冒烟")
    ap.add_argument("--only-seq", type=int, action="append",
                    help="只跑指定 source_seq（可重复给）。用于逐件复核；"
                         "**在 load_items 之后过滤**，不影响 seq 的生成方式")
    ap.add_argument("--batch", type=int, default=12, help="阶段一每批件数")
    ap.add_argument("--provider", choices=["anthropic", "openai", "claude_cli"],
                    default="claude_cli",
                    help="评分用哪条路。**默认 claude_cli**：走 `claude` CLI 的 "
                         "headless 模式，用本机订阅账号跑 claude-opus-5 —— 不需要 "
                         "API key，且恢复了「打分 Anthropic / 审计 OpenAI」的跨厂商设计"
                         "（2026-09-02 起两边都是 gpt-5.6-sol，交叉验证形同虚设）。"
                         "anthropic=直连 SDK 需 API key；openai=与审计同源，"
                         "跨轮比较时归因不到「证据」还是「模型」，务必在结论里标明")
    ap.add_argument("--model", default="", help="--provider openai 时的型号")
    ap.add_argument("--effort", default="",
                    help="一次把三个阶段的推理强度全设成这一档。"
                         "**不给就按 STAGE_EFFORT 的分阶段推荐值**"
                         "（阶段一 high / 阶段二 medium / 阶段三 xhigh，依据见该常量注释）")
    for _s in (1, 2, 3):
        ap.add_argument(f"--effort-stage{_s}", default="",
                        help=f"只覆盖阶段{_s}的推理强度，优先于 --effort")
    ap.add_argument("--key-file", default="~/.openai_key")
    ap.add_argument("--evidence", action="store_true",
                    help="把 artwork_meta 里已核实的事实喂进评分（只喂事实，"
                         "不喂审计的完备度/可信度结论，理由见 load_evidence 的注释）。"
                         "**务必配合独立的 --out-dir**，否则会与不带证据的那轮混在一起")
    args = ap.parse_args()

    global OPENAI, MODEL, CLAUDE_CLI
    if args.provider == "claude_cli":
        import claude_cli
        if not claude_cli.available():
            sys.exit("找不到 `claude` 命令。装 Claude Code，或改用 --provider openai")
        CLAUDE_CLI = args.model or claude_cli.DEFAULT_MODEL
        MODEL = CLAUDE_CLI + " (claude-cli)"
        print(f"[provider] claude CLI（订阅账号）/ {CLAUDE_CLI}")
        print("  注：CLI 不暴露 reasoning_effort，--effort* 在这条路径下无效；"
              "每次调用附带约 5.4k token 的 Claude Code 脚手架开销")
    elif args.provider == "openai":
        if not args.model:
            sys.exit("--provider openai 需要 --model")
        import audit_meta as A
        efforts = {}
        for st in STAGE_EFFORT:
            one = getattr(args, f"effort_stage{st[-1]}")     # --effort-stage1/2/3
            efforts[st] = A.norm_effort(one or args.effort or STAGE_EFFORT[st])
        OPENAI = (A.LazyClient(args.key_file), args.model, efforts)
        # 型号串里带上分阶段档位 —— scored_by 是判断「这批分怎么来的」的唯一依据，
        # 三个阶段用了不同档位却只记一个数字，等于把出处记错了。
        MODEL = args.model + " effort=" + "/".join(
            efforts[s] for s in ("tier_stage1", "tier_stage2", "tier_stage3"))
        print(f"[provider] openai / {MODEL}")

    base = Path(__file__).resolve().parent
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    m = MUSEUMS[args.museum]

    items = load_items(m, base, args.limit)
    if args.only_seq:
        want = set(args.only_seq)
        items = [it for it in items if it["seq"] in want]
        missing = want - {it["seq"] for it in items}
        if missing:
            sys.exit(f"--only-seq 指定的 {sorted(missing)} 在源表里不存在")
    print(f"{m.label}：{len(items)} 件"
          + ("（--limit 截断）" if args.limit else "")
          + (f"（--only-seq {sorted(args.only_seq)}）" if args.only_seq else ""))

    evidence = None
    if args.evidence:
        evidence = load_evidence(m.key)
        n = sum(1 for it in items if evidence.get(it["seq"]))
        print(f"证据模式：{n}/{len(items)} 件带已核实事实，"
              f"共 {sum(len(v.splitlines()) for v in evidence.values())} 条")

    client = LazyClient()
    p1 = out_dir / f"{m.key}_stage1.jsonl"
    p2 = out_dir / f"{m.key}_stage2.jsonl"
    p3 = out_dir / f"{m.key}_stage3.jsonl"

    s1 = stage1(client, m, items, p1, args.batch, evidence)
    s2 = stage2(client, m, items, s1, p2, evidence)

    # 先用 CR 算一遍 Core，挑出 S 候选，再决定谁需要跑阶段三
    cr, cores = {}, {}
    for it in items:
        s = it["seq"]
        g = s2[s]
        cr[s] = 0.5 * float(g["Q"]) + 0.3 * float(g["D"]) + 0.2 * float(g["G"])
        cores[s] = core_of(s1[s], cr[s])

    cands = [s for s in sorted(cores)
             if cores[s] >= 8.5
             and max(float(s1[s][d]) for d in DIMS_WITH_ER if d in s1[s]) >= 9]
    s3 = stage3(client, m, items, cands, s1, cores, p3, evidence) if cands else {}

    # 型号落盘。tier_v3_load.py 的 SCORED_BY 是写死的 claude-opus-5，
    # 换了供应商还照写就等于在库里伪造出处 —— scored_by 是判断「审计者与打分者
    # 是否同源」的唯一依据，写错了整条追溯链就断了。
    (out_dir / f"{m.key}.model").write_text(MODEL, encoding="utf-8")

    # 写审阅 CSV
    #
    # 默认对照列是源表评级（Excel 第 0 列）。但 --evidence 那一轮要回答的问题是
    # 「喂进证据之后，V3 的结论变了没有」，跟源表评级比毫无意义 —— 那两者本来就
    # 差着一整轮重评。所以证据模式下把对照换成库里现存的 V3 tier。
    old_tier = {it["seq"]: it["tier_old"] for it in items}
    old_label = "原表tier"
    if args.evidence:
        import meta_lib as M
        _c = M.connect(); _cur = _c.cursor()
        _cur.execute("SELECT source_seq, tier FROM artwork_tier_v3 WHERE museum_key=%s",
                     (m.key,))
        db = dict(_cur.fetchall()); _c.close()
        if db:
            old_tier = {s: db.get(s, "") for s in old_tier}
            old_label = "V3旧tier"
        else:
            print("  [warn] 库里没有 V3 评分，对照列仍用源表评级")

    review = out_dir / f"{m.key}_review.csv"
    changed = 0
    with review.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "名称EN", "名称CN", "展厅", "类别",
                    "对象类型", "同类组", "组内件数",
                    "HS", "IU", "VI", "VA", "CE", "ER",
                    "Q", "D", "G", "CR", "Core",
                    old_label, "V3新tier", "是否变化", "判定说明",
                    "证据可信度", "评分依据", "CR理由", "S-ness理由"])
        for it in items:
            s = it["seq"]
            r, g = s1[s], s2[s]
            t, why = tier_of(cores[s], r, s3.get(s))
            # 算法第十二节：低可信度对象不能直接成为正式 S
            if t == "S" and r["confidence"] == "low":
                t, why = "A", why + "；但证据可信度 low，按第十二节不得直接定 S"
            diff = "变" if t != old_tier[s] else ""
            if diff:
                changed += 1
            w.writerow([
                s, it["name_en"], it["name_cn"], it["gallery"], it["category"],
                r["object_type"], r["peer_group"], g.get("peer_size", ""),
                r["HS"], r["IU"], r["VI"], r["VA"], r["CE"], r.get("ER", 0),
                # 三位小数：门槛卡在 8.5/7.2/5.5，两位小数会把 8.497 显示成
                # 8.50，于是「Core 8.50 判为 A」看上去像 bug，其实是四舍五入。
                # 边界附近的可读性比表格宽度重要。
                g["Q"], g["D"], g["G"], f"{cr[s]:.3f}", f"{cores[s]:.3f}",
                old_tier[s], t, diff, why,
                r["confidence"], r["evidence"], g["cr_reason"],
                s3.get(s, {}).get("sness_reason", ""),
            ])

    import collections
    dist_new = collections.Counter()
    dist_old = collections.Counter(old_tier[it["seq"]] for it in items)
    for it in items:
        s = it["seq"]
        t, _ = tier_of(cores[s], s1[s], s3.get(s))
        if t == "S" and s1[s]["confidence"] == "low":
            t = "A"
        dist_new[t] += 1

    print(f"\n{old_label}：{dict(sorted(dist_old.items()))}")
    print(f"V3.0 评级：{dict(sorted(dist_new.items()))}")
    print(f"变化 {changed}/{len(items)} 件")
    print(f"\n审阅表：{review}")
    print("确认无误前不要写库。")


if __name__ == "__main__":
    main()
