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
import csv
import pathlib
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

# 入藏方式：**按分句取整段**，不要用非贪婪正则从句中任意位置起截。
# 早先写的是 `([^。；，]{2,40}?(?:基金|捐赠|购藏|遗赠|捐出))`，最短匹配会把句子
# 拦腰砍断，实测截出「MFA 创始理事、首任馆长 Martin Brimmer 于」
# 「捐赠者 William Sturgis Bigelow 一人」「器收藏的核心来自…」这类碎片 ——
# 而这些碎片会带着 FACT 标记进库、喂进评分。整句取才是完整的事实陈述。
ACQUIRE_WORDS = ("基金", "捐赠", "购藏", "遗赠", "捐出")
CLAUSE_SEP = re.compile(r"[。；，\n]")

# 馆方自己的重点标注。**只认原文写死的这几种说法**，不做语义判断 ——
# 一旦开始「理解」它有多重要，这一列就从事实变成了推断。
# 「镇馆」要写全「镇馆之宝」：光一个「镇馆」会匹配到词的一半（实测中过一次）。
HIGHLIGHT = re.compile(r"(该展厅的核心展品|展厅核心展品|镇馆之宝|代表作)")


def acquisition_of(desc: str) -> str | None:
    """取包含入藏关键词的**完整分句**。太长（>40 字）说明切错了，宁可不要。"""
    for c in CLAUSE_SEP.split(desc or ""):
        c = c.strip()
        if 2 <= len(c) <= 40 and any(w in c for w in ACQUIRE_WORDS):
            return c
    return None


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
    if (a := acquisition_of(d)):
        out.append(("acquisition", a))
    if (m := HIGHLIGHT.search(d)):
        out.append(("museum_highlight", m.group(1)))
    # 同一个键抽到多个值时只留第一个（如两段都判成 date_absolute）
    seen, uniq = set(), []
    for k, v in out:
        if k not in seen:
            seen.add(k); uniq.append((k, v))
    return uniq


TRANS_CSV = "translations_mfa_ext.csv"

# 抽出来的值哪些需要英译。accession_number 是编号，中英同形，不进译名表。
NO_TRANSLATE = {"accession_number"}


def has_cjk(s: str) -> bool:
    return any("㐀" <= c <= "鿿" for c in s or "")


def read_trans_rows(path: pathlib.Path) -> dict[str, dict]:
    """读 translations_mfa_ext.csv -> {中文: 整行}。缺文件不报错，只是没有译文。"""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        rows = [ln for ln in f if not ln.lstrip().startswith("#")]
    return {zh: r for r in csv.DictReader(rows)
            if (zh := (r.get("zh") or "").strip())}


def load_trans(path: pathlib.Path) -> dict[str, str]:
    """{中文: 英文}。**标了「存疑」的不算数** —— 那是模型说「我认不出这是谁」，
    它把中文原样退了回来。当成译文用，就等于把一个没译的值伪装成译好的。
    """
    out = {}
    for zh, r in read_trans_rows(path).items():
        en = (r.get("en") or "").strip()
        if en and en != zh and (r.get("confidence") or "").strip() != "存疑":
            out[zh] = en
    return out


def bilingual(k: str, v: str, trans: dict[str, str]) -> tuple[str, str]:
    """把抽出的中文值配上英文。

    三种情况：
      · 键在 NO_TRANSLATE 里（编号）或值本身不含中文（`1891`、`Joseph Lindon Smith`）
        —— 中英同形，直接用原值；
      · 译名表里有 —— 用译名；
      · 译名表里没有 —— **退回中文并让调用方统计**，不猜、不音译。
        英文导出的 CJK 扫描会把这些捞出来，那正是我们要的信号。
    """
    if k in NO_TRANSLATE or not has_cjk(v):
        return (v, v)
    return (v, trans.get(v, v))


def dump_values(rows, path: pathlib.Path) -> None:
    """把所有含中文的去重取值写成译名表骨架（en 留空待译）。

    **已有的 en 与 confidence 原样保留** —— 重跑不能冲掉人工校对过的结果，
    尤其不能把「存疑」改写成「官方」（2026-09-05 就这么把 7 条标记冲掉过一次：
    模型认不出而退回中文的行，被当成「已译好」重新写成了官方）。
    """
    have = read_trans_rows(path)
    need: dict[str, set] = {}
    for seq, name, desc, url, gallery in rows:
        vals = parse(name, desc, "mfa.org" in url)
        if "mfa.org" in url and gallery:
            vals.append(("gallery_official", gallery))
        for k, v in vals:
            if k not in NO_TRANSLATE and has_cjk(v):
                need.setdefault(v, set()).add(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("# mfa_boston_ext 的 metadata 取值译名表\n"
                "# kind 固定 meta_value_text；key 与 zh 都是抽出来的中文原值\n"
                "# confidence：官方=通行既定译名 / AI=机器翻译 / 存疑=拿不准，优先人工复核\n"
                "# **人名一栏是回译不是翻译**：拿不准就留中文并标存疑，\n"
                "#   造一个不存在的拼写（沙金 -> Shajin）比留着中文更糟。\n")
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["kind", "key", "zh", "en", "confidence", "used_by"])
        for v in sorted(need):
            old = have.get(v) or {}
            w.writerow(["meta_value_text", v, v,
                        (old.get("en") or "").strip(),
                        (old.get("confidence") or "").strip(),
                        "|".join(sorted(need[v]))])
    n_todo = sum(1 for v in need if not (have.get(v, {}).get("en") or "").strip())
    n_doubt = sum(1 for v in need
                  if (have.get(v, {}).get("confidence") or "").strip() == "存疑")
    print(f"{path}：{len(need)} 个含中文的去重取值，其中 {n_todo} 个待译"
          + (f"、{n_doubt} 个标了存疑（模型认不出，已退回中文）" if n_doubt else ""))


SYS_PERSON = """把博物馆编目里的**人名**从中文还原成通行的原文拼写。

**这是回译，不是翻译。** 这些中文多是西方艺术家姓名的音译
（「约翰·辛格·沙金」= John Singer Sargent、「阿尔布雷希特·丢勒」= Albrecht Dürer），
也有中日韩本名（「閻立本」= Yan Liben、「立石春美」= Tateishi Harumi）。

规则，按优先级：
1. 认得出是哪位艺术家 —— 给**该艺术家通行的原文姓名**，连同变音符号
   （Dürer、Renoir、Miró）。confidence 填 official。
2. 中日韩人名而无通行罗马化 —— 按规范罗马化（中文汉语拼音、日文训读/音读、
   韩文罗马字），confidence 填 AI。
3. **认不出、或拿不准是哪一位 —— 原样返回那段中文**，confidence 填 doubt。

**第 3 条是硬要求。** 绝不要按字音硬拼（「沙金」→ Shajin）造出一个不存在的名字：
错的拼写会被当成事实写进库、喂进评分；留着中文只是导出时缺一条英文，
而且会被 CJK 扫描捞出来交给人工。**编一个名字比承认不知道糟得多。**"""

SYS_TERM = """把博物馆编目字段从中文译成英文。这是藏品编目数据，不是文案。

- 材质按文物术语译：「泡桐木、彩绘与贴金」→ Paulownia wood with polychromy and gilding；
  「绢本设色」→ ink and color on silk
- 年代按英文习惯：「12 世纪初」→ early 12th century；「公元前 883–859 年」→ 883–859 BCE
- 朝代/政权用通行英文名：「北宋」→ Northern Song dynasty；「金」→ Jin dynasty
- 产地用通行国名/地区名：「中国」→ China
- 入藏方式保留基金或捐赠人原名：「Hervey Edward Wetzel 基金」→ Hervey Edward Wetzel Fund
- 展厅名保留其中已有的英文原文，只译中文部分

**不要增补原文没有的信息，不要解释。** 拿不准就原样返回中文并把 confidence 填 doubt。

**每条都标了它属于哪个字段，必须照字段义翻。** 同一个中文在不同字段下英文完全不同：
  「金」在 polity 下是 Jin dynasty，在 material 下才是 gold
  「朝鲜」在 polity 下是 Joseon dynasty，在 origin_place 下是 Korea
2026-09-05 就因为没把字段名传给模型，把 polity 的「金」译成了 gold。"""

TRANS_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"zh": {"type": "string"}, "en": {"type": "string"},
                       "confidence": {"type": "string",
                                      "enum": ["official", "AI", "doubt"]}},
        "required": ["zh", "en", "confidence"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}

CONF_ZH = {"official": "官方", "AI": "AI", "doubt": "存疑"}


def translate_csv(path: pathlib.Path, args) -> None:
    """把译名表里 en 为空的行补上。人名与术语分开问，提示词不同。

    **已有译文的行不动** —— 人工校对过的结果不能被重跑冲掉。
    """
    if not path.exists():
        raise SystemExit(f"{path} 不存在，先跑 --dump-values")
    if not args.model:
        raise SystemExit("--translate 需要 --model")
    import audit_meta as A
    client = A.LazyClient(args.key_file)
    effort = A.norm_effort(args.effort)

    with path.open(encoding="utf-8") as f:
        head = [ln for ln in f if ln.lstrip().startswith("#")]
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader([ln for ln in f if not ln.lstrip().startswith("#")]))

    todo = [r for r in rows if not (r.get("en") or "").strip()]
    person = [r for r in todo if "artist" in (r.get("used_by") or "")]
    term = [r for r in todo if r not in person]
    print(f"待译 {len(todo)} 条：人名 {len(person)}、术语 {len(term)}")

    got: dict[str, tuple[str, str]] = {}
    for label, group, system, size in (("人名", person, SYS_PERSON, 60),
                                       ("术语", term, SYS_TERM, 60)):
        for i in range(0, len(group), size):
            chunk = group[i:i + size]
            # 带上字段名 —— 同一个中文在不同字段下英文不同（金：polity=Jin dynasty
            # / material=gold）。返回时只按 zh 对齐，所以这批里不能有重复的 zh。
            user = (f"请逐条给出英文，共 {len(chunk)} 条。"
                    f"格式为「字段名｜中文」：\n"
                    + "\n".join(f"- {r.get('used_by') or '?'}｜{r['zh']}" for r in chunk))
            data = A.ask(client, args.model, system, user, "mfa_ext_trans",
                         TRANS_SCHEMA, effort, museum_key=MUSEUM,
                         scope=f"{label} {i + 1}-{i + len(chunk)}")
            for d in data["items"]:
                got[d["zh"]] = (d["en"], d["confidence"])
            miss = {r["zh"] for r in chunk} - {d["zh"] for d in data["items"]}
            if miss:
                raise SystemExit(f"{label}漏译 {len(miss)} 条，例：{sorted(miss)[:3]}")
            print(f"  {label} {min(i + size, len(group))}/{len(group)}")

    n_doubt = 0
    for r in rows:
        if r["zh"] in got:
            en, conf = got[r["zh"]]
            r["en"], r["confidence"] = en, CONF_ZH.get(conf, "AI")
            if conf == "doubt":
                n_doubt += 1
    with path.open("w", encoding="utf-8", newline="") as f:
        f.writelines(head)
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"\n已写回 {path}：新增 {len(got)} 条译文，其中 {n_doubt} 条标了「存疑」")
    if n_doubt:
        print("   `grep 存疑` 捞出来人工过一遍再写库 —— 存疑的多半是认不出的人名，"
              "它们会按中文写进 en 列并被 CJK 扫描捞出。")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-seq", type=int, help="只处理这一件，用于逐件核对")
    ap.add_argument("--dump-values", action="store_true",
                    help=f"把含中文的去重取值写成 {TRANS_CSV} 骨架（en 待译），不写库")
    ap.add_argument("--translate", action="store_true",
                    help=f"用 LLM 把 {TRANS_CSV} 里 en 为空的行补上，不写库")
    ap.add_argument("--model", default="", help="--translate 用的型号")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--key-file", default="~/.openai_key")
    ap.add_argument("--commit-every", type=int, default=200,
                    help="每写多少件提交一次。跨公网连接，攒批提交比逐件提交快得多")
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

    base = pathlib.Path(__file__).resolve().parent
    csv_path = base / TRANS_CSV

    if args.dump_values:
        dump_values(rows, csv_path)
        conn.rollback()
        return
    if args.translate:
        conn.rollback()
        translate_csv(csv_path, args)
        return

    trans = load_trans(csv_path)
    print(f"译名表 {TRANS_CSV}：{len(trans)} 条")

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

    # ── 批量写入 ────────────────────────────────────────────────────────────
    # **不逐件调 meta_lib.set_meta。** 它每件每键要发 1 次 DELETE + 1 次
    # executemany，而 ensure_value 对每个没见过的取值再查 1 次 —— 4464 件里
    # 3940 个馆藏号个个不同，全是缓存未命中。2026-09-05 实测：跨公网 13 分钟
    # 只写完 200 件，全量要 5 小时。瓶颈是**往返次数**不是数据量。
    #
    # 改成三步，总往返十几次：
    #   ① 一次查回所有已存在的 (zh,en) -> content_id
    #   ② 新值在本地分配 ID 后 executemany 建 content / content_text
    #   ③ 整馆一次 DELETE，再 executemany 写 artwork_meta
    #
    # evidence_type / source_quality 在写入时就按 SOURCE_RULES 填死，不留给审计回填：
    # tier_v3 的 --evidence 会把这两列拼进提示词，NULL 会渲染成「[?/? · xxx]」，
    # 而提示词里教模型怎么读 FACT/strong 的那四行就此作废。

    # 先把全部要写的行摊平，同时收集去重后的 (zh, en)
    flat = []          # (sk, seq, key, ord, zh, en)
    pairs: set[tuple[str, str]] = set()
    untranslated: set[str] = set()
    for sk, items in payload.items():
        for seq, vals in items:
            for ord_, (k, v) in enumerate(vals):
                zh, en = bilingual(k, v, trans)
                if zh == en and has_cjk(zh):
                    untranslated.add(zh)
                flat.append((sk, seq, k, ord_, zh, en))
                pairs.add((zh, en))
    print(f"待写 {len(flat)} 条，去重后 {len(pairs)} 个不同取值")

    # ① 已存在的取值
    cid_of: dict[tuple[str, str], int] = {}
    cur.execute("""SELECT z.text, e.text, z.content_id FROM content_text z
                   JOIN content c ON c.id = z.content_id AND c.kind = %s
                   JOIN content_text e ON e.content_id = z.content_id AND e.lang = 'en'
                   WHERE z.lang = 'zh-CN'""", (M.KIND_VALUE,))
    have = {(z, e): cid for z, e, cid in cur.fetchall()}
    cid_of.update({p: have[p] for p in pairs if p in have})
    todo = sorted(pairs - set(cid_of))
    print(f"  已在库中 {len(cid_of)} 个，需新建 {len(todo)} 个")

    # ② 新值：本地分配 ID 后批量插。ID 段见 AGENTS.md 第 3 条（metadata 段 2,000,000 起）
    if todo:
        cur.execute("SELECT COALESCE(MAX(id), %s) FROM content WHERE id >= %s",
                    (M.CONTENT_ID_BASE, M.CONTENT_ID_BASE))
        nxt = cur.fetchone()[0] + 1
        crows, trows = [], []
        for i, (zh, en) in enumerate(todo):
            cid = nxt + i
            cid_of[(zh, en)] = cid
            crows.append((cid, M.KIND_VALUE))
            trows.append((cid, "zh-CN", zh, M.SRC_ZH))
            trows.append((cid, "en", en, M.SRC_EN))
        cur.executemany("INSERT INTO content (id, kind) VALUES (%s,%s)", crows)
        cur.executemany("INSERT INTO content_text (content_id, lang, text, source)"
                        " VALUES (%s,%s,%s,%s)", trows)

    # ③ 只清本脚本两个 source_key 的旧值，别的来源原样保留（AGENTS.md 第 7 条）
    for sk in payload:
        cur.execute("DELETE FROM artwork_meta WHERE museum_key=%s AND source_key=%s",
                    (MUSEUM, sk))
    meta_rows = []
    for sk, seq, k, ord_, zh, en in flat:
        rule = SR.SOURCE_RULES[sk]
        meta_rows.append((
            MUSEUM, seq, k, sk, ord_, cid_of[(zh, en)],
            "MFA 官网展厅/部门页" if sk == "mfa_official"
            else "MFA 扩充清单 · Wikidata 条目",
            "high" if sk == "mfa_official" else "medium",
            "rule", rule[1], SR.quality_of(rule[0])))
    for i in range(0, len(meta_rows), 2000):
        cur.executemany(
            "INSERT INTO artwork_meta (museum_key, source_seq, key_name, source_key,"
            " ord, value_cid, source, confidence, filled_by,"
            " evidence_type, source_quality)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", meta_rows[i:i + 2000])
    conn.commit()
    n_done = sum(len(x) for x in payload.values())
    print(f"\n写入 artwork_meta {len(meta_rows)} 条，覆盖 {n_done} 件")
    if untranslated:
        print(f"⚠ {len(untranslated)} 个取值没有英译（含标了「存疑」的），已按中文写入 en 列。"
              f"英文导出的 CJK 扫描会把它们捞出来 —— 这是预期信号，不是 bug。")
        print("   例：" + "、".join(sorted(untranslated)[:5]))


if __name__ == "__main__":
    main()
