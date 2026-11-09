"""Candidate inventory of places on the Western New England University campus (Springfield, MA).

Same row schema as boston_area_list.py, so the capture, passage audit and list-mode build can follow
the same steps. Every row cites a first-party WNE page: the campus page, the campus map, the history
page, the libraries page, the dining page, the art gallery page, the athletics facilities page.
Campus-map numbers in the address field refer to the official numbered map.
"""
from __future__ import annotations

ADDRESS = "1215 Wilbraham Road, Springfield, MA 01119"

CAMPUS_PAGE = "https://wne.edu/become-a-student/why-wne/campus"
CAMPUS_MAP = "https://wne.edu/become-a-student/visit/campus-map"
HISTORY = "https://wne.edu/about/history"
LIBRARIES = "https://wne.edu/libraries/index"
DINING = "https://wne.edu/student-experience/dining/index"
ART_GALLERY = "https://wne.edu/art-gallery/index"
FACILITIES = "https://wnegoldenbears.com/facilities"
SOURCE_NAME = {
    CAMPUS_PAGE: "Western New England University（校园介绍）",
    CAMPUS_MAP: "Western New England University（校园地图）",
    HISTORY: "Western New England University（校史）",
    LIBRARIES: "Western New England University（图书馆）",
    DINING: "Western New England University（餐饮）",
    ART_GALLERY: "Western New England University（艺术画廊）",
    FACILITIES: "Western New England University Athletics（体育设施）",
}


def item(key: str, zone: str, kind: str, zh: str, en: str, zh_desc: str, en_desc: str,
         address: str, relation: str, access: str, source: str, note: str = "") -> dict:
    return {
        "id": key, "zone": zone, "kind": kind, "zh": zh, "en": en,
        "zh_desc": zh_desc, "en_desc": en_desc, "address": address,
        "relation": relation, "access": access,
        "source": source, "source_name": SOURCE_NAME[source],
        "note": note or "校园官方页面的内容；发布前须经原文审计。",
    }


ZONE = "Campus core"

rows = [
    item("wne_campus", ZONE, "大学", "西新英格兰大学校园", "Western New England University campus",
         "斯普林菲尔德 Wilbraham Road 上的 215 英亩校园，建有 28 座主要建筑，各楼环绕步行便利的中心区布置。",
         "A 215-acre campus on Wilbraham Road in Springfield, with 28 major buildings clustered around a walkable central core.",
         ADDRESS, "整体（以下条目为校园组成部分）", "校园开放与访客安排以学校为准；可参加学校组织的校园参观",
         CAMPUS_PAGE),
    item("wne_welcome_center", ZONE, "建筑", "Kevin S. Delbridge 访客中心", "Kevin S. Delbridge Welcome Center",
         "校园地图第 1 号，内有本科招生办公室与访客中心。",
         "Map location 1: houses Undergraduate Admissions and the Visitors Center.",
         ADDRESS + "（校区地址）", "校园入口", "访客入校安排以学校访客页面为准",
         CAMPUS_MAP),
    item("wne_deliso_hall", ZONE, "建筑", "Joseph J. Deliso Sr. Hall（Deliso 楼）", "Joseph J. Deliso Sr. Hall",
         "校园地图第 3 号，内有行政办公室，包括总务办公室、市场与对外事务部门。",
         "Map location 3: houses administrative offices, including the Controller's Office and Marketing and External Affairs.",
         ADDRESS + "（校区地址）", "校园行政楼", "办公楼，入内以学校安排为准",
         CAMPUS_MAP),
    item("wne_emerson_hall", ZONE, "建筑", "埃默森楼", "Emerson Hall",
         "1959 年启用，是校园第一座建筑，现为文理学院多个专业的教学楼。",
         "Opened in 1959 as the first building on campus, today's Emerson Hall.",
         ADDRESS, "校园历史建筑", "教学楼，入内以学校安排为准",
         HISTORY),
    item("wne_herman_hall", ZONE, "建筑", "赫尔曼楼", "Herman Hall",
         "设有数学与写作中心、艺术工作室和多媒体教室，经过 830 万美元的翻修。",
         "Houses the Math and Writer Centers, an Art Studio and multimedia classrooms; underwent an $8.3 million renovation.",
         ADDRESS + "（校区地址）", "校园教学楼", "教学楼，入内以学校安排为准",
         CAMPUS_PAGE),
    item("wne_csp", ZONE, "建筑", "科学与药学中心（Center for the Sciences and Pharmacy）", "Center for the Sciences and Pharmacy",
         "耗资 4000 万美元的高科技楼，设 19 间科学实验室、模型药房，二层设有健康与福祉中心。",
         "A $40 million building with 19 laboratories and a model pharmacy; the Center for Health and Well-Being is on the second floor.",
         ADDRESS + "（校区地址）", "校园科学楼", "教学与医疗服务场所，入内以学校安排为准",
         CAMPUS_PAGE),
    item("wne_damour_library", ZONE, "图书馆", "D'Amour 图书馆", "D'Amour Library",
         "校园研究与社交中心，有 110 多个数据库、24 小时自习区和媒体中心。",
         "A research and social hub for students, with access to more than 110 databases, a 24x7 study area and a Media Center.",
         ADDRESS + "（校区地址）", "校园图书馆", "图书馆，开放时间与入馆规定以学校公告为准",
         LIBRARIES),
    item("wne_blake_law_center", ZONE, "建筑", "Blake 法学中心", "Blake Law Center",
         "校园地图第 12 号，为法学院所在地，内有法学图书馆、普通法诊所与模拟法庭（Moot Courtroom）。",
         "Map location 12: home of the School of Law, with the Law Library, the Common Law Clinics and a Moot Courtroom.",
         ADDRESS + "（校区地址）", "法学院大楼", "法学院大楼，入内以学校安排为准",
         CAMPUS_MAP),
    item("wne_churchill_hall", ZONE, "建筑", "丘吉尔楼", "Churchill Hall",
         "商学院所在地，以首任校长 John D. Churchill 命名，内设 Cohen 交易室与技术中心。",
         "Home of the College of Business, named for the university's first president, Dr. John D. Churchill; features the Cohen Trading Room and Technology Center.",
         ADDRESS + "（校区地址）", "商学院大楼", "商学院大楼，入内以学校安排为准",
         CAMPUS_PAGE),
    item("wne_art_gallery", ZONE, "艺术", "校园艺术画廊", "WNE Art Gallery",
         "位于 St. Germain 校园中心，为校园艺术家提供免费展示场地，定期举办个人与群展及艺术家讲座。",
         "Located in the St. Germain Campus Center, the gallery hosts solo and curated group shows and gallery talks; gallery space is offered at no charge.",
         ADDRESS + "（校区地址）", "校园艺术展示", "展览与讲座时间以学校公告为准",
         ART_GALLERY),
    item("wne_university_commons", ZONE, "餐饮", "大学公共中心（University Commons）", "University Commons",
         "2018 年启用的餐饮与社交中心，设星巴克咖啡馆、餐台、便利店与两层的住校餐厅。",
         "Opened in 2018 as a dining and social hub, with a Starbucks café, a grille, a convenience store and a two-story residential dining hall.",
         ADDRESS + "（校区地址）", "校园餐饮", "营业时间与菜单以学校为准；不评价口味",
         CAMPUS_PAGE),
    item("wne_sleith_hall", ZONE, "建筑", "Sleith 楼", "Sleith Hall",
         "工程创新中心，有约 30 间工程实验室，其中生物医学工程套间模拟医院病房；经 1280 万美元翻修扩建。",
         "A hub of engineering innovation, with 30 engineering laboratories, including a biomedical engineering suite that replicates a hospital setting; a $12.8 million renovation and expansion.",
         ADDRESS + "（校区地址）", "工程学院大楼", "实验室入内以学校安排为准",
         CAMPUS_PAGE),
    item("wne_wood_auditorium", ZONE, "建筑", "Wood Hall 礼堂（官方页面称 Wood Hall Auditorium）", "Wood Hall Auditorium",
         "全校用于讲座、演讲与演出的礼堂。",
         "Used campus-wide for lectures, presentations and performances.",
         ADDRESS + "（校区地址）", "校园礼堂", "活动时间以学校公告为准",
         CAMPUS_PAGE),
    item("wne_rivers_memorial_hall", ZONE, "建筑", "Rivers 纪念楼", "Rivers Memorial Hall",
         "校园地图第 11 号，内有校园广播电台、学生出版物办公室，以及戏剧与音乐项目。",
         "Map location 11: houses the Radio Station, student publication offices, and Theatre and Music programs.",
         ADDRESS + "（校区地址）", "戏剧与音乐项目所在楼", "入内以学校安排为准",
         CAMPUS_MAP),
    item("wne_golden_bear_stadium", ZONE, "体育", "金熊体育场", "Golden Bear Stadium",
         "可容纳 1,500 人的体育场，是户外体育区的核心，学生在“The Cave”一侧为同学加油。",
         "A 1,500-seat stadium and the centerpiece of the outdoor sports complex; students cheer from \"The Cave\".",
         ADDRESS + "（校区地址）", "校园体育区", "比赛与开放时间以学校公告为准",
         CAMPUS_PAGE),
    item("wne_ahlc", ZONE, "体育", "Anthony S. Caprio 校友健康生活中心", "Anthony S. Caprio Alumni Healthful Living Center",
         "校园体育设施之一，用于男女篮球、女子排球及男女摔跤等项目。",
         "One of the campus athletic facilities, used by men's and women's basketball, women's volleyball, and men's and women's wrestling.",
         ADDRESS + "（校区地址）", "校园体育设施", "比赛与开放时间以学校公告为准",
         FACILITIES),
]

assert len({row["id"] for row in rows}) == len(rows), "duplicate WNE inventory ids"
SOURCES = sorted({row["source"] for row in rows})
