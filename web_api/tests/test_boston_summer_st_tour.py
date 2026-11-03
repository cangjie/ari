import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMPORT = ROOT / "utils" / "import_data"
TOUR = ROOT / "web_api" / "tour"
sys.path.insert(0, str(IMPORT))


def generated():
    return json.loads((TOUR / "data" / "boston_summer_st.json").read_text("utf-8"))


def test_boston_base_collection_contract():
    data = generated()
    assert data["key"] == "boston_summer_st"
    assert data["mode"] == "collection"
    assert len(data["stops"]) == 53
    assert len(data["places"]) == 53
    assert Counter(stop["tier"] for stop in data["stops"].values()) == {"A": 12, "B": 11, "C": 30}
    assert sum(stop["kind"] == "shop" for stop in data["stops"].values()) == 21
    assert {stop["area"]["zh"] for stop in data["stops"].values()} == {
        "跨区", "市中心西端", "Downtown Crossing", "金融区", "南站", "Fort Point", "海港区"
    }
    assert all(stop["sources"] for stop in data["stops"].values())
    assert data["provenance"]["business_database_written"] is False
    assert data["provenance"]["checked_on"] == "2026-11-03"


def test_review_findings_and_live_status_boundaries_are_visible():
    data = generated()
    reviews = [stop for stop in data["stops"].values() if stop["review"]]
    assert len(reviews) == 14
    shops = [stop for stop in data["stops"].values() if stop["kind"] == "shop"]
    assert all("未实时核实" in stop["status"]["zh"] for stop in shops)
    assert all("unverified" in stop["status"]["en"].lower() for stop in shops)

