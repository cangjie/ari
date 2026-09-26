#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 Wikidata 上吉林省博物院（Q18111051）名下的全部条目拉下来，存成 jlpm_wikidata_catalog.json（入仓库）。

    python3 jlpm_wikidata.py            # 已有缓存就只打印统计
    python3 jlpm_wikidata.py --refresh  # 重新查询（WDQS 限流时自动改用 QLever）

**这批条目只用来核对身份，不作为展品入库**（用户 2026-09-26 定）。
2026-09-26 实测 P195=Q18111051 共 11947 条，全部出自国家文物局《全国馆藏文物名录》
（引用 P248=Q132205121），每条只有五个属性：P31 类别、P195 收藏、P276 位置、P495 国家、
**P11699 可移动文物编号**。没有年代、简介、图片、文物级别，标签只有中文。
官网展品若能按名称**唯一**对上其中一条，就挂上这个编号 —— 那是国家文物局登记的身份，
解决的是 PEM 那种「对象认不出来」的问题（AGENTS.md 第 9 条）。

名称在这份名录里经常重复（「清乾隆彩墨」一个名字对应好几件），所以这里只存原样，
匹配规则放在 jlpm_build.py：**两边都唯一且完全相等才挂**，不做模糊匹配。
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.parse

from meta_scrape import QLEVER, WDQS, fetch

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "jlpm_wikidata_catalog.json"
MUSEUM_QID = "Q18111051"
SOURCE_QID = "Q132205121"           # 全国馆藏文物名录

# 标签取 zh，缺了再退到 zh-hans / zh-cn。实测 2026-09-26 的条目只有 zh
LANGS = ("zh", "zh-hans", "zh-cn")

PREFIX = """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""
COUNT = PREFIX + "SELECT (COUNT(DISTINCT ?item) AS ?n) WHERE { ?item wdt:P195 wd:%s . }" % MUSEUM_QID
# 分页取：2026-09-26 一次取全量，WDQS 传到 1.47MB 时连接被掐断（IncompleteRead，本机出口网络抖），
# 备用的 QLever 又 429。每页 2000 行、按全部输出列排序，页与页之间不重不漏；
# 一个条目的几行跨了页也没关系，build() 按 QID 合并
PAGE = 2000
SELECT = PREFIX + """
SELECT ?item ?label ?lang ?relic ?type WHERE {
  ?item wdt:P195 wd:%s .
  OPTIONAL { ?item rdfs:label ?label . BIND(LANG(?label) AS ?lang)
             FILTER(LANG(?label) IN ("zh", "zh-hans", "zh-cn")) }
  OPTIONAL { ?item wdt:P11699 ?relic }
  OPTIONAL { ?item wdt:P31 ?type }
}
ORDER BY ?item ?lang ?relic ?type
LIMIT %d OFFSET %%d
""" % (MUSEUM_QID, PAGE)


def ask(q: str) -> tuple[dict, str]:
    """WDQS 优先，限流或失败就改用 QLever（同 meta_scrape.load_wikidata）。-> (结果, 端点名)"""
    for label, ep in (("WDQS", WDQS), ("QLever", QLEVER)):
        url = ep + "?query=" + urllib.parse.quote(q) + "&format=json"
        try:
            return json.loads(fetch(url, 300)), label
        except urllib.error.HTTPError as exc:
            print(f"  [{label} HTTP {exc.code}，改用备用端点]", flush=True)
        except Exception as exc:
            print(f"  [{label} 失败 {str(exc)[:80]}，改用备用端点]", flush=True)
    raise SystemExit("WDQS 与 QLever 都取不到数据（已取到的页不落盘，查清原因再跑）")


def query() -> tuple[dict, str, int]:
    """-> (合并后的结果, 用到的端点, 总条目数)"""
    cnt, _ = ask(COUNT)
    total = int(cnt["results"]["bindings"][0]["n"]["value"])
    print(f"P195={MUSEUM_QID} 共 {total} 条，分页取（每页 {PAGE} 行）", flush=True)
    rows, used, off = [], set(), 0
    while True:
        page, ep = ask(SELECT % off)
        got = page["results"]["bindings"]
        used.add(ep)
        rows += got
        print(f"  OFFSET {off}：{len(got)} 行（{ep}）", flush=True)
        if len(got) < PAGE:
            break
        off += PAGE
    return {"results": {"bindings": rows}}, "+".join(sorted(used)), total


def build(data: dict) -> list[dict]:
    items: dict[str, dict] = {}
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        e = items.setdefault(qid, {"qid": qid, "labels": {}, "relic_id": [], "p31": []})
        if "label" in b:
            e["labels"].setdefault(b["lang"]["value"], b["label"]["value"])
        for key, var in (("relic_id", "relic"), ("p31", "type")):
            v = b.get(var, {}).get("value")
            if v:
                v = v.rsplit("/", 1)[-1]
                if v not in e[key]:
                    e[key].append(v)
    out = []
    for e in items.values():
        name = next((e["labels"][lg] for lg in LANGS if lg in e["labels"]), "")
        out.append({"qid": e["qid"], "name": name, "relic_id": sorted(e["relic_id"]),
                    "p31": sorted(e["p31"])})
    return sorted(out, key=lambda x: int(x["qid"][1:]))


def stats(doc: dict) -> None:
    items = doc["items"]
    names = collections.Counter(x["name"] for x in items)
    print(f"{doc['fetched_at']} 自 {doc['endpoint']}：{len(items)} 条")
    print(f"  无中文标签 {sum(not x['name'] for x in items)}，"
          f"无可移动文物编号 {sum(not x['relic_id'] for x in items)}，"
          f"编号不止一个 {sum(len(x['relic_id']) > 1 for x in items)}")
    dup = {n: c for n, c in names.items() if c > 1 and n}
    print(f"  名称唯一的 {sum(1 for n, c in names.items() if c == 1 and n)} 个；"
          f"重名的 {len(dup)} 个名字、共 {sum(dup.values())} 条，最多的：{names.most_common(5)}")
    relic = collections.Counter(r for x in items for r in x["relic_id"])
    print(f"  编号重复的 {sum(1 for c in relic.values() if c > 1)} 个")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--refresh", action="store_true", help="重新查询，覆盖 jlpm_wikidata_catalog.json")
    args = ap.parse_args()
    if OUT.exists() and not args.refresh:
        stats(json.loads(OUT.read_text("utf-8")))
        return
    data, endpoint, total = query()
    items = build(data)
    if len(items) != total:
        # 分页漏了或多了（两次查询之间数据变了，或某端点排序不稳）。不写半截的文件
        sys.exit(f"条目数对不上：COUNT 说 {total}，分页合并后 {len(items)}。不写文件，查清再跑")
    doc = {"museum_qid": MUSEUM_QID, "source_qid": SOURCE_QID, "endpoint": endpoint,
           "fetched_at": dt.datetime.now().isoformat(timespec="seconds"), "items": items}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=0) + "\n", "utf-8")
    stats(doc)


if __name__ == "__main__":
    main()
