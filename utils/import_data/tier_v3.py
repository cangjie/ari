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
    import anthropic
except ImportError:
    sys.exit("缺少 anthropic：pip install anthropic")

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
    # 其余五馆待试点校准通过后再填。故宫需特别注意：1758 件共用 7 段展厅级
    # 套话简介，逐件评分只能依据名称——源文件「评级标准」页自己写明了这一点。
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

    items = []
    for n, row in enumerate(rows[m.header_row + 1:]):
        name_en = cell(row, m.col_name_en)
        name_cn = cell(row, m.col_name_cn)
        if not (name_en or name_cn):
            continue
        items.append({
            "seq": n + 1,
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
            self._c = anthropic.Anthropic()
        return getattr(self._c, name)


def ask(client, system: str, user: str, schema: dict) -> dict:
    """一次结构化输出调用。schema 保证返回的第一个 text block 是合法 JSON。"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": schema},
        },
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"模型拒答：{resp.stop_details}")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


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


def fmt_item(it: dict) -> str:
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
    return "\n".join(parts)


def stage1(client, m: Museum, items: list[dict], out: Path, batch: int) -> dict:
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
            + "\n\n".join(fmt_item(it) for it in chunk)
        )
        data = ask(client, STAGE1_SYSTEM, user, STAGE1_SCHEMA)
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


def stage2(client, m: Museum, items: list[dict], s1: dict, out: Path) -> dict:
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
            )
        user = (
            f"博物馆语境：\n{m.context}\n\n"
            f"Peer Group：{group}\n"
            f"组内共 {len(seqs)} 件对象，请全部给出 Q / D / G：\n\n"
            + "\n\n".join(lines)
        )
        data = ask(client, STAGE2_SYSTEM, user, STAGE2_SCHEMA)
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
           s1: dict, cores: dict, out: Path) -> dict:
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
        )
    user = (f"博物馆语境：\n{m.context}\n\n"
            f"以下 {len(todo)} 件对象已达 S 门槛，请逐件做 S-ness Test：\n\n"
            + "\n\n".join(lines))
    data = ask(client, STAGE3_SYSTEM, user, STAGE3_SCHEMA)
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
    ap.add_argument("--batch", type=int, default=12, help="阶段一每批件数")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    m = MUSEUMS[args.museum]

    items = load_items(m, base, args.limit)
    print(f"{m.label}：{len(items)} 件" + ("（--limit 截断）" if args.limit else ""))

    client = LazyClient()
    p1 = out_dir / f"{m.key}_stage1.jsonl"
    p2 = out_dir / f"{m.key}_stage2.jsonl"
    p3 = out_dir / f"{m.key}_stage3.jsonl"

    s1 = stage1(client, m, items, p1, args.batch)
    s2 = stage2(client, m, items, s1, p2)

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
    s3 = stage3(client, m, items, cands, s1, cores, p3) if cands else {}

    # 写审阅 CSV
    review = out_dir / f"{m.key}_review.csv"
    changed = 0
    with review.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "名称EN", "名称CN", "展厅", "类别",
                    "对象类型", "同类组", "组内件数",
                    "HS", "IU", "VI", "VA", "CE", "ER",
                    "Q", "D", "G", "CR", "Core",
                    "原tier", "V3新tier", "是否变化", "判定说明",
                    "证据可信度", "评分依据", "CR理由", "S-ness理由"])
        for it in items:
            s = it["seq"]
            r, g = s1[s], s2[s]
            t, why = tier_of(cores[s], r, s3.get(s))
            # 算法第十二节：低可信度对象不能直接成为正式 S
            if t == "S" and r["confidence"] == "low":
                t, why = "A", why + "；但证据可信度 low，按第十二节不得直接定 S"
            diff = "变" if t != it["tier_old"] else ""
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
                it["tier_old"], t, diff, why,
                r["confidence"], r["evidence"], g["cr_reason"],
                s3.get(s, {}).get("sness_reason", ""),
            ])

    import collections
    dist_new = collections.Counter()
    dist_old = collections.Counter(it["tier_old"] for it in items)
    for it in items:
        s = it["seq"]
        t, _ = tier_of(cores[s], s1[s], s3.get(s))
        if t == "S" and s1[s]["confidence"] == "low":
            t = "A"
        dist_new[t] += 1

    print(f"\n原表评级：{dict(sorted(dist_old.items()))}")
    print(f"V3.0 评级：{dict(sorted(dist_new.items()))}")
    print(f"变化 {changed}/{len(items)} 件")
    print(f"\n审阅表：{review}")
    print("确认无误前不要写库。")


if __name__ == "__main__":
    main()
