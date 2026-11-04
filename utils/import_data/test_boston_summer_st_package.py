import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
KEY = "boston_summer_st"
PREFIX = KEY + "_v3"


def load(suffix):
    return json.loads((HERE / f"{PREFIX}_{suffix}").read_text("utf-8"))


def test_package_is_complete_bilingual_and_independently_audited():
    source_path = HERE / f"{PREFIX}_site_data.json"
    source = load("site_data.json")
    ratings = load("ratings.json")
    audits = [json.loads(line) for line in (HERE / f"{PREFIX}_audit1_slim.jsonl").read_text("utf-8").splitlines() if line]
    manifest = load("audit_manifest.json")
    translations = load("translations.json")
    final = load("final.json")
    report = load("verification_report.json")

    assert source["museum_key"] == KEY
    assert source["state"] == "独立审计完成"
    assert len(source["rows"]) == 53
    assert len({row["identity_key"] for row in source["rows"]}) == 53
    assert all(row["source_seq"] == index for index, row in enumerate(source["rows"], 1))
    assert all(row["identity_key"].islower() for row in source["rows"])
    assert sum(row["entry_kind"] == "特色商铺" for row in source["rows"]) == 21

    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert {manifest["input_sha256"], translations["input_sha256"], final["input_sha256"]} == {source_sha}
    from tour_collection_build import verify_inventory_rating
    revision = json.loads((HERE / f"{KEY}_revision_v3_draft.json").read_text('utf-8'))
    verify_inventory_rating(ratings, revision, source, translations)
    assert manifest["model"] == "claude-sonnet-5 effort=medium"
    assert manifest["count"] == 53
    assert len(audits) == 53
    assert {row["seq"] for row in audits} == set(range(1, 54))
    assert Counter(row["tier"] for row in ratings["results"]) == {"S": 1, "A": 12, "B": 10, "C": 30}
    assert final["state"] == "独立审计完成"
    assert len(final["rows"]) == 53
    assert all(row["rating"] == ratings["results"][row["source_seq"] - 1] for row in final["rows"])
    assert all(translations["values"][row["name"]]["en"] for row in source["rows"])
    assert all(translations["values"][row["description"]]["en"] for row in source["rows"])
    assert report["business_database_written"] is False
    assert report["production_questions_posted"] == 0


def test_every_row_has_saved_source_text_with_honest_retrieval_method():
    source = load("site_data.json")
    capture = load("source_capture.json")
    saved = {row["id"]: row for row in capture["sources"]}
    assert saved
    for row in source["rows"]:
        assert row["evidence"]
        for evidence in row["evidence"]:
            item = saved[evidence["source_id"]]
            assert item["status"] == "ok"
            assert item["http_status"] == 200
            assert item["retrieval_method"] == "verified_HTTP_extracted_text"
            assert evidence["quote"] in item["source_text"]
            assert item["url"] == evidence["url"]
            assert item["source_text"].strip()
            assert evidence["quote"].strip()

