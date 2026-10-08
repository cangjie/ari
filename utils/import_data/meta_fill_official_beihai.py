#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
北海公园：从官网景点介绍原文逐条摘 metadata，写 artwork_meta。零 API。

    python3 meta_fill_official_beihai.py --dry-run   # 逐件列出要写什么，不写库
    python3 meta_fill_official_beihai.py

**为什么是逐条登记而不是正则。** 本馆只有 23 个景点，原文是一两百字的散文，没有任何结构化字段；
数字出现的语境五花八门 —— 承光殿条的「高1.5米」是殿里白玉佛的高度，不是殿的；团城条的年份有
建殿、改名、毁于地震、重建、扩建五个。按模式抽，宁可漏也难免错（AGENTS.md 第 7 条）。
所以这里每一条取值都登记了**它出自哪段原文**（QUOTE），运行时逐条核对原文确实出现（去空白后），
对不上就报错退出，不写库。

    object_id     官网文章 id（detail/<id>，英文站 en/<id>）。每行都写 —— 不写的话有的景点一条来源都没有，
                  evidence_score 的 best_source_tier 就是空，而审计读的正是这一列（伪满皇宫节点踩过的坑）
    date_text     始建、改建年代，取原文整句里的那一段（含「相传」的照录，不替它定真伪）
    period        只有铁影壁：原文只写「元代遗物」，没有纪年
    dimensions    高度、面积、周长、重量，逐字照录
    site_parent   所在景点（团城、琼华岛），与源表「展厅」列同出 beihai_build.ZONE

**中英两站的数字不挑赢家**（AGENTS.md 第 7 条）：团城面积中文站写约 6176 平方米、英文站写 4,500 平方米，
两条都写，ord 区分，出处分别注明中文站、英文站 —— 矛盾留给审计看见，不在这里消解。

取值的英文（中文原文的那一侧）与中文（英文站原文的那一侧）是本脚本登记时的翻译，入库分别标「AI翻译」。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

import beihai_build as B
import meta_lib as M
import source_rules as SR

MUSEUM = "beihai"
OWN_KEYS = ("beihai_official",)          # 本脚本写的 source_key，重跑先整体清掉
SK = "beihai_official"
SRC_ZH_SITE = "北海公园官网中文站景点介绍"
SRC_EN_SITE = "北海公园官网英文站景点介绍"

# 原文出自哪一条：None = 本条；否则是那一条的身份键（beihai_build 的 key）
TUANCHENG = "zh:a5a1a9ebfd9c4a1a8c4f0c28068e70a3"
JADE_ISLET = "en:a99c01c264474b00a041a438926959c7"

# 身份键 -> [(键, 取值, 原文出处, 原文是中文站还是英文站, 出自哪一条)]
# 取值是 (中文, 英文)。原文在中文站时中文就是原文；在英文站时英文是原文、中文是登记时的翻译
Z, E = "zh", "en"
META: dict[str, list[tuple]] = {
    "zh:e19c2fef4cca4b41895e7c89d17c3cdf": [   # 漪澜堂
        ("date_text", ("肇建于乾隆十六年（公元1751年）", "First built in 1751 (16th year of the Qianlong reign)"),
         "漪澜堂景区肇建于乾隆十六年（公元1751年）", Z, None),
        ("dimensions", ("占地总面积1.2公顷，陆地面积1公顷，总建筑面积为3900余平方米",
                        "Site area 1.2 ha (land 1 ha); total floor area over 3,900 m²"),
         "占地总面积1.2公顷，陆地面积1公顷，总建筑面积为 3900余平方米", Z, None),
    ],
    "zh:2caa452e24d44f1b9edbe5d8d4b7e207": [   # 静心斋
        ("date_text", ("始建于清乾隆二十一年（1756年），乾隆二十三年（1758年）竣工",
                       "Begun in 1756 and completed in 1758 (21st–23rd years of the Qianlong reign)"),
         "始建于清乾隆二十一年（1756年），乾隆二十三年（1758年）竣工", Z, None),
        ("dimensions", ("占地面积9308平方米", "Site area 9,308 m²"), "占地面积9308平方米", Z, None),
    ],
    "zh:57ec180c97c844fba0ebbd17de5cacdf": [   # 琼岛春阴碑
        ("date_text", ("清代乾隆十六年（1751年）立", "Erected in 1751 (16th year of the Qianlong reign)"),
         "琼岛春阴碑于清代乾隆十六年（ 1751年）立于琼华岛东坡", Z, None),
    ],
    "zh:9C8802BA1A4249818ED0A95DDA5653FD": [   # 遮荫候
        ("date_text", ("相传为金代所植，至今已有八百多年",
                       "Said to have been planted in the Jin dynasty, over 800 years ago"),
         "相传为金代所植，至今已有八百多年", Z, None),
        ("dimensions", ("树高10余米", "Tree height over 10 m"), "树高10余米", Z, None),
    ],
    "zh:a1a20493b83b4ff28793958fdd8aa39f": [   # 玉瓮
        ("date_text", ("制作于至元二年（1265年）", "Made in 1265 (2nd year of the Zhiyuan reign, Yuan dynasty)"),
         "制作于至元二年（1265年）", Z, None),
        ("dimensions", ("通高70公分，周长493公分，重约1053-1178公斤",
                        "Overall H 70 cm; circumference 493 cm; weight approx. 1,053–1,178 kg"),
         "通高70公分，周长493公分，重约1053-1178公斤", Z, None),
    ],
    "zh:0a5cc638e98f4f93834b69aaf9160234": [   # 白袍将军
        ("date_text", ("相传植于金代", "Said to have been planted in the Jin dynasty"), "相传植于金代", Z, None),
    ],
    "zh:a5a1a9ebfd9c4a1a8c4f0c28068e70a3": [   # 团城
        ("date_text", ("至元元年（1264年）在其上建仪天殿", "1264: Yitian Hall built on the islet (Yuan dynasty)"),
         "至元元年（1264年）在其上建仪天殿", Z, None),
        ("date_text", ("乾隆十一年（1746年）扩建，成此规模", "1746: expanded to its present extent"),
         "乾隆十一年（1746年）扩建，成此规模", Z, None),
        ("dimensions", ("城高4.6米，面积约6176平方米，周长276米",
                        "Wall height 4.6 m; area approx. 6,176 m²; perimeter 276 m"),
         "城高4.6米，面积约6176平方米，周长276米", Z, None),
        ("dimensions", ("面积4500平方米，城墙高4.6米、长276米", "Area 4,500 m²; city wall 4.6 m high and 276 m long"),
         "The Round City occupies an area of 4,500 square meters, surrounded by a 4.6-meter high and "
         "276-meter long city wall", E, None),
    ],
    "zh:d382dab53c1442f49c5299e2f03442ff": [   # 阅古楼
        ("date_text", ("清乾隆十八年（1753年）为保存《三希堂法帖》石刻而建",
                       "Built in 1753 (18th year of the Qianlong reign) to house the stone carvings of the "
                       "Sanxitang model calligraphy"),
         "清乾隆十八年（1753年）为保存《三希堂法帖》石刻而建", Z, None),
    ],
    "zh:e61f3858b4654c42948bee513d1f733f": [   # 永安寺
        ("date_text", ("始建于清顺治八年（1651年）", "First built in 1651 (8th year of the Shunzhi reign)"),
         "始建于清顺治八年（1651年）", Z, None),
    ],
    "zh:4d8a6c27a86d4746948af8b1f85e18e8": [   # 先蚕坛
        ("date_text", ("清乾隆七年（1742年），建“先蚕坛”", "Built in 1742 (7th year of the Qianlong reign)"),
         "清乾隆七年（1742年），建“先蚕坛”", Z, None),
        ("dimensions", ("总占地面积17000平方米", "Total site area 17,000 m²"), "总占地面积 17000平方米", Z, None),
    ],
    "zh:d9d392e933884262bff657fca64602a6": [   # 画舫斋
        ("date_text", ("建于清乾隆二十二年（公元1757年）", "Built in 1757 (22nd year of the Qianlong reign)"),
         "建于清乾隆二十二年（公元1757年）", Z, None),
    ],
    "zh:1eec059c1d0d46d5848c836684de754f": [   # 濠濮间
        ("date_text", ("于乾隆二十二年(1757年)增建而成", "Added in 1757 (22nd year of the Qianlong reign)"),
         "于乾隆二十二年(1757年)增建而成", Z, None),
        ("dimensions", ("占地面积4416平方米，建筑面积350.12平方米", "Site area 4,416 m²; floor area 350.12 m²"),
         "占地面积4416平方米，建筑面积350.12平方米", Z, None),
    ],
    "zh:e5a54b29853949c8b919f2eb2a29337a": [   # 五龙亭
        ("date_text", ("建于明嘉靖朝（1522-1566年）", "Built in the Jiajing reign of the Ming dynasty (1522–1566)"),
         "建于明嘉靖朝（1522-1566年）", Z, None),
    ],
    "zh:3d515bb55280465c9bf0b6bb0f6bbb5b": [   # 西天梵境
        ("date_text", ("清乾隆十八年（1753年）至二十四年（1759年）改建",
                       "Rebuilt 1753–1759 (18th–24th years of the Qianlong reign)"),
         "经过清乾隆十八年（1753年）至二十四年（1759年）的改建", Z, None),
    ],
    "zh:88c99c368b504ecc9835a745fd168d25": [   # 快雪堂书法博物馆
        ("date_text", ("澄观堂、浴兰轩建于清乾隆十一年（1746年）",
                       "Chengguan Hall and Yulan Pavilion built in 1746 (11th year of the Qianlong reign)"),
         "澄观堂、浴兰轩建于清乾隆十一年（1746年）", Z, None),
        ("date_text", ("乾隆四十四年（1779年）增建快雪堂院落",
                       "1779: Kuaixue Hall courtyard added to house 48 calligraphy stone carvings"),
         "乾隆四十四年（1779年），乾隆皇帝为收藏48方书法石刻，特增建快雪堂院落", Z, None),
    ],
    "zh:0f640d0a13234781be93c9aa2797852a": [   # 九龙壁
        ("date_text", ("建于乾隆二十一年（1756年）", "Built in 1756 (21st year of the Qianlong reign)"),
         "建于乾隆二十一年（1756年）", Z, None),
        ("dimensions", ("壁高5.96米，厚1.60米，长25.52米", "H 5.96 m; thickness 1.60 m; L 25.52 m"),
         "壁高5.96米，厚1.60米，长25.52米", Z, None),
    ],
    "zh:845f0705cde44c51a0afe1fd2d2f5566": [   # 铜仙承露盘
        ("dimensions", ("通高6.6米", "Overall H 6.6 m"), "通高6.6米", Z, None),
    ],
    "zh:51faaa2e109843ef86d85ea8e47ecd5d": [   # 铁影壁
        ("period", ("元代", "Yuan dynasty"), "元代遗物", Z, None),
    ],
    "zh:26b8aa802284431c82905aed52581a75": [   # 小西天
        ("date_text", ("始建于清乾隆三十三年（公元1768年），建成于清乾隆三十五年（公元1770年）",
                       "Begun in 1768 and completed in 1770 (33rd–35th years of the Qianlong reign)"),
         "始建于清乾隆三十三年（公元1768 年），建成于清乾隆三十五年（公元1770 年）", Z, None),
        ("dimensions", ("占地1200平方米，横梁13.5米", "Area 1,200 m²; 13.5 m transverse beam"),
         "covering an area of 1,200 square meters with a 13.5-meter transverse beam", E, None),
    ],
    "zh:8d8a18c6964743309fd6688a83af3a04": [   # 智珠殿
        ("date_text", ("建于乾隆十六年（1751年）", "Built in 1751 (16th year of the Qianlong reign)"),
         "建于乾隆十六年（1751年）", Z, None),
    ],
    "en:1d7c20bd4abc4595aa285bb303b1d97a": [   # 白塔
        ("date_text", ("1651年建", "Built in 1651"), "Built in 1651", E, None),
        ("dimensions", ("高35.90米", "H 35.90 m"), "this 35.90-meter-tall dagoba", E, None),
    ],
}
PARENT_EN = {"团城": "Round City", "琼华岛": "Jade Islet"}


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def collect() -> list[tuple]:
    """-> [(seq, 名称, 键, (中文, 英文), 原文是哪站, 出处说明, confidence)]"""

    class Q:
        def say(self, *a):
            pass

    d = B.load()
    rows = B.build_rows(d, Q())
    B.assign_seq(rows, write=False, r=Q())
    by_key = {x["key"]: x for x in rows}
    unknown = set(META) - set(by_key)
    if unknown:
        sys.exit(f"[fatal] META 登记了源表里没有的身份键：{sorted(unknown)}")

    def text_of(key: str, lang: str) -> str:
        x = by_key[key]
        return x["desc"] if lang == Z else x["desc_en"]

    out = []
    for x in rows:
        name = x["name"] or x["name_en"]
        oid = x["oid"]
        out.append((x["seq"], name, "object_id", (oid, oid), Z, f"{SRC_ZH_SITE if x['key'].startswith('zh:') else SRC_EN_SITE}（官网 ID）", "high"))
        if x["hall"]:
            zone = B.ZONE[x["key"][3:] if x["key"].startswith("zh:") else x["key"]]
            out.append((x["seq"], name, "site_parent", (x["hall"], PARENT_EN[x["hall"]]),
                        E if zone[2].startswith("英文站") else Z,
                        f"{SRC_EN_SITE if zone[2].startswith('英文站') else SRC_ZH_SITE}（所在景点，据{zone[2]}原文）",
                        "high"))
        for key, (zh, en), quote, lang, frm in META.get(x["key"], []):
            src_key = frm or x["key"]
            if _flat(quote) not in _flat(text_of(src_key, lang)):
                sys.exit(f"[fatal] seq {x['seq']} {name} 的 {key} 原文对不上：{quote!r} 不在"
                         f"{'英文站' if lang == E else '中文站'}{'本条' if frm is None else frm}里")
            site = SRC_EN_SITE if lang == E else SRC_ZH_SITE
            label = {"date_text": "年代", "dimensions": "尺寸", "period": "年代"}[key]
            out.append((x["seq"], name, key, (zh, en), lang, f"{site}（{label}）", "high" if lang == Z else "medium"))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="逐件列出，不写库")
    args = ap.parse_args()

    if SK not in SR.SOURCE_RULES:
        sys.exit(f"[fatal] source_key {SK!r} 没在 source_rules.SOURCE_RULES 登记")
    out = collect()
    cur_seq = None
    for seq, name, key, (zh, en), lang, src, conf in sorted(out, key=lambda x: (x[0], x[2])):
        if seq != cur_seq:
            print(f"\n{seq:>4} {name}")
            cur_seq = seq
        print(f"       {key:12} {zh}  |  {en}   [{src} · {conf}]")
    print(f"\n合计 {len(out)} 条，覆盖 {len({x[0] for x in out})} 件；按键 {dict(Counter(x[2] for x in out))}")
    if args.dry_run:
        print("--dry-run：未写库")
        return
    write(out)


def write(out) -> None:
    """批量写入，一个事务（同 meta_fill_official_jlpm.write：逐条写跨公网会留残留事务）。"""
    ords: Counter = Counter()
    flat = []
    for seq, name, key, (zh, en), lang, src, conf in out:
        flat.append((seq, key, ords[(seq, key)], zh, en, lang, src, conf))
        ords[(seq, key)] += 1
    # 取值去重按 (中文, 英文, 哪一侧是原文)：同一对文字若一处是中文原文、一处是英文原文，来源标注不同
    vals = {(zh, en, lang) for _s, _k, _o, zh, en, lang, _src, _c in flat}

    conn = M.connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM artwork a JOIN museum m ON m.id = a.museum_id"
                    " WHERE m.key_name = %s", (MUSEUM,))
        if cur.fetchone()[0] != 23:
            sys.exit("[fatal] 库里 beihai 的景点不是 23 个，先跑 import_artworks.py")
        cur.execute("SELECT COUNT(*) FROM meta_key WHERE key_name IN ('object_id','site_parent','date_text',"
                    "'dimensions','period')")
        if cur.fetchone()[0] != 5:
            sys.exit("[fatal] meta_key 里缺键（object_id / site_parent / date_text / dimensions / period）")
        cur.execute("""SELECT z.text, e.text, z.source, e.source, z.content_id FROM content_text z
                         JOIN content c ON c.id = z.content_id AND c.kind = %s
                         JOIN content_text e ON e.content_id = z.content_id AND e.lang = 'en'
                        WHERE z.lang = 'zh-CN'""", (M.KIND_VALUE,))
        have = {}
        for z, e, zs, es, cid in cur.fetchall():
            lang = Z if zs == "原始" else E if es == "原始" else None
            if lang:
                have.setdefault((z, e, lang), cid)
        cid_of = {v: have[v] for v in vals if v in have}
        todo = sorted(vals - set(cid_of))
        if todo:
            cur.execute("SELECT COALESCE(MAX(id), %s) FROM content WHERE id >= %s",
                        (M.CONTENT_ID_BASE, M.CONTENT_ID_BASE))
            nxt = cur.fetchone()[0] + 1
            crows, trows = [], []
            for i, (zh, en, lang) in enumerate(todo):
                cid_of[(zh, en, lang)] = nxt + i
                crows.append((nxt + i, M.KIND_VALUE))
                trows += [(nxt + i, "zh-CN", zh, "原始" if lang == Z else "AI翻译"),
                          (nxt + i, "en", en, "原始" if lang == E else "AI翻译")]
            cur.executemany("INSERT INTO content (id, kind) VALUES (%s,%s)", crows)
            cur.executemany("INSERT INTO content_text (content_id, lang, text, source)"
                            " VALUES (%s,%s,%s,%s)", trows)
        cur.execute("DELETE FROM artwork_meta WHERE museum_key = %s AND source_key = %s", (MUSEUM, SK))
        cleared = cur.rowcount
        tier, etype, _ = SR.SOURCE_RULES[SK]
        rows = [(MUSEUM, seq, key, SK, o, cid_of[(zh, en, lang)], src, conf, "rule", etype, SR.quality_of(tier))
                for seq, key, o, zh, en, lang, src, conf in flat]
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
          f"取值 {len(vals)} 个（新建 {len(todo)}）")


if __name__ == "__main__":
    main()
