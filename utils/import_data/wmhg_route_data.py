"""伪满皇宫博物院（wmhg）游览线路的静态数据：参观顺序、坐标、停留时间、地点出处。

由 route_plan.py 读取。评级、Core、在展状态、名称**不在这里**，一律从库里取 ——
这里只放库里没有、排路线又必需的东西。

**哪些是事实，哪些是估计，分开看：**

- 参观顺序：取自馆方 2023 年导览（文章 2657）给出的推荐顺序，地点按 2026 年春节导览
  （文章 3295）更新。两篇的原文都在 wmhg_article_data.py 里。
- 坐标：OpenStreetMap，2026-10-09 用 Overpass 取回，逐条记着 OSM 编号，可复查。
  OSM 上找不到的 4 个点**借用**一个有出处的邻近点，借用理由写在 `anchor` 里，
  导出时这几站的步行时间会标「坐标借用」。
- 停留时间：**全部是估计**（AI 推断，2026-10-09），依据是官网写明的面积、展线长度、
  展品数量。没有任何馆方或游客实测数据。改了这里，路线会跟着变。

两个节点不进路线，理由见 MERGED / UNPLACED，route_plan.py 会逐条列在「候选总表」里。
"""

# ---------------------------------------------------------------- 出处
SOURCES = {
    "guide2023": ("馆方 2023 年导览（文章 2657）",
                  "Museum's 2023 visitor guide (article 2657)",
                  "https://www.wmhg.com.cn/detail/2657.html"),
    "guide2026": ("馆方 2026 年春节导览（文章 3295）",
                  "Museum's 2026 Spring Festival guide (article 3295)",
                  "https://www.wmhg.com.cn/detail/3295.html"),
    "exhib": ("官网常设展览页", "Museum website, permanent exhibition page", None),
    "article3263": ("官网文章 3263（2026-01-20 上新）",
                    "Museum article 3263 (new display, 2026-01-20)",
                    "https://www.wmhg.com.cn/detail/3263.html"),
}

# ---------------------------------------------------------------- 坐标
# (纬度, 经度, OSM 编号, 借用说明 zh, 借用说明 en)；借用说明为 None 即 OSM 上就是这个点。
POINTS = {
    "ticket":     (43.90234, 125.34240, "way/227349455", None, None),      # 售票处
    "tongde":     (43.90398, 125.34323, "way/227328266", None, None),
    # 官网：书画楼亦称「小白楼」。OSM 另有三块「画书楼」在其北 30 米，按官网别名取小白楼
    "shuhua":     (43.90414, 125.34315, "way/1492049115", None, None),
    "east_garden": (43.90327, 125.34388, "way/227329947", None, None),
    "pool":       (43.90327, 125.34388, "way/227329947",
                   "OSM 无此点；官网导览说游泳池在东御花园内，取花园中心",
                   "Not in OSM; the museum guide places it inside the East Garden, so the garden centre is used"),
    "shelter":    (43.90377, 125.34406, "node/14085074201", None, None),  # 御用防空洞入口
    "shrine":     (43.90323, 125.34420, "way/1492049116", None, None),    # 「建国神庙」遗址
    "amaterasu":  (43.90310, 125.34395, "node/13673335173", None, None),
    "west_wing":  (43.90348, 125.34216, "way/227343332", None, None),
    "south_wing": (43.90328, 125.34249, "way/227326613", None, None),
    "jixi":       (43.90359, 125.34239, "way/227326611", None, None),
    "qinmin":     (43.90412, 125.34226, "relation/20216231", None, None),
    "huaiyuan":   (43.90437, 125.34215, "relation/20216230", None, None),
    "jiale":      (43.90447, 125.34263, "way/227328265", None, None),
    "west_garden": (43.90352, 125.34176, "way/227337989", None, None),    # OSM 名「西花园」
    "zhixiu":     (43.90373, 125.34171, "way/227338689", None, None),
    "changchun":  (43.90390, 125.34166, "way/227338688", None, None),
    "gongneifu":  (43.90424, 125.34158, "way/227338002", None, None),
    "racecourse": (43.90339, 125.34013, "way/227339274", None, None),
    "carriage":   (43.90339, 125.34013, "way/227339274",
                   "OSM 无此点；2023 导览把它与跑马场同列为休闲娱乐区，取跑马场",
                   "Not in OSM; the 2023 guide lists it with the racecourse in the leisure area, so the racecourse is used"),
    "locomotive": (43.90339, 125.34013, "way/227339274",
                   "OSM 无此点；2026 导览说在西部区域、2023 导览与跑马场同列，取跑马场",
                   "Not in OSM; the guides place it in the western area with the racecourse, so the racecourse is used"),
    "xunnan":     (43.90339, 125.34013, "way/227339274",
                   "OSM 无此点；2023 导览只说在休闲娱乐区出口外，位置不明，暂取跑马场",
                   "Not in OSM; the 2023 guide only says it is past the leisure-area exit, so the racecourse is used for now"),
    "occupation": (43.90404, 125.34492, "way/227337999", None, None),     # 东北沦陷史陈列馆
}

ENTRANCE = "ticket"
ENTRANCE_NAME = ("售票处（入口）", "Ticket office (entrance)")

# ---------------------------------------------------------------- 站点
# 按参观顺序排列；路线从中选取子集，**顺序不变**（第十节约束 3）。
# (seq, 坐标点, 停留分钟, 停留依据 zh, 停留依据 en, 地点出处, 现状说明 zh, 现状说明 en)
# 现状说明为 None 时，导出直接用库里的在展状态。
STOPS = [
    (36, "tongde", 30,
     "地上地下三层、3707 平方米，二楼另有修缮纪实展",
     "Three storeys incl. basement, 3,707 m², plus a restoration exhibition upstairs",
     "guide2023", None, None),
    (45, "shuhua", 10, "二层小楼，670 平方米",
     "Two-storey building, 670 m²", "guide2023", None, None),
    (40, "east_garden", 15, "约 1 万平方米，院内最大园林",
     "About 10,000 m², the largest garden on site", "guide2023", None, None),
    (42, "pool", 5, "露天遗迹，驻足即可", "Open-air remains, a short stop",
     "guide2023", None, None),
    (41, "shelter", 10, "可进入的地下多室结构", "Walk-through underground rooms",
     "guide2023", None, None),
    (43, "shrine", 5, "仅存基石", "Only the foundations remain", "guide2023", None, None),
    (44, "amaterasu", 5, "防空洞外观与神龛", "Shelter and shrine niche",
     "exhib", None, None),
    (52, "west_wing", 10, "《证人溥仪》展的场地之一（东、西、南厢房共一展）",
     "One of three wings housing the 'Puyi as Witness' exhibition",
     "guide2026",
     "2026 春节导览：《证人溥仪》长期展出", "2026 guide: 'Puyi as Witness', long-term"),
    (53, "south_wing", 10, "《证人溥仪》展的场地之一（东、西、南厢房共一展）",
     "One of three wings housing the 'Puyi as Witness' exhibition",
     "guide2026",
     "2026 春节导览：《证人溥仪》长期展出", "2026 guide: 'Puyi as Witness', long-term"),
    (38, "jixi", 20, "二层寝宫，1325 平方米", "Two-storey residence, 1,325 m²",
     "guide2023", None, None),
    (37, "qinmin", 20, "二层方形圈楼，政务与典礼场所",
     "Two-storey courtyard building used for state ceremonies", "guide2023", None, None),
    (46, "huaiyuan", 10, "一楼奉先殿等（二楼清宴堂另计）",
     "Ground-floor ancestral hall etc. (upstairs exhibition counted separately)",
     "guide2023", None, None),
    (51, "huaiyuan", 20, "145 件文物", "145 objects", "article3263", None, None),
    (35, "jiale", 45, "展厅 680 平方米、展线 240 米、照片 421 张、文物 260 余件",
     "680 m² hall, 240 m display line, 421 photos, 260+ objects",
     "guide2026",
     "2026 春节导览：嘉乐殿，长期展出；2026 年在招标改陈设计（三次流标）",
     "2026 guide: Jiale Hall, long-term; a redesign tender was issued in 2026 (failed three times)"),
    (47, "west_garden", 10, "2200 平方米", "2,200 m²", "guide2023", None, None),
    (48, "zhixiu", 5, "单层小轩", "Small single-storey pavilion", "guide2023", None, None),
    (49, "changchun", 5, "单层小轩", "Small single-storey pavilion", "guide2023", None, None),
    (50, "gongneifu", 10, "四合院式小院", "Courtyard compound", "guide2023", None, None),
    (55, "carriage", 10, "车库陈列", "Garage display", "guide2023",
     "仅 2023 导览列出，现状未核实", "Listed only in the 2023 guide; current status unverified"),
    (56, "locomotive", 10, "单件大型蒸汽机车", "A single large steam locomotive",
     "guide2026", "2026 春节导览：长期展出", "2026 guide: long-term"),
    (57, "racecourse", 5, "露天场地", "Open-air ground", "guide2023",
     "仅 2023 导览列出，现状未核实", "Listed only in the 2023 guide; current status unverified"),
    (58, "xunnan", 15, "茶室、文创与二楼书画展",
     "Tea room, shop and an upstairs painting exhibition", "guide2023",
     "仅 2023 导览列出，现状未核实", "Listed only in the 2023 guide; current status unverified"),
    (59, "occupation", 45, "照片 560 张、文物 348 件，地上一层与地下一层",
     "560 photos and 348 objects on Floor 1 and the basement",
     "guide2026", "2026 春节导览：陈列馆一楼，长期展出",
     "2026 guide: Floor 1, long-term"),
    (60, "occupation", 40, "照片 320 余张、文物 350 件",
     "320+ photos and 350 objects", "guide2026",
     "2026 春节导览：陈列馆二楼，长期展出", "2026 guide: Floor 2, long-term"),
    (61, "occupation", 20, "规模不明，按小型专题陈列估",
     "Size unknown; estimated as a small themed display", "guide2023",
     "2023 导览列出，2026 春节导览未再提及，现状未核实",
     "Listed in the 2023 guide but not in the 2026 guide; current status unverified"),
]

# 并入另一站、不单独计值的节点（第十节约束 2：父级与子节点不重复计算价值）
MERGED = {
    54: (35, "嘉乐殿就是《从皇帝到公民》的展厅（2026 春节导览），殿与展只算一次，按展计",
         "Jiale Hall is the venue of 'From Emperor to Citizen' (2026 guide); "
         "hall and exhibition are counted once, as the exhibition"),
}

# 位置不明、排不进路线的节点
UNPLACED = {
    39: ("官网与两篇导览都没写展在哪栋楼",
         "Neither the website nor either guide says which building it is in"),
}

# 时间预算（分钟）：只算停留与步行，不含排队、安检、午餐
BUDGETS = [
    ("2h", 120, "2 小时", "2 hours"),
    ("half", 240, "半日（4 小时）", "Half day (4 hours)"),
    ("full", 420, "全日（7 小时）", "Full day (7 hours)"),
]

OPENING = ("08:30 开馆，16:30 停票，17:30 闭馆（2026 春节导览）",
           "Opens 08:30, last entry 16:30, closes 17:30 (2026 guide)")
