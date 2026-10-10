"""导览站（web_api/tour/）的验收测试。

导览站是纯静态站点，线上由 Nginx 直接提供，不经过 FastAPI。这里不测服务，
测的是「生成出来的数据自己对不对得上」和「页面有没有引用站外的东西」——
前者错了地图上的点会画歪或路线分钟数对不上，后者在国内网络上表现为页面卡住。

数据由 utils/import_data/tour_build.py 生成；这些测试不连数据库。
"""

import json
import math
import re
from pathlib import Path

import pytest

TOUR_DIR = Path(__file__).resolve().parent.parent / "tour"
MUSEUMS = sorted(p.stem for p in (TOUR_DIR / "data").glob("*.json"))


@pytest.fixture(params=MUSEUMS)
def tour(request):
    return json.loads((TOUR_DIR / "data" / f"{request.param}.json").read_text(encoding="utf-8"))


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def in_area(x, y, area):
    poly = area["poly"]
    inside, best = False, float("inf")
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        t = 0 if l2 == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / l2))
        best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
    return inside or best <= area["buffer"]


def test_at_least_one_museum_is_published():
    assert MUSEUMS, "web_api/tour/data/ 下没有数据文件 —— 先跑 tour_build.py"


def test_places_and_stops_reference_each_other(tour):
    places = {p["id"]: p for p in tour["places"]}
    assert len(places) == len(tour["places"]), "地点 id 重复"

    listed = [seq for p in tour["places"] for seq in p["stops"]]
    assert sorted(listed) == sorted(int(k) for k in tour["stops"]), "地点下列出的站与站表不是同一批"
    for key, stop in tour["stops"].items():
        assert stop["seq"] == int(key)
        assert stop["seq"] in places[stop["place"]]["stops"]
        assert stop["intro"] and all(p.strip() for p in stop["intro"]), f"seq {key} 没有介绍"
        assert stop["tier"] in "SABC"


def test_places_sit_inside_canvas_and_area(tour):
    w, h = tour["canvas"]["w"], tour["canvas"]["h"]
    for p in tour["places"] + [tour["entrance"]]:
        name = p["name"]["zh"]
        assert 0 <= p["x"] <= w and 0 <= p["y"] <= h, f"{name} 画到了画布外面"
        assert in_area(p["x"], p["y"], tour["area"]), f"{name} 在景区范围之外，站在那里圆点会是灰的"


def test_projection_reproduces_place_coordinates(tour):
    """页面用 proj 把 GPS 换成画布坐标；同一组参数必须把地点的经纬度换回它自己的 x、y。"""
    q = tour["proj"]
    for p in tour["places"] + [tour["entrance"]]:
        e, n = (p["lon"] - q["lon0"]) * q["mlon"], (p["lat"] - q["lat0"]) * q["mlat"]
        x, y = q["a"] * e + q["b"] * n + q["tx"], q["c"] * e + q["d"] * n + q["ty"]
        assert math.hypot(x - p["x"], y - p["y"]) < 0.2, p["name"]["zh"]


def test_routes_follow_the_visiting_order(tour):
    order = [int(k) for k in tour["stops"]]            # 站表按参观顺序写出
    ids = [r["id"] for r in tour["routes"]]
    assert len(ids) == len(set(ids))
    assert tour["default_route"] in ids
    for r in tour["routes"]:
        assert r["stops"], f"路线 {r['id']} 是空的"
        assert set(r["stops"]) <= set(order), f"路线 {r['id']} 里有站表之外的站"
        assert r["stops"] == [s for s in order if s in set(r["stops"])], f"路线 {r['id']} 没按参观顺序排"


def test_route_minutes_add_up(tour):
    """停留是各站之和；步行按地点坐标重算一遍，应与生成器（route_plan）给的数对上。"""
    places = {p["id"]: p for p in tour["places"]}
    ent, walk = tour["entrance"], tour["walk"]
    for r in tour["routes"]:
        stay = sum(tour["stops"][str(s)]["dwell"] for s in r["stops"])
        assert r["stay"] == stay

        pts = [(ent["lat"], ent["lon"])]
        pts += [(places[tour["stops"][str(s)]["place"]]["lat"],
                 places[tour["stops"][str(s)]["place"]]["lon"]) for s in r["stops"]]
        pts.append((ent["lat"], ent["lon"]))
        minutes = sum(haversine(*a, *b) for a, b in zip(pts, pts[1:])) * walk["detour"] / walk["m_per_min"]
        assert abs(r["walk"] - minutes) <= 0.51, f"路线 {r['id']} 的步行分钟数与坐标对不上"
        assert abs(r["total"] - (stay + minutes)) <= 0.51
        assert r["total"] <= r["budget"], f"路线 {r['id']} 超出了时间预算"


def test_photos_listed_in_data_exist(tour):
    photos = [tour["card"]["cover"]] + [p["photo"] for p in tour["places"]]
    for stop in tour["stops"].values():
        photos.append(stop["photo"])
        photos += [o["photo"] for o in stop["objects"]]
    for rel in filter(None, photos):
        assert (TOUR_DIR / rel).is_file(), f"数据里写了 {rel}，仓库里没有这个文件"


def test_page_loads_nothing_from_other_sites():
    """字体、脚本、样式全部随站点提供。引用站外资源在国内网络上会让页面卡住或缺样式。"""
    for name in ("index.html", "app.css", "app.js"):
        text = (TOUR_DIR / name).read_text(encoding="utf-8")
        # 页面图标是内嵌的 SVG，里面的命名空间声明不是网络请求
        text = text.replace("http://www.w3.org/2000/svg", "")
        assert not re.search(r"https?://|[\"'(]//[\w.-]+\.\w", text), f"{name} 引用了站外地址"


def test_stylesheet_fonts_exist():
    css = (TOUR_DIR / "app.css").read_text(encoding="utf-8")
    fonts = re.findall(r'url\("(fonts/[^"]+)"\)', css)
    assert fonts
    for rel in fonts:
        assert (TOUR_DIR / rel).is_file(), rel
