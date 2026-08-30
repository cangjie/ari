#!/usr/bin/env python3
"""从 PEM 现有字段确定性提取 metadata，写入 artwork_meta。

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

用法：
    python3 meta_fill_pem.py --dry-run    # 只统计与抽样，不写库
    python3 meta_fill_pem.py
"""
from __future__ import annotations

import argparse
import re

import meta_lib as M

MUSEUM = "pem"

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
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

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
        ORDER BY a.source_seq""", (MUSEUM,))
    rows = cur.fetchall()
    print(f"{MUSEUM.upper()} {len(rows)} 件")

    for k, zh, en, note in [
            ("object_form", "器型·类别", "Object Form", "器物形制或作品类型，自由文本"),
            ("artist", "作者", "Artist", "画家、工匠、作坊；可多值"),
            ("period", "年代", "Period", "朝代或世纪，如「清」「19世纪」"),
            ("date_text", "确切纪年", "Date", "有确切纪年时填，如「宣德三年」「1889」"),
            ("cultural_context", "文化归属", "Cultural Attribution", "如「徽州」「大和民族」「毛利」")]:
        M.ensure_key(cur, k, zh, en, note)

    cache, stat, samples = {}, {}, {}
    for seq, ne, nz, me, mz, de in rows:
        blob = f"{ne} {de or ''}"
        out = []
        if me and mz:
            out.append(("object_form", (mz, me), "source_file", "源文件 Category 列", "high"))
        who = artist_of(ne)
        if who:
            out.append(("artist", (who, who), "rule", "名称解析（作者, 作品名）", "high"))
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
                M.set_meta(cur, MUSEUM, seq, key, [(vzh, ven)], source_key=skey,
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
