"""主题路线的编辑选择与接驳依据；道路、距离和分钟数由构建器计算。"""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='nanluo_shichahai'


def main():
    def write(suffix,value):
        (HERE/f'{KEY}_{suffix}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    package=json.loads((HERE/f'{KEY}_final.json').read_text())
    identities={r['source_seq']:r['identity_key'] for r in package['rows']}
    model=json.loads((HERE/f'{KEY}_shop_labels_model.json').read_text())
    write('shop_labels',dict(checked_on='2026-10-24',model=model['model'],effort=model['effort'],
          policy='分类表示经营内容，标签表示商品或空间特色。文艺为编辑标签；经济实惠仅用于有不超过35元人均快照的小吃简餐，非实时价格，也不是服务质量评级。邻近中戏不等于便宜、可进入校园或能见到演员。',
          items=[dict(r,identity_key=identities[r['seq']])for r in model['result']['items']]))
    station_source=dict(title='北京地铁官方网站 · 线路与站点',url='https://www.bjsubway.com/station/xltcx/line6/2013-08-23/133.html')
    stations=[
       dict(id='nanluo',name='南锣鼓巷站 E口',lines=[6,8],osm_node=4400766341,source=station_source),
       dict(id='shichahai',name='什刹海站 A2口',lines=[8],osm_node=8805687980,source=station_source),
       dict(id='beihai',name='北海北站 B口',lines=[6],osm_node=13239733934,source=station_source),
       dict(id='gulou',name='鼓楼大街站 G口',lines=[2,8],osm_node=4253043927,source=station_source),
    ]
    for station in stations:
        pages={'nanluo':'line8/2013-12-27/377.html','shichahai':'line8/2013-12-27/376.html?sk=1','beihai':'line6/2013-08-23/132.html','gulou':'line8/2013-12-27/375.html?sk=1'}
        station['source']=dict(title='北京地铁官方网站 · '+station['name'],url='https://www.bjsubway.com/station/xltcx/'+pages[station['id']])
        station['position_source']=dict(title='OpenStreetMap · 地铁出入口',url=f'https://www.openstreetmap.org/node/{station["osm_node"]}')
    def step(seq,minutes,note,streets=None,related=None):
        street_names={1:['南锣鼓巷'],4:['雨儿胡同'],5:['帽儿胡同'],11:['板厂胡同'],12:['东棉花胡同'],16:['后圆恩寺胡同'],17:['菊儿胡同'],36:['银锭桥'],40:['荷花市场'],41:['烟袋斜街']}
        if streets is None:streets=street_names[seq]
        return dict(seq=seq,minutes=minutes,note=note,streets=streets,related=related or [])
    pgm=dict(title='恭王府博物馆 · 门票参考（页面更新2022-06-06）',url='https://en.pgm.org.cn/2022-06/06/c_759193.htm')
    song=dict(title='北京宋庆龄故居 · 参观时间与票价',url='https://www.sql.org.cn/')
    themes=[
      dict(id='classic',name='经典游览线路',default_start='nanluo',end_station='beihai',
           description='第一次来：胡同肌理、烟袋斜街与银锭桥，再看王府和前海。',
           fee='门票参考40元（恭王府入馆）；餐饮、购物、交通另计。不入馆可改门外停留10分钟，较本方案减少约110分钟。',
           access='恭王府入馆须提前查看预约及当日公告；未约到或闭馆时只看外围。其他站按公共街巷或外观安排。',
           sources=[pgm],optional_shops=[85,86,95,96],steps=[
             step(1,30,'从南口感受主街；街道仍承担日常生活功能。'),
             step(5,20,'从公共街巷看院落肌理；不进入可园、婉容旧居等未确认开放院落。'),
             step(41,20,'沿街看老街空间与特色店铺。'),
             step(36,15,'桥上观景，避让行人与车辆。'),
             step(59,120,'预约后进馆；内部组成节点不逐一重复累加时间。',['前海西街','柳荫街']),
             step(48,15,'故居门外识别；若入馆，另查预约、票价并增加时间。',['前海西街']),
             step(40,20,'沿公共湖岸步行，结束后接驳北海北站。'),
           ]),
      dict(id='arts',name='文艺观光线路',default_start='nanluo',end_station='shichahai',
           description='围绕中戏东城校区周边、手作设计小店与文学艺术旧居，慢逛胡同。',
           fee='基础行程不安排收费入馆，门票预算0元。咖啡、正餐和文创按需消费，不设最低消费承诺。',
           access='中戏只在校门外与公共街道观看，不承诺游客入校。茅盾、齐白石旧居列为沿途可选；入馆另核开放安排与具体入口。未定位商铺不设独立导航点。',
           sources=[],optional_shops=[87,88,89,90,91,92,93,94,99],steps=[
             step(11,15,'板厂胡同街景。'),
             step(18,10,'了解僧王府府址与侣松园宾馆的关系；不进入宾馆客房或其他在用院落。',['板厂胡同','炒豆胡同','南锣鼓巷']),
             step(12,15,'漫步东棉花胡同。'),
             step(31,10,'校门外了解戏剧教育背景；校园并非默认开放景点。',['东棉花胡同']),
             step(1,55,'主街文创与手作橱窗慢逛；小店位置以门牌和现场招牌核对。',related=[90,91,92,93,94]),
             step(16,25,'公共街巷与文学记忆；茅盾故居可按当天开放情况加访。',related=[23]),
             step(4,25,'雨儿胡同与齐白石旧居周边；未确认开放时只走公共街道。',related=[22]),
           ]),
      dict(id='history',name='历史探索线路',default_start='beihai',end_station='gulou',
           description='从清代王府到近现代人物，再到寺院与城门，串联什刹海的历史层次。',
           fee='成人门票参考60元：恭王府40元、宋庆龄故居20元；以各自票务系统为准，优惠另核。餐饮、交通另计。',
           access='恭王府与宋庆龄故居均应提前核实预约和当日公告；宋庆龄故居官网列周二至周日9:00—17:00、周一闭馆，16:20停止售票。闭馆改外观，不在未开放院落内穿行。广化寺只安排门外识别，不承诺宗教活动或入内。',
           sources=[pgm,song],optional_shops=[95,97],steps=[
             step(59,120,'清代王府建筑与花园；看整体，内部节点时间不重复相加。',['前海西街','柳荫街']),
             step(48,15,'郭沫若故居门外识别；入馆另核安排。',['前海西街']),
             step(49,60,'预约或购票后参观宋庆龄故居，范围限原西花园。',['后海北沿']),
             step(44,15,'广化寺外观与寺院沿革，不把历史记载当今日入内许可。',['鸦儿胡同']),
             step(50,10,'从公共街巷识别醇亲王府北府，区别于已改作宋庆龄故居的西花园。',['后海北沿']),
             step(57,15,'箭楼外观与老城城门；不含登楼、室内陈列。',['德胜门内大街','德胜门东大街','德胜门西大街']),
           ]),
      dict(id='budget',name='穷游线路',default_start='shichahai',end_station='nanluo',
           description='公共湖岸、桥梁、老街和钟鼓楼外观；步行串联，不安排必须购买的项目。',
           fee='必选门票0元；不含登钟鼓楼、王府或故居收费区、游船、冰场、演出。可自带水；一顿简餐可按30—40元预留个人预算，这是估算，非店铺报价。',
           access='只走公共街道、湖岸与桥梁；不将“从外面看”说成可以免费入馆。人均27元与28元分别是方砖厂、护国寺小吃的历史平台快照，现场价格另核。',
           sources=[],optional_shops=[86,98],steps=[
             step(40,15,'前海公共湖岸。'),step(36,10,'银锭桥与湖面景观。'),
             step(41,20,'烟袋斜街逛街，消费自选。'),step(43,10,'火德真君庙门外识别。',['地安门外大街']),
             step(61,15,'鼓楼外观，不购登楼票。',['鼓楼东大街','鼓楼西大街','地安门外大街']),
             step(62,10,'从钟楼湾胡同看钟楼外观，不进围墙内、不登楼。',['钟楼湾胡同']),step(17,15,'菊儿胡同街景。'),
             step(16,15,'后圆恩寺胡同公共街段。'),step(4,15,'雨儿胡同公共街段。'),
             step(1,20,'沿南锣鼓巷返回地铁站。'),
           ]),
    ]
    write('experience',dict(checked_on='2026-10-24',labels_file=f'{KEY}_shop_labels.json',osm_file=f'{KEY}_osm_data.json',
          policy='四条主题步行方案均可选6号线/8号线周边四个地铁起点；更换起点只改变到首站的接驳，景点次序不变。选择主题线路可开始GPS导览，查看当前位置并在靠近已记录的街道参考点时提示到达附近。地图为已记录公共道路的步行示意，过街及出入口以现场人行设施为准。距离依据OSM，步行按60米/分估算；停留、排队、购票、交通衔接均有个体差异，所列总时长未计用餐和排队。路线到场所附近公共街道参考点，并非检票入口。地铁出口编号取自OSM，临时封闭以现场为准。',
          stations=stations,themes=themes))


if __name__=='__main__':main()
