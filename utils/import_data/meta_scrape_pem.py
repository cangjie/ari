#!/usr/bin/env python3
"""从外部源抓取 PEM 展品 metadata，写入 artwork_meta，来源逐条记录。

**为什么只用两个源**

  explore-art.pem.org   PEM 官方藏品门户 —— 已停止服务（443 拒绝、连接超时）
  Google Arts & Culture 356 件，实际是印度现代艺术专题，与本馆这 196 件几乎不交叉
  Wikipedia             对泛称条目（如「Robert Feke, Portrait of Gentleman」）
                        只会返回无关条目，给不出结构化字段，投入产出不划算
  ---- 以下两个可用 ----
  wikidata          SPARQL 一次拉全，字段最硬：馆藏号 P217、创作年 P571、
                    材质 P186、作者 P170。但 PEM 在 Wikidata 只有约 50 件。
  pem_customprints  PEM 官方复制品商店，/search/artist/<姓名> 返回 detail 链接，
                    slug 形如 lane-twilight-on-the-kennebec-1849，含规范标题与
                    年份，另有图片 URL（库里 PEM 的 image_url 是 0/196）。
                    只覆盖有署名作者且在售的作品。

**匹配必须严**。早先用宽松分词匹配 196×50，报出 28 条候选，人工核对后只有 1 条
是真的，其余全是 john / captain / mask / vase 这类常见词碰巧撞上。故本脚本要求
共同「显著词」达阈值，并把匹配依据一并写进 source 字段以便复核。

**冲突不消解**。同一个键允许多个来源各写各的：源文件说 pre-contact 而 Wikidata
标 1825 年，两条都留。谁对谁错由读取方按 source_key + confidence 判断。

用法：
    python3 meta_scrape_pem.py --dry-run
    python3 meta_scrape_pem.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import pathlib

import meta_lib as M

MUSEUM = "pem"
UA = "ari-metadata-research/1.0 (museum visit-planning dataset; contact via repo)"
WDQS = "https://query.wikidata.org/sparql"
PEM_Q = "Q3373790"                       # Peabody Essex Museum
CP = "https://customprints.pem.org"

# 匹配时忽略的高频词。它们出现在几十件展品名里，两边撞上不说明任何问题 ——
# 28 条假阳性几乎全是被这些词带出来的。
STOP = {"portrait", "painting", "print", "view", "ship", "museum", "with", "from",
        "collection", "the", "and", "for", "small", "large", "set", "pair", "study",
        "sketch", "fragment", "scene", "figure", "carved", "wooden", "wood", "glass",
        "silver", "export", "chinese", "japanese", "american", "salem"}


def toks(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


def fetch(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/sparql-results+json, text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


# --------------------------------------------------------------- Wikidata
SPARQL = """
SELECT ?item ?itemLabel ?inv ?inception ?creatorLabel ?matLabel WHERE {
  ?item wdt:P195 wd:%s .
  OPTIONAL { ?item wdt:P217 ?inv }
  OPTIONAL { ?item wdt:P571 ?inception }
  OPTIONAL { ?item wdt:P170 ?creator }
  OPTIONAL { ?item wdt:P186 ?mat }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
""" % PEM_Q


def load_wikidata(cache_path: str = "meta_cache/wikidata_pem.json",
                  refresh: bool = False) -> list[dict]:
    """拉取并缓存 PEM 在 Wikidata 的全部藏品。

    结果落盘缓存，默认直接复用：这份数据几周才变一次，而 WDQS 会限流
    （实测遇到过 429「Aggressively rate-limiting to 1 req / min」，是他们
    故障期的临时规则）。每跑一次脚本就去打一次公共查询服务既不必要也不礼貌。
    要强制刷新用 --refresh-wikidata。
    """
    cache = pathlib.Path(cache_path)
    if cache.exists() and not refresh:
        data = json.loads(cache.read_text(encoding="utf-8"))
        print(f"(用缓存 {cache})", end=" ")
    else:
        url = WDQS + "?query=" + urllib.parse.quote(SPARQL) + "&format=json"
        last = None
        for attempt in range(4):
            try:
                data = json.loads(fetch(url, 60)); break
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code != 429:
                    raise
                wait = 20 * (attempt + 1)
                print(f"\n  [429] WDQS 限流，{wait}s 后重试 …", flush=True)
                time.sleep(wait)
        else:
            raise SystemExit(f"WDQS 持续限流，放弃：{last}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    merged: dict[str, dict] = {}
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        lab = b.get("itemLabel", {}).get("value", "")
        if re.fullmatch(r"Q\d+", lab):          # 没有英文标签的条目，无法匹配
            continue
        e = merged.setdefault(qid, {"qid": qid, "label": lab, "mats": set()})
        for k, p in (("inv", "inv"), ("year", "inception"), ("creator", "creatorLabel")):
            v = b.get(p, {}).get("value")
            if v and not e.get(k):
                e[k] = v[:4] if k == "year" else v
        m = b.get("matLabel", {}).get("value")
        if m and not m.startswith("http"):
            e["mats"].add(m)
    return list(merged.values())


def match_wikidata(name: str, artist: str | None, wd: list[dict]):
    """严格匹配。命中需满足其一：
       ① 共同显著词 >= 3；
       ② 作者姓氏出现在对方标签中，且**题名部分**的共同显著词 >= 2。

    关键在「题名部分」：作者名的词必须从共同词里剔除。同一作者的两件不同作品，
    姓名必然重合，拿它当匹配证据是循环论证 —— 实测「Robert Feke, Portrait of
    Gentleman」正是靠 robert/feke 两词错配到了「Judge Richard Saltonstall by
    Robert Feke」，而那是另一幅画。
    """
    tn = toks(name)
    ta = toks(artist) if artist else set()
    best = None
    for e in wd:
        tw = toks(e["label"])
        ov = (tn & tw) - ta                      # 剔除作者名，只看题名重合
        sur = (artist or "").split()[-1].lower() if artist else ""
        strong = len(ov) >= 3 or (sur and sur in e["label"].lower() and len(ov) >= 2)
        if strong and (best is None or len(ov) > len(best[1])):
            best = (e, ov)
    return best


# --------------------------------------------------- PEM Custom Prints
SLUG = re.compile(r"/detail/(\d+)/([a-z0-9\-]+)")


def cp_by_artist(artist: str, cache: dict) -> list[tuple[str, str]]:
    """返回该作者名下的 [(detail_id, slug), ...]。整页只请求一次并缓存。"""
    if artist in cache:
        return cache[artist]
    q = urllib.parse.quote_plus(artist.lower())
    try:
        html = fetch(f"{CP}/search/artist/{q}")
        out = sorted(set(SLUG.findall(html)))
    except Exception as exc:                     # 网络抖动不该中断整轮
        print(f"    [warn] customprints 查询失败 {artist}: {exc}", file=sys.stderr)
        out = []
    cache[artist] = out
    time.sleep(0.7)                              # 对第三方站点保持克制
    return out


YEAR_IN_SLUG = re.compile(r"-(1[5-9]\d{2}|20[0-2]\d)(?:-|$)")


def match_customprints(name: str, artist: str, cache: dict):
    """在该作者名下的作品里按题名词匹配，返回 (detail_id, slug, year, 共同词)。

    阈值比 Wikidata 松：检索本身已按作者限定，作者不必再充当证据，且题名往往很短
    （「Pastures by the Sea」剔除作者名后只剩 pastures 一个四字以上的词）。
    故只要求 >= 1 个题名共同词，但要求**唯一命中** —— 同一作者名下有多件都能对上时
    宁可放弃，也不猜。
    """
    tn, ta = toks(name), toks(artist)
    cands = []
    for did, slug in cp_by_artist(artist, cache):
        ts = toks(slug.replace("-", " "))
        ov = (tn & ts) - ta                      # 作者名不算匹配证据
        if ov:
            cands.append((did, slug, ov))
    if not cands:
        return None
    top = max(len(c[2]) for c in cands)
    best = [c for c in cands if len(c[2]) == top]
    if len(best) != 1:                           # 并列则放弃，不猜
        return None
    did, slug, ov = best[0]
    y = YEAR_IN_SLUG.search(slug)
    return did, slug, (y.group(1) if y else None), ov


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--refresh-wikidata", action="store_true",
                    help="忽略本地缓存，重新查 WDQS（注意对方限流）")
    args = ap.parse_args()

    conn = M.connect()
    cur = conn.cursor()
    cur.execute("""SELECT a.source_seq, ne.text FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        JOIN content_text ne ON ne.content_id = a.name_cid AND ne.lang = 'en'
        ORDER BY a.source_seq""", (MUSEUM,))
    rows = cur.fetchall()
    if args.limit:
        rows = rows[:args.limit]

    # 作者取自已入库的规则提取结果，避免在此重复实现解析
    cur.execute("""SELECT am.source_seq, t.text FROM artwork_meta am
        JOIN content_text t ON t.content_id = am.value_cid AND t.lang = 'en'
        WHERE am.museum_key = %s AND am.key_name = 'artist'""", (MUSEUM,))
    artists = dict(cur.fetchall())

    print(f"{MUSEUM.upper()} {len(rows)} 件；已知作者 {len(artists)} 件")
    print("拉取 Wikidata …", end=" ", flush=True)
    wd = load_wikidata(refresh=args.refresh_wikidata)
    print(f"{len(wd)} 件 PEM 藏品")

    for k, zh, en, note in [("date_text", "确切纪年", "Date", "有确切纪年时填"),
                            ("accession_no", "馆藏编号", "Accession Number", "馆方编号，原样照录"),
                            ("material", "材质", "Material", "可多值"),
                            ("artist", "作者", "Artist", "画家、工匠、作坊；可多值"),
                            ("image_url", "图片链接", "Image URL", "外部图片地址")]:
        M.ensure_key(cur, k, zh, en, note)

    cache_v, cp_cache = {}, {}
    stat = {"wikidata": 0, "pem_customprints": 0}
    hits_wd, hits_cp = [], []

    for i, (seq, name) in enumerate(rows, 1):
        art = artists.get(seq)

        m = match_wikidata(name, art, wd)
        if m:
            e, ov = m
            stat["wikidata"] += 1
            hits_wd.append((seq, name, e, sorted(ov)))
            # 来源串要语种中立：它会原样出现在中英两版导出里，
            # 而 artwork_meta.source 不走内容表，翻不了。
            src = f"wikidata:{e['qid']} matched={'/'.join(sorted(ov))}"
            if not args.dry_run:
                if e.get("inv"):
                    M.set_meta(cur, MUSEUM, seq, "accession_no", [(e["inv"], e["inv"])],
                               source_key="wikidata", source=src, confidence="high",
                               filled_by="scrape", cache=cache_v)
                if e.get("year"):
                    M.set_meta(cur, MUSEUM, seq, "date_text",
                               [(f"{e['year']} 年", e["year"])], value_nums=[int(e["year"])],
                               source_key="wikidata", source=src, confidence="medium",
                               filled_by="scrape", cache=cache_v)
                if e.get("creator"):
                    M.set_meta(cur, MUSEUM, seq, "artist", [(e["creator"], e["creator"])],
                               source_key="wikidata", source=src, confidence="high",
                               filled_by="scrape", cache=cache_v)
                if e["mats"]:
                    vals = [(x, x) for x in sorted(e["mats"])]
                    M.set_meta(cur, MUSEUM, seq, "material", vals,
                               source_key="wikidata", source=src, confidence="high",
                               filled_by="scrape", cache=cache_v)

        if art:
            cp = match_customprints(name, art, cp_cache)
            if cp:
                did, slug, year, ov = cp
                stat["pem_customprints"] += 1
                hits_cp.append((seq, name, slug, year, sorted(ov)))
                url = f"{CP}/detail/{did}/{slug}"
                if not args.dry_run:
                    if year:
                        M.set_meta(cur, MUSEUM, seq, "date_text",
                                   [(f"{year} 年", year)], value_nums=[int(year)],
                                   source_key="pem_customprints", source=url,
                                   confidence="medium", filled_by="scrape", cache=cache_v)
                    img = f"{CP}/vitruvius/render/1200/{did}.jpg"
                    M.set_meta(cur, MUSEUM, seq, "image_url", [(img, img)],
                               source_key="pem_customprints", source=url,
                               confidence="high", filled_by="scrape", cache=cache_v)
        if i % 40 == 0:
            print(f"  {i}/{len(rows)}")

    print(f"\nWikidata 命中 {stat['wikidata']} 件：")
    for seq, n, e, ov in hits_wd:
        print(f"  seq{seq:3d} {n[:40]:40s} -> {e['label'][:38]:38s} "
              f"馆藏号={e.get('inv','—')} 年={e.get('year','—')} 共同词={ov}")
    have = sum(1 for a, v in cp_cache.items() if v)
    print(f"\ncustomprints：查询了 {len(cp_cache)} 位作者，其中 {have} 位在该站有作品；"
          f"命中 {stat['pem_customprints']} 件：")
    for seq, n, slug, y, ov in hits_cp:
        print(f"  seq{seq:3d} {n[:40]:40s} -> {slug[:44]:44s} 年={y or '—'} 共同词={ov}")

    if args.dry_run:
        conn.rollback(); print("\n--dry-run：未写库")
    else:
        conn.commit(); print("\n已提交")
    conn.close()


if __name__ == "__main__":
    main()
