"""南锣鼓巷及什刹海已审清单的展示配置。"""
# 与当前Excel复用同一个平台快照提取器，不重新推断星级、价格或营业。
from nanluo_shichahai_export_data import platform_reference

VIEW_MODE = 'collection'
STATUS_EN = {
    '当前开放未核实；历史安排不作实时承诺': 'Current access is unverified; historical arrangements are not a live opening guarantee.',
    '平台/文旅网页有记录；现场营业、菜单、价格及体验项目未实时核实': 'Live business status, menu, prices and activities are unverified.',
}
NAME = dict(zh='北京南锣鼓巷及什刹海', en='Beijing Nanluoguxiang and Shichahai')
CARD = dict(
    city=dict(zh='北京', en='Beijing'), district=dict(zh='东城 · 西城', en='Dongcheng · Xicheng'),
    type=dict(zh='胡同 · 湖畔 · 特色商铺', en='Hutongs, lakes and specialty shops'),
    short=dict(zh='南锣鼓巷 · 什刹海', en='Nanluoguxiang · Shichahai'),
    desc=dict(zh='从南锣鼓巷的街巷与旧居，到什刹海的湖岸、王府与纪念馆，收录84条文化参观点和16家特色商铺。',
              en='Explore 84 cultural places and 16 specialty shops across Nanluoguxiang and Shichahai.'),
    hours='各场所开放及门店营业时间请出行前核实',
    hours_note=dict(zh='查看介绍、评级与来源', en='Browse introductions, ratings and sources'),
)
OPENING = dict(zh='各场所开放、预约、收费及门店营业时间请出行前核实；历史报道和平台快照不代表今日状态。',
               en='Check access, reservations, admission and shop hours before visiting; historical reports and platform snapshots are not live information.')
PLANNING = dict(zh='100条资料包含整体与组成部分，并非100个互不重叠的路线站点。当前提供清单浏览，地图坐标与路线尚未核实。商铺的S/A/B/C评级衡量文化与参观价值，平台口碑与消费信息另列。',
                en='The 100 records include wholes and their components, rather than 100 separate itinerary stops. Browse the collection; map positions and routes are unverified. Shop tiers measure cultural and visit value; platform reputation and spending information are shown separately.')
