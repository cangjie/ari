"""伪满皇宫博物院（wmhg）手机导览页的静态配置：地图范围、画布朝向、各地点叫什么。

由 tour_osm_fetch.py 与 tour_build.py 读取。参观顺序、坐标、停留时间**不在这里**，
在 wmhg_route_data.py；评级、名称、介绍、在展状态在库里。这里只放导览页独有、
别处又没有的东西。

**哪些是事实，哪些是取舍：**

- OSM 要素编号：2026-10-10 用 Overpass 核对过，原始几何在 wmhg_osm_data.json。
- 画布朝向与比例：取舍。照原型把北朝右、院区竖着放，手机竖屏才放得下
  （院区东西约 600 米、南北约 300 米）。
- 地点名称：一律取库里某个节点的名称或它的展厅名，这里只登记「取哪一个」，不另写名字。
- 目的地卡片的一句话介绍：原型里的文案，不是馆方原文。
"""

# ---------------------------------------------------------------- OSM
# (南, 西, 北, 东)。比院区边界每边多出约 60 米，把光复路与东侧陈列馆都框进来。
OSM_BBOX = (43.9012, 125.3378, 43.9054, 125.3464)

# 院区边界：OSM 上 tourism=attraction、名为「伪满皇宫博物院」的那个面。
# 「在不在景区范围内」按它外扩 AREA_BUFFER_M 米判定。
BOUNDARY = "way/227373465"
AREA_BUFFER_M = 30

# ---------------------------------------------------------------- 画布
# 画布 = 以 ORIGIN 为中心的本地平面坐标（东、北，单位米）旋转 ROTATE_DEG 后按比例放大。
# ROTATE_DEG 是「北」在画布上相对正上方顺时针转过的角度，也就是指北针的转角。
# 取 101.5：院内主体建筑的长边方位角是 78.5 度（OSM 轮廓按边长加权，这一组占 43%；
# 另有一组 8.5 度的占 19%，是西侧后建的那几栋）。转 101.5 度之后主体建筑横平竖直、
# 北朝右略偏下，与原型的摆法一致。tour_build.py 每次生成都会重算这个角度并打印偏差。
ORIGIN = (43.9035, 125.3421)
ROTATE_DEG = 101.5
PX_PER_M = 1.72            # 原型是 0.58 米/像素
CANVAS_MARGIN_PX = 40      # 范围多边形到画布边缘留的白

# ---------------------------------------------------------------- 地点
# 每个坐标点（wmhg_route_data.POINTS 的键）在地图上叫什么、标签放在标记的哪一侧。
# 名称来源：("node", 序号) 取库里那个节点的名称；("gallery", 序号) 取那个节点所在展厅的名称。
# 标签朝向：b 下、t 上、r 右、l 左，只为避开相邻的标记，没有别的含义。
# 一个点上有好几站时（怀远楼、陈列馆），地点叫建筑的名字，各站列在介绍里。
PLACES = {
    "tongde":      (("node", 36), "b"),
    "shuhua":      (("node", 45), "r"),
    "east_garden": (("node", 40), "t"),
    "shelter":     (("node", 41), "r"),
    "shrine":      (("node", 43), "b"),
    "amaterasu":   (("node", 44), "l"),
    "west_wing":   (("node", 52), "t"),
    "south_wing":  (("node", 53), "l"),
    "jixi":        (("node", 38), "r"),
    "qinmin":      (("node", 37), "b"),
    "huaiyuan":    (("node", 46), "t"),
    "jiale":       (("node", 54), "r"),       # 嘉乐殿；《从皇帝到公民》是殿里的展
    "west_garden": (("node", 47), "l"),
    "zhixiu":      (("node", 48), "t"),
    "changchun":   (("node", 49), "b"),
    "gongneifu":   (("node", 50), "t"),
    "racecourse":  (("node", 57), "b"),
    "occupation":  (("gallery", 59), "b"),    # 东北沦陷史陈列馆；三个陈列共用这栋楼
}

# 坐标是借用的那几站（wmhg_route_data.POINTS 里写了借用说明的）不单独成点，列在所借地点的
# 介绍里，并把下面这句话给游客看。路线数据里的借用说明是写给排路线的人看的
#（「OSM 无此点…取花园中心」），这里是同一个事实换成游客的说法。每一站都要有，缺了报错。
BORROWED_NOTE = {
    42: ("馆方导览说游泳池在东御花园内；具体位置未核实，地图上没有单独标出。",
         "The museum guide places the pool inside the East Garden; its exact position is "
         "unverified and it is not marked separately on the map."),
    55: ("2023 年导览把它与御用跑马场同列在休闲娱乐区；具体位置未核实，地图上没有单独标出。",
         "The 2023 guide lists it with the racecourse in the leisure area; its exact position is "
         "unverified and it is not marked separately on the map."),
    56: ("馆方导览说它在皇宫西部，与御用跑马场同在休闲娱乐区；具体位置未核实，地图上没有单独标出。",
         "The guides place it in the western area with the racecourse; its exact position is "
         "unverified and it is not marked separately on the map."),
    58: ("2023 年导览只说它在休闲娱乐区出口外；具体位置未核实，地图上没有单独标出。",
         "The 2023 guide only says it is past the leisure-area exit; its exact position is "
         "unverified and it is not marked separately on the map."),
}

# 介绍文字的出处，按库里 artwork.official_url 判断。(网址片段, 中文, 英文)，从上往下取第一个匹配的；
# 一个都不匹配就报错。注意这与路线数据里的「地点出处」不是一回事 ——
# 那一列说的是「这一站在哪儿」从哪来，这里说的是「这段介绍」从哪来。
INTRO_SOURCES = [
    ("/exhib/detail/", "伪满皇宫博物院官网 · 常设展览", "Museum website, permanent exhibitions"),
    ("/detail/3263.", "伪满皇宫博物院官网 · 2026 年 1 月展讯", "Museum website, exhibition notice (Jan 2026)"),
    ("/detail/2657.", "伪满皇宫博物院官网 · 2023 年参观导览", "Museum website, 2023 visitor guide"),
]

# 地图上另外标出名字的 OSM 要素（不是热区，只是帮人认方向）。(要素, 中文, 英文)
# 入口（售票处）不在这里：它的名字取 wmhg_route_data.ENTRANCE_NAME。
LANDMARKS = [
    ("way/227343333", "同德门", "Tongde Gate"),
    ("way/227326616", "中和门", "Zhonghe Gate"),
]
# 院外道路的名字，沿路标一次。(OSM 名称, 英文)
ROADS = [("光复路", "Guangfu Rd")]

# ---------------------------------------------------------------- 目的地卡片
CARD = {
    "city": ("长春", "Changchun"),
    "district": ("宽城区", "Kuancheng"),
    "type": ("宫廷遗址", "Palace site"),
    "short": ("伪满皇宫", "Manchukuo Palace"),
    "desc": ("伪满洲国傀儡皇帝溥仪的宫廷旧址，今为伪满皇宫博物院，"
             "是日本侵占中国东北十四年历史的见证。",
             "The former palace of Puyi, puppet emperor of Manchukuo, now a museum "
             "bearing witness to Japan's fourteen-year occupation of Northeast China."),
    "hours": "08:30–17:30",
    "hours_note": ("16:30 停止售票", "Last entry 16:30"),
    "cover_seq": 36,           # 卡片照片用哪个节点的官网图片（同德殿）
}

# 默认选中的路线：(时间预算的键, 选站规则)，同原型
DEFAULT_ROUTE = ("2h", "utility")
