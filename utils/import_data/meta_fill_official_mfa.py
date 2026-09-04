#!/usr/bin/env python3
"""从 MFA 扩充清单（mfa_boston_ext）确定性抽取 metadata。**一次 API 都不调。**

这份源文件的名称与简介是**半结构化**的，字段就写在文本里：

    名称: 《观音菩萨像》Guanyin, Bodhisattva of Compassion（中国，金代，12 世纪初；泡桐木、彩绘与贴金）
                                                          └─ 产地，朝代，年代；材质 ─┘
    简介: …Hervey Edward Wetzel 基金购藏，编号 20.590。
                └────── 入藏方式 ──────┘  └─ 馆藏号 ─┘

实测覆盖率：名称带括号注 3397/3521（96%），简介带藏品编号 3973/4464（89%）。
所以这些字段不需要模型来读，正则就够 —— 而且正则的结果可复算、可复核、不要钱。

**两个来源必须分开登记。** 同一份文件里：
  · official_url 指向 mfa.org 的 135 条 —— 馆方展厅页/部门页，Tier 1
  · 指向 wikidata.org 的 4329 条 —— 源文件自己标明「展厅与在展状态未经官网确认」，Tier 3
混为一谈就等于把后者伪装成馆方权威发布。见 source_rules.py。

**朝代按并存政权处理，不做取舍。** 辽/金/北宋在 12 世纪初是并存政权，不是先后相承
（山西北部属辽、南部属北宋，1125 后才全境入金）。同一件对象在不同来源下被标成
「金代」与「宋代」不是数据打架，是不同的政权归属表述。所以：
  · date_absolute（12 世纪初）与 polity（金代）分开成两个键 —— 前者各方无争议；
  · artwork_meta 主键含 source_key，两说并存，写入方不挑赢家（AGENTS.md 第 7 条）。
南北朝、五代十国、三国同理。

用法：
    python3 meta_fill_official_mfa.py --dry-run          # 只看抽出什么，不写库
    python3 meta_fill_official_mfa.py                     # 写库
    python3 meta_fill_official_mfa.py --only-seq 124      # 只处理一件
"""
from __future__ import annotations

import argparse
import re

import meta_lib as M
import source_rules as SR

MUSEUM = "mfa_boston_ext"

# 要抽的键：key_name -> (中文显示名, 英文显示名)
KEYS = {
    "accession_number": ("馆藏号", "Accession number"),
    "origin_place":     ("产地", "Place of origin"),
    "artist":           ("作者", "Artist or maker"),
    "polity":           ("政权/朝代", "Polity or dynasty"),
    "date_absolute":    ("绝对年代", "Absolute date"),
    "material":         ("材质", "Materials"),
    "acquisition":      ("入藏方式", "Acquisition"),
    "gallery_official":  ("官方展厅", "Official gallery"),
    "museum_highlight": ("馆方标注的展厅重点", "Museum-designated highlight"),
}

# ---------------------------------------------------------------------------
# 名称括号里的内容怎么解析
#
# 【2026-09-04 修正：不能按位置猜字段】
# 这份文件里两种来源的括号结构**完全不同**：
#   官网来源（96 件带括号）：（产地，年代[，补充]；材质）
#   Wikidata（3387 件）    ：（作者，ISO日期[，材质]）—— 第一段是**人名**
# 初版把第一段一律当产地，于是「威廉·莫里斯·亨特」「约翰·辛格·沙金」「閻立本」
# 这些人名会被整批写成产地，3387 条。而且官网那 96 件的第一段实测有 76 种取值，
# 产地、年代、朝代、材质、题材描述（「弹弦乐器的女子」）、
# 专辑标签（「Japanese Collection Highlights 专辑封面作品」）混在一起 ——
# 按位置解析在两种格式下都不成立。
#
# 现在改成：**逐段按模式判别，认不出的一概不写**。
# 宁可漏一条 metadata，也不能把人名写进产地 —— 错的事实会被当证据喂进评分，
# 漏掉的只是少一条。这与 meta_fill_rule.looks_like_person 的取舍一致。
# ---------------------------------------------------------------------------

PAREN = re.compile(r"（([^）]{4,})）")

# Wikidata 导出的日期占位：0650-01-01 这种，月日是机器补的，只取年。
ISO_DATE = re.compile(r"^(\d{3,4})-\d{2}-\d{2}$")
# 可辨认的年代表述：世纪 / 公元前 / 纯年份或年份区间（约 1638、1806–09、1885-86）
DATE_TEXT = re.compile(r"(世纪|公元前|\d{3,4}\s*[–—-]\s*\d{2,4}|^约?\s*\d{3,4}\s*年?$)")

# 政权 / 朝代。**只认整段等于表里的词**（可带「代」），认不出就不写 polity。
# 不试图识别「古王国第四王朝」「希腊化时期」这类分期表述 —— 它们是时期不是政权，
# 硬塞进 polity 只会让这一列的含义糊掉。
POLITY = ("北宋", "南宋", "宋", "辽", "金", "西夏", "元", "明", "清", "唐", "隋",
          "汉", "秦", "商", "周", "五代", "镰仓", "室町", "江户", "平安", "奈良",
          "飞鸟", "桃山", "高丽", "朝鲜", "新罗")

# 产地白名单。**只收国家/地区名**，且必须整段相等。
# 不做「短的中文串就当产地」这类推断 —— 官网那批里 Saichi（人名）、
# 「弹弦乐器的女子」（题材）都是短串，猜一次就错一次。
PLACES = ("中国", "日本", "朝鲜", "韩国", "印度", "埃及", "伊拉克", "伊朗", "希腊",
          "罗马", "意大利", "法国", "英国", "德国", "西班牙", "荷兰", "美国",
          "墨西哥", "巴拿马", "秘鲁", "尼日利亚", "加纳", "刚果", "埃塞俄比亚",
          "土耳其", "叙利亚", "黎巴嫩", "以色列", "巴基斯坦", "泰国", "柬埔寨",
          "缅甸", "越南", "印度尼西亚", "菲律宾", "新西兰", "澳大利亚",
          "巴布亚新几内亚", "尼泊尔", "西藏", "蒙古", "俄罗斯", "苏丹", "利比里亚")

# 材质词。整段含其一即判材质 —— 材质名不会与人名、地名撞车。
MATERIAL_WORDS = ("油彩", "油画", "木", "石", "铜", "金", "银", "玉", "陶", "瓷",
                  "漆", "绢", "纸", "布", "丝", "棉", "麻", "象牙", "骨", "玻璃",
                  "大理石", "青铜", "水彩", "版画", "蚀刻", "石膏", "屏風", "屏风",
                  "手卷", "册页", "挂轴", "textile", "彩绘", "贴金", "鎏金")

ACCESSION = re.compile(r"(?:藏品)?编号\s*([0-9]{2,4}\.[0-9]+(?:\.[0-9]+)*)")
ACQUIRE = re.compile(r"([^。；，]{2,40}?(?:基金|捐赠|购藏|遗赠|捐出))")
# 馆方自己的重点标注。**只认原文写死的这几种说法**，不做语义判断 ——
# 一旦开始「理解」它有多重要，这一列就从事实变成了推断。
HIGHLIGHT = re.compile(r"(该展厅的核心展品|展厅核心展品|镇馆|代表作)")


def classify(seg: str, strict: bool = False) -> tuple[str, str] | None:
    """把括号里的一段判成 (key, value)。**判不出返回 None，调用方必须丢弃。**

    【整段相等才算字段名，出现在更长的串里就是别的东西】
    朝代与产地一律**整段等值**匹配（朝代可带「代」「朝」后缀）：
      「宋」    -> polity=宋        整段就是朝代名
      「宋徽宗」 -> 不是 polity      朝代名只是姓氏，这是人名
      「唐寅」   -> 不是 polity      同上
    这条规则对材质更要紧，因为材质是**子串**匹配的（「泡桐木、彩绘与贴金」
    必须靠子串才认得出）。而子串规则撞上音译人名就是灾难：
      约翰·辛格·沙「金」 欧仁·「布」丹 立「石」春美 阿尔「布」雷希特·丢勒
    实测 207 条作者被这么误判成材质。所以 strict=True 时**关掉子串规则**，
    只保留整段等值与日期格式 —— 调用方对「这一段应该是人名」的位置必须传 strict。
    """
    seg = seg.strip().strip("“”\"'")
    if not seg:
        return None
    if (m := ISO_DATE.match(seg)):
        return ("date_absolute", m.group(1))          # 0650-01-01 -> 0650
    for suf in ("代", "朝", ""):
        if suf and seg.endswith(suf) and seg[:-len(suf)] in POLITY:
            return ("polity", seg[:-len(suf)])
        if not suf and seg in POLITY:
            return ("polity", seg)
    if seg in PLACES:
        return ("origin_place", seg)
    if DATE_TEXT.search(seg):
        return ("date_absolute", seg)
    if strict:
        return None                # 子串规则以下一概不用 —— 这一段该是人名
    if any(w in seg for w in MATERIAL_WORDS):
        return ("material", seg)
    return None


def parse(name: str, desc: str, is_official: bool) -> list[tuple[str, str]]:
    """返回 [(key_name, value)]。抽不出的键就不返回，不写空值、不猜。

    is_official 决定第一段怎么读：Wikidata 那批的格式是机器按
    `creator, inception, material` 拼出来的，第一段是作者这件事是**格式事实**，
    不是猜测；官网那批第一段实测 76 种取值，一律走 classify()，判不出就丢。
    """
    out: list[tuple[str, str]] = []
    m = PAREN.search(name or "")
    if m:
        head, _, mat = m.group(1).partition("；")
        if mat.strip():                                # 官网格式的分号后固定是材质
            out.append(("material", mat.strip()))
        parts = [p.strip() for p in head.split("，") if p.strip()]
        for i, seg in enumerate(parts):
            # Wikidata 格式的第一段按格式定义就是作者，只有当它**整段**等于
            # 朝代/产地或是个日期时才改判 —— 所以走 strict，关掉材质的子串规则。
            artist_slot = (i == 0 and not is_official)
            hit = classify(seg, strict=artist_slot)
            if hit:
                out.append(hit)
            elif artist_slot:
                out.append(("artist", seg))
            # 其余判不出的一律丢弃 —— 不猜

    d = desc or ""
    if (m := ACCESSION.search(d)):
        out.append(("accession_number", m.group(1)))
    if (m := ACQUIRE.search(d)):
        out.append(("acquisition", m.group(1).strip()))
    if (m := HIGHLIGHT.search(d)):
        out.append(("museum_highlight", m.group(1)))
    # 同一个键抽到多个值时只留第一个（如两段都判成 date_absolute）
    seen, uniq = set(), []
    for k, v in out:
        if k not in seen:
            seen.add(k); uniq.append((k, v))
    return uniq


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-seq", type=int, help="只处理这一件，用于逐件核对")
    args = ap.parse_args()

    conn = M.connect()
    cur = conn.cursor()

    where = "AND a.source_seq = %s" if args.only_seq else ""
    params = [MUSEUM] + ([args.only_seq] if args.only_seq else [])
    cur.execute(f"""
        -- ⚠ 名称取 a.name_key（源数据原值），**不要取 content_text 的展示名**。
        -- 展示名会被译名表覆盖：2026-09-04 把 seq 4434 的中文名从
        -- 「古帝王图（閻立本，0650-01-01）」改成《历代帝王像》之后，
        -- 括号里的作者与年代就对抽取器不可见了 —— 而那正是要抽的东西。
        -- name_key 是标识符不用于展示，永远保留源数据原值，是唯一可靠的解析输入。
        SELECT a.source_seq, a.name_key, td.text, COALESCE(a.official_url,''),
               COALESCE(g.name_key,'')
        FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        LEFT JOIN gallery g ON g.id = a.gallery_id
        LEFT JOIN content_text td ON td.content_id = a.description_cid AND td.lang='zh-CN'
        WHERE 1=1 {where}
        ORDER BY a.source_seq""", params)
    rows = cur.fetchall()

    for k, (zh, en) in KEYS.items():
        M.ensure_key(cur, k, zh, en)

    # 按 official_url 的域名分流。这一列没参与抽取，拿它分来源是非循环的。
    n_off = n_wd = 0
    payload: dict[str, list] = {"mfa_official": [], "mfa_ext_wikidata": []}
    for seq, name, desc, url, gallery in rows:
        sk = "mfa_official" if "mfa.org" in url else "mfa_ext_wikidata"
        vals = parse(name, desc, sk == "mfa_official")
        if sk == "mfa_official" and gallery:
            vals.append(("gallery_official", gallery))
        if not vals:
            continue
        (n_off := n_off + 1) if sk == "mfa_official" else (n_wd := n_wd + 1)
        payload[sk].append((seq, vals))

    print(f"{MUSEUM}：{len(rows)} 件")
    print(f"  mfa_official     (Tier 1) 抽到 {len(payload['mfa_official'])} 件")
    print(f"  mfa_ext_wikidata (Tier 3) 抽到 {len(payload['mfa_ext_wikidata'])} 件")
    import collections
    hist = collections.Counter(k for v in payload.values() for _, vals in v for k, _ in vals)
    for k, n in hist.most_common():
        print(f"     {k:20s} {n} 条")

    if args.dry_run:
        for sk, items in payload.items():
            for seq, vals in items[:3]:
                print(f"\n  [{sk} seq {seq}]")
                for k, v in vals:
                    print(f"     {k:20s} = {v}")
        conn.rollback()
        print("\n--dry-run：未写库")
        return

    total = 0
    for sk, items in payload.items():
        for seq, vals in items:
            # 只清自己 source_key 的旧值（AGENTS.md 第 7 条：冲突取值并存，不消解）
            cur.execute("DELETE FROM artwork_meta WHERE museum_key=%s AND source_seq=%s"
                        " AND source_key=%s", (MUSEUM, seq, sk))
            for ord_, (k, v) in enumerate(vals):
                cid = M.ensure_value(cur, v, v)     # 值本身多为专名/编号，中英同形
                # evidence_type / source_quality 在**写入时**就按 SOURCE_RULES 填死，
                # 不留给 audit_load.py 事后回填。理由：tier_v3 的 --evidence 会把这
                # 两列拼进提示词，NULL 会渲染成「[?/? · mfa_official]」——
                # 而提示词里花了四行教模型怎么读 FACT/strong 与 INFERENCE，
                # 递过去一个 ?/? 等于把那段说明作废。来源等级是 source_key 的函数，
                # 确定性可知，没有任何理由推迟到审计阶段才填。
                etype, quality = SR.SOURCE_RULES[sk][1], SR.quality_of(SR.SOURCE_RULES[sk][0])
                cur.execute(
                    "INSERT INTO artwork_meta (museum_key, source_seq, key_name,"
                    " source_key, ord, value_cid, source, confidence,"
                    " evidence_type, source_quality)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (MUSEUM, seq, k, sk, ord_, cid,
                     "MFA 官网展厅/部门页" if sk == "mfa_official"
                     else "MFA 扩充清单 · Wikidata 条目",
                     "high" if sk == "mfa_official" else "medium",
                     etype, quality))
                total += 1
    conn.commit()
    print(f"\n写入 artwork_meta {total} 条")


if __name__ == "__main__":
    main()
