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
    python3 meta_scrape.py --museum pem --dry-run
    python3 meta_scrape.py --museum pem
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
import difflib
import unicodedata

import meta_lib as M

# 每个馆在 Wikidata 里的收藏实体。哈佛给两个：一部分藏品挂在下属的 Fogg 名下，
# 只查上位实体会漏。列表里任一命中即算该馆藏品。
MUSEUM_QID = {
    "pem":        ["Q3373790"],              # Peabody Essex Museum
    "mfa_boston": ["Q49133"],                # Museum of Fine Arts, Boston
    "ham":        ["Q3783572", "Q809600"],   # Harvard Art Museums / Fogg Museum
}
UA = "ari-metadata-research/1.0 (museum visit-planning dataset; contact via repo)"
WDQS = "https://query.wikidata.org/sparql"
# WDQS 故障期会整段拒绝（2026-09-01 实测连等 210s 仍 429）。QLever 是弗莱堡大学
# 的公共 Wikidata SPARQL 端点，同一份数据，另一套实现。它不支持 Wikidata 专有的
# SERVICE wikibase:label，标签得自己 join，故两边用两份查询文本。
QLEVER = "https://qlever.cs.uni-freiburg.de/api/wikidata"
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
def sparql_qlever(qids: list[str]) -> str:
    """QLever 版：显式 join rdfs:label，不用 SERVICE wikibase:label。"""
    values = " ".join(f"wd:{q}" for q in qids)
    return """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?item ?itemLabel ?inv ?inception ?creatorLabel ?matLabel WHERE {
  VALUES ?museum { %s }
  ?item wdt:P195 ?museum .
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "en")
  OPTIONAL { ?item wdt:P217 ?inv }
  OPTIONAL { ?item wdt:P571 ?inception }
  OPTIONAL { ?item wdt:P170 ?creator .
             ?creator rdfs:label ?creatorLabel . FILTER(LANG(?creatorLabel) = "en") }
  OPTIONAL { ?item wdt:P186 ?mat .
             ?mat rdfs:label ?matLabel . FILTER(LANG(?matLabel) = "en") }
}
""" % values


def sparql_for(qids: list[str]) -> str:
    values = " ".join(f"wd:{q}" for q in qids)
    return """
SELECT ?item ?itemLabel ?inv ?inception ?creatorLabel ?matLabel WHERE {
  VALUES ?museum { %s }
  ?item wdt:P195 ?museum .
  OPTIONAL { ?item wdt:P217 ?inv }
  OPTIONAL { ?item wdt:P571 ?inception }
  OPTIONAL { ?item wdt:P170 ?creator }
  OPTIONAL { ?item wdt:P186 ?mat }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
""" % values


def load_wikidata(museum: str, refresh: bool = False) -> list[dict]:
    """拉取并缓存某馆在 Wikidata 的全部藏品。

    结果落盘缓存，默认直接复用：这份数据几周才变一次，而 WDQS 会限流
    （实测遇到过 429「Aggressively rate-limiting to 1 req / min」，是他们
    故障期的临时规则）。每跑一次脚本就去打一次公共查询服务既不必要也不礼貌。
    要强制刷新用 --refresh-wikidata。
    """
    qids = MUSEUM_QID[museum]
    SPARQL = sparql_for(qids)
    cache = pathlib.Path(f"meta_cache/wikidata_{museum}.json")
    if cache.exists() and not refresh:
        data = json.loads(cache.read_text(encoding="utf-8"))
        print(f"(用缓存 {cache})", end=" ")
    else:
        url = WDQS + "?query=" + urllib.parse.quote(SPARQL) + "&format=json"
        # 先试官方 WDQS，被限流就换 QLever —— 不再苦等。
        # 那条「1 req / min」规则每次被拒都会重置窗口，短间隔重试永远打不进去，
        # 而长等也未必有用（实测连等 210s 仍 429）。换端点比死等划算。
        data = None
        for label, ep, q in (("WDQS", WDQS, SPARQL),
                             ("QLever", QLEVER, sparql_qlever(qids))):
            url = ep + "?query=" + urllib.parse.quote(q) + "&format=json"
            try:
                data = json.loads(fetch(url, 180))
                print(f"({label}) ", end="", flush=True)
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429:
                    raise
                print(f"  [{label} 429 限流，改用备用端点] ", end="", flush=True)
            except Exception as exc:
                print(f"  [{label} 失败 {str(exc)[:60]}，改用备用端点] ", end="", flush=True)
        if data is None:
            raise SystemExit("WDQS 与 QLever 都取不到数据")
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


TITLE_STOP = {"the", "a", "an", "of", "and", "with", "in", "on", "at", "by",
              "for", "to", "from", "or"}


def title_norm(s: str) -> str:
    """去变音符、去标点、压空格。用来做整体标题比对。"""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def title_toks(s: str) -> set[str]:
    return {w for w in title_norm(s).split() if w not in TITLE_STOP}


def strip_artist_prefix(name: str, artist: str | None) -> str:
    """剥掉「作者, 题名」里的作者前缀。

    哈佛的源表名称多是这个格式（「Botticelli, Madonna and Child with Angels」），
    而 Wikidata 那边只有题名。不剥的话，库里的题名永远比对方多出作者那几个词，
    正好落在被禁掉的那个包含方向上 —— 2026-09-01 实测哈佛因此只匹配上 3/204。
    只在前缀确实等于已知作者时才剥，不靠猜。
    """
    if not artist:
        return name
    head, sep, tail = name.partition(",")
    if sep and tail.strip() and title_norm(head) == title_norm(artist):
        return tail.strip()
    return name


def match_wikidata(name: str, artist: str | None, wd: list[dict],
                   dup_labels: set[str] | None = None):
    """按**整体标题**匹配，不再用「共同词 >= 3」。

    共同词阈值是为 PEM 那种描述性转写名设计的（「Robert Feke, Portrait of
    Gentleman」这类，本来就没有真题名可比）。MFA 与哈佛的名称是真实编目题名，
    用同一套阈值会把通用题名撞成一片 —— 2026-09-01 实测：
      「Still-Life with Apples and Oranges」错配到「…Apples and Chestnuts」
      「Still-Life with Pitcher and Fruit」错配到「Still Life of Bottles and Pitcher」
      两件不同展品同时指向同一个 Wikidata 条目
    「Still / Life / Saint / Holy Family」这些词在题名里满地都是，共同三个词
    说明不了任何事。

    改判两条，命中其一即可：
      ① 整体标题相似度 >= 0.95 —— 实测这一档 8/8 全对
      ② 库里的题名被 Wikidata 题名**完整包含**，且相似度 >= 0.72
         （「Mrs. Fiske Warren and Her Daughter」⊂「Mrs. Fiske Warren
           (Gretchen Osgood) and Her Daughter Rachel」，是同一幅；
          而 Apples/Oranges 与 Apples/Chestnuts 互不包含，被挡掉）
         **包含只认这一个方向。** 反过来（Wikidata 那边更笼统）不算数：
         「Still-Life with Pitcher and Fruit」对上「Still Life with Fruit」、
         「Bust of a Young Girl」对上「A young girl」，笼统的一方能套上一大片。
         代价是漏掉「Mademoiselle Victorine Meurent」→「Victorine Meurent」
         这类真的，认了 —— 错的会被当成事实喂进评分，漏的只是少一条。
    还有一条硬约束：**匹配上的 Wikidata 题名必须在该馆藏品里唯一**。
    2026-09-01 实测 MFA 的 4410 个条目里「self portrait」重名 25 次、
    「portrait of a woman」22 次、「virgin and child」23 次 —— 匹配到这类通用题名
    等于没匹配，哪怕相似度是 1.00 也分不出是其中哪一件。

    返回 (条目, 依据串, 可信度)。
    """
    dup_labels = dup_labels or set()
    # 两边都知道作者时，作者必须对得上。这一条挡掉的全是「题名像、作者根本不是
    # 同一个人」的错配 —— 2026-09-01 实测哈佛：
    #   「Van Gogh, Landscape with Trees」配到 1902 年的同名作（梵高 1890 年已故）
    #   「Lorenzo Lotto, Portrait of a Young Nobleman」配到「…Young Afsharid Nobleman」
    # 只在**双方都有**作者时才判，缺一方就不拦（不知道不等于不符）。
    a_toks = {t for t in title_toks(artist or "") if len(t) >= 4}
    tn = title_toks(name)
    if not tn:
        return None
    nn = title_norm(name)
    best = None
    for e in wd:
        tw = title_toks(e["label"])
        if not tw or title_norm(e["label"]) in dup_labels:
            continue
        cre = e.get("creator")
        if a_toks and cre:
            c_toks = {t for t in title_toks(cre) if len(t) >= 4}
            if c_toks and not (a_toks & c_toks):
                continue
        r = difflib.SequenceMatcher(None, nn, title_norm(e["label"])).ratio()
        if r >= 0.95:
            why, conf = f"title~{r:.2f}", "high"
        elif r >= 0.72 and tn <= tw and not (a_toks and not cre):
            # 最后那半句：库里知道作者、而 Wikidata 条目没记作者时，不收包含型匹配。
            # 这一档本来就只靠题名被包含，没有作者可对，撞上同名异作的概率很高 ——
            # 实测「Charles Willson Peale, Self-Portrait」配到 1973 年的
            # 「Male Nude (Self-portrait)」、「Lorenzo Lotto, Portrait of a Young
            # Nobleman」配到「…Young Afsharid Nobleman」，两条都是这么来的。
            # 相似度 >= 0.95 那一档不受此限：题名几乎逐字相同，本身就够硬。
            why, conf = f"title⊆{r:.2f}", "medium"
        else:
            continue
        if best is None or r > best[3]:
            best = (e, why, conf, r)
    return best[:3] if best else None


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
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", required=True, choices=sorted(MUSEUM_QID),
                    help="museum.key_name")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--refresh-wikidata", action="store_true",
                    help="忽略本地缓存，重新查 WDQS（注意对方限流）")
    args = ap.parse_args()
    museum = args.museum

    conn = M.connect()
    cur = conn.cursor()
    cur.execute("""SELECT a.source_seq, ne.text FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        JOIN content_text ne ON ne.content_id = a.name_cid AND ne.lang = 'en'
        ORDER BY a.source_seq""", (museum,))
    rows = cur.fetchall()
    if args.limit:
        rows = rows[:args.limit]

    # 作者取自已入库的规则提取结果，避免在此重复实现解析
    cur.execute("""SELECT am.source_seq, t.text FROM artwork_meta am
        JOIN content_text t ON t.content_id = am.value_cid AND t.lang = 'en'
        WHERE am.museum_key = %s AND am.key_name = 'artist'""", (museum,))
    artists = dict(cur.fetchall())

    print(f"{museum.upper()} {len(rows)} 件；已知作者 {len(artists)} 件")
    print("拉取 Wikidata …", end=" ", flush=True)
    wd = load_wikidata(museum, refresh=args.refresh_wikidata)
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

    # 先全量匹配，再剔歧义：同一个 Wikidata 条目被两件展品同时认领，说明至少有
    # 一件是错的，而我们分不清是哪件 —— 两件都丢。2026-09-01 实测 MFA 有三对
    # （26.167 / 02.4 / 26.141），源表里本来就有重复条目，留着必然张冠李戴。
    import collections as _c
    _lab = _c.Counter(title_norm(e["label"]) for e in wd)
    dup_labels = {l for l, n in _lab.items() if n > 1}
    print(f"  Wikidata 条目 {len(wd)}，其中题名重名的 {len(dup_labels)} 种，"
          f"这些一律不参与匹配（分不出是哪一件）")
    prelim = {seq: match_wikidata(strip_artist_prefix(name, artists.get(seq)),
                                  artists.get(seq), wd, dup_labels)
              for seq, name in rows}
    claimed = {}
    for seq, m in prelim.items():
        if m:
            claimed.setdefault(m[0]["qid"], []).append(seq)
    ambiguous = {q: ss for q, ss in claimed.items() if len(ss) > 1}
    if ambiguous:
        drop = {s2 for ss in ambiguous.values() for s2 in ss}
        print(f"  [歧义] {len(ambiguous)} 个 Wikidata 条目被多件展品同时匹配上，"
              f"涉及 {len(drop)} 件，全部丢弃：")
        for q, ss in sorted(ambiguous.items()):
            print(f"     {q} <- seq {ss}")
        prelim = {k: (None if k in drop else v) for k, v in prelim.items()}

    for i, (seq, name) in enumerate(rows, 1):
        art = artists.get(seq)

        m = prelim.get(seq)
        if m:
            e, why, conf_t = m
            stat["wikidata"] += 1
            hits_wd.append((seq, name, e, why, conf_t))
            # 来源串要语种中立：它会原样出现在中英两版导出里，
            # 而 artwork_meta.source 不走内容表，翻不了。
            src = f"wikidata:{e['qid']} {why}"
            if not args.dry_run:
                if e.get("inv"):
                    M.set_meta(cur, museum, seq, "accession_no", [(e["inv"], e["inv"])],
                               source_key="wikidata", source=src, confidence=conf_t,
                               filled_by="scrape", cache=cache_v)
                if e.get("year"):
                    M.set_meta(cur, museum, seq, "date_text",
                               [(f"{e['year']} 年", e["year"])], value_nums=[int(e["year"])],
                               source_key="wikidata", source=src,
                               confidence="medium" if conf_t == "high" else "low",
                               filled_by="scrape", cache=cache_v)
                if e.get("creator"):
                    M.set_meta(cur, museum, seq, "artist", [(e["creator"], e["creator"])],
                               source_key="wikidata", source=src, confidence=conf_t,
                               filled_by="scrape", cache=cache_v)
                if e["mats"]:
                    vals = [(x, x) for x in sorted(e["mats"])]
                    M.set_meta(cur, museum, seq, "material", vals,
                               source_key="wikidata", source=src, confidence=conf_t,
                               filled_by="scrape", cache=cache_v)

        if art:
            # customprints 是 PEM 自家的复制品商店，其余馆没有对应站点
            cp = match_customprints(name, art, cp_cache) if museum == "pem" else None
            if cp:
                did, slug, year, ov = cp
                stat["pem_customprints"] += 1
                hits_cp.append((seq, name, slug, year, sorted(ov)))
                url = f"{CP}/detail/{did}/{slug}"
                if not args.dry_run:
                    if year:
                        M.set_meta(cur, museum, seq, "date_text",
                                   [(f"{year} 年", year)], value_nums=[int(year)],
                                   source_key="pem_customprints", source=url,
                                   confidence="medium", filled_by="scrape", cache=cache_v)
                    img = f"{CP}/vitruvius/render/1200/{did}.jpg"
                    M.set_meta(cur, museum, seq, "image_url", [(img, img)],
                               source_key="pem_customprints", source=url,
                               confidence="high", filled_by="scrape", cache=cache_v)
        if i % 40 == 0:
            print(f"  {i}/{len(rows)}")

    print(f"\nWikidata 命中 {stat['wikidata']} 件：")
    for seq, n, e, why, conf_t in hits_wd:
        print(f"  seq{seq:3d} {n[:40]:40s} -> {e['label'][:38]:38s} "
              f"馆藏号={e.get('inv','—')} 年={e.get('year','—')} {why}/{conf_t}")
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
