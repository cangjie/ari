#!/usr/bin/env python3
"""核实 mfa_boston_ext 里 Wikidata 来源的展品，是否真的收藏于波士顿美术馆。

**为什么要查（2026-09-11）**：用户问「导出的 MFA 表格，你保证所有展品都属于这个馆吗」。
扩充清单 4329 件来自 Wikidata，源文件自承「展厅与在展状态未经官网确认」。
馆藏号「格式像 MFA」不算证据 —— 「年份.序号」是大都会、大英等很多馆通用的编号格式。

判据是 Wikidata 的 **P195（collection，收藏机构）**：
  · 含 Q49133（Museum of Fine Arts, Boston）         -> 属于 MFA
  · 有 P195 但不含 Q49133                            -> **不属于 MFA**（要剔除）
  · 完全没有 P195                                    -> 无从核实
一件东西可以有多个 P195（曾藏于 A、后归 B），所以按「含不含 MFA」判，
不按「第一个是不是 MFA」判。

结果落 `mfa_membership.json`，**抓回来的东西要落进仓库**（AGENTS.md 的规矩）。
"""
import json, pathlib, re, sys, time, urllib.parse, urllib.request
import meta_lib as M

MFA_QID = "Q49133"
ENDPOINTS = ("https://query.wikidata.org/sparql",
             "https://qlever.cs.uni-freiburg.de/api/wikidata")
UA = "ari-museum-audit/1.0 (+https://github.com/cangjie/ari)"


def sparql(q: str) -> list[dict]:
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    ep + "?" + urllib.parse.urlencode({"query": q, "format": "json"}),
                    headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    return json.loads(r.read())["results"]["bindings"]
            except Exception as e:                       # noqa: BLE001
                last = e; time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"两个 SPARQL 端点都失败：{last}")


def main() -> None:
    c = M.connect().cursor()
    c.execute("""SELECT a.source_seq, a.official_url, a.name_key FROM artwork a
     JOIN museum m ON m.id=a.museum_id AND m.key_name='mfa_boston_ext'
     WHERE a.official_url LIKE '%%wikidata.org%%'""")
    rows = c.fetchall()
    seq_of, name_of = {}, {}
    for s, u, n in rows:
        m = re.search(r'(Q\d+)', u or "")
        if m:
            seq_of[m.group(1)] = s; name_of[s] = n
    qids = list(seq_of)
    print(f"Wikidata 来源 {len(rows)} 件，解析出 QID {len(qids)} 个")

    coll: dict[str, set] = {q: set() for q in qids}
    label: dict[str, str] = {}
    B = 200
    for i in range(0, len(qids), B):
        vals = " ".join(f"wd:{q}" for q in qids[i:i + B])
        q = f"""SELECT ?item ?c ?cLabel WHERE {{
          VALUES ?item {{ {vals} }}
          OPTIONAL {{ ?item wdt:P195 ?c . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}"""
        for b in sparql(q):
            it = b["item"]["value"].rsplit("/", 1)[-1]
            if "c" in b:
                cq = b["c"]["value"].rsplit("/", 1)[-1]
                coll[it].add(cq)
                label[cq] = b.get("cLabel", {}).get("value", cq)
        print(f"  {min(i + B, len(qids))}/{len(qids)}")
        time.sleep(1)

    res = {"in_mfa": [], "not_mfa": [], "no_p195": []}
    for q, cs in coll.items():
        s = seq_of[q]
        rec = {"seq": s, "qid": q, "name": name_of[s],
               "collections": sorted(label.get(x, x) for x in cs)}
        if not cs:              res["no_p195"].append(rec)
        elif MFA_QID in cs:     res["in_mfa"].append(rec)
        else:                   res["not_mfa"].append(rec)
    pathlib.Path("mfa_membership.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n属于 MFA {len(res['in_mfa'])} / **不属于 MFA {len(res['not_mfa'])}** / "
          f"无 P195 {len(res['no_p195'])}")
    print("已写 mfa_membership.json")


if __name__ == "__main__":
    main()
