"""Build the sourced, bilingual Summer Street corridor inventory.

Run: python3 utils/import_data/boston_summer_st_list.py
The workbook is a research inventory, not a V3-rated tour package.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


AS_OF = date(2026, 11, 2)
OUT = Path(__file__).parent / "exports" / "波士顿Summer Street周边景点与商铺_双语清单.xlsx"

FREEDOM = "https://www.thefreedomtrail.org/trail-sites"
FREEDOM_INFO = "https://www.thefreedomtrail.org/visit/experience-freedom-trail-now-visitor-resource"
MEET_DOWNTOWN = "https://www.meetboston.com/explore/neighborhoods/downtown-crossing-financial-district/"


def item(key, zone, kind, zh, en, zh_desc, en_desc, address, relation, access, source, source_name, note=""):
    return dict(id=key, zone=zone, kind=kind, zh=zh, en=en, zh_desc=zh_desc,
                en_desc=en_desc, address=address, relation=relation, access=access,
                source=source, source_name=source_name, note=note)


trail = [
    ("T01", "波士顿公园", "Boston Common", "市中心西端", "老城公共绿地，也是自由之路起点。", "Historic public park and the starting point of the Freedom Trail.", "139 Tremont St.", "https://www.thefreedomtrail.org/trail-sites/boston-common"),
    ("T02", "马萨诸塞州议会大厦", "Massachusetts State House", "市中心西端", "位于波士顿公园旁的州议会大厦。", "State capitol beside Boston Common.", "Beacon St.", FREEDOM),
    ("T03", "公园街教堂", "Park Street Church", "市中心西端", "自由之路沿线的历史教堂。", "Historic church on the Freedom Trail.", "Park St. & Tremont St.", FREEDOM),
    ("T04", "谷仓墓地", "Granary Burying Ground", "市中心西端", "市中心历史墓地，毗邻公园街教堂。", "Historic downtown burial ground beside Park Street Church.", "120 Tremont St.", "https://www.boston.gov/cemeteries/granary-burying-ground"),
    ("T05", "国王礼拜堂及墓地", "King's Chapel & Burying Ground", "市中心西端", "自由之路上的教堂与相邻墓地。", "Church and adjacent burial ground on the Freedom Trail.", "Tremont St. & School St.", FREEDOM),
    ("T06", "波士顿拉丁学校旧址与富兰克林像", "Boston Latin School Site / Benjamin Franklin Statue", "市中心西端", "旧校址以纪念标识和富兰克林雕像呈现。", "Former school site marked by a memorial and Benjamin Franklin statue.", "School St.", FREEDOM),
    ("T07", "老街角书店旧址", "Old Corner Bookstore", "市中心西端", "自由之路上的历史建筑；名称不代表现在仍是书店。", "Historic Freedom Trail building; the name does not imply an operating bookstore today.", "283 Washington St.", FREEDOM),
    ("T08", "老南会议厅", "Old South Meeting House", "市中心西端", "与1773年波士顿倾茶事件前的群众集会有关。", "Meeting house linked to the mass meeting before the 1773 Boston Tea Party.", "310 Washington St.", FREEDOM),
    ("T09", "老州议会大厦", "Old State House", "金融区", "波士顿现存最古老的公共建筑之一。", "One of Boston's oldest surviving public buildings.", "206 Washington St.", FREEDOM),
    ("T10", "波士顿惨案遗址", "Boston Massacre Site", "金融区", "纪念1770年波士顿惨案的街道遗址标记。", "Street marker commemorating the 1770 Boston Massacre.", "State St. & Congress St.", FREEDOM),
    ("T11", "法尼尔厅", "Faneuil Hall", "金融区", "自由之路上的历史集会场所。", "Historic meeting hall on the Freedom Trail.", "1 Faneuil Hall Sq.", FREEDOM),
    ("T12", "保罗·里维尔故居", "Paul Revere House", "北端延伸", "北端的自由之路历史住宅站点。", "Historic house on the Freedom Trail in the North End.", "19 N Square", FREEDOM),
    ("T13", "老北教堂", "Old North Church", "北端延伸", "与1775年警讯灯笼故事有关的历史教堂。", "Historic church associated with the 1775 lantern signal.", "193 Salem St.", FREEDOM),
    ("T14", "科普山墓地", "Copp's Hill Burying Ground", "北端延伸", "北端的历史墓地。", "Historic burial ground in the North End.", "Hull St.", FREEDOM),
    ("T15", "宪法号军舰", "USS Constitution", "查尔斯敦延伸", "停泊在查尔斯敦海军造船厂的历史军舰。", "Historic warship at Charlestown Navy Yard.", "Charlestown Navy Yard", FREEDOM),
    ("T16", "邦克山纪念碑", "Bunker Hill Monument", "查尔斯敦延伸", "纪念邦克山战役的查尔斯敦地标。", "Charlestown monument commemorating the Battle of Bunker Hill.", "Monument Sq.", FREEDOM),
]

rows = [
    item("F00", "跨区", "步道", "自由之路", "Freedom Trail", "约2.5英里的红线历史步道，串联16处官方站点；本表另列全部站点。", "A roughly 2.5-mile red-lined historic trail linking 16 official sites; all sites are indexed separately.", "Boston / Charlestown", "周边串联", "公共步道；场馆另核", FREEDOM_INFO, "Freedom Trail Foundation", "整条步道超出Summer Street走廊。"),
]

for key, zh, en, zone, zh_desc, en_desc, address, source in trail[:11]:
    rows.append(item(key, zone, "自由之路站点", zh, en, zh_desc, en_desc, address,
                     "步行衔接", "街道可看；入内另核", source,
                     "Boston.gov" if "boston.gov" in source else "Freedom Trail Foundation"))

rows += [
    item("P01", "Downtown Crossing", "街区", "市中心十字路口商圈", "Downtown Crossing", "Summer与Washington街交汇处的步行购物区。", "Pedestrian shopping district around Summer and Washington Streets.", "Summer St. & Washington St.", "沿线", "公共街道", MEET_DOWNTOWN, "Meet Boston"),
    item("P02", "Downtown Crossing", "广场", "夏街广场", "Summer Street Plaza", "市中心步行区的公共聚集空间。", "Public gathering space in the Downtown Crossing pedestrian zone.", "10 Summer St.", "沿线", "公共空间", "https://www.downtownboston.org/business/summer-street-plaza/", "Downtown Boston Alliance"),
    item("P03", "Downtown Crossing", "剧院", "公民歌剧院", "Citizens Opera House", "市中心十字路口附近的演出场馆。", "Performing arts venue near Downtown Crossing.", "539 Washington St.", "步行衔接", "演出需查票务", "https://www.citizensoperahouse.com/getting-here/", "Citizens Opera House"),
    item("P04", "Downtown Crossing", "纪念地", "爱尔兰大饥荒纪念广场", "Irish Famine Memorial Plaza", "位于老南会议厅与老街角书店之间，纪念19世纪爱尔兰大饥荒及移民。", "Plaza between Old South Meeting House and Old Corner Bookstore commemorating the Great Irish Famine and migration.", "10 School St.", "步行衔接", "公共空间", "https://www.downtownboston.org/business/irish-famine-memorial-plaza/", "Downtown Boston Alliance"),
    item("P05", "金融区", "公园", "诺曼·B·莱文塔尔公园", "Norman B. Leventhal Park", "位于邮政广场的金融区公共绿地。", "Public green space at Post Office Square in the Financial District.", "Post Office Square", "步行衔接", "开放时间见官网", "https://www.normanbleventhalpark.org/hours-information/", "Friends of Post Office Square"),
    item("P06", "南站", "公园", "罗斯·肯尼迪绿道", "Rose Fitzgerald Kennedy Greenway", "贯穿市中心多个街区的线性公园，南端接近南站。", "Linear park through central Boston, with its southern end near South Station.", "Surface Rd. / Dewey Sq.", "步行衔接", "公共空间", "https://www.rosekennedygreenway.org/overview/", "Greenway Conservancy"),
    item("P07", "南站", "交通地标", "波士顿南站", "South Station", "Summer Street旁的主要铁路与地铁换乘点，历史站房可从外部观看。", "Major rail and transit hub by Summer Street, with a historic headhouse visible outside.", "700 Atlantic Ave.", "沿线", "交通设施", "https://bostonsouthstation.com/", "South Station"),
    item("P08", "Fort Point", "历史街区", "堡点水道地标区", "Fort Point Channel Landmark District", "旧仓库与工业建筑集中的历史街区，适合看建筑外观。", "Historic district of former warehouses and industrial lofts; exterior architecture can be viewed from public streets.", "Summer St. / A St. / Congress St.", "沿线", "公共街道外观", "https://content.boston.gov/historic-district/fort-point-channel-landmark-district", "City of Boston"),
    item("P09", "Fort Point", "历史建筑", "波士顿码头公司旧办公楼及屋顶标牌", "Boston Wharf Company Office Building & Sign", "Summer与Melcher街角的堡点地标；从公共街道观看建筑及屋顶标牌。", "Fort Point landmark at Summer and Melcher Streets; view the building and rooftop sign from public streets.", "263 Summer St. / 10 Melcher St.", "沿线", "外观", "https://263summerst.com/history/", "263 Summer St. building site", "市历史报告使用363 Summer St./10 Melcher St.；现址网站使用263 Summer St。"),
    item("P10", "Fort Point", "博物馆", "波士顿倾茶事件船舰与博物馆", "Boston Tea Party Ships & Museum", "位于国会街桥的历史体验馆，另有不购票可进入的茶室与商店。", "Historic experience on Congress Street Bridge; its tea room and gift shop are accessible without a museum ticket.", "306 Congress St.", "步行衔接", "展览需预约购票", "https://www.bostonteapartyship.com/faq", "Boston Tea Party Ships & Museum"),
    item("P11", "Fort Point", "博物馆", "波士顿儿童博物馆", "Boston Children's Museum", "位于堡点水道边的儿童博物馆。", "Children's museum on Fort Point Channel.", "308 Congress St.", "步行衔接", "入馆另核", "https://bostonchildrensmuseum.org/visit/directions-and-parking/", "Boston Children's Museum"),
    item("P12", "Fort Point", "公园", "马丁公园", "Martin's Park", "儿童博物馆旁的包容性滨水游乐公园。", "Inclusive waterfront play park beside Boston Children's Museum.", "64 Sleeper St.", "步行衔接", "公共公园", "https://content.boston.gov/departments/parks-and-recreation/martins-park", "City of Boston"),
    item("P13", "Fort Point", "博物馆", "波士顿消防博物馆", "Boston Fire Museum", "设在旧消防站内，展示波士顿消防史。", "Museum of Boston firefighting history in a former firehouse.", "344 Congress St.", "步行衔接", "开放日另核", "https://www.bostonsparks.com/boston-fire-museum", "Boston Sparks Association"),
    item("P14", "海港区", "步道", "波士顿海港步道海港区段", "Boston Harborwalk — Seaport segment", "沿海港岸线连接公共空间与文化地点的步道；此条只指海港区段。", "Waterfront public path linking open spaces and cultural sites; this entry covers the Seaport segment only.", "Seaport waterfront", "步行衔接", "公共步道", "https://www.bostonharborwalk.org/how-to-use-the-harborwalk-webtool/", "Boston Harborwalk"),
    item("P15", "海港区", "美术馆", "波士顿当代艺术学院", "Institute of Contemporary Art/Boston", "海港区滨水的当代艺术馆。", "Contemporary art museum on the Seaport waterfront.", "25 Harbor Shore Dr.", "步行衔接", "入馆另核", "https://www.icaboston.org/visit/", "ICA Boston"),
    item("P16", "海港区", "公共活动地", "D草坪", "The Lawn on D", "会议中心旁的户外活动空间，活动安排需另查。", "Outdoor event space beside the convention center; check its calendar before visiting.", "415 Summer St.", "沿线", "活动开放另核", "https://www.signatureboston.com/lawn-on-d/community-activities", "Signature Boston"),
    item("P17", "海港区", "会展地标", "托马斯·M·梅尼诺会展中心", "Thomas M. Menino Convention & Exhibition Center", "Summer Street上的大型会展场馆，原名波士顿会展中心；按具体活动决定能否入内。", "Major convention venue on Summer Street, formerly the Boston Convention & Exhibition Center; access depends on the event.", "415 Summer St.", "沿线", "非日常开放景点", "https://www.massconvention.com/about-us/contact-us/boston-convention-exhibition-center/1000", "Massachusetts Convention Center Authority"),
    item("P18", "海港区", "演出场所", "Laugh Boston 喜剧俱乐部", "Laugh Boston", "Summer Street上的喜剧演出场所。", "Comedy venue on Summer Street.", "425 Summer St.", "沿线", "演出需查票务", "https://www.meetboston.com/listing/laugh-boston/13539/", "Meet Boston"),
    item("P19", "海港区", "步行连接", "夏街阶梯", "Summer Street Steps", "400 Summer Street旁连接高处街道与海港方向的公共阶梯。", "Public steps beside 400 Summer Street connecting the elevated street toward the harbor.", "400 Summer St.", "沿线", "公共空间", "https://www.wsdevelopment.com/our-properties/400-summer-street/", "WS Development"),
    item("P20", "海港区", "公园", "Harbor Way 绿地", "Harbor Way park", "连接Summer Street与海港岸线的步行公共空间。", "Pedestrian open space linking Summer Street to the harbor edge.", "Harbor Way / Summer St.", "步行衔接", "公共空间", "https://www.wsdevelopment.com/news/how-to-humanize-a-22-billion-neighborhood-built-from-scratch/", "WS Development"),
]

rows += [
    item("S01", "Downtown Crossing", "服饰", "Primark 市中心店", "Primark — Downtown Crossing", "位于Burnham Building的服饰及家居零售店。", "Fashion and home goods store in the Burnham Building.", "10 Summer St.", "沿线", "门店营业另核", "https://www.downtownboston.org/business/primark/", "Downtown Boston Alliance"),
    item("S02", "Downtown Crossing", "百货", "梅西百货市中心店", "Macy's — Downtown Crossing", "位于Washington Street的市中心百货店。", "Downtown department store on Washington Street.", "450 Washington St.", "步行衔接", "门店营业另核", "https://www.downtownboston.org/business/macys/", "Downtown Boston Alliance"),
    item("S03", "Downtown Crossing", "食品零售", "Roche Bros. 超市", "Roche Bros. — Downtown Crossing", "位于10 Summer Street的超市。", "Supermarket at 10 Summer Street.", "10 Summer St.", "沿线", "门店营业另核", "https://www.downtownboston.org/business/roche-bros-supermarket/", "Downtown Boston Alliance"),
    item("S04", "Downtown Crossing", "面包咖啡", "Tatte Bakery 夏街店", "Tatte Bakery — Summer Street", "位于125 Summer Street的烘焙咖啡店。", "Bakery and cafe at 125 Summer Street.", "125 Summer St.", "沿线", "门店营业另核", "https://www.downtownboston.org/business/tatte-bakery-125-summer-street/", "Downtown Boston Alliance"),
    item("S05", "Downtown Crossing", "咖啡", "Caffè Nero 夏街店", "Caffè Nero — Summer Street", "位于10 Summer Street的咖啡店。", "Coffee shop at 10 Summer Street.", "10 Summer St.", "沿线", "门店营业另核", "https://www.downtownboston.org/business/caffh-nero-10-summer-st/", "Downtown Boston Alliance"),
    item("S06", "Downtown Crossing", "甜品", "The Peach Cobbler Factory 夏街店", "The Peach Cobbler Factory — Summer Street", "位于77 Summer Street的甜品店。", "Dessert shop at 77 Summer Street.", "77 Summer St.", "沿线", "门店营业另核", "https://www.downtownboston.org/business/the-peach-cobbler-factory/", "Downtown Boston Alliance"),
    item("S07", "Downtown Crossing", "简餐", "Chacarero 智利三明治", "Chacarero", "Arch Street上的智利风味三明治店。", "Chilean-style sandwich shop on Arch Street.", "101 Arch St.", "步行衔接", "门店营业另核", "https://www.downtownboston.org/business/chacarero/", "Downtown Boston Alliance"),
    item("S08", "Downtown Crossing", "简餐", "Sam LaGrassa's 三明治店", "Sam LaGrassa's", "Province Street上的老牌三明治店。", "Long-running sandwich shop on Province Street.", "44 Province St.", "步行衔接", "门店营业另核", "https://www.downtownboston.org/business/sam-lagrassas/", "Downtown Boston Alliance"),
    item("S09", "Downtown Crossing", "咖啡", "George Howell Coffee 市中心店", "George Howell Coffee — Downtown", "Washington Street上的精品咖啡店。", "Specialty coffee shop on Washington Street.", "505 Washington St.", "步行衔接", "门店营业另核", "https://www.downtownboston.org/business/george-howell-coffee/", "Downtown Boston Alliance"),
    item("S10", "Downtown Crossing", "书店", "Brattle 二手书店", "Brattle Book Shop", "West Street上的旧书与珍本书店。", "Used and antiquarian bookshop on West Street.", "9 West St.", "步行衔接", "门店营业另核", "https://www.brattlebookshop.com/", "Brattle Book Shop"),
    item("S11", "Downtown Crossing", "餐饮", "Democracy Brewing 酿酒餐吧", "Democracy Brewing", "Temple Place上的员工持有制酿酒餐吧。", "Worker-owned brewery and pub on Temple Place.", "35 Temple Pl.", "步行衔接", "门店营业另核", "https://www.downtownboston.org/business/democracy-brewing/", "Downtown Boston Alliance"),
    item("S12", "Downtown Crossing", "海鲜餐饮", "Legal Sea Foods 市中心十字路口店", "Legal Sea Foods — Downtown Crossing", "Washington Street上的海鲜餐厅，按具体分店识别。", "Seafood restaurant on Washington Street; listed as a specific branch.", "558 Washington St.", "步行衔接", "门店营业另核", "https://www.legalseafoods.com/locations/boston-downtown-crossing/", "Legal Sea Foods"),
    item("S13", "金融区", "美食广场", "High Street Place 美食广场", "High Street Place Food Hall", "High Street上的多商户美食广场。", "Multi-vendor food hall on High Street.", "100 High St.", "步行衔接", "档口另核", "https://www.highstreetplace.com/", "High Street Place"),
    item("S14", "Fort Point", "面包咖啡", "Flour Bakery 堡点店", "Flour Bakery + Cafe — Fort Point", "Farnsworth Street上的烘焙咖啡店。", "Bakery and cafe on Farnsworth Street.", "12 Farnsworth St.", "步行衔接", "门店营业另核", "https://www.flourbakery.com/", "Flour Bakery + Cafe", "具体地址另据Signature Boston 2025海港区商户图。"),
    item("S15", "Fort Point", "海鲜餐饮", "Row 34 海港区店", "Row 34 — Seaport", "设在旧波士顿码头公司仓库里的海鲜餐厅。", "Seafood restaurant in a former Boston Wharf Company warehouse.", "383 Congress St.", "步行衔接", "门店营业另核", "https://www.row34.com/location/row34-seaport/", "Row 34"),
    item("S16", "Fort Point", "酿酒餐饮", "Trillium 堡点店", "Trillium — Fort Point", "Thomson Place上的精酿啤酒与餐饮场所。", "Craft brewery and dining venue on Thomson Place.", "50 Thomson Pl.", "步行衔接", "门店营业另核", "https://trilliumbrewing.com/pages/fort-point", "Trillium Brewing"),
    item("S17", "Fort Point", "茶室", "Abigail's Tea Room", "Abigail's Tea Room", "波士顿倾茶博物馆内可不购博物馆门票进入的茶室。", "Tea room at the Tea Party museum, accessible without a museum ticket.", "306 Congress St.", "步行衔接", "茶室营业另核", "https://www.bostonteapartyship.com/faq", "Boston Tea Party Ships & Museum"),
    item("S18", "海港区", "餐饮", "Coquette 餐厅", "Coquette", "位于450 Summer Street的地中海风格餐厅。", "Mediterranean-inspired restaurant at 450 Summer Street.", "450 Summer St.", "沿线", "门店营业另核", "https://www.coquetteboston.com/location/coquette/", "Coquette"),
    item("S19", "海港区", "餐吧", "M.J. O'Connor's 海港区店", "M.J. O'Connor's — Seaport", "位于425 Summer Street的餐吧。", "Restaurant and pub at 425 Summer Street.", "425 Summer St.", "沿线", "门店营业另核", "https://www.mjoconnors.com/location/mj-oconnors-seaport/", "M.J. O'Connor's"),
    item("S20", "海港区", "酿酒餐饮", "Harpoon 波士顿酿酒厂", "Harpoon Boston Brewery", "Northern Avenue上的酿酒厂与啤酒厅。", "Brewery and beer hall on Northern Avenue.", "306 Northern Ave.", "步行衔接", "门店营业另核", "https://harpoonbrewery.com/boston-brewery/", "Harpoon Brewery"),
    item("S21", "海港区", "海鲜餐饮", "Legal Sea Foods 海港店", "Legal Sea Foods — Boston Harborside", "Northern Avenue上的海港区海鲜餐厅。", "Seaport seafood restaurant on Northern Avenue.", "270 Northern Ave.", "步行衔接", "门店营业另核", "https://www.legalseafoods.com/locations/boston-harborside/", "Legal Sea Foods"),
]


def style_sheet(ws, widths, table_rows, freeze="A2"):
    ws.freeze_panes = freeze
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{table_rows}"
    ws.sheet_view.showGridLines = False
    for idx, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="17324D")
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="1C2733")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F0F5F8")
        ws.row_dimensions[row[0].row].height = 54


def make_tab(wb, name, lang, data):
    ws = wb.create_sheet(name)
    if lang == "zh":
        ws.append(["ID", "区域", "类别", "名称", "英文原名", "简介", "地址", "与Summer St关系", "访问属性", "来源机构", "来源链接", "核查日期", "编者说明"])
        for x in data:
            ws.append([x["id"], x["zone"], x["kind"], x["zh"], x["en"], x["zh_desc"], x["address"], x["relation"], x["access"], x["source_name"], x["source"], AS_OF, x["note"]])
        widths = [9, 19, 17, 33, 39, 75, 28, 19, 25, 27, 65, 15, 58]
    else:
        kind_en = {"步道":"Trail", "自由之路站点":"Freedom Trail site", "街区":"District", "广场":"Plaza", "剧院":"Theatre", "纪念地":"Memorial", "公园":"Park", "交通地标":"Transit landmark", "历史街区":"Historic district", "历史建筑":"Historic building", "博物馆":"Museum", "美术馆":"Art museum", "公共活动地":"Event space", "会展地标":"Convention venue", "演出场所":"Performance venue", "步行连接":"Pedestrian link", "服饰":"Apparel", "百货":"Department store", "食品零售":"Grocery", "面包咖啡":"Bakery & cafe", "咖啡":"Coffee", "甜品":"Dessert", "简餐":"Casual dining", "书店":"Bookshop", "餐饮":"Dining", "海鲜餐饮":"Seafood dining", "美食广场":"Food hall", "酿酒餐饮":"Brewery & dining", "茶室":"Tea room", "餐吧":"Restaurant & pub"}
        relation_en = {"沿线":"On Summer Street", "步行衔接":"Walking link", "周边串联":"Area link"}
        zone_en = {"跨区":"Across districts", "市中心西端":"Western downtown", "金融区":"Financial District", "南站":"South Station", "海港区":"Seaport"}
        access_en = {"公共步道；场馆另核":"Public trail; check each venue", "公共步道":"Public trail", "街道可看；入内另核":"Visible from street; check indoor access", "公共街道":"Public street", "公共空间":"Public space", "演出需查票务":"Check event tickets", "开放时间见官网":"Check official hours", "交通设施":"Transit facility", "公共街道外观":"Exterior from public street", "外观":"Exterior", "展览需预约购票":"Book museum ticket", "入馆另核":"Check admission", "公共公园":"Public park", "开放日另核":"Check opening days", "活动开放另核":"Check event schedule", "非日常开放景点":"Access depends on event", "门店营业另核":"Check current business hours", "档口另核":"Check individual vendors", "茶室营业另核":"Check tea room hours"}
        note_en = {"F00":"The full trail extends beyond the Summer Street corridor.", "P09":"The city historic report uses 363 Summer St./10 Melcher St.; the current building site uses 263 Summer St.", "S14":"The address is also shown on Signature Boston's 2025 Seaport dining map."}
        ws.append(["ID", "Area", "Type", "Name", "Chinese name", "Description", "Address", "Summer St link", "Visit note", "Source organization", "Source URL", "Checked", "Editor note"])
        for x in data:
            ws.append([x["id"], zone_en.get(x["zone"], x["zone"]), kind_en[x["kind"]], x["en"], x["zh"], x["en_desc"], x["address"], relation_en[x["relation"]], access_en[x["access"]], x["source_name"], x["source"], AS_OF, note_en.get(x["id"], "")])
        widths = [9, 19, 23, 44, 33, 80, 28, 21, 25, 27, 65, 15, 58]
    style_sheet(ws, widths, ws.max_row)
    for row in ws.iter_rows(min_row=2):
        cell = row[10]
        cell.hyperlink = cell.value
        cell.font = Font(name="Arial", size=10, color="0563C1", underline="single")
        row[11].number_format = "yyyy-mm-dd"
    return ws


def build():
    assert len(rows) == 53, len(rows)
    assert len({x["id"] for x in rows}) == len(rows)
    assert all(x["source"].startswith("https://") and x["zh_desc"] and x["en_desc"] for x in rows)
    wb = Workbook()
    wb.remove(wb.active)
    make_tab(wb, "zh-CN", "zh", rows)
    make_tab(wb, "en", "en", rows)
    make_tab(wb, "特色商铺", "zh", [x for x in rows if x["id"].startswith("S")])

    ws = wb.create_sheet("自由之路16站")
    ws.append(["顺序", "ID", "中文名", "English name", "与本区关系", "位置", "简述", "官方来源", "核查日期"])
    for i, (key, zh, en, zone, zh_desc, _, address, source) in enumerate(trail, 1):
        ws.append([i, key, zh, en, "本区步行衔接" if i <= 11 else "北端/查尔斯敦延伸", address, zh_desc, source, AS_OF])
    style_sheet(ws, [8, 10, 35, 50, 25, 32, 70, 70, 16], ws.max_row)
    for row in ws.iter_rows(min_row=2):
        row[7].hyperlink = row[7].value
        row[7].font = Font(name="Arial", size=10, color="0563C1", underline="single")
        row[8].number_format = "yyyy-mm-dd"

    ws = wb.create_sheet("说明")
    notes = [
        ("范围", "Summer Street从Downtown Crossing经South Station、Fort Point至Seaport；收录沿线和步行可衔接的代表性地点。‘步行衔接’为编辑范围标签，尚未测算实际距离或路线。"),
        ("自由之路", "官方自由之路共16站，整条步道超出Summer Street范围。主表收录市中心11站；北端与查尔斯敦5站只放在‘自由之路16站’对照页。"),
        ("商铺", "按具体分店识别。来源页面只能证明核查时有公开列示；营业、搬迁、价格、预约与临时闭馆须在出行当天复核。"),
        ("来源", "每行给出可点击的机构或经营者网页；简述由这些资料重新概括，中英文本均为本次编辑译写，不冒充馆方原文。"),
        ("评级与路线", "本版是来源可查的候选清单，未运行V3评级、独立审计、坐标核对或路线生成，也未接入Web/App或数据库。"),
        ("照片", "本版未收集图片，不把商铺外观或整体街区图片冒充具体景点照片。"),
        ("核查日期", AS_OF.isoformat()),
        ("重建", "python3 utils/import_data/boston_summer_st_list.py；来源与条目保存在该脚本中。"),
    ]
    ws.append(["项目", "说明"])
    for note in notes:
        ws.append(note)
    style_sheet(ws, [22, 110], ws.max_row)
    for row in range(2, ws.max_row + 1):
        ws.row_dimensions[row].height = 56

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    check = load_workbook(OUT, read_only=True)
    assert check.sheetnames == ["zh-CN", "en", "特色商铺", "自由之路16站", "说明"]
    assert check["zh-CN"].max_row == 54 and check["en"].max_row == 54
    assert check["特色商铺"].max_row == 22 and check["自由之路16站"].max_row == 17
    print(OUT)
    print(f"53 main entries, 21 shops, 16 official trail sites; {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    build()
