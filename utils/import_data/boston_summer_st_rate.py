"""V3.0 visitor-priority scoring for the sourced Summer Street workbook.

Run from the repository root with the import_data virtualenv Python:
  utils/import_data/.venv/bin/python utils/import_data/boston_summer_st_rate.py 1
  utils/import_data/.venv/bin/python utils/import_data/boston_summer_st_rate.py groups
  utils/import_data/.venv/bin/python utils/import_data/boston_summer_st_rate.py 2
  utils/import_data/.venv/bin/python utils/import_data/boston_summer_st_rate.py 3
  utils/import_data/.venv/bin/python utils/import_data/boston_summer_st_rate.py export

The input is the dated, sourced inventory, not live opening or review data. All
model outputs are checkpointed. A changed input refuses to reuse old scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import boston_summer_st_list as listing
import codex_cli
import llm_cache
import tier_v3 as tier

HERE = Path(__file__).parent
PREFIX = "boston_summer_st"
BASE = listing.OUT
OUT = BASE.with_name("波士顿Summer Street周边景点与商铺_双语清单_V3评级版.xlsx")
MODEL = "gpt-5.6-luna"
EFFORTS = dict(tier.STAGE_EFFORT)
CONTEXT = (
    "波士顿 Summer Street 从 Downtown Crossing 经 South Station、Fort Point 到 Seaport 的步行游览语境。"
    "评级衡量首次到访游客在这条走廊及步行衔接范围的文化参观优先级，不是波士顿全市排名。"
    "自由之路的整条步道与市中心11站有整体和组成关系；北端/查尔斯敦5站只是范围外对照，不参加评分。"
    "餐饮和零售只按文化与参观价值评价，不按味道、服务、价格或平台星级评分。"
    "营业和场馆入内状态来自公开资料快照，不能推断当天开放。"
    "仅凭输入中已列的简述和来源身份作判断；具体证据不足时降低confidence，不凭空补史实。"
)


def path(suffix: str) -> Path:
    return HERE / f"{PREFIX}_{suffix}"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload() -> list[dict]:
    return [{k: r[k] for k in ("id", "zone", "kind", "zh", "en", "zh_desc", "en_desc",
                              "address", "relation", "access", "source", "source_name", "note")}
            for r in listing.rows]


def input_hash() -> str:
    return sha(json.dumps(payload(), ensure_ascii=False, sort_keys=True).encode())


def init():
    digest = input_hash()
    manifest = path("rating_input.json")
    if manifest.exists():
        old = json.loads(manifest.read_text("utf-8"))
        if (old["input_sha256"] != digest or old["model"] != MODEL or
                old["efforts"] != EFFORTS or old["context"] != CONTEXT):
            raise ValueError("清单或评分语境已改变；旧评分断点不能复用")
    else:
        manifest.write_text(json.dumps({"input_sha256": digest, "model": MODEL,
                                        "efforts": EFFORTS, "context": CONTEXT,
                                        "ids": [r["id"] for r in listing.rows]},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if llm_cache._connect() is None:
        raise RuntimeError("统一 LLM 缓存不可用；停止付费模型调用")
    if not codex_cli.available():
        raise RuntimeError("Codex CLI 不可用")
    tier.CODEX_CLI = (MODEL, EFFORTS)
    tier.MODEL = MODEL + " effort=high/medium/xhigh (codex-cli)"
    items = []
    for seq, r in enumerate(listing.rows, 1):
        items.append(dict(seq=seq, name_cn=r["zh"], name_en=r["en"], gallery="",
                          category=f"{r['kind']} · {r['zone']} · {r['relation']}",
                          description=(f"{r['zh_desc']}\n地址：{r['address']}。访问属性：{r['access']}。"
                                       f"来源：{r['source_name']} {r['source']}。{r['note']}"),
                          tier_old=""))
    return SimpleNamespace(key=PREFIX, context=CONTEXT), items


def first(m, items):
    result = tier.stage1(None, m, items, path("rating_stage1.jsonl"), 12)
    wanted = set(range(1, len(items) + 1))
    if set(result) != wanted:
        raise ValueError("阶段一未覆盖全部条目")
    for r in result.values():
        if any(not 0 <= float(r[d]) <= 10 for d in ("HS", "IU", "VI", "VA", "CE", "ER")):
            raise ValueError(f"seq {r['seq']} 存在越界维度")
    return result


def groups(m, items, s1):
    output = path("rating_groups.json")
    if output.exists():
        data = json.loads(output.read_text("utf-8"))
        if data["input_sha256"] != input_hash() or data["stage1_sha256"] != sha(path("rating_stage1.jsonl").read_bytes()):
            raise ValueError("同类组不匹配现行评分输入")
        return {int(k): v for k, v in data["groups"].items()}
    seqs = sorted(s1)
    packet = [{"seq": s, "name": items[s-1]["name_cn"], "kind": listing.rows[s-1]["kind"],
               "object_type": s1[s]["object_type"], "raw_group": s1[s]["peer_group"]}
              for s in seqs]
    system = ("按照 Ariadne V3.0 的同类竞争规则，在完整53条名单中统一同类组。"
              "性质和功能相似的对象使用相同组名；不同 object_type 绝不能混组。"
              "自由之路整条步道与单个站点分开；餐饮、零售、公共空间和历史建筑也分开。"
              "按对象的形态与功能分组，不按分数、来源长度、行政片区或待定Tier分组。"
              "只返每个 seq 的 peer_group；全部53条恰返一次。")
    schema = {"type": "object", "properties": {"items": {"type": "array", "items": {
        "type": "object", "properties": {"seq": {"type": "integer"}, "peer_group": {"type": "string"}},
        "required": ["seq", "peer_group"], "additionalProperties": False}}},
        "required": ["items"], "additionalProperties": False}
    user = json.dumps(packet, ensure_ascii=False)
    def request():
        answer, usage = codex_cli.ask(system, user, schema, MODEL, "medium")
        return answer, codex_cli.Usage(usage)
    def valid(d):
        got = d.get("items", [])
        if sorted(x["seq"] for x in got) != seqs:
            got_seqs = [x["seq"] for x in got]
            print(f"同类组覆盖异常：缺 {sorted(set(seqs)-set(got_seqs))}，"
                  f"重复 {sorted(s for s in set(got_seqs) if got_seqs.count(s)>1)}，"
                  f"多出 {sorted(set(got_seqs)-set(seqs))}", flush=True)
            return False
        types = defaultdict(set)
        for x in got:
            types[x["peer_group"]].add(s1[x["seq"]]["object_type"])
        mixed = {group: sorted(kinds) for group, kinds in types.items() if len(kinds) > 1}
        if mixed:
            print(f"同类组跨对象类型：{mixed}", flush=True)
        return not mixed
    answer = llm_cache.call(request, provider="openai_codex", model=MODEL, effort="medium",
                            stage="tier_peer_groups", museum_key=PREFIX, seqs=seqs,
                            scope="full Summer Street inventory", system=system, user=user,
                            schema=schema, validate=valid, retries=0)
    data = {"input_sha256": input_hash(), "stage1_sha256": sha(path("rating_stage1.jsonl").read_bytes()),
            "model": MODEL + " medium", "groups": {str(x["seq"]): x["peer_group"] for x in answer["items"]}}
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {int(k): v for k, v in data["groups"].items()}


def second(m, items, s1, merged):
    for seq, name in merged.items():
        s1[seq]["peer_group"] = name
    by_group = defaultdict(list)
    for seq, r in s1.items():
        by_group[r["peer_group"]].append(seq)
    by_seq = {x["seq"]: x for x in items}
    output = path("rating_stage2.jsonl")
    done = tier.read_done(output)
    singletons = []
    for group, seqs in sorted(by_group.items()):
        if all(s in done for s in seqs):
            continue
        if len(seqs) == 1:
            singletons.append((group, seqs[0]))
            continue
        user = tier.stage2_user(m, group, seqs, by_seq, s1, None)
        want = set(seqs)
        answer = tier.ask(None, tier.STAGE2_SYSTEM, user, tier.STAGE2_SCHEMA,
                          stage="tier_stage2", museum_key=PREFIX, scope=group, seqs=seqs,
                          validate=lambda d, w=want: {x["seq"] for x in d["results"]} == w)
        for r in answer["results"]:
            r["peer_group"] = group
            r["peer_size"] = len(seqs)
            tier.append(output, r)
            done[r["seq"]] = r
        print("group", group, len(seqs), flush=True)
    for i in range(0, len(singletons), 8):
        chunk = singletons[i:i+8]
        user = tier.stage2_user_merged(m, chunk, by_seq, s1, None)
        want = {s for _, s in chunk}
        answer = tier.ask(None, tier.STAGE2_SYSTEM, user, tier.STAGE2_SCHEMA,
                          stage="tier_stage2", museum_key=PREFIX,
                          scope="singleton groups", seqs=sorted(want),
                          validate=lambda d, w=want: {x["seq"] for x in d["results"]} == w)
        group_of = {s: g for g, s in chunk}
        for r in answer["results"]:
            r["peer_group"] = group_of[r["seq"]]
            r["peer_size"] = 1
            tier.append(output, r)
            done[r["seq"]] = r
        print("singleton groups", len(chunk), flush=True)
    if set(done) != set(s1):
        raise ValueError("阶段二未覆盖全部条目")
    return done


def third(m, items, s1, s2):
    cr = {s: .5*r["Q"] + .3*r["D"] + .2*r["G"] for s, r in s2.items()}
    cores = {s: tier.core_of(r, cr[s]) for s, r in s1.items()}
    cands = [s for s in sorted(cores) if cores[s] >= 8.5 and
             max(float(s1[s][d]) for d in tier.DIMS_WITH_ER if d in s1[s]) >= 9]
    s3 = tier.stage3(None, m, items, cands, s1, cores, path("rating_stage3.jsonl"))
    results = []
    for seq, item in enumerate(items, 1):
        r = s1[seq]
        rank, reason = tier.tier_of(cores[seq], r, s3.get(seq))
        if rank == "S" and r["confidence"] == "low":
            rank, reason = "A", reason + "；低置信度不能直接定S"
        results.append(dict(seq=seq, id=listing.rows[seq-1]["id"], name=item["name_cn"],
                            tier=rank, core=round(cores[seq], 4), confidence=r["confidence"],
                            object_type=r["object_type"], peer_group=r["peer_group"],
                            dimensions={d: r[d] for d in ("HS", "IU", "VI", "VA", "CE", "ER")},
                            CR=round(cr[seq], 4), evidence=r["evidence"],
                            cr_reason=s2[seq]["cr_reason"], sness=s3.get(seq), tier_reason=reason))
    result = {"input_sha256": input_hash(), "model": tier.MODEL,
              "method": "Ariadne V3.0 stages 1-3; current-source summary input; no independent audit",
              "counts": dict(Counter(r["tier"] for r in results)), "results": results}
    path("ratings.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ratings", result["counts"], flush=True)
    return result


def export():
    data = json.loads(path("ratings.json").read_text("utf-8"))
    if data["input_sha256"] != input_hash():
        raise ValueError("评级与现行清单不匹配")
    if len(data["results"]) != len(listing.rows):
        raise ValueError("评级未覆盖清单")
    by_id = {r["id"]: r for r in data["results"]}
    wb = load_workbook(BASE)
    for sheet in ("zh-CN", "en", "特色商铺"):
        ws = wb[sheet]
        headers = ["Tier", "Core", "置信度", "评分依据（中文）"] if sheet != "en" else ["Tier", "Core", "Confidence", "Scoring rationale (Chinese)"]
        first_col = ws.max_column + 1
        for j, header in enumerate(headers):
            cell = ws.cell(1, first_col + j, header)
            cell.fill = PatternFill("solid", fgColor="17324D")
            cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for row_num in range(2, ws.max_row + 1):
            r = by_id[ws.cell(row_num, 1).value]
            reason = r["evidence"] + "；同类比较：" + r["cr_reason"] + "；" + r["tier_reason"]
            for j, val in enumerate((r["tier"], r["core"], r["confidence"], reason)):
                cell = ws.cell(row_num, first_col + j, val)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.font = Font(name="Arial", size=10, color="1C2733")
                if row_num % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="F0F5F8")
            ws.cell(row_num, first_col + 1).number_format = "0.0000"
        for j, width in enumerate((10, 12, 13, 100)):
            ws.column_dimensions[get_column_letter(first_col + j)].width = width
        ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
    ws = wb["自由之路16站"]
    first_col = ws.max_column + 1
    ws.cell(1, first_col, "Tier（本区11站）")
    ws.cell(1, first_col + 1, "Core")
    ws.column_dimensions[get_column_letter(first_col)].width = 19
    ws.column_dimensions[get_column_letter(first_col + 1)].width = 12
    for col in (first_col, first_col + 1):
        cell = ws.cell(1, col)
        cell.fill = PatternFill("solid", fgColor="17324D")
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    for row_num in range(2, ws.max_row + 1):
        key = ws.cell(row_num, 2).value
        if key in by_id:
            ws.cell(row_num, first_col, by_id[key]["tier"])
            ws.cell(row_num, first_col + 1, by_id[key]["core"])
        else:
            ws.cell(row_num, first_col, "范围外未评分")
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
    detail = wb.create_sheet("V3评分明细")
    detail.append(["ID", "名称", "Tier", "Core", "HS", "IU", "VI", "VA", "CE", "ER", "CR",
                   "对象类型", "同类组", "置信度", "初评依据", "组内比较理由", "S-ness结论", "Tier判定"])
    for r in data["results"]:
        detail.append([r["id"], r["name"], r["tier"], r["core"]] +
                      [r["dimensions"][d] for d in ("HS", "IU", "VI", "VA", "CE", "ER")] +
                      [r["CR"], r["object_type"], r["peer_group"], r["confidence"], r["evidence"],
                       r["cr_reason"], (r["sness"] or {}).get("sness_reason", ""), r["tier_reason"]])
    detail.freeze_panes = "C2"
    detail.auto_filter.ref = f"A1:R{detail.max_row}"
    detail.sheet_view.showGridLines = False
    for col, width in enumerate((10, 42, 9, 12, 8, 8, 8, 8, 8, 8, 8, 13, 36, 13, 85, 85, 55, 65), 1):
        detail.column_dimensions[get_column_letter(col)].width = width
    for row in detail:
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="FFFFFF" if cell.row == 1 else "1C2733",
                             bold=cell.row == 1)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row == 1:
                cell.fill = PatternFill("solid", fgColor="17324D")
            elif cell.row % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F0F5F8")
        detail.row_dimensions[row[0].row].height = 32 if row[0].row == 1 else 58
    for row_num in range(2, detail.max_row + 1):
        detail.cell(row_num, 4).number_format = "0.0000"
        detail.cell(row_num, 11).number_format = "0.0000"
    notes = wb["说明"]
    for row in notes.iter_rows(min_row=2):
        if row[0].value == "评级与路线":
            row[1].value = "本版已完成V3.0工作评级，独立审计、坐标核对和路线生成尚未执行；未接入Web/App或数据库。"
    notes.append(("V3.0评级", "本版按Ariadne V3.0对主表53条评文化参观优先级：五维初评、完整清单同类组、组内CR、S候选S-ness。Core门槛S≥8.5、A≥7.2、B≥5.5、C<5.5；S另需至少一维≥9及S-ness至少2/3。"))
    notes.append(("评分模型与证据", f"{data['model']}；使用本清单的来源链接、简短介绍及访问边界，不宣称读取网页原始全文。低置信度不得定S。独立审计尚未完成，Tier为当前证据下的工作评级。"))
    notes.append(("商铺口径", "店铺按文化和游览价值评分；C不表示餐饮质量、口味或服务差。营业及票务仍需出行当天复核。"))
    notes.append(("自由之路", "主表只评与Summer Street游览范围步行衔接的11个市中心站；北端和查尔斯敦5站在对照页保留，标为范围外未评分。"))
    counts = data["counts"]
    notes.append(("评级数量", " / ".join(f"{t}{counts.get(t,0)}" for t in "SABC")))
    for n in range(notes.max_row - 4, notes.max_row + 1):
        for cell in notes[n]:
            cell.font = Font(name="Arial", size=10, color="1C2733")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        notes.row_dimensions[n].height = 65
    notes.auto_filter.ref = f"A1:B{notes.max_row}"
    wb.save(OUT)
    check = load_workbook(OUT, read_only=True)
    assert check["zh-CN"].max_row == 54 and check["en"].max_row == 54
    assert check["特色商铺"].max_row == 22 and check["自由之路16站"].max_row == 17
    assert check["V3评分明细"].max_row == 54
    print(OUT)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["1", "groups", "2", "3", "export"])
    args = ap.parse_args()
    if args.stage == "export":
        export()
        return
    m, items = init()
    s1 = first(m, items)
    if args.stage == "1":
        return
    merged = groups(m, items, s1)
    if args.stage == "groups":
        return
    s2 = second(m, items, s1, merged)
    if args.stage == "2":
        return
    third(m, items, s1, s2)


if __name__ == "__main__":
    main()
