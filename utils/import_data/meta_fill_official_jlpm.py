#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
吉林省博物院：从官网接口的结构化字段确定性抽 metadata，写 artwork_meta。零 API。

    python3 meta_fill_official_jlpm.py --dry-run   # 逐件列出要写什么，不写库
    python3 meta_fill_official_jlpm.py

**只写评分范围的 107 行**（源表「评分范围」列为「评分」）。其余 1.76 万行只有名称与分类字段，
metadata 是给打分与审计当证据用的，那些行不进评分，写了没人读（用户 2026-09-27 定全部入库、只评有介绍的）。

**为什么不用 meta_fill_rule.py**：它解析英文，本馆官网没有英文。这里只取馆方接口本来就分好的字段，
每个取值都能在 jlpm_site_data.py / jlpm_collectdb.jsonl 里逐字指认：
    object_id       官网 ID（collect/<n>、collectdb/<十六进制>、exhibition/<n>），每行都写
    object_form     类别（typeName）。「其他」和空的不写；节点写对象层级（基本陈列 / 临时展览）
    period          年代（yearTypeName），照录馆方分类。辽、金、宋这类是馆方的年代标签，
                    不据此判政权归属（AGENTS.md 第 7 条：分裂时期不建单值 polity）
    material        质地（texture），逗号分隔的多值各占一行
    dimensions      尺寸（size），中文逐字；英文按「标签+数字」逐段翻，**有一个标签认不出就整条不写**
    relic_grade     文物级别（levelName），只有镇馆之宝有。新键，本脚本 ensure_key
    museum_highlight  镇馆之宝栏目
    relic_id        国家文物局可移动文物编号：jlpm_build.match_catalog 名称逐字相同且两边唯一才挂，
                    source_key=wikidata（第 3 级），取值带 QID 以便回查。新键，本脚本 ensure_key
镇馆之宝与数据库合并的 11 件，字段取镇馆之宝那一条（两边尺寸有 26.2 / 26 这类差异，不挑赢家，只写一边）。
翻译表外的取值直接报错 —— 不猜（AGENTS.md「取不到就喊」）。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

import jlpm_build as B
import meta_lib as M
import source_rules as SR

MUSEUM = "jlpm"
OWN_KEYS = ("jlpm_official", "jlpm_collectdb")   # 本脚本写的 source_key，重跑先整体清掉
WD_KEY = "relic_id"                              # 另清本馆 source_key=wikidata 且键为 relic_id 的

NEW_KEYS = [
    ("relic_grade", "文物级别", "Cultural Relic Grade", "国家文物定级：一级/二级/三级/一般，照录馆方"),
    ("relic_id", "可移动文物编号", "Movable Cultural Relic ID",
     "国家文物局可移动文物编号（Wikidata P11699），取值附 QID"),
]

SRC = {"t:": ("jlpm_official", "吉林省博物院官网镇馆之宝栏目"),
       "d:": ("jlpm_collectdb", "吉林省博物院官网藏品数据库"),
       "x:": ("jlpm_official", "吉林省博物院官网展览栏目")}
SRC_WD = "Wikidata《全国馆藏文物名录》条目（名称逐字相同）"

# 官网藏品数据库的 35 个类别（/collectdb/dict.do 的 typeList），逐个对译
CAT_EN = {
    "书法、绘画": "Calligraphy and painting", "陶器": "Pottery", "瓷器": "Porcelain", "铜器": "Bronze",
    "玉石器、宝石": "Jade, stone and gems", "金银器": "Gold and silver", "档案文书": "Archival documents",
    "名人遗物": "Personal effects of notable figures", "武器": "Weapons", "钱币": "Coins and currency",
    "票据": "Bills and certificates", "石器、石刻、砖瓦": "Stone implements, stone carvings, bricks and tiles",
    "铁器、其他金属器": "Iron and other metalwork", "文件、宣传品": "Documents and propaganda materials",
    "甲骨": "Oracle bones", "玺印符牌": "Seals and tallies", "玻璃器": "Glass", "雕塑、造像": "Sculpture and statues",
    "织绣": "Textiles and embroidery", "牙骨角器": "Ivory, bone and horn", "文具": "Stationery",
    "漆器": "Lacquerware", "古籍图书": "Rare books", "珐琅器": "Enamelware", "度量衡器": "Weights and measures",
    "乐器、法器": "Musical and ritual instruments", "家具": "Furniture", "竹木雕": "Bamboo and wood carving",
    "碑帖拓本": "Stele rubbings and model calligraphy", "皮革": "Leather", "邮品": "Philatelic items",
    "交通、运输工具": "Vehicles and transport", "音像制品": "Audio-visual materials",
    "标本、化石": "Specimens and fossils",
}
CAT_SKIP = {"", "其他"}
NODE_FORM_EN = {"基本陈列": "Core exhibition", "临时展览": "Temporary exhibition"}

PERIOD_EN = {
    "新石器时代": "Neolithic", "商": "Shang", "周": "Zhou", "西周": "Western Zhou", "东周": "Eastern Zhou",
    "春秋时代": "Spring and Autumn period", "战国时代": "Warring States period", "秦": "Qin", "汉": "Han",
    "西汉": "Western Han", "东汉": "Eastern Han", "三国": "Three Kingdoms", "唐": "Tang",
    "五代十国": "Five Dynasties and Ten Kingdoms", "宋": "Song", "北宋": "Northern Song", "南宋": "Southern Song",
    "辽": "Liao", "西夏": "Western Xia", "金": "Jin (1115–1234)", "元": "Yuan", "明": "Ming", "清": "Qing",
    "中华民国": "Republic of China (1912–1949)", "中华人民共和国": "People's Republic of China",
    "公元20世纪": "20th century",
}
# 「44」是安图人牙齿化石那条的年代字段，显然不是年代标签；「其他」「年代不详」没有信息
PERIOD_SKIP = {"", "其他", "年代不详", "44"}

MATERIAL_EN = {
    "纸": "paper", "铜": "bronze (copper alloy)", "铜质": "bronze (copper alloy)", "丝": "silk", "石": "stone",
    "金": "gold", "银": "silver", "铁": "iron", "钢质": "steel", "木": "wood", "竹": "bamboo",
    "陶": "earthenware", "瓷": "porcelain", "瓷器": "porcelain", "宝玉石": "jade and gemstone",
    "玉石器": "jade and stone", "骨角牙": "bone, horn and ivory", "毛": "wool or hair",
    "其他无机质": "other inorganic material", "皮革": "leather", "棉麻纤维": "cotton and bast fibre",
    "纸本设色": "ink and colour on paper",
}

# 尺寸标签。只收评分范围里实际出现的；新标签出现时整条不写并进报告，补进来再重跑
DIM_EN = {
    "高": "H", "通高": "overall H", "足高": "foot H", "钮高": "knob H", "纵": "H", "横": "W",
    "画横": "painting W", "书横": "calligraphy W", "长": "L", "通长": "overall L", "宽": "W", "厚": "thickness",
    "边厚": "rim thickness", "缘厚": "rim thickness", "最厚处": "max thickness", "直径": "D", "园径": "D",
    "外径": "outer D", "宽径": "width/D", "口径": "mouth D", "口": "mouth D", "腹径": "belly D", "腹": "belly D",
    "底径": "base D", "底": "base D", "足": "foot D", "口长": "mouth L", "口宽": "mouth W", "边长": "side L",
    "塔座长": "base L", "珠径": "bead D", "金管长": "gold tube L", "刃宽": "blade W", "銎长": "socket L",
    "銎宽": "socket W", "援长": "blade (yuan) L", "内长": "tang (nei) L", "柄长": "handle L", "茎": "stem L",
    "面长": "face L", "额宽": "forehead W", "身长": "body L", "胸围": "chest circumference",
    "牙长": "tooth L", "牙根长": "root L", "牙冠长": "crown L", "牙冠宽": "crown W",
    "金銙长": "gold belt-plaque L", "玉铊尾长": "jade belt-end L", "桃形玉銙长": "peach-shaped jade plaque L",
}
UNIT_RE = re.compile(r"厘米|公分|cm", re.I)
NUM = r"\d+(?:\.\d+)?(?:\s*[-—]\s*\d+(?:\.\d+)?)?"
PAIR_RE = re.compile(rf"([^\d\s.,，、;；*×xX\-—]+?)\s*[：:]?\s*({NUM})")


def dims(size: str):
    """-> (中文逐字, 英文) / None（空、占位值、或有标签认不出）/ ("?", 原因)。"""
    s = (size or "").strip()
    if s in ("", "-", "0"):
        return None
    unit = " cm" if UNIT_RE.search(s) else " (unit not stated)"
    t = UNIT_RE.sub(" ", s).replace("．", ".")
    if m := re.fullmatch(rf"\s*({NUM})\s*[*×xX]\s*({NUM})\s*", t):
        return s, f"{m.group(1)} × {m.group(2)}{unit}"
    pairs = PAIR_RE.findall(t)
    left = PAIR_RE.sub("", t)
    bad = [lab for lab, _ in pairs if lab not in DIM_EN]
    if not pairs or bad or re.search(r"[^\s.,，、;；]", left):
        return "?", f"认不出：标签 {bad}，余下 {left.strip()!r}"
    return s, "; ".join(f"{DIM_EN[lab]} {re.sub(r'\s+', '', n)}" for lab, n in pairs) + unit


class _Quiet:
    def say(self, *a):
        pass


def collect() -> tuple[list, list]:
    """-> ([(seq, 名称, key, (中文值, 英文值), source_key, 出处说明, confidence)], [没写的尺寸])"""
    q = _Quiet()
    rows = B.build_rows(q)
    B.assign_seq(rows, write=False, r=q)
    B.match_catalog(rows, q)
    out, skipped = [], []

    def add(row, key, val, sk, src, conf="high"):
        if val:
            out.append((row["seq"], row["name"], key, val, sk, src, conf))

    for row in rows:
        if row["scope"] != B.SCOPE_YES:
            continue
        sk, src = SRC[row["key"][:2]]
        # 官网自己的 ID（collect/<n>、collectdb/<32 位十六进制>、exhibition/<n>），按它能回官网查到这一件。
        # 每行都写：有的藏品除名称与介绍外一个结构化字段都没有（汉新莽始建国铜尺：类别、年代都是「其他」），
        # 不写的话它在 artwork_meta 里一条来源都没有，evidence_score 的 best_source_tier 就是空 ——
        # 而审计读的正是这一列（伪满皇宫节点踩过的坑）
        add(row, "object_id", (row["oid"], row["oid"]), sk, src + "（官网 ID）")
        if row["level"] != "藏品":
            add(row, "object_form", (row["level"], NODE_FORM_EN[row["level"]]), sk, src + "（对象层级）")
            continue
        cat = row["cat"]
        if cat not in CAT_SKIP:
            if cat not in CAT_EN:
                sys.exit(f"[fatal] 类别「{cat}」没在 CAT_EN 里（seq {row['seq']} {row['name']}）")
            add(row, "object_form", (cat, CAT_EN[cat]), sk, src + "（类别）")
        yr = row["year"]
        if yr not in PERIOD_SKIP:
            if yr not in PERIOD_EN:
                sys.exit(f"[fatal] 年代「{yr}」没在 PERIOD_EN 里（seq {row['seq']} {row['name']}）")
            add(row, "period", (yr, PERIOD_EN[yr]), sk, src + "（年代）")
        tex = row["texture"].strip()
        parts = [tex.replace(" ", "")] if tex.replace(" ", "") in MATERIAL_EN else \
            [p.strip() for p in tex.split(",") if p.strip()]
        for p in parts:
            if p not in MATERIAL_EN:
                sys.exit(f"[fatal] 质地「{p}」没在 MATERIAL_EN 里（seq {row['seq']} {row['name']}）")
            add(row, "material", (p, MATERIAL_EN[p]), sk, src + "（质地）")
        d = dims(row["size"])
        if d and d[0] == "?":
            skipped.append((row["seq"], row["name"], row["size"], d[1]))
        else:
            add(row, "dimensions", d, sk, src + "（尺寸）", "medium")
        if row["key"].startswith("t:"):
            add(row, "museum_highlight", ("镇馆之宝", "Museum treasure (official highlights list)"),
                sk, src + "（栏目）")
            g = row["grade"]
            if g:
                add(row, "relic_grade", (g, {"一级": "Grade I", "二级": "Grade II", "三级": "Grade III",
                                             "一般": "General (ungraded)"}[g]), sk, src + "（文物级别）")
        if row["relic"]:
            add(row, WD_KEY, (f"{row['relic']}（Wikidata {row['qid']}）", f"{row['relic']} (Wikidata {row['qid']})"),
                "wikidata", SRC_WD, "medium")
    return out, skipped


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="逐件列出，不写库")
    args = ap.parse_args()

    out, skipped = collect()
    for sk in {x[4] for x in out}:
        if sk not in SR.SOURCE_RULES:
            sys.exit(f"[fatal] source_key {sk!r} 没在 source_rules.SOURCE_RULES 登记")
    cur_seq = None
    for seq, name, key, (zh, en), sk, src, conf in sorted(out, key=lambda x: (x[0], x[2])):
        if seq != cur_seq:
            print(f"\n{seq:>4} {name}")
            cur_seq = seq
        print(f"       {key:17} {zh}  |  {en}   [{sk} · {conf}]")
    print(f"\n合计 {len(out)} 条，覆盖 {len({x[0] for x in out})} 件；按键 {dict(Counter(x[2] for x in out))}")
    for s in skipped:
        print(f"  尺寸没写（有标签认不出）：seq {s[0]} {s[1]}：{s[2]!r} —— {s[3]}")
    if args.dry_run:
        print("--dry-run：未写库")
        return
    write(out)


def write(out) -> None:
    """批量写入，一个事务（同 meta_fill_official_wmhg.write：逐条写跨公网会留残留事务）。"""
    ords: Counter = Counter()
    flat = []
    for seq, name, key, (zh, en), sk, src, conf in out:
        flat.append((seq, key, sk, ords[(seq, key, sk)], zh, en, src, conf))
        ords[(seq, key, sk)] += 1
    pairs = {(zh, en) for *_, zh, en, _src, _conf in flat}

    conn = M.connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM artwork a JOIN museum m ON m.id = a.museum_id"
                    " WHERE m.key_name = %s", (MUSEUM,))
        if cur.fetchone()[0] == 0:
            sys.exit("[fatal] 库里还没有 jlpm 的展品，先跑 import_artworks.py")
        for k, zh, en, note in NEW_KEYS:
            M.ensure_key(cur, k, zh, en, note)
        cur.execute("""SELECT z.text, e.text, z.content_id FROM content_text z
                         JOIN content c ON c.id = z.content_id AND c.kind = %s
                         JOIN content_text e ON e.content_id = z.content_id AND e.lang = 'en'
                        WHERE z.lang = 'zh-CN'""", (M.KIND_VALUE,))
        have = {(z, e): cid for z, e, cid in cur.fetchall()}
        cid_of = {p: have[p] for p in pairs if p in have}
        todo = sorted(pairs - set(cid_of))
        if todo:
            cur.execute("SELECT COALESCE(MAX(id), %s) FROM content WHERE id >= %s",
                        (M.CONTENT_ID_BASE, M.CONTENT_ID_BASE))
            nxt = cur.fetchone()[0] + 1
            crows, trows = [], []
            for i, (zh, en) in enumerate(todo):
                cid_of[(zh, en)] = nxt + i
                crows.append((nxt + i, M.KIND_VALUE))
                trows += [(nxt + i, "zh-CN", zh, M.SRC_ZH), (nxt + i, "en", en, M.SRC_EN)]
            cur.executemany("INSERT INTO content (id, kind) VALUES (%s,%s)", crows)
            cur.executemany("INSERT INTO content_text (content_id, lang, text, source)"
                            " VALUES (%s,%s,%s,%s)", trows)
        ph = ",".join(["%s"] * len(OWN_KEYS))
        cur.execute(f"DELETE FROM artwork_meta WHERE museum_key = %s AND (source_key IN ({ph})"
                    f" OR (source_key = 'wikidata' AND key_name = %s))", (MUSEUM, *OWN_KEYS, WD_KEY))
        cleared = cur.rowcount
        rows = []
        for seq, key, sk, o, zh, en, src, conf in flat:
            tier, etype, _ = SR.SOURCE_RULES[sk]
            rows.append((MUSEUM, seq, key, sk, o, cid_of[(zh, en)], src, conf, "rule",
                         etype, SR.quality_of(tier)))
        cur.executemany(
            "INSERT INTO artwork_meta (museum_key, source_seq, key_name, source_key,"
            " ord, value_cid, source, confidence, filled_by, evidence_type, source_quality)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"已提交：清空旧值 {cleared} 条，写入 artwork_meta {len(rows)} 条；"
          f"取值 {len(pairs)} 个（新建 {len(todo)}）")


if __name__ == "__main__":
    main()
