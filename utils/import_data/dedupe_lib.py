#!/usr/bin/env python3
"""跨语言展品去重的共用判据。`dedupe_*.py` 四个脚本共用。

**两边各存一份必然分叉，且不报错** —— 同 `museum_context.py`、`gallery_text.py` 的道理。

## 为什么要有这套东西（2026-09-16）

合并表里同一件实物常以中英两条记录并存：
`J.M.W. Turner《Slave Ship》奴隶船（1840）` 与 `奴隸船（约瑟夫·马洛德·威廉·透纳，1840-01-01，油彩）`
是同一幅画。上一轮的召回是**纯 token 重叠**，跨语言命中全靠运气 ——
「奴隶船」能中只因为对侧名称里正好含这三个中文字；繁体「奴隸船」、
纯英文 `Fine Wind, Clear Weather` 一个都召不到。

## 三个子集，字段可用性差别极大（实测）

| 子集 | 行数 | 有作者 | 有年代 | 有馆藏号 |
|---|---:|---:|---:|---:|
| ext·wikidata | 4224 | 3710 可用 | 3160 | 3864 |
| ext·官网 | 134 | 0（作者嵌在名称串里） | 64 | 2 |
| 原清单 | 179 | 16（全英文） | 39 | 15 |

所以判据必须能在「一侧信息很全、另一侧几乎什么都没有」的情况下工作，
且**任一侧信息缺失一律不能当成否决证据**。
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- 行键与子集

KEY_COLS = ("来源表", "来源行")


def row_key(row: dict) -> tuple:
    """行的唯一标识。

    **用 `(来源表, 来源行)`，不用 `序号`** —— `序号` 在合并表里不唯一
    （两个 museum key 各自从 1 编号），拿它建行映射会让 A 件的答案写进 B 件的行且不报错。
    实测这个键在 4537 行上零重复、零缺失。
    """
    return (row.get("来源表"), row.get("来源行"))


def subset(row: dict) -> str:
    """三个来源子集之一：`原清单` / `ext·官网` / `ext·wikidata`。"""
    if "扩充清单" not in str(row.get("博物馆") or ""):
        return "原清单"
    return "ext·wikidata" if "wikidata.org" in str(row.get("官方页面") or "") else "ext·官网"


QID_RE = re.compile(r"\b(Q\d+)\b")


def qid_of(row: dict) -> str | None:
    m = QID_RE.search(str(row.get("官方页面") or ""))
    return m.group(1) if m else None


# ---------------------------------------------------------------- 馆藏号

# **必须保留第三段**：`1986.127.1` ≠ `1986.127`，截断会把七开册页折成一件。
ACC_RE = re.compile(r"\b\d{1,4}\.\d+(?:\.\d+)?[a-z]?\b")
# 管线来源：Wikidata 的 P217 落在「馆藏号」，metadata 管线的落在「馆藏编号」。
ACC_COLS = {"馆藏号": "wikidata", "馆藏编号": "meta"}


def accessions(row: dict) -> dict[str, set[str]]:
    """按管线分组的馆藏号。

    ⚠ **馆藏号相等只有「两条记录来自不同管线」时才是硬证据。**
    实测：跨管线相等 15 组，15/15 是真重复；而同管线（ext 内部）相等 38 组里
    抽查 12/15 是彻底不同的作品 —— `19.8` 同时挂在柯洛《Old Beech Tree》和
    亨特《Man in Wheat Field》上，`2003.25` 同时挂在德加和 Claudio Bravo 上，
    都是 Wikidata 的 P217 被截断或填错。同管线相等只能当候选。
    """
    out: dict[str, set[str]] = {"wikidata": set(), "meta": set()}
    for col, pipe in ACC_COLS.items():
        for m in ACC_RE.findall(str(row.get(col) or "")):
            out[pipe].add(m)
    # 简介里的「藏品编号 X」也是 Wikidata 那条管线抄来的
    for m in re.findall(r"藏品编号\s*([\d.]+[a-z]?)", str(row.get("展品简介") or "")):
        if ACC_RE.fullmatch(m):
            out["wikidata"].add(m)
    return out


def acc_base(acc: str) -> str:
    """册页/组画的基号：`1986.127.1` → `1986.127`。**只用于组画聚合，不用于判同一件。**"""
    parts = acc.split(".")
    return ".".join(parts[:2]) if len(parts) >= 3 else acc


# ---------------------------------------------------------------- 年代区间

DYNASTIES = {
    # 中国
    "商": (-1600, -1046), "西周": (-1046, -771), "东周": (-770, -256),
    "春秋": (-770, -476), "战国": (-475, -221), "秦": (-221, -206),
    "西汉": (-206, 8), "东汉": (25, 220), "汉": (-206, 220),
    "三国": (220, 280), "西晋": (265, 316), "东晋": (317, 420),
    "南北朝": (420, 589), "隋": (581, 618), "唐": (618, 907),
    "五代": (907, 960), "五代十国": (907, 979),
    "北宋": (960, 1127), "南宋": (1127, 1279), "宋": (960, 1279),
    "辽": (916, 1125), "金": (1115, 1234), "西夏": (1038, 1227),
    "元": (1271, 1368), "明": (1368, 1644), "清": (1644, 1912),
    "民国": (1912, 1949),
    # 日本
    "奈良": (710, 794), "平安": (794, 1185), "镰仓": (1185, 1333),
    "室町": (1336, 1573), "桃山": (1573, 1615), "江户": (1603, 1868),
    "明治": (1868, 1912), "大正": (1912, 1926), "昭和": (1926, 1989),
    # 朝鲜
    "高丽": (918, 1392), "朝鲜王朝": (1392, 1897), "新罗": (-57, 935),
    # 古埃及。**必须有**：MFA 的埃及藏品是招牌，而「古王国第四王朝」这类写法
    # 在中文朝代表里一条都匹配不上，于是整批拿不到年代、召回时年代通道失效。
    "古王国": (-2686, -2181), "中王国": (-2055, -1650), "新王国": (-1550, -1069),
    "后王朝": (-664, -332), "托勒密": (-305, -30), "罗马时期": (-30, 395),
    "第一王朝": (-3100, -2890), "第二王朝": (-2890, -2686),
    "第三王朝": (-2686, -2613), "第四王朝": (-2613, -2494),
    "第五王朝": (-2494, -2345), "第六王朝": (-2345, -2181),
    "第十八王朝": (-1550, -1292), "第十九王朝": (-1292, -1189),
    "第二十五王朝": (-744, -656), "第二十六王朝": (-664, -525),
    # 其它古代
    "亚述": (-911, -609), "巴比伦": (-1894, -539), "米诺斯": (-2700, -1450),
}

# ISO 日期可以出现在名称中间（`Tiger（曾我萧白，1770-01-01，纸）`），所以用 search；
# 但前面必须是起首或标点，否则 `ship-1840-01-01` 会被读成公元前 1840 年。
_ISO = re.compile(r"(?:^|(?<=[\s（(，,：:]))(-?\d{1,4})-\d{1,2}-\d{1,2}(?!\d)")
_CENTURY = re.compile(r"(公元前\s*)?(\d{1,2})\s*[–\-—~]?\s*(\d{1,2})?\s*世纪\s*(初|中|末|晚|前期|后期)?")
_YEAR_RANGE = re.compile(r"(公元前\s*)?(\d{3,4})\s*[–\-—~]\s*(公元前\s*)?(\d{3,4})")
# `约 1830–31` 这类省略写法：末尾只写后两位。实测 ext·官网的年代列大量这么写。
_YEAR_RANGE_ABBR = re.compile(r"(\d{3,4})\s*[–\-—~]\s*(\d{1,2})\b")
# 年份两侧不能紧贴 ASCII 字母数字 —— 否则会从十六进制串里抠数字（见 year_span 的注释）。
# 用 ASCII 而不用 \w：Python 的 \w 含中文，会把「1885年」也挡掉。
_YEAR = re.compile(r"(公元前\s*)?(?<![A-Za-z0-9])(\d{3,4})(?![A-Za-z0-9])\s*年?")
_URL = re.compile(r"https?://\S+|\b[0-9a-f]{16,}\b", re.I)
# ⚠ 朝代名不能用子串匹配：「公元」里含「元」、「纪元」同理。
# 这与 AGENTS.md 那条「朝代与产地必须整段等值匹配（「宋」是朝代，「宋徽宗」是人名）」同源。
_DYN_BAD_PREFIX = ("公", "纪")


def year_span(text) -> tuple[int, int, bool] | None:
    """把任意年代文本规范成 `(lo, hi, approx)`；认不出返回 None。

    **判「区间重叠」而不是「相等」** —— 同一件东西在两份资料里会写成
    `约 1830–31` 和 `1830-01-01`、`12 世纪初` 和 `1101`。要求相等会把它们判成不同。

    ⚠ **返回 None（未知）绝不能当作「冲突」使用。** ext·wikidata 有 1064 行没有年代，
    把未知当冲突会把这 1064 行静默排除在召回外 —— 那正是上一轮 151 件零候选的同类错误。
    """
    # ⚠ 先剥掉网址与长十六进制串。合并表里有几百行名称嵌着 Wikidata 匿名节点的网址
    # （`…/.well-known/genid/13ef7cce561dc0415…`），不剥的话年份正则会从哈希里
    # 抠出数字：实测解析出过 4214 年、6023 年、620 年，年代闸因此会乱判。
    s = _URL.sub(" ", str(text or "")).strip()
    if not s:
        return None
    approx = bool(re.search(r"约|ca\.|circa|c\.\s*\d", s, re.I))

    # ISO 日期最先判。ext·wikidata 的年代全是 `1830-01-01` 这个形状，
    # 而它长得跟「省略区间」`1830–31` 一模一样 —— 不先吃掉，`1830-01-01`
    # 会被读成 1830–1901。（负号开头的是公元前，如 `-0400-01-01`。）
    m = _ISO.search(s)
    if m:
        y = int(m.group(1))
        return (y, y, approx)

    # 其余数字优先。朝代名放最后 —— 「公元 700–1520 年」里的「元」不是元朝，
    # 先吃掉数字就不会走到朝代那一步。
    m = _YEAR_RANGE.search(s)
    if m:
        a = int(m.group(2)) * (-1 if m.group(1) else 1)
        b = int(m.group(4)) * (-1 if (m.group(3) or m.group(1)) else 1)
        return (min(a, b), max(a, b), approx)

    m = _YEAR_RANGE_ABBR.search(s)
    if m:
        a = int(m.group(1))
        tail = m.group(2)
        b = int(str(a)[:len(str(a)) - len(tail)] + tail)   # 1830–31 → 1831
        if b < a:                                          # 1830–9 这类跨十位，补进位
            b += 10 ** len(tail)
        return (min(a, b), max(a, b), approx)

    m = _CENTURY.search(s)
    if m:
        bce = bool(m.group(1))
        c1 = int(m.group(2))
        c2 = int(m.group(3)) if m.group(3) else c1
        lo, hi = (c1 - 1) * 100, c2 * 100 - 1
        if bce:
            lo, hi = -hi, -lo
        part = m.group(4)
        if part == "初" or part == "前期":
            hi = lo + 33
        elif part == "中":
            lo, hi = lo + 33, lo + 66
        elif part in ("末", "晚", "后期"):
            lo = hi - 33
        return (lo, hi, True)

    m = _YEAR.search(s)
    if m:
        y = int(m.group(2)) * (-1 if m.group(1) else 1)
        return (y, y, approx)

    # 最后才查朝代，且要求朝代名前一个字不是「公」「纪」——「公元」不是元朝
    for name, (lo, hi) in DYNASTIES.items():
        i = s.find(name)
        while i != -1:
            if i == 0 or s[i - 1] not in _DYN_BAD_PREFIX:
                return (lo, hi, True)
            i = s.find(name, i + 1)
    return None


APPROX_PAD = 3          # `约 1830–31` 这类各向外放宽的年数


def year_relation(a, b) -> str:
    """两个年代区间的关系：`overlap` / `conflict` / `unknown`。"""
    if a is None or b is None:
        return "unknown"
    (alo, ahi, aap), (blo, bhi, bap) = a, b
    if aap:
        alo, ahi = alo - APPROX_PAD, ahi + APPROX_PAD
    if bap:
        blo, bhi = blo - APPROX_PAD, bhi + APPROX_PAD
    if alo <= bhi and blo <= ahi:
        return "overlap"
    # 两侧都是窄区间且不相交时，**容差按年代分档** —— 越古老的东西断代越不精确。
    # 实测：同一套《平治物语绘卷》一条记 1275、一条记 1300，差 25 年；
    # 按固定容差会被判成「冲突」而直接否决，可它们是同一件。
    # 而 1670 与 1840 差 170 年，仍然该判冲突。
    if (ahi - alo) <= 50 and (bhi - blo) <= 50:
        gap = blo - ahi if blo > ahi else alo - bhi
        newest = max(ahi, bhi)
        tol = 2 if newest >= 1800 else (30 if newest >= 1500 else 60)
        return "conflict" if gap > tol else "unknown"
    return "unknown"


# ---------------------------------------------------------------- 题名

_PAREN_TAIL = re.compile(r"[（(][^（()]*[)）]\s*$")
_ACC_TAIL = re.compile(r"-\d[\d.]*[a-z]?$")
_STOP_EN = {"the", "a", "an", "of", "and", "with", "in", "on", "at", "for", "from"}
CJK_RE = re.compile(r"[一-鿿]")


def has_cjk(s) -> bool:
    return bool(CJK_RE.search(str(s or "")))


def norm_title(s) -> str:
    """题名规范化：去括注、去馆藏号尾巴、去冠词介词、去标点空格、大小写与全半角折叠。"""
    s = unicodedata.normalize("NFKC", str(s or "")).strip()
    s = _PAREN_TAIL.sub("", s)
    s = _ACC_TAIL.sub("", s)
    s = s.lower()
    words = re.findall(r"[a-z0-9]+", s)
    if words:
        kept = [w for w in words if w not in _STOP_EN] or words
        latin = "".join(kept)
    else:
        latin = ""
    cjk = "".join(CJK_RE.findall(s))
    return cjk + latin


def cjk_tokens(s: str, n: int = 2) -> set[str]:
    """中文按 n-gram 切块，用于部分重叠比较。"""
    cjk = "".join(CJK_RE.findall(str(s or "")))
    return {cjk[i:i + n] for i in range(len(cjk) - n + 1)} if len(cjk) >= n else set()


def en_tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(s or "").lower()) if w not in _STOP_EN}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------- 人名归一

_NAME_DROP = re.compile(r"[·.·\s,'\-–—]")


def norm_person(s) -> str:
    """人名规范化，用于跨语言别名词典反查。

    `J.M.W. Turner` / `J. M. W. Turner`、`葛饰北斋` / `葛飾北斎` 这类写法差异，
    靠 NFKC + 去分隔符 + 小写折叠抹平；**简繁之别不在这里处理** ——
    由 Wikidata 的 `zh-hans` / `zh-hant` 两条标签天然覆盖，不引入 opencc。
    """
    s = unicodedata.normalize("NFKC", str(s or "")).strip().lower()
    return _NAME_DROP.sub("", s)


GENID_RE = re.compile(r"\.well-known/genid/")


def artist_usable(s) -> bool:
    """表里的「作者」列有五种形态，只有两种能用。

    实测 4224 行 ext·wikidata 里：中文名 1874、拉丁名 2263（这两种能用），
    以及 329 个 genid URL（Wikidata 里的**匿名创作者节点**，意思是「作者不可考」，
    不是「没抓到」）、185 个裸 QID、87 个空。
    把 genid 当人名去匹配，会让一堆不同作品因为「同一个匿名节点」被召到一起。
    """
    s = str(s or "").strip()
    if not s or GENID_RE.search(s):
        return False
    return not re.fullmatch(r"Q\d+", s)


# ---------------------------------------------------------------- 粗类型：平面 / 立体

# 用户 2026-09-17 定的判据含「类型相同（都是绘画、都是雕塑）」。
# 只分两大类：细分到「版画 vs 绘画」反而会误伤 —— 同一张北斋，一边记「多色木版画」，
# 另一边 Wikidata 记「畫作」。平面 vs 立体的错配才是确定无疑的：
# 2026-09-18 实测 haiku 把木造《毗沙门天像》与一幅 Wikidata 记为「畫作」的
# 《Bishamonten … with his Retinue》判成同一件。
_FLAT = re.compile(r"畫作|绘画|繪畫|油画|油彩|水彩|素描|布面|绢本|絹本|纸本|手卷|挂轴|屏风|屏風|"
                   r"繪卷|绘卷|版画|版畫|木刻|painting|print|drawing|canvas|watercolor", re.I)
# ⚠「像」不能单独当立体：「肖像」「画像」是画。只认成词的雕塑说法。
_SOLID = re.compile(r"雕像|塑像|立像|坐像|胸像|三联像|夫妇像|双人像|雕塑|石雕|木雕|木造|"
                    r"青铜|铜像|大理石|杂砂岩|花岗岩|sculpture|statue|statuette|\bbust\b", re.I)


def coarse_type(row: dict) -> str | None:
    """`平面` / `立体` / None（认不出或两种信号都有）。只读记录自己的字段，不读模型的话。"""
    text = " ".join(str(row.get(k) or "") for k in ("展品名称", "展品简介", "材质", "门类", "器型·类别"))
    text = re.sub(r"肖像|画像|畫像|图像", "", text)
    flat, solid = bool(_FLAT.search(text)), bool(_SOLID.search(text))
    if flat and not solid:
        return "平面"
    if solid and not flat:
        return "立体"
    return None
