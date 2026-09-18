#!/usr/bin/env python3
"""给去重取事实：Wikidata 的作者/年代/馆藏号 + 多语标签别名。零 OpenAI 费用。

用法：
    python3 dedupe_facts.py --xlsx "exports/展品_波士顿美术馆_展厅检索.xlsx"
    python3 dedupe_facts.py --limit 200        # 先小批验证

产物 `dedupe_facts.json` 入仓库 —— **抓回来的东西要落进仓库，不能只落进 Excel**
（AGENTS.md 的教训：光入库就等于把最硬的证据变成孤儿数据）。

## 为什么必须联网取这一层

表里的「作者」列有五种形态，跨语言完全没法比：中文名 1874、拉丁名 2263、
**genid URL 329（Wikidata 里的匿名创作者节点，意思是「作者不可考」）**、
裸 QID 185、空 87。而 `葛饰北斋` 与 `Katsushika Hokusai`、
`约瑟夫·马洛德·威廉·透纳` 与 `J.M.W. Turner` 必须落到同一个创作者 QID 才能配上对。

取回创作者 QID 的多语标签与别名，就同时解决三件事：
  · 跨语言归一（`葛饰北斋` / `葛飾北斎` / `Katsushika Hokusai` → 同一个 Q5586）
  · **简繁不必引 opencc** —— Wikidata 的 `zh-hans` / `zh-hant` 两条标签天然覆盖
  · 把 185 个裸 QID 解析成名字，并把 329 个 genid 明确标成「作者不可考」

作品自身的多语标签同样重要：`Q219344` 有 `zh-hans=奴隶船` / `zh-hant=奴隸船`，
这正是 `Slave Ship ↔ 奴隸船` 那一对的桥。
**但它只能覆盖一部分** —— 实测 `Q106769954`（Fine Wind, Clear Weather）与
`Q12162390`（The Fog Warning）**一条中文标签都没有**，那两对只能靠作者+年代召回。

⚠ `verify_mfa_membership.sparql()` 用的是裸 `urlopen`，本机实测会
`CERTIFICATE_VERIFY_FAILED`（python.org 版 Python 不带根证书）。这里必须传 `tls.ssl_ctx()`，
否则失败信息长得像网络抖动，会被误判成限流。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

import openpyxl

from dedupe_lib import qid_of, row_key, subset
from tls import ssl_ctx

HERE = pathlib.Path(__file__).parent
OUT = HERE / "dedupe_facts.json"
SHEET = "去重后总表"

ENDPOINTS = ("https://query.wikidata.org/sparql",
             "https://qlever.cs.uni-freiburg.de/api/wikidata")
UA = "ari-museum-dedupe/1.0 (+https://github.com/cangjie/ari)"
LANGS = ("en", "zh", "zh-hans", "zh-hant", "ja")
BATCH = 150


def sparql(q: str) -> list[dict]:
    """双端点 + 三次退避。取不到就抛，不返回空列表冒充「没有数据」。"""
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    ep + "?" + urllib.parse.urlencode({"query": q, "format": "json"}),
                    headers={"User-Agent": UA,
                             "Accept": "application/sparql-results+json"})
                with urllib.request.urlopen(req, timeout=120, context=ssl_ctx()) as r:
                    return json.loads(r.read())["results"]["bindings"]
            except Exception as e:                       # noqa: BLE001
                last = e
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"两个 SPARQL 端点都失败：{last}")


def val(b: dict, k: str) -> str | None:
    v = b.get(k, {}).get("value")
    return v.rsplit("/", 1)[-1] if v and v.startswith("http") else v


def fetch_claims(qids: list[str]) -> dict[str, dict]:
    """P170 创作者、P571 创作时间、P217 馆藏号。"""
    out = {q: {"creators": [], "inception": [], "acc": []} for q in qids}
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        vals = " ".join(f"wd:{q}" for q in chunk)
        q = f"""SELECT ?item ?creator ?inception ?acc WHERE {{
          VALUES ?item {{ {vals} }}
          OPTIONAL {{ ?item wdt:P170 ?creator . }}
          OPTIONAL {{ ?item wdt:P571 ?inception . }}
          OPTIONAL {{ ?item wdt:P217 ?acc . }}
        }}"""
        for b in sparql(q):
            it = val(b, "item")
            r = out[it]
            for key, field in (("creator", "creators"), ("inception", "inception"),
                               ("acc", "acc")):
                v = val(b, key)
                if v and v not in r[field]:
                    r[field].append(v)
        print(f"  claims {min(i + BATCH, len(qids))}/{len(qids)}")
        time.sleep(1)
    return out


def fetch_labels(qids: list[str]) -> dict[str, dict]:
    """多语标签 + 别名。别名很关键 —— `The Slave Ship` 的英文别名是那个长副题。"""
    out: dict[str, dict] = {q: {"labels": {}, "aliases": {}} for q in qids}
    langs = ",".join(f'"{x}"' for x in LANGS)
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        vals = " ".join(f"wd:{q}" for q in chunk)
        q = f"""SELECT ?item ?label ?alias WHERE {{
          VALUES ?item {{ {vals} }}
          OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) IN ({langs})) }}
          OPTIONAL {{ ?item skos:altLabel ?alias . FILTER(LANG(?alias) IN ({langs})) }}
        }}"""
        for b in sparql(q):
            it = val(b, "item")
            if "label" in b:
                out[it]["labels"][b["label"]["xml:lang"]] = b["label"]["value"]
            if "alias" in b:
                lg = b["alias"]["xml:lang"]
                out[it]["aliases"].setdefault(lg, [])
                if b["alias"]["value"] not in out[it]["aliases"][lg]:
                    out[it]["aliases"][lg].append(b["alias"]["value"])
        print(f"  labels {min(i + BATCH, len(qids))}/{len(qids)}")
        time.sleep(1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--limit", type=int, help="只取前 N 个 QID，用于小批验证")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.xlsx, read_only=True, data_only=True)
    ws = wb[SHEET]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    qids, by_sub = [], {}
    for r in it:
        row = dict(zip(hdr, r))
        q = qid_of(row)
        by_sub[subset(row)] = by_sub.get(subset(row), 0) + 1
        if q and q not in qids:
            qids.append(q)
    print(f"子集分布：{by_sub}")
    print(f"解析出作品 QID {len(qids)} 个")
    if args.limit:
        qids = qids[:args.limit]
        print(f"--limit：只取前 {len(qids)} 个")

    print("取作品 claims …")
    claims = fetch_claims(qids)
    creators = sorted({c for v in claims.values() for c in v["creators"]})
    print(f"涉及创作者 QID {len(creators)} 个")

    print("取作品标签 …")
    work_labels = fetch_labels(qids)
    print("取创作者标签 …")
    creator_labels = fetch_labels(creators) if creators else {}

    facts = {
        "works": {q: {**claims[q], **work_labels.get(q, {})} for q in qids},
        "creators": creator_labels,
    }
    OUT.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")

    got_creator = sum(1 for v in facts["works"].values() if v["creators"])
    got_year = sum(1 for v in facts["works"].values() if v["inception"])
    zh = sum(1 for v in facts["works"].values()
             if any(k.startswith("zh") for k in v.get("labels", {})))
    print(f"\n已写出 {OUT.name}")
    print(f"  作品 {len(qids)}：有创作者 {got_creator}（{got_creator/len(qids)*100:.0f}%）、"
          f"有创作年代 {got_year}、有中文标签 {zh}（{zh/len(qids)*100:.0f}%）")
    print(f"  创作者 {len(creator_labels)} 个已取多语标签别名")

    # 验收：三个已知 QID 的创作者必须对上
    want = {"Q106769954": "Q5586", "Q12162390": "Q344838", "Q219344": "Q159758"}
    for q, exp in want.items():
        if q in facts["works"]:
            got = facts["works"][q]["creators"]
            ok = exp in got
            print(f"  {'✓' if ok else '✗'} {q} 创作者 {got} 期望含 {exp}")
            if not ok:
                sys.exit("已知样本的创作者对不上 —— 取数有问题，已中止")


if __name__ == "__main__":
    main()
