"""V3.0 visitor-priority scoring for the Greater Boston candidate inventory.

Adapted from boston_summer_st_rate.py. Differences:
- Inventory is boston_area_list.rows (73 candidate rows), checkpoint prefix boston_area_v3.
- Each row's description also carries its audit-verified source passage (the passages cited by the
  final Haiku 5.5 content audit, quoted from the captured page text). Rows whose source page was not
  captured carry only the inventory description, and say so.
- No Excel export and no Web/App publication here; ratings are written as JSON for the package builder.

Run from the repository root with the import_data virtualenv Python:
  utils/import_data/.venv/bin/python utils/import_data/boston_area_rate.py 1
  utils/import_data/.venv/bin/python utils/import_data/boston_area_rate.py groups
  utils/import_data/.venv/bin/python utils/import_data/boston_area_rate.py 2
  utils/import_data/.venv/bin/python utils/import_data/boston_area_rate.py 3
All model outputs are checkpointed; a changed input refuses to reuse old scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import boston_area_list as listing
import codex_cli
import llm_cache
import tier_v3 as tier

HERE = Path(__file__).parent
PREFIX = "boston_area_v3"
MODEL = "gpt-5.6-luna"
EFFORTS = dict(tier.STAGE_EFFORT)
REQUEST = HERE / "boston_area_v3_audit_request.json"
AUDIT = HERE / "boston_area_v3_audit_results_haiku55.json"
EXCERPT_CHARS = 700
CONTEXT = (
    "大波士顿（波士顿各社区，以及剑桥、萨勒姆、康科德、莱克星顿等周边地区）的首次到访游客文化参观优先级。"
    "评级衡量一位游客在有限行程中，这一地点作为文化参观的价值，不是全市或全区排名，也不是旅游平台星级。"
    "自由之路、黑人遗产步道等路线与其组成站点分开评，不把整体与组成点视为互不重叠的地点。"
    "餐饮只按文化与历史参观价值评价，不按味道、服务、价格或营业状况评分。"
    "营业、票务、预约和入内状态来自公开资料快照，不能推断当天开放。"
    "仅凭输入中的简述、来源身份与已核验的原文依据作判断；没有原文依据的条目降低 confidence，不凭空补史实。"
)


def path(suffix: str) -> Path:
    return HERE / f"{PREFIX}_{suffix}"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def excerpts() -> dict[int, str]:
    """Quote the passages the final audit cited for each supported row, truncated per passage."""
    request = json.loads(REQUEST.read_text("utf-8"))
    audit = json.loads(AUDIT.read_text("utf-8"))
    passages = {item["seq"]: {p["id"]: p["text"] for p in item["passages"]} for item in request["items"]}
    out = {}
    for item in audit["items"]:
        if not (item["supported"] and item["address_supported"] and item["passage_ids"]):
            continue
        texts = []
        for pid in item["passage_ids"][:2]:
            text = passages[item["seq"]].get(pid)
            if text:
                texts.append(text[:EXCERPT_CHARS])
        if texts:
            out[item["seq"]] = " … ".join(texts)
    return out


def payload() -> list[dict]:
    keys = ("id", "zone", "kind", "zh", "en", "zh_desc", "en_desc", "address", "relation", "access",
            "source", "source_name", "note")
    return [{k: r[k] for k in keys} for r in listing.rows]


def input_hash() -> str:
    body = {"rows": payload(), "excerpts": {str(k): v for k, v in sorted(excerpts().items())}}
    return sha(json.dumps(body, ensure_ascii=False, sort_keys=True).encode())


def init():
    digest = input_hash()
    manifest = path("rating_input.json")
    if manifest.exists():
        old = json.loads(manifest.read_text("utf-8"))
        if (old["input_sha256"] != digest or old["model"] != MODEL or
                old["efforts"] != EFFORTS or old["context"] != CONTEXT):
            raise ValueError("清单、原文依据或评分语境已改变；旧评分断点不能复用")
    else:
        manifest.write_text(json.dumps({"input_sha256": digest, "model": MODEL, "efforts": EFFORTS,
                                        "context": CONTEXT, "ids": [r["id"] for r in listing.rows]},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if llm_cache._connect() is None:
        raise RuntimeError("统一 LLM 缓存不可用；停止付费模型调用")
    if not codex_cli.available():
        raise RuntimeError("Codex CLI 不可用")
    tier.CODEX_CLI = (MODEL, EFFORTS)
    tier.MODEL = MODEL + " effort=high/medium/xhigh (codex-cli)"
    quotes = excerpts()
    items = []
    for seq, r in enumerate(listing.rows, 1):
        basis = quotes.get(seq)
        evidence = (f"原文依据（已核验引用的节选）：{basis}" if basis
                    else "来源正文未取得或未通过审计，仅凭简述与来源身份，置信度应降低。")
        items.append(dict(seq=seq, name_cn=r["zh"], name_en=r["en"], gallery="",
                          category=f"{r['kind']} · {r['zone']} · {r['relation']}",
                          description=(f"{r['zh_desc']}\n地址：{r['address']}。访问属性：{r['access']}。"
                                       f"来源：{r['source_name']} {r['source']}。{r['note']}\n{evidence}"),
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
    system = (f"按照 Ariadne V3.0 的同类竞争规则，在完整{len(seqs)}条候选清单中统一同类组。"
              "性质和功能相似的对象使用相同组名；不同 object_type 绝不能混组。"
              "自由之路等整条路线与单个站点分开；餐饮、公园、校园、博物馆、历史建筑和街区也分开。"
              "按对象的形态与功能分组，不按分数、来源长度、行政片区或待定Tier分组。"
              f"只返每个 seq 的 peer_group；全部{len(seqs)}条恰返一次。")
    schema = {"type": "object", "properties": {"items": {"type": "array", "items": {
        "type": "object", "properties": {"seq": {"type": "integer"}, "peer_group": {"type": "string"}},
        "required": ["seq", "peer_group"], "additionalProperties": False}}},
        "required": ["items"], "additionalProperties": False}
    user = json.dumps(packet, ensure_ascii=False)

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

    answer = llm_cache.call(lambda: codex_call(system, user, schema), provider="openai_codex", model=MODEL,
                            effort="medium", stage="tier_peer_groups", museum_key=PREFIX, seqs=seqs,
                            scope="full Boston area candidate inventory", system=system, user=user,
                            schema=schema, validate=valid, retries=0)
    data = {"input_sha256": input_hash(), "stage1_sha256": sha(path("rating_stage1.jsonl").read_bytes()),
            "model": MODEL + " medium", "groups": {str(x["seq"]): x["peer_group"] for x in answer["items"]}}
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {int(k): v for k, v in data["groups"].items()}


def codex_call(system, user, schema):
    answer, usage = codex_cli.ask(system, user, schema, MODEL, "medium")
    return answer, codex_cli.Usage(usage)


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
              "method": "Ariadne V3.0 stages 1-3 on the Boston area inventory; audited source excerpts where available",
              "counts": dict(Counter(r["tier"] for r in results)), "results": results}
    path("ratings.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ratings", result["counts"], flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["1", "groups", "2", "3"])
    args = ap.parse_args()
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
