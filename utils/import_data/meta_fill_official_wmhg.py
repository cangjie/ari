#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
伪满皇宫博物院：从馆方中文原文确定性抽 metadata，写 artwork_meta。零 API。

    python3 meta_fill_official_wmhg.py --dry-run   # 逐件列出要写什么，不写库
    python3 meta_fill_official_wmhg.py

**为什么不用 meta_fill_rule.py。** 2026-09-24 对本馆 22 件（中英名都有的）试跑，
一半以上会写错：作者抽出「Yesterday」「People」「Kant」「Manchuria」；纪年取「文中最早的年份」，
《寒林群鸦图》得 1793（渡边华山生年）、昭和三年的银杯得 1926（昭和元年）；
文化归属见「Japanese」就判日本，伪满纪念章的英文简介写的是「Japanese aggressors」。
它解析的是**英文**，而本馆英文是馆方机翻；它的规则是为 PEM/MFA 的英文编目写的。

所以这里只从**中文题名、官网类目、简介里带单位的尺寸片段**取，每个字段的规则都能在原文里
逐字指认。宁可漏，不可错（AGENTS.md 第 7 条）：
    object_form       官网类目（瓷器、日本画……），只给官网藏品
    artist            日本画题名「作者《题名》」里《之前的部分，只在日本画类目里用
    polity            题名以「伪满」开头 -> 伪满洲国
    cultural_context  题名以「日本」开头，或类目是日本画 -> 日本
    date_text         题名里的年号（昭和三年 -> 1928）；文章 3263 每件的年代行
    dimensions        简介里「高/口径/直径… 数字 厘米」片段，逐字；含「原本/原来/原为」的句子整句不取 ——
                      景仁宫御用地毯写的是「原本长250厘米，宽145厘米，厚2厘米」，后来被裁成了多块
    gallery_official  文章 3263 写明的展出地点「怀远楼二楼清宴堂」（4 件 + 与 478 同一件的凤纹瓶）

节点只写 object_form（对象层级），来源随节点出处，见 NODE_SRC。行与序号取自 wmhg_build.build_rows / assign_seq，
与源 Excel、wmhg_seq_map.csv 同出一处。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

import meta_lib as M
import source_rules as SR
import wmhg_article_data as art
import wmhg_build as B

MUSEUM = "wmhg"
OWN_KEYS = ("wmhg_official", "wmhg_article", "wmhg_guide_2023")   # 本脚本写的 source_key，重跑先整体清掉

# 固定词汇的确定性英译。人名、地名不在这里：没有可靠英文就留中文，导出的 CJK 扫描会捞出来
CAT_EN = {"瓷器": "Porcelain", "日本画": "Japanese painting", "纪念章": "Commemorative medal",
          "宫廷文物": "Court relic", "铜镜": "Bronze mirror", "画报": "Pictorial magazine"}
POLITY = ("伪满洲国", "Manchukuo")
JAPAN = ("日本", "Japanese")                     # 与 meta_fill_rule 已写入库的取值同形，便于去重

ERA = {"明治": (1867, "Meiji"), "大正": (1911, "Taishō"), "昭和": (1925, "Shōwa"),
       "大同": (1931, "Datong"), "康德": (1933, "Kangde")}
CN_NUM = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
ERA_RE = re.compile(r"(明治|大正|昭和|大同|康德)([元一二三四五六七八九十]{1,3})年")

DIM_LABEL = {"画心纵": "image H", "画心横": "image W", "通纵": "overall H", "通横": "overall W",
             "通高": "overall H", "口径": "mouth D",
             "底径": "base D", "腹径": "belly D", "足径": "foot D", "直径": "D", "缘厚": "rim thickness",
             "高": "H", "长": "L", "宽": "W", "厚": "thickness", "纵": "H", "横": "W"}
# 标签后可带冒号：日本画写成「画心纵：124厘米」「通纵:102.5厘米」（第一版漏了这两件）
DIM_RE = re.compile(r"(画心纵|画心横|通纵|通横|通高|口径|底径|腹径|足径|直径|缘厚|高|长|宽|厚|纵|横)"
                    r"\s*[：:]?\s*(约)?\s*([\d.]+)\s*(厘米|公分|cm|毫米|mm)", re.I)
# 一句里出现这些词，这句的尺寸整句不取。只跳紧挨着的那一段不够：景仁宫御用地毯
# 「原本长250厘米，宽145厘米，厚2厘米」—— 宽与厚同样是裁剪之前的尺寸
DIM_SKIP_CLAUSE = re.compile(r"原本|原来|原为")

YWZ_PLACE = (B.YWZ_PLACE, B.YWZ_PLACE)          # 地名不硬译，英文侧先留中文
# 节点的器型·类别取 wmhg_build 给的「对象层级」。官网常设那 16 个，馆方自己列在
# 「原状复原陈列」页（/permanent.html 的标题）上；不给节点写任何 metadata 的话，
# evidence_score.py 算出的 best_source_tier 全是空 —— 而审计读的正是这一列
NODE_FORM_EN = {"原状陈列": "Period room / preserved palace site", "基本陈列": "Core exhibition",
                "专题陈列": "Thematic exhibition", "展区": "Exhibition area"}
NODE_SRC = {"x:": ("wmhg_official", "伪满皇宫博物院官网常设展览栏目", "high"),
            "t:": ("wmhg_article", f"伪满皇宫博物院官网文章 {B.YWZ_ARTICLE}", "high"),
            "g:": ("wmhg_guide_2023", f"伪满皇宫博物院 2023 年官方导览 {B.GUIDE_ARTICLE}", "medium")}
DATE_LINE_EN = {"伪满（1932年—1945年）": "Manchukuo period (1932–1945)",
                "日本昭和（1926年—1989年）": "Shōwa period, Japan (1926–1989)"}


def _cn_int(s: str) -> int:
    """一到九十九的中文数字。年号年份用不到更大的数。"""
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return CN_NUM.get(a, 1) * 10 + CN_NUM.get(b, 0)
    return CN_NUM[s]


def era_date(name: str):
    m = ERA_RE.search(name)
    if not m:
        return None
    base, en = ERA[m.group(1)]
    n = _cn_int(m.group(2))
    return m.group(0), f"{en} {n} ({base + n})"


def dims(text: str):
    """简介里的尺寸片段 -> (中文逐字，英文)。含「原本/原来/原为」的句子整句不取。"""
    zh, en = [], []
    for clause in re.split(r"[。；！？\n]", text or ""):
        if DIM_SKIP_CLAUSE.search(clause):
            continue
        for m in DIM_RE.finditer(clause):
            unit = "mm" if m.group(4).lower() in ("毫米", "mm") else "cm"
            zh.append(re.sub(r"\s+", "", m.group(0)))
            en.append(f"{DIM_LABEL[m.group(1)]} {'approx. ' if m.group(2) else ''}{m.group(3)} {unit}")
    if not zh:
        return None
    return "，".join(zh), "; ".join(en)


def date_line(block: str):
    """文章 3263 每件的年代行：块的第一行，截到第一个尺寸标签之前。"""
    first = block.split("\n")[0]
    head = re.split(r"(?=口径|底径|通高|高\s*[\d.])", first)[0].strip()
    if not head:
        return None
    if m := re.fullmatch(r"(\d{4})年", head):
        return head, m.group(1)
    return head, DATE_LINE_EN.get(head, head)


class _Quiet:
    def say(self, *a):
        pass


def collect() -> list[tuple[int, str, str, tuple[str, str], str, str, str]]:
    """-> [(seq, 名称, key, (中文值, 英文值), source_key, 出处说明, confidence)]"""
    rows = B.build_rows(_Quiet())
    B.assign_seq(rows, write=False, r=_Quiet())
    ywz = {it["name"]: it for it in B.ywz_items()}
    out = []

    def add(row, key, val, sk, src, conf="high"):
        if val:
            out.append((row["seq"], row["name"] or row["name_en"], key, val, sk, src, conf))

    for row in rows:
        if row["level"] != "藏品":
            sk, src, conf = NODE_SRC[row["key"][:2]]
            add(row, "object_form", (row["level"], NODE_FORM_EN[row["level"]]), sk,
                src + "（对象层级）", conf)
            continue
        k, name, cat = row["key"], row["name"], row["cat"]
        official = k.startswith(("c:", "en:"))
        sk = "wmhg_official" if official else "wmhg_article"
        src = "伪满皇宫博物院官网藏品栏目" if official else f"伪满皇宫博物院官网文章 {B.YWZ_ARTICLE}"
        if official:
            add(row, "object_form", (cat, CAT_EN[cat]), sk, src + "（类目）")
        if cat == "日本画" and (m := re.match(r"^(.+?)\s*《", name)):
            add(row, "artist", (m.group(1), m.group(1)), sk, src + "（题名）")
        if name.startswith("伪满"):
            add(row, "polity", POLITY, sk, src + "（题名）")
        if name.startswith("日本") or cat == "日本画":
            add(row, "cultural_context", JAPAN, sk, src + ("（类目）" if cat == "日本画" else "（题名）"))
        add(row, "date_text", era_date(name), sk, src + "（题名年号）")
        if official:
            add(row, "dimensions", dims(row["desc"]), sk, src + "（简介）", "medium")
        else:
            add(row, "date_text", date_line(row["desc"]), sk, src + "（年代行）")
            add(row, "dimensions", dims(row["desc"]), sk, src + "（尺寸行）")
            add(row, "gallery_official", YWZ_PLACE, sk, src + "（展览信息）")

    # 与官网 478 是同一件的凤纹瓶（用户 2026-09-24 确认）：文章给的年代、尺寸、展出地点
    # 记在 478 名下、source_key=wmhg_article，与官网那套并存，不挑赢家（AGENTS.md 第 7 条）
    by_key = {row["key"]: row for row in rows}
    for art_name, cid in B.YWZ_SAME_AS.items():
        row, block = by_key[f"c:{cid}"], ywz[art_name]["desc"]
        src = f"伪满皇宫博物院官网文章 {B.YWZ_ARTICLE}"
        add(row, "date_text", date_line(block), "wmhg_article", src + "（年代行）")
        add(row, "dimensions", dims(block), "wmhg_article", src + "（尺寸行）")
        add(row, "gallery_official", YWZ_PLACE, "wmhg_article", src + "（展览信息）")
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="逐件列出，不写库")
    args = ap.parse_args()

    out = collect()
    for sk in {x[4] for x in out}:
        if sk not in SR.SOURCE_RULES:
            sys.exit(f"[fatal] source_key {sk!r} 没在 source_rules.SOURCE_RULES 登记")
    cur_seq = None
    for seq, name, key, (zh, en), sk, src, conf in sorted(out, key=lambda x: (x[0], x[2])):
        if seq != cur_seq:
            print(f"\n{seq:>3} {name}")
            cur_seq = seq
        print(f"      {key:17} {zh}  |  {en}   [{sk} · {conf}]")
    print(f"\n合计 {len(out)} 条，覆盖 {len({x[0] for x in out})} 件；按键 {dict(Counter(x[2] for x in out))}")
    if args.dry_run:
        print("--dry-run：未写库")
        return

    write(out)


def write(out) -> None:
    """批量写入，总共十来次往返，一个事务。

    **不用 meta_lib.set_meta 逐条写。** 2026-09-24 第一版逐条写：108 条要跨公网来回几百次，
    途中网络一抖客户端就断（2013 Lost connection），而服务器那头的会话不知道，挂着一个
    未提交的事务、锁着 174 行睡到 wait_timeout（8 小时）—— 紧接着的第二次运行卡在等锁
    （1205）。办法同 meta_fill_official_mfa.py：往返次数压到最少，事务短，失败整体回滚。
    """
    # 同一件、同一个键、同一来源的多个取值按出现顺序给 ord
    ords: Counter = Counter()
    flat = []                       # (seq, key, sk, ord, zh, en, src, conf)
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
            sys.exit("[fatal] 库里还没有 wmhg 的展品，先跑 import_artworks.py")
        # ① 已存在的取值（按中英整体去重，同 meta_lib.ensure_value）
        cur.execute("""SELECT z.text, e.text, z.content_id FROM content_text z
                         JOIN content c ON c.id = z.content_id AND c.kind = %s
                         JOIN content_text e ON e.content_id = z.content_id AND e.lang = 'en'
                        WHERE z.lang = 'zh-CN'""", (M.KIND_VALUE,))
        have = {(z, e): cid for z, e, cid in cur.fetchall()}
        cid_of = {p: have[p] for p in pairs if p in have}
        todo = sorted(pairs - set(cid_of))
        # ② 新值本地分配 ID 后批量插（metadata 段 2,000,000 起，AGENTS.md 第 3 条）
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
        # ③ 只清本脚本名下的 source_key，别的来源原样保留（AGENTS.md 第 7 条）
        ph = ",".join(["%s"] * len(OWN_KEYS))
        cur.execute(f"DELETE FROM artwork_meta WHERE museum_key = %s AND source_key IN ({ph})",
                    (MUSEUM, *OWN_KEYS))
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
