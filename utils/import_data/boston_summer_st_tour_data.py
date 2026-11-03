"""Published collection configuration for Boston Summer Street."""

VIEW_MODE = "collection"
GPS_GUIDE = True
CHECKED_ON = "2026-11-03"

AREAS = {
    "跨区": "Across districts",
    "市中心西端": "Western downtown",
    "Downtown Crossing": "Downtown Crossing",
    "金融区": "Financial District",
    "南站": "South Station",
    "Fort Point": "Fort Point",
    "海港区": "Seaport",
}

STATUS_EN = {
    "地点与简介有来源；开放、预约、收费及临时关闭未实时核实":
        "The place and description are sourced; current opening, reservations, admission and temporary closures are unverified.",
    "公开网页有记录；现场营业、菜单、价格及临时停业未实时核实":
        "The business has a public web listing; live operation, menu, prices and temporary closures are unverified.",
}

NAME = {"zh": "波士顿 Summer Street 及周边", "en": "Boston Summer Street and Nearby"}
CARD = {
    "city": {"zh": "波士顿", "en": "Boston"},
    "district": {"zh": "市中心 · Fort Point · 海港区", "en": "Downtown, Fort Point and Seaport"},
    "type": {"zh": "城市历史 · 滨水 · 特色商铺", "en": "Urban history, waterfront and specialty shops"},
    "short": {"zh": "Summer Street", "en": "Summer Street"},
    "desc": {
        "zh": "沿 Summer Street 从 Downtown Crossing 走到海港区，并衔接自由之路市中心站点；共53条双语资料。",
        "en": "Follow Summer Street from Downtown Crossing to the Seaport, with linked downtown Freedom Trail sites; 53 bilingual records.",
    },
    "hours": "开放、预约、票价及营业请在出行当天核实",
    "hours_note": {"zh": "查看介绍、评级、来源与复核提示", "en": "Browse descriptions, tiers, sources and review notes"},
}

OPENING = {
    "zh": "场馆开放、预约、票价、门店营业及临时关闭均未实时核实；请在出行当天查看各自官网。",
    "en": "Venue access, reservations, admission, business hours and temporary closures are not live-verified; check each official site on the day of travel.",
}

PLANNING = {
    "zh": "53条包含自由之路整体与组成站点，并非53个互不重叠的路线站。S/A/B/C表示本走廊文化参观优先级；餐饮不按口味、服务或价格评级。地图位置、路线与步行时间以保存的公开街道资料为依据，属于导览估计而非逐向导航。",
    "en": "The 53 records include the Freedom Trail as a whole and individual sites, so they are not 53 non-overlapping route stops. S/A/B/C measures cultural visit priority within this corridor; food is not rated for taste, service or price. Map positions, walks and timings use saved public-street references and are guide estimates, not turn-by-turn navigation.",
}


def platform_reference(row, capture):
    return (
        "经营者或街区网页快照；实时营业、菜单、价格与临时停业未核实",
        "Operator or district web snapshot; live operation, menu, prices and temporary closures are unverified",
    )
