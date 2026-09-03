#!/usr/bin/env python3
"""从展品现有字段确定性提取 metadata，写入 artwork_meta。任意馆通用。

**这不是抓取。** PEM 的藏品门户 explore-art.pem.org 已不可访问（443 连接被拒），
库里 PEM 的 official_url 与 image_url 均为 0/196，没有可抓的链接。逐件网络搜索
对知名藏品有效（实测「Twilight on the Kennebec」可查到 1849 年、油彩画布、
2014 年 Serena M. Hatch 捐赠），但对源文件里的泛称条目（如「Robert Feke,
Portrait of Gentleman」）查不到 —— 那类条目疑似填充数据。故本脚本只做
**从已有文本的确定性提取**，网络增补另作它议。

能提取的四个键，及其上限：
    object_form  196/196  源文件 Category 列直接可用，中英双语现成
    artist        30/196  名称形如「作者, 作品名」
    period        ~67/196 名称或英文简介里的年代词
    cultural_context ~103/196 名称或英文简介里的文化/地域词

**提取不到的**（源数据里根本没有，不是规则不够好）：
    尺寸 0/196、馆藏编号 0/196、出土地 1/196

本脚本原名 meta_fill_pem.py，只跑 PEM。抽取逻辑（作者/年代/文化解析）本来
就与馆无关，写死一个馆只会逼着下一个馆去复制一份 —— 复制出来的两份迟早分叉，
且不报错。故就地泛化为 --museum。上面那组覆盖率是 PEM 的实测值，
其余馆各不相同：名称形如「作者, 作品名」的比例、简介里带不带年代词，都不一样。

用法：
    python3 meta_fill_rule.py --museum pem --dry-run   # 只统计与抽样，不写库
    python3 meta_fill_rule.py --museum mfa_boston
"""
from __future__ import annotations

import argparse
import re

import meta_lib as M


# ---- 作者 -------------------------------------------------------------------
# 名称形如「Xxx Yyy, 作品名」。裸正则的准确率只有 30/44=68%，因为
# 「Sinhalese ivory combs, export set」这类器物名也是逗号分隔。
# 加「前缀每个词首字母都大写」后升到 30/33，剩下三个是首字母恰好全大写的
# 器物名，只能显式排除 —— 196 条的规模下，一份可审的排除表比再堆正则更诚实。
ARTIST_RE = re.compile(r"^([A-Z][A-Za-z\.‐’' ]{2,34}),\s")
NOT_ARTIST = {"Yin Yu Tang", "Nanban Byobu", "Rush Figurehead"}


def artist_of(name_en: str) -> str | None:
    m = ARTIST_RE.match(name_en)
    if not m:
        return None
    who = m.group(1).strip()
    if who in NOT_ARTIST:
        return None
    # 每个词首字母大写才算人名；含小写词的多半是器物名
    if not all(w[:1].isupper() for w in who.split() if w):
        return None
    return who


# ---- 年代 -------------------------------------------------------------------
# 顺序即优先级：具体王朝/时期先于泛化的世纪，避免「Qing‑dynasty 18th century」
# 被记成「18世纪」而丢掉朝代。
PERIODS = [
    (r"pre[‐\-]contact",              "前接触期",   "Pre-contact"),
    (r"Kamakura",                          "镰仓时代",   "Kamakura period"),
    (r"Edo[‐\- ]period|\bEdo\b",      "江户时代",   "Edo period"),
    (r"Joseon",                            "朝鲜王朝",   "Joseon dynasty"),
    (r"Qing[‐\- ]dynasty|\bQing\b",   "清",         "Qing dynasty"),
    (r"Ming[‐\- ]dynasty|\bMing\b",   "明",         "Ming dynasty"),
    (r"Safavid",                           "萨法维",     "Safavid"),
    (r"Qajar",                             "卡扎尔",     "Qajar"),
    (r"Ottoman",                           "奥斯曼",     "Ottoman"),
    (r"Mughal",                            "莫卧儿",     "Mughal"),
    (r"Federal[‐\- ](?:era|period)",  "联邦时期",   "Federal period"),
    (r"Renaissance",                       "文艺复兴",   "Renaissance"),
    (r"Baroque",                           "巴洛克",     "Baroque"),
    (r"Gothic",                            "哥特",       "Gothic"),
]
CENTURY_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[‐\- ]century", re.I)
ORD = {1: "st", 2: "nd", 3: "rd"}


POSSESSIVE_RE = re.compile(
    r"\b([A-Z][A-Za-z\u2018\u2019'\u2010-]{1,20}"
    r"(?: (?:van|von|de|del|della|da|di|le|la))?"
    r"(?: [A-Z][A-Za-z\u2018\u2019'\u2010-]{1,20}){0,2})[\u2019']s\b")

# 简介里以所有格出现的大写人名，几乎只会是作者：
#   「John Sargent's greatest group portrait」「Monet's famous Saint-Lazare series」
# 要求首字母大写，把「the postman's wife」这类普通名词挡在外面。
DESC_NOT_ARTIST = {"Boston", "Museum", "America", "North", "China", "Japan", "Europe",
                   "Paris", "London", "Salem", "Harvard", "Ming", "Qing", "Edo", "Zen"}


# 名称前缀是不是作者，是**每个源文件的格式事实**，跟「取哪一列 tier」同类，
# 所以记在这里而不是做成命令行开关 —— 开关会被下一个人忘了加，配置不会。
# 2026-09-01 逐馆实测（前缀候选数 -> 其中真是人名的）：
#   pem         30 -> 29    「Fitz Henry Lane, Twilight on the Kennebec」
#   ham         94 -> 92    「Rembrandt, Bust of an Old Man」，混着少量器物名
#   mfa_boston  18 ->  3    「Vase, Ming Yong-le」「Aphrodite, "Boston Aphrodite"」
#                            前缀基本是器型或题材，开了净是错的
NAME_ARTIST_PREFIX = {"pem": True, "ham": True, "mfa_boston": False}

# 器型 / 材质 / 题材 / 风格词。人名里不会出现，题名前缀里很常见，
# 用来兜住 NAME_ARTIST_PREFIX 为真的馆里混进来的器物名（如「Bronze Owl Zun」）。
OBJ_WORDS = {
    "bronze", "silver", "gold", "gilt", "stone", "sandstone", "marble", "wood",
    "wooden", "jade", "ivory", "glazed", "lacquer", "porcelain", "ceramic", "clay",
    "terracotta", "iron", "tapestry", "diptych", "triptych", "fragment",
    "vase", "bowl", "spoon", "set", "tile", "panel", "helmet", "armor", "armour",
    "head", "figure", "statue", "sculpture", "screen", "scroll", "print",
    "painting", "portrait", "mirror", "sword", "robe", "mask", "jar", "cup",
    "plate", "dish", "box", "chair", "table", "clock", "quilt", "fan", "drum", "doll",
    "buddha", "bodhisattva", "guanyin", "aphrodite", "athena", "apollo", "venus",
    "zeus", "krishna", "shiva", "zun", "ding", "gothic", "baroque", "samurai",
    # 朝代与画中人物。所有格解析会把「Emperor Huizong of Song's」截成「Song」、
    # 把「emphasizing Susanna's dignity」里的画中人 Susanna 当成作者
    # （那件的真作者 Artemisia Gentileschi 写在简介开头，不带所有格）。
    "song", "ming", "qing", "tang", "han", "shang", "zhou", "edo", "meiji", "joseon",
    "susanna", "judith", "madonna", "christ", "emperor", "empress",
}


def looks_like_person(w: str) -> bool:
    """粗筛：至多四个词，且不含器型/题材词。

    「Grant Wood」这样的真作者会被 wood 误杀 —— 这是刻意的取舍：
    错的作者会被当成事实喂进评分，漏掉的只是少一条 metadata。
    """
    toks = [t.lower() for t in re.findall(r"[A-Za-z]+", w)]
    return bool(toks) and len(toks) <= 4 and not (set(toks) & OBJ_WORDS)


def artist_from_desc(desc: str) -> str | None:
    """从英文简介的所有格里取作者。取不到就返回 None —— 宁可漏，不可错。"""
    for m in POSSESSIVE_RE.finditer(desc or ""):
        who = m.group(1).strip()
        if who in DESC_NOT_ARTIST or len(who) < 4 or not looks_like_person(who):
            continue
        return who
    return None


def period_of(text: str):
    for pat, zh, en in PERIODS:
        if re.search(pat, text, re.I):
            return zh, en
    m = CENTURY_RE.search(text)
    if m:
        n = int(m.group(1))
        suf = ORD.get(n % 10 if n % 100 not in (11, 12, 13) else 0, "th")
        return f"{n}世纪", f"{n}{suf} century"
    return None


# ---- 文化归属 ---------------------------------------------------------------
CULTURES = [
    ("Hawaiian", "夏威夷", "Hawaiian"), ("Māori|Maori", "毛利", "Māori"),
    ("Fijian|Fiji", "斐济", "Fijian"), ("Tongan|Tonga", "汤加", "Tongan"),
    ("Samoan", "萨摩亚", "Samoan"), ("Marquesan", "马克萨斯", "Marquesan"),
    ("Rapa Nui", "拉帕努伊", "Rapa Nui"), ("New Hebrides", "新赫布里底", "New Hebrides"),
    ("New Britain|Melanesian", "美拉尼西亚", "Melanesian"),
    ("Polynesian", "波利尼西亚", "Polynesian"),
    ("Japanese|Nanban|Arita|Imari|netsuke|ukiyo", "日本", "Japanese"),
    ("Korean|Joseon", "朝鲜", "Korean"),
    ("Chinese|Canton|Huizhou", "中国", "Chinese"),
    ("Sinhalese", "斯里兰卡", "Sinhalese"),
    (r"Anglo[‐\-]Indian|Vizagapatam", "英属印度", "Anglo-Indian"),
    ("Mughal|Rajput|Indian", "印度", "Indian"),
    ("Persian|Safavid|Qajar", "波斯", "Persian"),
    ("Ottoman|Mamluk", "奥斯曼与马穆鲁克", "Ottoman and Mamluk"),
    ("Egyptian", "埃及", "Egyptian"), ("Etruscan", "伊特鲁里亚", "Etruscan"),
    ("Roman", "罗马", "Roman"), ("Greek", "希腊", "Greek"),
    ("Venetian|Italian", "意大利", "Italian"), ("Dutch|delft", "荷兰", "Dutch"),
    ("American|Salem|New England", "美国", "American"),
]


# ---- 确切纪年 ---------------------------------------------------------------
# 与 period 分工：period 记朝代/世纪这类区段，date_text 记文本里出现的具体年份。
# 两者不互斥，一件展品可以同时有「清」和「1849」。
YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20[0-2]\d)\b")


def year_of(text: str):
    ys = YEAR_RE.findall(text)
    if not ys:
        return None
    y = sorted(set(ys))[0]          # 多个年份时取最早的，通常是创作年
    return f"{y} 年", y


def culture_of(text: str):
    for pat, zh, en in CULTURES:
        if re.search(pat, text, re.I):
            return zh, en
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", required=True,
                    help="museum.key_name，如 pem / mfa_boston / ham")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    museum = args.museum

    conn = M.connect()
    cur = conn.cursor()
    cur.execute("""SELECT a.source_seq, ne.text, nz.text, me.text, mz.text, de.text
        FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        JOIN content_text ne ON ne.content_id = a.name_cid AND ne.lang = 'en'
        JOIN content_text nz ON nz.content_id = a.name_cid AND nz.lang = 'zh-CN'
        LEFT JOIN content_text me ON me.content_id = a.medium_cid AND me.lang = 'en'
        LEFT JOIN content_text mz ON mz.content_id = a.medium_cid AND mz.lang = 'zh-CN'
        LEFT JOIN content_text de ON de.content_id = a.description_cid AND de.lang = 'en'
        ORDER BY a.source_seq""", (museum,))
    rows = cur.fetchall()
    if not rows:
        raise SystemExit(f"库中没有 museum_key={museum!r} 的展品")
    print(f"{museum.upper()} {len(rows)} 件")

    for k, zh, en, note in [
            ("object_form", "器型·类别", "Object Form", "器物形制或作品类型，自由文本"),
            ("artist", "作者", "Artist", "画家、工匠、作坊；可多值"),
            ("period", "年代", "Period", "朝代或世纪，如「清」「19世纪」"),
            ("date_text", "确切纪年", "Date", "有确切纪年时填，如「宣德三年」「1889」"),
            ("cultural_context", "文化归属", "Cultural Attribution", "如「徽州」「大和民族」「毛利」")]:
        M.ensure_key(cur, k, zh, en, note)

    # 先清空本脚本名下的两个 source_key。set_meta 只按 (seq, key, source_key) 覆盖，
    # 某件这次不再产出 artist 时，上一轮写错的那条会原地留下 —— 必须整体清。
    # 只删自己的 source_key，不碰 wikidata / pem_official / evidence（AGENTS.md 第 3 条）。
    if not args.dry_run:
        cur.execute("DELETE FROM artwork_meta WHERE museum_key=%s"
                    " AND source_key IN ('rule','source_file')", (museum,))
        print(f"  清空本脚本名下旧值 {cur.rowcount} 条")

    cache, stat, samples = {}, {}, {}
    for seq, ne, nz, me, mz, de in rows:
        blob = f"{ne} {de or ''}"
        out = []
        if me and mz:
            out.append(("object_form", (mz, me), "source_file", "源文件 Category 列", "high"))
        # 名称形如「作者, 作品名」**只有部分馆成立**，是源表格式而非通则：
        #   PEM  Fitz Henry Lane, Twilight on the Kennebec   -> 成立
        #   MFA  Vase, Ming Yong-le blue-and-white           -> 前缀是器型不是人
        #        Aphrodite, "Boston Aphrodite"               -> 前缀是题材不是人
        #   哈佛  Rembrandt, Bust of an Old Man（成立）与
        #        Bronze Owl Zun, Shang Dynasty（不成立）混在一起
        # 2026-09-01 实测：不加开关直接跑 MFA 与哈佛，抓出 Lullaby / Aphrodite /
        # Vase / Guanyin / Bronze Owl Zun 这类假作者 112 条。错的作者比没有作者更糟 ——
        # 它会被当成事实喂进评分。故改为按馆显式声明，默认关闭。
        who = artist_of(ne) if NAME_ARTIST_PREFIX.get(museum) else None
        if who and not looks_like_person(who):
            who = None
        if who:
            out.append(("artist", (who, who), "rule", "名称解析（作者, 作品名）", "high"))
        else:
            # 与名称格式无关的兜底：简介里的所有格人名
            who = artist_from_desc(de or "")
            if who:
                out.append(("artist", (who, who), "rule", "英文简介所有格解析", "medium"))
        p = period_of(blob)
        if p:
            out.append(("period", p, "rule", "名称与英文简介解析", "medium"))
        y = year_of(blob)
        if y:
            out.append(("date_text", y, "rule", "名称与英文简介解析", "medium"))
        cu = culture_of(blob)
        if cu:
            out.append(("cultural_context", cu, "rule", "名称与英文简介解析", "medium"))
        for key, (vzh, ven), skey, src, conf in out:
            stat[key] = stat.get(key, 0) + 1
            samples.setdefault(key, []).append((seq, vzh, ven))
            if not args.dry_run:
                M.set_meta(cur, museum, seq, key, [(vzh, ven)], source_key=skey,
                           source=src, confidence=conf, filled_by="rule", cache=cache)

    print(f"\n{'键':18s}{'命中':>6s}{'覆盖率':>8s}   抽样")
    for k in ("object_form", "artist", "period", "date_text", "cultural_context"):
        n = stat.get(k, 0)
        s = "; ".join(f"{q}:{z}" for q, z, _ in samples.get(k, [])[:4])
        print(f"{k:18s}{n:6d}{n/len(rows)*100:7.0f}%   {s}")
    print(f"\n合计写入 {sum(stat.values())} 条；新建值内容 {len(cache)} 段")

    if args.dry_run:
        conn.rollback(); print("\n--dry-run：未写库")
    else:
        conn.commit(); print("\n已提交")
    conn.close()


if __name__ == "__main__":
    main()
