#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PEM 的展厅基准表与旧标签映射。

**为什么这份东西在仓库里而不只在库里。**
`import_artworks.py` 每次重灌都 `DELETE FROM gallery`，且原本的 gallery 行是从
展品表第 4 列「展厅」收集出来的副产品。只改数据库，下次重灌就蒸发 —— 同
译名表那条规矩（见 AGENTS.md「译名必须留在 translations_*.csv」）。

**两份清单零交集。** 库里原有的 23 个 PEM「展厅」不是展厅，是每件展品身上的
主题标签（`Asian Export Art Gallery`、`Oceanic Gallery`、`Ancient Mediterranean`）。
本表的 26 个才是 PEM 官网的实体/冠名展厅。两边**一个同名的都没有**，
所以这不是改名，是换了一个维度 —— 对应关系只能由人给，见 LABEL_MAP。

来源：`PEM_ChatGPT_Gallery_List_with_Chinese.xlsx`（用户 2026-09-21 提供）。
`category` 一列是源文件自带的，**必须留着**：26 个里只有 16 个标「明确确认」，
另外 10 个标「待确认」或「内部物理节点编号」。本项目在模型编造展厅号上栽过两次
（见 AGENTS.md 第 10 条那张表），这批东西的成色必须一眼看得见，不能混成一锅。
`note` / `source_tag` 同样照录，措辞里的保留（「通常用于」「相关」）是信息。
"""

GALLERIES = (
    dict(category='明确确认的冠名实体展厅',
         name_en='Seamans Gallery',
         name_zh='西曼斯展厅',
         note='美洲艺术 (American Art) 相关展区',
         source_tag='American Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Sean M. Healey Family Gallery of Asian Export Art',
         name_zh='肖恩·M·希利家族亚洲外销艺术展厅',
         note='亚洲外销艺术 (Asian Export Art)',
         source_tag='Asian Export Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Jurrien Timmer Gallery',
         name_zh='朱里恩·蒂默展厅',
         note='通常用于特展或当代艺术',
         source_tag='Vanessa Platacis 等'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Yu Kil-Chun Gallery of Korean Art and Culture',
         name_zh='俞吉濬韩国艺术与文化展厅',
         note='韩国艺术与文化展厅',
         source_tag='Korean Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Byrne Family Gallery of Maritime Art',
         name_zh='伯恩家族航海艺术展厅',
         note='航海艺术展厅',
         source_tag='Maritime Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Nancy and George Putnam Gallery',
         name_zh='南希与乔治·普特南展厅',
         note='美洲艺术与本土原住民艺术相关',
         source_tag='On This Ground'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Barbara Weld Putnam Gallery',
         name_zh='芭芭拉·韦尔德·普特南展厅',
         note='美洲艺术相关',
         source_tag='On This Ground'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Louise Du Pont Crowninshield Gallery',
         name_zh='路易丝·杜邦·克劳宁希尔德展厅',
         note='早期美洲装饰艺术或特定捐赠展区',
         source_tag='相关馆藏源'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Chester and Davida Herwitz Gallery',
         name_zh='切斯特与达维达·赫维茨展厅',
         note='南亚现代艺术 (南亚主题)',
         source_tag='South Asian Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Prashant H. Fadia Foundation and Deshpande Foundation Gallery',
         name_zh='普拉尚特·H·法迪亚基金会与德什潘德基金会展厅',
         note='南亚艺术相关',
         source_tag='South Asian Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='H.A. Crosby Forbes Gallery',
         name_zh='H.A.克罗斯比·福布斯展厅',
         note='亚洲外销艺术相关',
         source_tag='Asian Export Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Pamela Cunningham Copeland Gallery',
         name_zh='帕梅拉·坎宁安·科普兰展厅',
         note='亚洲外销艺术相关',
         source_tag='Asian Export Art'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Carl and Iris Barrel Apfel Gallery of Fashion and Design',
         name_zh='卡尔与艾瑞斯·巴瑞尔·阿普菲尔时尚与设计展厅',
         note='时尚与设计展厅 (Fashion and Design)',
         source_tag='Fashion & Design'),
    dict(category='明确确认的冠名实体展厅',
         name_en='James Duncan Phillips Trust Gallery',
         name_zh='詹姆斯·邓肯·菲利普斯信托展厅',
         note='相关历史主题或美洲艺术',
         source_tag='Pressing Importance'),
    dict(category='明确确认的冠名实体展厅',
         name_en='Yin Yu Tang Interpretive Gallery',
         name_zh='荫余堂诠释展厅',
         note='荫余堂诠释展厅 (非荫余堂本体，为其配套展览)',
         source_tag='Double Happiness 等'),
    dict(category='明确确认的冠名实体展厅',
         name_en='East India Marine Hall',
         name_zh='东印度海事厅',
         note='核心历史保护建筑',
         source_tag='East India Marine Hall'),
    dict(category='官网使用名称 (待确认或临时展厅)',
         name_en='Studio Glass Gallery',
         name_zh='现代玻璃艺术展厅',
         note='现代玻璃艺术展区',
         source_tag='Studio Glass 活动'),
    dict(category='官网使用名称 (待确认或临时展厅)',
         name_en='Japanese Gallery',
         name_zh='日本艺术展厅',
         note='日本艺术展区',
         source_tag='日本艺术馆藏活动'),
    dict(category='官网使用名称 (待确认或临时展厅)',
         name_en='Witch Trials Gallery',
         name_zh='女巫审判展厅',
         note='塞勒姆女巫审判主题 (常为特展/长期展)',
         source_tag='Witch Trials 活动'),
    dict(category='官网使用名称 (待确认或临时展厅)',
         name_en='Salem Stories Gallery',
         name_zh='塞勒姆故事展厅',
         note='塞勒姆故事主题展区',
         source_tag='相关主题活动'),
    dict(category='官网使用名称 (待确认或临时展厅)',
         name_en='Anila Quayyum Agha’s All the Flowers Are for Me Gallery',
         name_zh='阿尼拉·卡尤姆·阿迦“所有花朵都为你”展厅',
         note='特定艺术家的光影装置展厅',
         source_tag='特定展览命名'),
    dict(category='内部物理节点编号/临时大厅',
         name_en='Special Exhibition Gallery A',
         name_zh='特展厅A',
         note='特展厅A',
         source_tag='Special Exhibition Gallery A'),
    dict(category='内部物理节点编号/临时大厅',
         name_en='Special Exhibition Gallery C',
         name_zh='特展厅C',
         note='特展厅C',
         source_tag='特展信息'),
    dict(category='内部物理节点编号/临时大厅',
         name_en='Gallery 115',
         name_zh='115号展厅',
         note='具体房间号 115',
         source_tag='Gallery 115'),
    dict(category='内部物理节点编号/临时大厅',
         name_en='Gallery 201 / Dodge 2 Galleries',
         name_zh='201号展厅 / 道奇二层展厅',
         note='具体房间号 201 / Dodge 二层展厅',
         source_tag='Gallery 201'),
    dict(category='内部物理节点编号/临时大厅',
         name_en='Gallery 300',
         name_zh='300号展厅',
         note='具体房间号 300',
         source_tag='Gallery 300'),
)


# 旧标签 -> 实体展厅。键是 PEM 源表第 4 列的原值（注意 Islamic‑Asian、Gardner‑Pingree
# 用的是 U+2011 非断字连字符，不是 ASCII 连字号）。
#
# 对应关系**由用户 2026-09-21 给定**，不是推断出来的。值为 None 表示该标签不对应任何
# 实体展厅，展品的 gallery_id 置 NULL —— 官网没有证明它是独立房间，就不据此填展厅。
#
# 本表必须**穷举**源表出现过的全部标签：`import_artworks.py` 查不到就 sys.exit，
# 不默认置空。将来 PEM 源表加一个新标签而这里没登记，静默变 NULL 是查不出来的
# （AGENTS.md 第 10 条：「取不到就退而求其次」一律改成「取不到就喊」）。
LABEL_MAP = {
    'Yin Yu Tang Courtyard':
        None,  # 荫余堂本体的院落；源表的 Yin Yu Tang Interpretive Gallery 是另设的配套展厅，不是同一处
    'Japanese Art Gallery':
        'Japanese Gallery',  # 目标展厅在源表里标「待确认或临时展厅」
    'Oceanic Art Gallery':
        None,  # 门类，不是实体房间
    'Asian Export Art Gallery':
        'Sean M. Healey Family Gallery of Asian Export Art',
    'American Art Gallery':
        'Seamans Gallery',
    'Maritime Gallery':
        'Byrne Family Gallery of Maritime Art',
    'Maritime Gallery Captain Collectors':
        'Byrne Family Gallery of Maritime Art',  # 同一展厅内的子展区，并入
    'Powerful Figures Gallery':
        'Louise Du Pont Crowninshield Gallery',
    'Gardner‑Pingree Historic House':
        None,  # 独立历史建筑，不是馆内展厅
    'Art & Nature Center':
        None,  # 独立设施，不在冠名展厅清单内
    'Korean Art Gallery':
        'Yu Kil-Chun Gallery of Korean Art and Culture',
    'Mixed Oceanic Gallery':
        None,  # 门类，不是实体房间
    'Gardner‑Pingree House':
        None,  # 独立历史建筑，不是馆内展厅
    'American Contemporary Gallery':
        None,  # 门类，不是实体房间
    'Oceanic Gallery':
        None,  # 门类，不是实体房间
    'Korean Contemporary Gallery':
        None,  # 门类，不是实体房间
    'American Decorative Arts':
        None,  # 门类，不是实体房间
    'Phillips Library Display Case':
        None,  # 展柜，不是展厅
    'Islamic‑Asian Gallery':
        None,  # 门类，不是实体房间
    'Photography Gallery':
        None,  # 门类，不是实体房间
    'Ancient Mediterranean':
        None,  # 门类，不是实体房间
    'European Decorative Arts':
        None,  # 门类，不是实体房间
    'Special Case Display':
        None,  # 展柜，不是展厅
}


# ---------------------------------------------------------------- 在展原句 -> 展厅
#
# 官网藏品页的「On view in …」里写的**不一定是展厅**：可能是展览名、可能是
# 楼梯间或中庭这种不成其为展厅的地方、也可能是个笼统说法。2026-09-21 实测
# 110 条在展原句只指向 19 个目标（外加 17 条裸徽章 ON VIEW），**这里逐个登记**。
#
# 契约与 LABEL_MAP 相同：**查不到抛 KeyError，登记为 None 就是「确实不对应展厅」**。
# 「没登记」和「登记为没有」必须长得不一样。
#
# 值为 EXHIBITION 的，表示这是个展览名，要去 pem_exhibition_data 查它在哪个展厅
# —— 展览页写「Located in the X.」才算数，写了两个展厅的一个都不用。
EXHIBITION = "<exhibition>"

ONVIEW_MAP = {
    # —— 直接点名 26 个实体展厅之一 ——
    'Sean M. Healey Family Gallery of Asian Export Art':
        'Sean M. Healey Family Gallery of Asian Export Art',
    'Byrne Family Gallery of Maritime Art':
        'Byrne Family Gallery of Maritime Art',
    'East India Marine Hall':
        'East India Marine Hall',
    'Carl and Iris Barrel Apfel Gallery of Fashion and Design':
        'Carl and Iris Barrel Apfel Gallery of Fashion and Design',
    # 官网这一条少了 "Family"。**手工登记，不做模糊匹配** —— 相似度匹配一旦放开，
    # 「Salem Stories」和「Salem Stories Gallery」这种循环命名就会跟着被放进来。
    'Sean M. Healey Gallery of Asian Export Art':
        'Sean M. Healey Family Gallery of Asian Export Art',

    # —— 官网在用、但不是 26 个里的写法；沿用用户 2026-09-21 定的同一映射 ——
    'Japanese Art Gallery': 'Japanese Gallery',
    'American Art Gallery': 'Seamans Gallery',

    # —— 展览名，去展览页查 ——
    'On This Ground: Being and Belonging in America': EXHIBITION,
    'On this Ground: Being and Belonging in America': EXHIBITION,   # 官网自己的大小写不一致
    'Double Happiness: Celebration in Chinese Art': EXHIBITION,
    'Powerful Figures': EXHIBITION,
    # 展览页没写在哪个展厅。26 个里确实有个 "Salem Stories Gallery"，但那个展厅名
    # 在源表里分类是「官网使用名称（待确认）」、备注「塞勒姆故事主题展区」——
    # **展厅名本身是从展览名来的，拿它当证据是循环的**。留给展览查询，查不到就是 None。
    'Salem Stories': EXHIBITION,

    # —— 26 个里没有对应的实体展厅 ——
    # 南亚有两个展厅（Herwitz、Fadia/Deshpande），官网这个笼统说法指不到具体哪一个
    'South Asian Art Gallery': None,
    # 特展厅有 A 和 C 两个，「our special exhibitions gallery」指不到哪一个
    'our special exhibitions gallery': None,

    # —— 不是展厅的地方 ——
    'Pod': None,                                                    # 独立装置空间
    'Garden Atrium': None,                                          # 中庭
    'On view on the Ground Level of the New Wing stairwell': None,   # 楼梯间
    'stairway of the new wing': None,                               # 楼梯间
    'On view on Level 2 of the new wing at the top of the stairs': None,  # 楼梯口
}


# ---------------------------------------------------------------- 栏目 -> 展厅（推断）
#
# ⚠ **这是推断，不是证据。** 由「这件东西登在官网哪个栏目页上」推出「它在哪个展厅」
# —— 栏目说的是**门类**，展厅是**房间**，两者不是一回事。用户 2026-09-21 知情后
# 授权批量做，条件是**单独成列、标明未证实，绝不写进 artwork.gallery_id**。
#
# 反例就在数据里：`korean-art` 按门类指向俞吉濬展厅，可该栏目里**每一条有在展原文
# 的记录写的都是「Salem Stories」或「Garden Atrium」** —— 馆方自己的陈述与栏目推断
# 打架。这正是它必须与证据分开存放的理由。
#
# 17 个栏目逐个登记，**能映射的只有 5 个**。其余写 None 分两种情形，注释里说明是哪种：
# 「26 个里没有对应的展厅」和「有但不止一个，指不到具体哪个」。
SECTION_MAP = {
    'american-art':               'Seamans Gallery',
    'japanese-art':               'Japanese Gallery',
    'korean-art':                 'Yu Kil-Chun Gallery of Korean Art and Culture',
    'maritime-art-and-history':   'Byrne Family Gallery of Maritime Art',
    'fashion-textiles':           'Carl and Iris Barrel Apfel Gallery of Fashion and Design',

    # —— 有对应展厅，但不止一个，指不到具体哪个 ——
    'asian-export-art':           None,   # Healey / Crosby Forbes / Copeland 三个
    'south-asian-art':            None,   # Herwitz / Fadia-Deshpande 两个
    'native-american-art':        None,   # On This Ground 横跨两个普特南展厅

    # —— 26 个里没有对应的实体展厅 ——
    'african-art':                None,
    'american-decorative-art':    None,   # Crowninshield 的备注写的是「或特定捐赠展区」，带保留
    'chinese-art':                None,   # 荫余堂诠释展厅只办 Double Happiness 一个展
    'contemporary-art':           None,   # 源表标记写 Jurrien Timmer，但展览页写的是 Crosby Forbes
    'european-art':               None,
    'natural-history':            None,   # Art & Nature Center 不在 26 个里
    'oceanic-art':                None,
    'photography':                None,
    # ⚠ 不是 James Duncan Phillips Trust Gallery。那是冠名展厅，**只是名字撞车**
    'phillips-library-collection': None,
}


BY_NAME = {g["name_en"]: g for g in GALLERIES}

# 映射的目标必须真的存在于 GALLERIES，否则导入时才发现就晚了。
# 放在模块顶层，import 的那一刻就炸。
_bad = sorted({t for t in LABEL_MAP.values() if t and t not in BY_NAME})
if _bad:
    raise AssertionError(f"LABEL_MAP 指向了 GALLERIES 里没有的展厅：{_bad}")
if len(BY_NAME) != len(GALLERIES):
    raise AssertionError("GALLERIES 里有重名展厅")
_bad = sorted({t for t in ONVIEW_MAP.values()
               if t and t != EXHIBITION and t not in BY_NAME})
if _bad:
    raise AssertionError(f"ONVIEW_MAP 指向了 GALLERIES 里没有的展厅：{_bad}")
_bad = sorted({t for t in SECTION_MAP.values() if t and t not in BY_NAME})
if _bad:
    raise AssertionError(f"SECTION_MAP 指向了 GALLERIES 里没有的展厅：{_bad}")


def resolve_onview(text):
    """
    藏品页的在展原句 -> (展厅英文名 或 None, 依据)。

    三种输入：None / "ON VIEW" 裸徽章 / "On view in <目标>"。
    **没登记的目标抛 KeyError** —— 官网改了写法要被发现，不能静默变成「没展厅」。
    """
    t = (text or "").strip()
    if not t:
        return None, "页面未写在展"
    if t.upper() == "ON VIEW":
        # 馆方说它在展，但没说在哪儿。on_view 是「在展」，展厅是未知 —— 两件事。
        return None, "裸徽章 ON VIEW，未点名地点"
    import re as _re
    target = _re.sub(r"(?i)^on view in (the )?", "", t).rstrip(". ").strip()
    dest = ONVIEW_MAP[target]              # 没登记就抛，由调用方喊出来
    if dest is None:
        return None, f"{target} —— 已登记为不对应实体展厅"
    if dest == EXHIBITION:
        import pem_exhibition_data as E
        g = E.gallery_of(target)
        if g:
            return g, f"展览《{target}》的展览页点名：{g}"
        v = E.EXHIBITIONS.get(target, {})
        return None, f"展览《{target}》：{v.get('note', '未登记')}"
    return dest, f"在展原句直接点名：{target}"


def resolve(label):
    """
    旧展厅标签 -> 实体展厅英文名；该标签不对应实体展厅时返回 None。

    **查不到不返回 None，而是抛 KeyError** —— 调用方负责喊出来。
    「没登记」和「登记为不对应」必须长得不一样，同 AGENTS.md 第 9 条
    「没跑」和「跑出来是 0」必须在库里长得不一样。
    """
    return LABEL_MAP[label]


def zh_of(name_en):
    """实体展厅英文名 -> 中文名。"""
    return BY_NAME[name_en]["name_zh"]
