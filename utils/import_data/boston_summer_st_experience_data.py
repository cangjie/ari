"""Prepare proposed Boston routes; publication is gated on source and media review."""
import json
from pathlib import Path

from boston_summer_st_draft_walks import ROUTES, STREETS
import boston_summer_st_list as inventory

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'
STATIONS=[
    {'id':'park','name':'Park Street 站 · Boston Common 出口','lines':['Red','Green'],
     'lines_label':'红线 / 绿线','gtfs_stop_id':'door-pktrm-tremontw','place':'place-pktrm'},
    {'id':'downtown','name':'Downtown Crossing 站 · Summer Street 出口','lines':['Red','Orange'],
     'lines_label':'红线 / 橙线','gtfs_stop_id':'door-dwnxg-summer','place':'place-dwnxg'},
    {'id':'courthouse','name':'Courthouse 站 · Seaport Boulevard 出口','lines':['Silver'],
     'lines_label':'银线','gtfs_stop_id':'door-crtst-north','place':'place-crtst'},
    {'id':'silver','name':'Silver Line Way 站','lines':['Silver'],
     'lines_label':'银线','gtfs_stop_id':'place-conrd','place':'place-conrd'},
]
STAY={2:20,3:15,4:10,5:15,6:15,7:10,8:10,9:15,10:15,11:5,12:20,19:10,
      20:15,21:5,22:15,24:15,27:20,31:10,32:15,36:10,45:15,46:10,47:10,50:10,52:20}
NOTES={
    2:'从公共步道看历史公园，室外活动以现场安排为准。',
    3:'从公共街道观看州议会大厦外观，入内须另核开放安排。',
    4:'在公共街道观看教堂外观，入内另核。',
    5:'从墓地外围或开放区域参观，开放与维护安排另核。',
    6:'教堂与墓地的入内安排分别核实。',
    7:'看旧校址标识及富兰克林雕像。',
    8:'观看历史建筑外观；旧名不表示现为书店。',
    9:'从街道识别历史会议厅，入馆购票与开放安排另核。',
    10:'观看老州议会大厦外观，参观展览另核。',
    11:'留意街道纪念标记，过街遵守现场信号。',
    12:'看法尼尔厅外观及周边公共空间。',
    19:'从 Summer Street 一侧看南站历史站房。',
    20:'从公共街道观察 Fort Point 旧仓库与街区肌理。',
    21:'在附近公共街道辨认波士顿码头公司历史标牌。',
    22:'在桥和公共区域观看倾茶博物馆与水道；入馆另核。',
    24:'从公共公园与滨水步道观景。',
    27:'从公共滨水区域看当代艺术学院；参观展览另核。',
    31:'经过 Summer Street Steps；如有封闭按现场指示绕行。',
    32:'沿 Harbor Way 公共步行空间前往海港。',
    36:'烘焙咖啡可按需选购；营业状态当日核实。',
    45:'美食广场可按需用餐；营业与档口安排当日核实。',
    46:'Fort Point 面包咖啡店；营业状态当日核实。',
    47:'海鲜餐厅；营业与预约当日核实。',
    50:'450 Summer Street 餐厅；营业与预约当日核实。',
    52:'Harpoon 波士顿酒厂；营业、参观与年龄要求当日核实。',
}


def main():
    sources={'title':'MBTA 官方站点信息','url':'https://www.mbta.com/stops/'}
    for station in STATIONS:
        station['source']={'title':station['name'],'url':'https://www.mbta.com/stops/'+station['place']}
        station['position_source']={'title':'MBTA 官方 GTFS 停站和入口资料','url':'https://cdn.mbta.com/MBTA_GTFS.zip'}
    common={'fee':'公共街道和外观游览不含入馆票；餐饮及交通自理。',
            'access':'开放、购票、营业、过街及出入口以现场与运营方公告为准。',
            'sources':[sources]}
    defs=[
        {'id':'sightseeing','name':'纯观光路线','description':'自由之路市中心站点、南站、Fort Point 和海港滨水。',
         'default_start':'park','start_stations':['park'],'end_station':'courthouse','optional_shops':[]},
        {'id':'food','name':'观光＋美食路线','description':'从市中心到海港，把历史景点与面包、海鲜、美食广场和酒厂串起来。',
         'default_start':'downtown','start_stations':['downtown'],'end_station':'silver','optional_shops':[48,51,53]},
    ]
    themes=[]
    for item in defs:
        draft=ROUTES[item['id']]
        themes.append({**common,**item,'steps':[
            {'seq':s,'minutes':STAY[s],'note':NOTES[s],'streets':STREETS[s],'related':[21] if s==20 else []}
            for s in draft['steps']]})
    labels={'policy':'分类只描述经营类别，不代表餐饮口味、质量或价格。','items':[
        {'seq':seq,'identity_key':row['id'].lower(),'category':row['kind'],'tags':[],
         'reason':'依据该条资料中的经营类别整理；实时营业状态请另核。'}
        for seq,row in enumerate(inventory.rows,1) if row['id'].startswith('S')]}
    manifest={'checked_on':'2026-11-03','state':'draft_not_for_publication',
              'labels_file':KEY+'_shop_labels.json','osm_file':KEY+'_osm.json',
              'transit_file':KEY+'_mbta_stops.json','stations':STATIONS,'themes':themes,
              'itinerary_map_brand':'波士顿 Summer Street',
              'itinerary_exit_note':'时长未计用餐和排队。车站出口及临时封闭以现场为准。',
              'itinerary_spread_markers':True,
              'policy':'距离依据已保存的公开街道资料估算；出入口、过街、封路及可达性以现场为准。用餐、排队与购票时间另计。',
              'navigation_policy':'路线提示公共街道附近而非入口。GPS 精度较低时不新增到达提醒；路径和通行条件以现场为准。'}
    (HERE/(KEY+'_shop_labels.json')).write_text(json.dumps(labels,ensure_ascii=False,indent=2)+'\n','utf-8')
    (HERE/(KEY+'_experience.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('Two fixed-start itinerary definitions saved as draft')


if __name__=='__main__':main()
