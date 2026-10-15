"""宛平城馆桥城园的人工策划路线。时间是估计；资料不写生产业务表。

OSM几何见wanping_osm_data.json，原始HTTP响应另存XML。城门方位按官方原文，
OSM西门节点误标顺治门，不采用其名称。没有单独位置的内容归入所属整体。
"""
DATA_PACKAGE = 'wanping_final.json'
TRANSLATIONS = 'wanping_translations.json'
ACCESS = 'wanping_access.json'
TOUR_TRANSLATIONS = 'wanping_tour_translations.json'
ATTACHMENT_NOTE = ' 本条随所属整体阅读；地图仅标出整体或所属区域，不代表单件、室内分区的精确位置。'

# id, 地点中文/英文, OSM定位依据, 热区半径米, 标签朝向, 本地点资料序号。
# 园区采用西侧公共道路节点作为到达点，不把园中心当作入口。
PLACES = [
    ('east_gate', '顺治门（东门）', 'Shunzhi Gate (east)', 'node/296346557', 35, 'r', [2, 1, 5]),
    ('war_museum', '中国人民抗日战争纪念馆', 'War of Resistance Memorial', 'node/296346725', 35, 't', list(range(19, 30))),
    ('square', '宛平广场', 'Wanping Square', 'way/1052576120', 30, 'b', [30]),
    ('main_street', '宛平大街', 'Wanping Main Street', 'node/296346512', 25, 't', list(range(7, 13))),
    ('west_gate', '永昌门（西门）', 'Yongchang Gate (west)', 'node/296346505', 30, 't', [3, 6, 4, 13]),
    ('bridge', '卢沟桥', 'Lugou Bridge', 'node/296346558', 35, 'l', [14, 15, 16, 17, 18, 39]),
    ('sculpture_park', '抗战雕塑园（西侧到达点）', 'Memorial Sculpture Park (west approach)', 'node/8278912752', 35, 'b', list(range(31, 39))),
]
ENTRANCE = 'east_gate'
ENTRANCE_NAME = ('东门出发 / 返回', 'Start / finish at the east gate')
# 资料的计时归属，0分钟表示时间已包含在整体里；不是额外的路线站。
INCLUDED_IN = {1: 2, 19: 20, **{s: 20 for s in range(21, 30)},
               **{s: 7 for s in range(8, 13)}, 13: 3,
               **{s: 14 for s in [15, 16, 17, 18, 39]},
               **{s: 31 for s in range(32, 39)}}
DWELL = {2: 5, 5: 10, 20: 90, 30: 5, 7: 15, 3: 5, 6: 10, 4: 35, 14: 40, 31: 40}
ROUTES = [
    dict(id='free', label=('免费线', 'Free route'), budget=270,
         stops=[2, 5, 20, 30, 7, 3, 6, 31], ticket_cny=0,
         fee=('门票 0 元', 'Admission CNY 0'),
         note=('城内街巷、城门外观、地面弹痕、抗战馆与雕塑园；不登城墙、不进入卢沟桥收费区。县衙等沿街建筑只看外观，不假定室内免费开放。',
               'Public streets, gate exteriors, shell scars from ground level, the memorial and sculpture park. No paid wall-top or bridge admission; other street-side buildings are exterior visits only.')),
    dict(id='full', label=('全面线', 'Comprehensive route'), budget=390,
         stops=[2, 5, 20, 30, 7, 3, 6, 4, 14, 31], ticket_cny=50,
         fee=('成人门票参考约 50 元（登城 30 + 卢沟桥 20）', 'Reference adult admission about CNY 50 (wall 30 + bridge 20)'),
         note=('免费线基础上增加西城墙登城和卢沟桥桥面、石狮、碑刻。登城从西侧入口往返，按开放段行走；不承诺整圈城墙可通行。卢沟桥历史博物馆当前开放及联票待现场确认，未计入必访和时长。',
               'Adds the west wall-top and bridge, lions and stelae. Return to the west wall entrance and follow the sections actually open. The bridge history museum is optional, subject to confirmation, and not timed.')),
]
# 路线间步行沿OSM公开道路求最短路；园内游览和登城往返包含在停留估计。
WALK_M_PER_MIN = 60
CONNECTOR_MAX_M = 90
DENIED_WAYS = {27035588, 27035590, 27035592}  # 城墙上步道不充当地面穿行捷径
PAID_WAYS = {27035564}  # 卢沟桥桥面
ALLOW_HIGHWAYS = {'footway', 'pedestrian', 'path', 'steps', 'residential', 'service', 'tertiary', 'unclassified', 'living_street'}
STATUS = {4: '登城另购票，西侧入口往返；只走当天开放段。',
          6: '地面环城步道，不等于收费的城墙顶部；按现场开放路段行走。',
          8: '复建建筑；本路线仅作外观经过，室内开放和收费待现场确认。',
          13: '2025年展讯；当前是否延续、开放与收费未核实，不作必访。',
          14: '进入桥面收费区需购票；免费线不入内。',
          19: '免费安检入馆；常规周一闭馆。半景画须另预约。',
          20: '基本陈列及九个组成部分合计建议90分钟，馆内按现场动线参观。',
          31: '免费园区；园内游览已计40分钟，分区及单件按现场标识寻找。',
          39: '只有官方索引资料；当前开放及是否随卢沟桥票参观待现场确认，不计必访。'}
STATUS.update({s: '本路线仅作外观经过；室内开放与收费待现场确认。' for s in range(9, 13)})
DEFAULT_STATUS = '参观现状以现场公告为准。'
