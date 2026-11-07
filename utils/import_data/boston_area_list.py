"""Curated candidate inventory and bilingual review workbook for Greater Boston."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill


AS_OF = date(2026, 11, 7)
HERE = Path(__file__).resolve().parent
OUT = HERE / "exports" / "波士顿及周边景点_双语清单.xlsx"

MEET_BOSTON = "https://www.meetboston.com/explore/neighborhoods/"
NEIGHBORHOODS = [
    ("Allston", "奥尔斯顿"),
    ("Back Bay", "后湾"),
    ("Beacon Hill", "灯塔山"),
    ("Brighton", "布莱顿"),
    ("Charlestown", "查尔斯敦"),
    ("Chinatown / Theatre District", "唐人街／剧院区"),
    ("Dorchester", "多切斯特"),
    ("Downtown / Financial District", "市中心／金融区"),
    ("East Boston", "东波士顿"),
    ("Fenway–Kenmore", "芬威—肯莫尔"),
    ("Hyde Park", "海德公园"),
    ("Jamaica Plain", "牙买加平原"),
    ("Mattapan", "马塔潘"),
    ("Mission Hill", "使命山"),
    ("North End", "北端"),
    ("Roslindale", "罗斯林代尔"),
    ("Roxbury", "罗克斯伯里"),
    ("Seaport District", "海港区"),
    ("South Boston", "南波士顿"),
    ("South End", "南端"),
    ("Waterfront", "海滨"),
    ("West End", "西端"),
    ("West Roxbury", "西罗克斯伯里"),
]
ZONE_NEIGHBORHOOD = {
    "Boston Common": {"Downtown / Financial District"},
    "Back Bay": {"Back Bay"},
    "Downtown": {"Downtown / Financial District"},
    "Downtown / North End / Charlestown": {"Downtown / Financial District", "North End", "Charlestown"},
    "Beacon Hill": {"Beacon Hill"},
    "Fenway–Kenmore": {"Fenway–Kenmore"},
    "Jamaica Plain": {"Jamaica Plain"},
    "Roxbury / Dorchester / Jamaica Plain": {"Roxbury", "Dorchester", "Jamaica Plain"},
    "Roxbury": {"Roxbury"},
    "South End": {"South End"},
    "South Boston": {"South Boston"},
    "Downtown / Waterfront": {"Downtown / Financial District", "Waterfront"},
    "Waterfront / Seaport / East Boston": {"Waterfront", "Seaport District", "East Boston"},
    "Seaport": {"Seaport District"},
    "South Boston Waterfront": {"South Boston", "Waterfront"},
    "East Boston": {"East Boston"},
    "Mattapan": {"Mattapan"},
    "West Roxbury": {"West Roxbury"},
    "Brighton": {"Brighton"},
    "Harvard Square / Cambridge": set(),
    "Kendall Square / Cambridge": set(),
    "Cambridge": set(),
    "Salem": set(),
    "Lexington / Lincoln / Concord": set(),
    "Concord": set(),
    "Lexington": set(),
    "Quincy": set(),
    "North End / Downtown": {"North End", "Downtown / Financial District"},
    "North End": {"North End"},
    "South End / Boston": {"South End"},
}


def item(
    key: str,
    zone: str,
    kind: str,
    zh: str,
    en: str,
    zh_desc: str,
    en_desc: str,
    address: str,
    relation: str,
    access: str,
    source: str,
    source_name: str,
    note: str = "",
) -> dict:
    return {
        "id": key,
        "zone": zone,
        "kind": kind,
        "zh": zh,
        "en": en,
        "zh_desc": zh_desc,
        "en_desc": en_desc,
        "address": address,
        "relation": relation,
        "access": access,
        "source": source,
        "source_name": source_name,
        "note": note or "候选条目；须捕获来源正文并复核身份、地址和访问边界后方可发布。",
    }


rows = [
    item("boston_common", "Boston Common", "公园", "波士顿公园", "Boston Common",
         "波士顿历史公园，适合作为市中心步行游览的公共绿地；季节性设施以现场公告为准。",
         "Historic Boston park and public green space for a downtown walk; check on-site notices for seasonal facilities.",
         "Boston Common", "市中心历史区", "室外公共空间；设施开放情况另核",
         "https://www.boston.gov/parks/boston-common", "City of Boston"),
    item("public_garden", "Back Bay", "公园", "波士顿公共花园", "Boston Public Garden",
         "美国早期公共植物园之一，园内有花园景观、雕塑与天鹅船等设施；季节和运营时间须另核。",
         "An early American public botanical garden with landscaped paths, monuments and seasonal attractions; check current operations.",
         "Boston Public Garden", "市中心步行衔接", "公共花园；天鹅船等设施另核",
         "https://www.boston.gov/parks/public-garden", "City of Boston"),
    item("freedom_trail", "Downtown / North End / Charlestown", "古迹", "自由之路", "Freedom Trail",
         "由红线串联的城市历史步行路线；各站点的室内开放、门票与路线状况分别核对。",
         "A red-lined urban history route; verify indoor access, tickets and conditions separately at each site.",
         "Boston and Charlestown", "区域步行路线", "公共街道步行；沿线场馆另核",
         "https://www.thefreedomtrail.org/trail-sites", "Freedom Trail Foundation",
         "路线与组成站点分开建档；不把全线与单站视为互不重叠地点。"),
    item("massachusetts_state_house", "Beacon Hill", "建筑", "马萨诸塞州议会大厦", "Massachusetts State House",
         "位于灯塔山一带的州议会大厦；建筑外观可从公共区域观察，入内参观须按官方安排。",
         "The Massachusetts state capitol on Beacon Hill; view the exterior from public areas and check official arrangements for interior visits.",
         "24 Beacon St, Boston", "自由之路相关", "外观可见；入内与导览另核",
         "https://malegislature.gov/StateHouse/Tours", "Massachusetts Legislature"),
    item("boston_public_library", "Back Bay", "建筑", "波士顿公共图书馆中央馆", "Boston Public Library, Central Library",
         "科普利广场旁的图书馆与历史建筑群；公共空间、展览和导览以图书馆公告为准。",
         "Library and historic building complex by Copley Square; check library notices for public areas, exhibitions and tours.",
         "Copley Square", "科普利广场步行衔接", "建筑外观可见；室内开放区域与活动另核",
         "https://www.bpl.org/locations/1/", "Boston Public Library",
         "官方网页抓取受限，后续需从可访问的官方资料补证。"),
    item("trinity_church", "Back Bay", "建筑", "三一教堂", "Trinity Church",
         "科普利广场的历史教堂建筑；礼拜、活动与游客参观安排可能影响入内。",
         "Historic church at Copley Square; worship and event schedules may affect visitor access.",
         "Copley Square", "科普利广场步行衔接", "外观可见；入内按教堂访客规定",
         "https://trinitychurchboston.org/visit", "Trinity Church in the City of Boston"),
    item("boston_athenaeum", "Downtown", "建筑", "波士顿雅典娜图书馆", "Boston Athenaeum",
         "市中心的独立图书馆与文化机构；访客入内方式、展览和预约要求须查官方访客说明。",
         "Independent library and cultural institution downtown; check official visitor information for admission, exhibitions and reservations.",
         "10 1/2 Beacon St, Boston", "灯塔山步行衔接", "访客准入、预约和费用另核",
         "https://www.bostonathenaeum.org/visit/", "Boston Athenaeum"),
    item("museum_of_science", "West End", "博物馆", "波士顿科学博物馆", "Museum of Science, Boston",
         "查尔斯河畔的科学博物馆；展览、票务和开放时间均以当日馆方信息为准。",
         "Science museum on the Charles River; check the museum for current exhibitions, tickets and hours.",
         "1 Science Park, Boston", "西端／河滨", "需按馆方信息购票或预约",
         "https://www.mos.org/visit", "Museum of Science"),
    item("mfa_boston", "Fenway–Kenmore", "博物馆", "波士顿美术博物馆", "Museum of Fine Arts, Boston",
         "波士顿主要艺术博物馆之一；入馆、展览和交通信息以馆方最新访客页面为准。",
         "Major Boston art museum; consult the museum's current visitor information for admission, exhibitions and transit.",
         "465 Huntington Ave, Boston", "芬威博物馆区", "入馆、票务及开放时间另核",
         "https://www.mfa.org/visit", "Museum of Fine Arts, Boston",
         "自动网页读取返回403；不得据此宣称页面不可用，后续须寻求可保存的馆方正文。"),
    item("gardner_museum", "Fenway–Kenmore", "博物馆", "伊莎贝拉·斯图尔特·加德纳博物馆", "Isabella Stewart Gardner Museum",
         "以伊莎贝拉·斯图尔特·加德纳的收藏与陈列为核心的艺术博物馆；建议按馆方要求提前安排门票。",
         "Art museum centered on Isabella Stewart Gardner's collection and displays; follow the museum's ticketing guidance.",
         "25 Evans Way, Boston", "芬威博物馆区", "需购票；可能需提前预订",
         "https://www.gardnermuseum.org/visit", "Isabella Stewart Gardner Museum"),
    item("fenway_park", "Fenway–Kenmore", "建筑", "芬威球场", "Fenway Park",
         "波士顿红袜队主场与城市体育地标；参观、比赛和场馆导览分别按运营方信息安排。",
         "Home of the Boston Red Sox and a city sports landmark; check the operator for games, tours and venue access.",
         "4 Jersey St, Boston", "芬威街区", "比赛需票；导览与场馆开放另核",
         "https://www.mlb.com/redsox/ballpark", "Boston Red Sox"),
    item("back_bay_fens", "Fenway–Kenmore", "公园", "芬威公园地带", "Back Bay Fens",
         "翡翠项链公园系统中的城市公园地带；具体路径、设施和施工状况以公园公告为准。",
         "Urban parkland within the Emerald Necklace; check park notices for paths, facilities and construction.",
         "Fenway area", "翡翠项链步行衔接", "室外公共空间；路径与设施另核",
         "https://www.emeraldnecklace.org/park-overview/back-bay-fens/", "Emerald Necklace Conservancy"),
    item("arnold_arboretum", "Jamaica Plain", "公园", "阿诺德植物园", "Arnold Arboretum of Harvard University",
         "哈佛大学管理的植物园与公共景观；访客须遵守园方开放、交通及植物保护规定。",
         "A Harvard University arboretum and public landscape; follow its visitor, access and conservation rules.",
         "Jamaica Plain", "翡翠项链南段", "户外园区；建筑与设施开放另核",
         "https://arboretum.harvard.edu/visit/", "Arnold Arboretum of Harvard University"),
    item("franklin_park", "Roxbury / Dorchester / Jamaica Plain", "公园", "富兰克林公园", "Franklin Park",
         "波士顿大型公园之一，横跨多个社区；公园路径、设施和活动须按城市信息核对。",
         "One of Boston's major parks spanning several neighborhoods; check city information for paths, facilities and events.",
         "Franklin Park", "翡翠项链南段", "公共公园；园内设施及动物园另核",
         "https://www.boston.gov/parks/franklin-park", "City of Boston"),
    item("franklin_park_zoo", "Roxbury / Dorchester", "公园", "富兰克林公园动物园", "Franklin Park Zoo",
         "位于富兰克林公园内的动物园；入园与季节性运营按动物园公告核实。",
         "Zoo within Franklin Park; check the operator for admission and seasonal operations.",
         "1 Franklin Park Rd, Boston", "富兰克林公园内", "需按运营方信息购票并核实开放",
         "https://www.zoonewengland.org/franklin-park-zoo/", "Zoo New England",
         "暂按公园/户外目的地分组；本身是独立收费动物园，不应与免费公园空间混为一谈。"),
    item("black_heritage_trail", "Beacon Hill", "古迹", "波士顿黑人遗产步道", "Black Heritage Trail",
         "串联灯塔山黑人历史相关地点的步行路线；路线站点可外观浏览，导览及建筑入内另核。",
         "Walking route connecting Black history sites on Beacon Hill; verify guided tours and interior access separately.",
         "Beacon Hill", "自由之路邻近路线", "公共街道步行；室内场馆另核",
         "https://www.nps.gov/boaf/planyourvisit/index.htm", "National Park Service"),
    item("nubian_square", "Roxbury", "街道", "努比亚广场", "Nubian Square",
         "罗克斯伯里社区的公共街区节点；周边公共艺术、商铺和活动须逐项核实。",
         "Public neighborhood center in Roxbury; verify nearby public art, businesses and events individually.",
         "Roxbury", "罗克斯伯里社区", "公共街道；商铺与活动状态另核",
         MEET_BOSTON, "Meet Boston"),
    item("sowa", "South End", "街道", "SoWa艺术与设计区", "SoWa Art + Design District",
         "南端的艺术、设计与市场区域；市场及画廊开放可能随日期变化。",
         "Arts, design and market area in the South End; market and gallery access may vary by date.",
         "Harrison Ave / Thayer St area", "南端社区", "街道公共区域；商户营业和市场日期另核",
         "https://www.sowaboston.com/", "SoWa Boston"),
    item("castle_island", "South Boston", "古迹", "城堡岛与独立堡", "Castle Island and Fort Independence",
         "南波士顿海滨公共休闲区及历史堡垒；堡内开放时间与活动须查市方公告。",
         "South Boston waterfront recreation area and historic fort; check city notices for fort access and events.",
         "2010 William J Day Blvd, Boston", "南波士顿海滨", "岛上公共空间；堡内开放另核",
         "https://www.boston.gov/parks/castle-island", "City of Boston"),
    item("rose_kennedy_greenway", "Downtown / Waterfront", "公园", "罗斯·肯尼迪绿道", "Rose Kennedy Greenway",
         "穿过波士顿市中心的线性公共公园；公共艺术、市场和活动内容按运营方日历核对。",
         "Linear public park through central Boston; check the conservancy calendar for public art, markets and events.",
         "Surface Rd / Atlantic Ave corridor", "市中心步行连接", "公共户外空间；活动另核",
         "https://www.rosekennedygreenway.org/overview/", "Rose Kennedy Greenway Conservancy"),
    item("boston_harborwalk", "Waterfront / Seaport / East Boston", "街道", "波士顿海港步道", "Boston Harborwalk",
         "沿波士顿海滨分段连接公共空间的步行系统；各段连续性、施工和开放情况须现场复核。",
         "Segmented public waterfront walkway; verify continuity, construction and access for each segment.",
         "Multiple Boston waterfront segments", "区域步行连接", "公共步道分段；不等同完整连续路线",
         "https://www.boston.gov/departments/environment/harborwalk", "City of Boston"),
    item("boston_tea_party_ships", "Seaport", "博物馆", "波士顿倾茶船与博物馆", "Boston Tea Party Ships & Museum",
         "以波士顿倾茶事件为主题的互动场馆；参观时段、票务和无障碍安排按运营方页面核对。",
         "Interactive venue focused on the Boston Tea Party; check the operator for tour times, tickets and accessibility.",
         "306 Congress St, Boston", "海港区步行衔接", "需购票或预约；时段另核",
         "https://www.bostonteapartyship.com/", "Boston Tea Party Ships & Museum"),
    item("ica_boston", "Seaport", "博物馆", "波士顿当代艺术学院", "Institute of Contemporary Art / Boston",
         "海港区的当代艺术机构；展览和访客政策以馆方当前访客页面为准。",
         "Contemporary art institution in the Seaport; consult current visitor information for exhibitions and policies.",
         "25 Harbor Shore Dr, Boston", "海港区", "入馆、票务和活动另核",
         "https://www.icaboston.org/visit/", "Institute of Contemporary Art / Boston",
         "需确认站点在抓取时仍对应ICA Boston官方访客页。"),
    item("boston_childrens_museum", "South Boston Waterfront", "博物馆", "波士顿儿童博物馆", "Boston Children's Museum",
         "面向儿童与家庭的互动博物馆；入馆政策、票务和开放时间以馆方信息为准。",
         "Interactive museum for children and families; check the museum for admission policies and hours.",
         "308 Congress St, Boston", "海港步行衔接", "需按馆方信息购票并核实开放",
         "https://bostonchildrensmuseum.org/visit/", "Boston Children's Museum"),
    item("jfk_library", "Dorchester", "博物馆", "约翰·F·肯尼迪总统图书馆与博物馆", "John F. Kennedy Presidential Library and Museum",
         "哥伦比亚角的总统图书馆与博物馆；展览、交通、票务与开放时间以馆方当日信息为准。",
         "Presidential library and museum at Columbia Point; check current museum information for exhibitions, transit and admission.",
         "Columbia Point, Boston", "多切斯特海滨", "需按馆方信息购票并核实开放",
         "https://www.jfklibrary.org/visit-museum", "John F. Kennedy Presidential Library and Museum"),
    item("emk_institute", "Dorchester", "博物馆", "爱德华·M·肯尼迪美国参议院研究所", "Edward M. Kennedy Institute for the United States Senate",
         "以美国参议院与公民参与为主题的教育机构；开放和预约安排须查运营方信息。",
         "Educational institution focused on the U.S. Senate and civic participation; check the operator for public hours and reservations.",
         "Columbia Point, Boston", "JFK图书馆邻近", "访客开放及预约另核",
         "https://www.emkinstitute.org/visit", "Edward M. Kennedy Institute"),
    item("piers_park", "East Boston", "公园", "皮尔斯公园", "Piers Park",
         "东波士顿海滨公共公园；活动、设施及临时关闭须按管理方公告核实。",
         "Public waterfront park in East Boston; check management notices for events, facilities and closures.",
         "95 Marginal St, East Boston", "东波士顿海滨", "公共户外空间；设施开放另核",
         "https://www.pierspark.org/", "Piers Park Sailing Center"),
    item("boston_nature_center", "Mattapan", "公园", "波士顿自然中心与野生动物保护区", "Boston Nature Center & Wildlife Sanctuary",
         "马萨诸塞州奥杜邦协会管理的自然保护区；步道、活动及访客开放须按保护区信息核对。",
         "Mass Audubon nature sanctuary; check its visitor information for trails, programs and access.",
         "500 Walk Hill St, Mattapan", "马塔潘", "自然保护区；步道及设施开放另核",
         "https://www.massaudubon.org/places-to-explore/wildlife-sanctuaries/boston-nature-center", "Mass Audubon"),
    item("millennium_park", "West Roxbury", "公园", "千禧公园", "Millennium Park",
         "西罗克斯伯里的城市公园；入口、停车、路径和设施以波士顿市公园信息为准。",
         "City park in West Roxbury; check Boston Parks for entrances, parking, paths and facilities.",
         "West Roxbury", "西罗克斯伯里", "公共户外空间；设施开放另核",
         "https://www.boston.gov/parks/millennium-park", "City of Boston"),
    item("chestnut_hill_reservoir", "Brighton", "公园", "栗山水库步道", "Chestnut Hill Reservoir",
         "位于布莱顿边缘的水库公共步行环线；路径条件与水务设施限制须按管理方公告核对。",
         "Public walking loop at the edge of Brighton; check management notices for path conditions and water-facility restrictions.",
         "Beacon St, Brighton", "布莱顿社区", "公共步行区域；不得进入受限水务设施",
         "https://www.mass.gov/locations/chestnut-hill-reservoir", "Massachusetts Department of Conservation and Recreation"),
    item("harvard_university", "Harvard Square / Cambridge", "大学", "哈佛大学校园", "Harvard University campus",
         "剑桥的大学校园与历史建筑群；校园公共空间与教学建筑的访客准入须分别核对。",
         "University campus and historic building complex in Cambridge; verify access separately for public grounds and academic buildings.",
         "Harvard Square, Cambridge", "剑桥步行模块", "不保证教学建筑开放；参观须遵守校方规定",
         "https://www.harvard.edu/visit/", "Harvard University"),
    item("harvard_art_museums", "Harvard Square / Cambridge", "博物馆", "哈佛艺术博物馆", "Harvard Art Museums",
         "哈佛大学艺术博物馆群；馆方访客页面提供入馆、交通与活动信息，出行前须再次确认。",
         "Harvard University's art museums; consult the visitor page for admission, transit and events before visiting.",
         "32 Quincy St, Cambridge", "哈佛广场步行衔接", "馆方访客政策与活动另核",
         "https://harvardartmuseums.org/visit", "Harvard Art Museums"),
    item("harvard_peabody_museum", "Harvard Square / Cambridge", "博物馆", "哈佛自然历史博物馆", "Harvard Museum of Natural History",
         "哈佛大学自然历史博物馆；展览、联票及入馆信息以馆方访客说明为准。",
         "Harvard University's natural history museum; check the visitor page for exhibitions, combined tickets and admission.",
         "26 Oxford St, Cambridge", "哈佛广场步行衔接", "需核实入馆、票务和开放时间",
         "https://hmnh.harvard.edu/visit", "Harvard Museum of Natural History"),
    item("mit_campus", "Kendall Square / Cambridge", "大学", "麻省理工学院校园", "Massachusetts Institute of Technology campus",
         "剑桥查尔斯河畔的大学校园；室外公共空间、建筑和展览的访问权限并不相同。",
         "University campus by the Charles River in Cambridge; access differs among outdoor public spaces, buildings and exhibitions.",
         "77 Massachusetts Ave, Cambridge", "肯德尔广场／河滨", "不保证教学建筑开放；须遵守校方规定",
         "https://visit.mit.edu/", "Massachusetts Institute of Technology"),
    item("mit_museum", "Kendall Square / Cambridge", "博物馆", "麻省理工学院博物馆", "MIT Museum",
         "展示科学、技术与艺术相关内容的大学博物馆；展览、票务及访客入口以馆方说明为准。",
         "University museum presenting science, technology and art; check the museum for exhibitions, tickets and visitor entrance.",
         "314 Main St, Cambridge", "肯德尔广场", "入馆与开放时间另核",
         "https://mitmuseum.mit.edu/visit", "MIT Museum"),
    item("harvard_square", "Harvard Square / Cambridge", "街道", "哈佛广场", "Harvard Square",
         "剑桥公共街区与步行商业区；校园、商户和交通设施各有不同的开放边界。",
         "Public district and pedestrian-oriented commercial area in Cambridge; campus, businesses and transit facilities have separate access rules.",
         "Harvard Square, Cambridge", "哈佛大学周边", "公共街道；商户和校园建筑另核",
         "https://cambridgeusa.org/neighborhood/harvard-square/", "Cambridge Office for Tourism"),
    item("longfellow_house", "Cambridge", "古迹", "朗费罗故居—华盛顿总部国家历史遗址", "Longfellow House–Washington's Headquarters National Historic Site",
         "由美国国家公园管理局管理的剑桥历史遗址；建筑内部开放按预约与季节安排核实。",
         "Cambridge historic site managed by the National Park Service; verify reservations and seasonal access for the house interior.",
         "105 Brattle St, Cambridge", "哈佛广场步行衔接", "室外场地与室内参观开放安排不同",
         "https://www.nps.gov/long/planyourvisit/index.htm", "National Park Service"),
    item("mount_auburn_cemetery", "Cambridge / Watertown", "公园", "奥本山公墓", "Mount Auburn Cemetery",
         "剑桥与沃特敦交界的历史公墓、景观与植物园；访客须遵守开放时间和安静场所规则。",
         "Historic cemetery, landscape and arboretum on the Cambridge–Watertown line; follow hours and its quiet-place rules.",
         "580 Mount Auburn St, Cambridge", "剑桥西部", "公共访客空间；遵守墓园规定",
         "https://mountauburn.org/visit/", "Mount Auburn Cemetery"),
    item("pem", "Salem", "博物馆", "皮博迪·埃塞克斯博物馆", "Peabody Essex Museum",
         "塞勒姆的艺术与文化博物馆；部分历史住宅另需定时票，展览、开放和交通须按当日馆方信息核实。",
         "Art and culture museum in Salem; some historic houses require timed tickets, so check current exhibitions, hours and transit.",
         "161 Essex St, Salem", "塞勒姆市中心", "入馆按馆方票务；部分场馆需定时票",
         "https://pem.org/visit", "Peabody Essex Museum"),
    item("salem_maritime", "Salem", "古迹", "塞勒姆海事国家历史遗址", "Salem Maritime National Historic Site",
         "美国国家公园管理局管理的海事历史遗址；游客中心、码头和建筑开放安排分项核实。",
         "Maritime historic site managed by the National Park Service; verify visitor center, wharf and building access separately.",
         "Salem waterfront", "塞勒姆海滨", "户外遗址公共区域；建筑开放时间另核",
         "https://www.nps.gov/sama/planyourvisit/index.htm", "National Park Service"),
    item("house_of_seven_gables", "Salem", "古迹", "七角楼", "The House of the Seven Gables",
         "塞勒姆海滨的历史建筑与博物馆；导览、门票和场地开放按运营方最新信息安排。",
         "Historic house and museum on Salem's waterfront; check the operator for tours, admission and site access.",
         "115 Derby St, Salem", "塞勒姆海事区", "导览和入内需按运营方安排",
         "https://7gables.org/visit/", "The House of the Seven Gables"),
    item("salem_witch_museum", "Salem", "博物馆", "塞勒姆女巫博物馆", "Salem Witch Museum",
         "以1692年塞勒姆审巫事件为主题的博物馆；场次、预约和票务以博物馆信息为准。",
         "Museum focused on the 1692 Salem witch trials; check the museum for showtimes, reservations and tickets.",
         "19 1/2 N Washington Sq, Salem", "塞勒姆市中心", "入馆时段与票务另核",
         "https://salemwitchmuseum.com/visit/", "Salem Witch Museum"),
    item("salem_willows", "Salem", "公园", "塞勒姆柳园", "Salem Willows",
         "塞勒姆海滨公园与休闲区；游乐设施、季节性商户和活动的开放情况须按运营方核对。",
         "Waterfront park and recreation area in Salem; verify amusement facilities, seasonal vendors and events.",
         "Salem Willows Park", "塞勒姆海滨", "公共户外区域；季节性设施和商户另核",
         "https://www.salemma.gov/parks-rec/pages/salem-willows-park", "City of Salem"),
    item("minute_man_nhp", "Lexington / Lincoln / Concord", "古迹", "米努特曼国家历史公园", "Minute Man National Historical Park",
         "横跨莱克星顿、林肯和康科德的历史公园；步道、游客中心与历史建筑的季节开放各不相同。",
         "Historic park spanning Lexington, Lincoln and Concord; trails, visitor centers and historic buildings have different seasonal schedules.",
         "Multiple park units", "跨镇历史路线", "公共步道；建筑及游客中心按季节开放",
         "https://www.nps.gov/mima/planyourvisit/placestogo.htm", "National Park Service"),
    item("north_bridge", "Concord", "古迹", "北桥", "North Bridge",
         "康科德的历史桥梁与纪念景观；停车、步道和游客中心开放情况须按国家公园公告核对。",
         "Historic bridge and commemorative landscape in Concord; check the National Park Service for parking, trails and visitor center access.",
         "Monument St, Concord", "米努特曼国家历史公园", "户外纪念地；游客中心季节开放",
         "https://www.nps.gov/mima/planyourvisit/placestogo.htm", "National Park Service"),
    item("battle_road_trail", "Lexington / Lincoln / Concord", "公园", "战役路步道", "Battle Road Trail",
         "国家历史公园内连接多个历史地点的步道；距离、路段和步行状况以国家公园地图为准。",
         "Trail connecting historic sites in the national historical park; consult the park map for distances, segments and conditions.",
         "Route 2A corridor", "米努特曼国家历史公园", "公共步道；路段和季节条件另核",
         "https://www.nps.gov/mima/planyourvisit/placestogo.htm", "National Park Service"),
    item("concord_museum", "Concord", "博物馆", "康科德博物馆", "Concord Museum",
         "收藏与展示康科德地区历史和艺术的博物馆；展览、开放和票务以馆方访客信息为准。",
         "Museum of Concord-area history and art; check the museum's visitor information for exhibitions, hours and admission.",
         "53 Cambridge Turnpike, Concord", "康科德市中心", "入馆和开放时间另核",
         "https://concordmuseum.org/visit/", "Concord Museum"),
    item("orchard_house", "Concord", "古迹", "果园之家", "Orchard House",
         "与路易莎·梅·奥尔科特及其家庭相关的历史故居；室内参观须按运营方导览和预约安排。",
         "Historic home associated with Louisa May Alcott and her family; interior visits follow operator tour and reservation arrangements.",
         "399 Lexington Rd, Concord", "康科德文学遗产", "室内仅按导览与预约开放",
         "https://louisamayalcott.org/visit", "Louisa May Alcott's Orchard House"),
    item("the_wayside", "Concord", "古迹", "路边故居：作家之家", "The Wayside: Home of Authors",
         "国家公园管理局管理的康科德历史住宅；室外场地与住宅内部有不同开放安排，须核对季节公告。",
         "Historic Concord house managed by the National Park Service; verify separate seasonal access for grounds and interior.",
         "455 Lexington Rd, Concord", "米努特曼国家历史公园", "室外场地与室内开放分开核实",
         "https://www.nps.gov/mima/planyourvisit/placestogo.htm", "National Park Service"),
    item("walden_pond", "Concord", "公园", "瓦尔登湖州立保留地", "Walden Pond State Reservation",
         "马萨诸塞州管理的湖泊与自然保留地；停车、游泳、步道和季节规则须按州方公告核对。",
         "State-managed pond and nature reservation; check state notices for parking, swimming, trails and seasonal rules.",
         "Concord", "康科德自然与文学路线", "公共保留地；季节设施及停车另核",
         "https://www.mass.gov/locations/walden-pond-state-reservation", "Massachusetts Department of Conservation and Recreation"),
    item("lexington_battle_green", "Lexington", "古迹", "莱克星顿战场绿地", "Lexington Battle Green",
         "莱克星顿市中心的历史公共绿地；纪念活动、步行范围和附近场馆开放须分别核对。",
         "Historic public green in downtown Lexington; verify commemorations, walking access and nearby venue hours separately.",
         "Lexington Center", "米努特曼国家历史公园周边", "公共户外空间；附近场馆另核",
         "https://www.lexingtonma.gov/1135/Lexington-Battle-Green", "Town of Lexington"),
    item("buckman_tavern", "Lexington", "古迹", "巴克曼酒馆", "Buckman Tavern",
         "莱克星顿历史协会管理的历史建筑；导览、季节开放和票务须查历史协会公告。",
         "Historic building managed by Lexington Historical Society; check the society for tours, seasonal hours and admission.",
         "1 Bedford St, Lexington", "莱克星顿战场绿地", "室内开放及导览另核",
         "https://lexingtonhistory.org/visit/", "Lexington Historical Society"),
    item("hancock_clarke_house", "Lexington", "古迹", "汉考克—克拉克故居", "Hancock-Clarke House",
         "莱克星顿历史协会管理的历史住宅；是否开放、导览和季节安排须查运营方信息。",
         "Historic house managed by Lexington Historical Society; check the operator for access, tours and seasonal schedule.",
         "36 Hancock St, Lexington", "莱克星顿历史路线", "室内开放及导览另核",
         "https://lexingtonhistory.org/visit/", "Lexington Historical Society"),
    item("adams_nhp", "Quincy", "古迹", "亚当斯国家历史公园", "Adams National Historical Park",
         "昆西的总统家族历史遗址；住宅、游客中心和穿梭交通的开放按国家公园季节安排核对。",
         "Presidential family historic sites in Quincy; verify seasonal access for houses, visitor center and shuttle service.",
         "Quincy", "昆西一日行程", "部分场地需导览或交通接驳；开放另核",
         "https://www.nps.gov/adam/planyourvisit/index.htm", "National Park Service"),
    item("union_oyster_house", "North End / Downtown", "餐饮", "联合牡蛎屋", "Union Oyster House",
         "市中心历史餐饮场所候选；本条仅用于地点识别，不评价口味、服务或价格，营业与预约须当日核对。",
         "Candidate historic dining venue downtown; listed for place identification only, not for food, service or price evaluation. Check current hours and reservations.",
         "41 Union St, Boston", "市中心步行衔接", "餐厅营业、预约和无障碍情况另核",
         "https://www.unionoysterhouse.com/", "Union Oyster House"),
    item("mikes_pastry", "North End", "餐饮", "Mike's Pastry（北端店）", "Mike's Pastry (North End)",
         "北端甜品店候选；须核实此具体门店、经营者资料和当日营业状态，不作口味或排队时长承诺。",
         "Candidate North End pastry shop; verify this specific location, operator information and current hours. No claims about taste or queue time.",
         "North End; exact storefront to verify", "北端街区", "营业及门店位置须以经营者最新信息为准",
         "https://www.mikespastry.com/", "Mike's Pastry"),
    item("regina_pizzeria_north_end", "North End", "餐饮", "雷吉娜披萨（北端店）", "Regina Pizzeria (North End)",
         "北端披萨店候选；按具体分店识别，营业、候位和预订以经营者信息为准。",
         "Candidate North End pizzeria; identify the specific branch and check operator information for hours, waits and reservations.",
         "North End; exact storefront to verify", "北端街区", "营业及分店地址须以经营者最新信息为准",
         "https://www.reginapizzeria.com/", "Regina Pizzeria",
         "官网首页说明北端旗舰店；具体街道地址与分店状态仍须单独核实。"),
    item("flour_bakery", "South End / Boston", "餐饮", "Flour Bakery（波士顿门店）", "Flour Bakery (Boston locations)",
         "波士顿本地烘焙与餐饮门店候选；需在发布前选定具体分店并核实地址和营业信息。",
         "Candidate Boston bakery and dining business; select a specific branch and verify its address and hours before publication.",
         "Multiple locations; branch to verify", "城市多店", "须绑定单一分店；营业及菜单另核",
         "https://flourbakery.com/locations", "Flour Bakery + Cafe"),
    item("oleana", "Cambridge", "餐饮", "Oleana", "Oleana",
         "剑桥餐厅候选；以经营者资料确认地点和餐厅身份，不评价菜品、服务、价格或当日营业。",
         "Candidate Cambridge restaurant; use operator information to confirm location and identity, without rating food, service, prices or daily operations.",
         "Cambridge; address to verify", "剑桥餐饮候选", "须核实地址、预约与当日营业",
         "https://www.oleanarestaurant.com/", "Oleana Restaurant"),
    item("turners_seafood_salem", "Salem", "餐饮", "Turner's Seafood（塞勒姆店）", "Turner's Seafood (Salem)",
         "塞勒姆餐饮候选；须确认具体门店与经营信息，不评价餐食品质或实时营业。",
         "Candidate Salem dining venue; confirm the specific location and operator information without rating food or current operations.",
         "Salem; exact storefront to verify", "塞勒姆市中心", "营业、预约与分店地址另核",
         "https://turners-seafood.com/", "Turner's Seafood"),
    item("colonial_inn_dining", "Concord", "餐饮", "康科德殖民旅馆餐饮", "Concord's Colonial Inn dining",
         "康科德旅馆餐饮候选；须确认对非住客开放的服务、具体餐厅和当日营业安排。",
         "Candidate dining at a Concord inn; verify restaurant identity, access for non-guests and current hours.",
         "Concord Center; exact entrance to verify", "康科德历史区", "营业、餐厅准入和预约另核",
         "https://www.concordscolonialinn.com/dining/", "Concord's Colonial Inn"),
]


KIND_EN = {
    "大学": "University",
    "博物馆": "Museum",
    "古迹": "Heritage site",
    "公园": "Park",
    "建筑": "Architecture",
    "街道": "Street / district",
    "餐饮": "Dining",
}


def style_sheet(ws, widths: list[int]) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="24445C")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(1, index).column_letter].width = width
    for row in ws.iter_rows(min_row=2):
        ws.row_dimensions[row[0].row].height = 58
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="1C2733")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F0F5F8")


def make_inventory_sheet(wb: Workbook, lang: str) -> None:
    ws = wb.create_sheet("zh-CN" if lang == "zh" else "en")
    if lang == "zh":
        headers = ["ID", "区域", "类别", "名称", "英文原名", "简介", "位置／地址", "关联", "访问边界", "来源机构", "来源链接", "核查日期", "编者说明"]
        rows_out = [
            [r["id"], r["zone"], r["kind"], r["zh"], r["en"], r["zh_desc"], r["address"],
             r["relation"], r["access"], r["source_name"], r["source"], AS_OF, r["note"]]
            for r in rows
        ]
    else:
        headers = ["ID", "Area", "Category", "Name", "Chinese name", "Description", "Location / address", "Relation", "Access boundary", "Source organization", "Source URL", "Checked", "Editor note"]
        rows_out = [
            [r["id"], r["zone"], KIND_EN[r["kind"]], r["en"], r["zh"], r["en_desc"],
             r["address"], r["relation"], r["access"], r["source_name"], r["source"],
             AS_OF, r["note"]]
            for r in rows
        ]
    ws.append(headers)
    for row in rows_out:
        ws.append(row)
    style_sheet(ws, [28, 29, 21, 43, 46, 80, 36, 27, 44, 37, 68, 15, 75])
    for row in ws.iter_rows(min_row=2):
        row[10].hyperlink = row[10].value
        row[10].font = Font(name="Arial", size=10, color="0563C1", underline="single")
        row[11].number_format = "yyyy-mm-dd"


def build() -> None:
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids)), "duplicate inventory IDs"
    assert all(row["kind"] in KIND_EN for row in rows)
    assert all(row["source"].startswith("https://") for row in rows)
    assert all(row["zh_desc"] and row["en_desc"] and row["access"] for row in rows)

    wb = Workbook()
    wb.remove(wb.active)
    make_inventory_sheet(wb, "zh")
    make_inventory_sheet(wb, "en")

    ws = wb.create_sheet("Boston社区覆盖")
    ws.append(["English area", "中文区域", "当前候选条目数", "编辑说明", "范围来源"])
    for en, zh in NEIGHBORHOODS:
        count = sum(en in ZONE_NEIGHBORHOOD.get(row["zone"], set()) for row in rows)
        ws.append([
            en,
            zh,
            count,
            "此表用于覆盖检查；没有可核实游客锚点时，不以街区名称冒充景点。"
            if count else "目前没有独立候选地点；须继续研究或明确记为本版不收录。",
            MEET_BOSTON,
        ])
    style_sheet(ws, [36, 24, 22, 75, 68])
    for row in ws.iter_rows(min_row=2):
        row[4].hyperlink = row[4].value
        row[4].font = Font(name="Arial", size=10, color="0563C1", underline="single")

    capture_path = HERE / "boston_area_v3_source_capture.json"
    if capture_path.exists():
        capture = json.loads(capture_path.read_text("utf-8"))
        ws = wb.create_sheet("来源抓取状态")
        ws.append(["状态", "HTTP", "来源标题", "来源链接", "绑定条目ID", "方法／错误"])
        for source in capture["sources"]:
            ws.append([
                source["status"],
                source["http_status"],
                source["title"] or "",
                source["url"],
                ", ".join(source["bound_inventory_ids"]),
                source["retrieval_method"] + (f" — {source['error']}" if source.get("error") else ""),
            ])
        style_sheet(ws, [16, 10, 52, 72, 60, 75])
        for row in ws.iter_rows(min_row=2):
            row[3].hyperlink = row[3].value
            row[3].font = Font(name="Arial", size=10, color="0563C1", underline="single")

    ws = wb.create_sheet("使用说明")
    notes = [
        ("用途", "这是Greater Boston候选地点清单，不是穷尽名录，也不是已完成的发布资料包。"),
        ("范围", "波士顿各社区；明确包含Cambridge、Salem、Concord、Lexington；其他相邻城镇须满足有来源的游客价值标准。"),
        ("类别", "大学、博物馆、古迹、公园、建筑、街道／街区、餐饮。"),
        ("身份与去重", "每个候选地点使用稳定小写ID。步道整体与组成站点分开；多店经营者须绑定具体分店后才能发布。"),
        ("访问边界", "入馆、预约、票务、公共空间、仅外观及季节条件须按来源正文逐项核实；当前营业状态不是永久事实。"),
        ("餐饮", "仅作候选地点识别，不评价口味、服务、价格或餐饮质量；不使用未经核实的分店地址。"),
        ("证据状态", "各行来源URL目前是待抓取候选；下一阶段须保存实际页面正文、核查日期及页面不可访问状态。搜索摘要不得当作页面原文。"),
        ("核查日期", AS_OF.isoformat()),
        ("构建", "python3 utils/import_data/boston_area_list.py"),
    ]
    ws.append(["项目", "说明"])
    for note in notes:
        ws.append(note)
    style_sheet(ws, [24, 125])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    check = load_workbook(OUT, read_only=True)
    expected_sheets = ["zh-CN", "en", "Boston社区覆盖"]
    if capture_path.exists():
        expected_sheets.append("来源抓取状态")
    expected_sheets.append("使用说明")
    if check.sheetnames != expected_sheets:
        raise ValueError(f"unexpected workbook sheets: {check.sheetnames}")
    if check["zh-CN"].max_row != len(rows) + 1 or check["en"].max_row != len(rows) + 1:
        raise ValueError("workbook row count does not match inventory")
    print(OUT)
    print(f"{len(rows)} candidate places; {len(NEIGHBORHOODS)} Boston-area coverage rows")


if __name__ == "__main__":
    build()
