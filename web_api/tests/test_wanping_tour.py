"""宛平城发布契约：免费线路不能引导付费，审过的资料不能在发布时漏掉。"""
import hashlib
import json
from pathlib import Path

from app import tour_qa_llm as llm

ROOT = Path(__file__).resolve().parents[2]
TOUR = ROOT / 'web_api/tour'


def published():
    path = TOUR / 'data/wanping.json'
    assert path.exists(), '宛平城尚未发布到共享导览数据'
    return json.loads(path.read_text())


def test_server_catalog_selects_existing_destinations_without_duplicate_keys():
    keys = json.loads((TOUR / 'catalog.json').read_text())['museums']
    assert keys and len(keys) == len(set(keys))
    for key in keys:
        assert json.loads((TOUR / 'data' / f'{key}.json').read_text())['key'] == key


def test_every_reviewed_record_is_available_without_invented_indoor_hotspots():
    m = published()
    assert set(map(int, m['stops'])) == set(range(1, 40))
    assert len({p['id'] for p in m['places']}) == len(m['places'])
    assert len(m['places']) < 15  # 九个馆内分区不能伪装成九个GPS地点
    locations = {m['stops'][str(s)]['place'] for s in range(19, 30)}
    assert len(locations) == 1
    assert all(m['stops'][str(s)]['included_in'] == 20 for s in range(21, 30))
    assert all(m['stops'][str(s)]['dwell'] == 0 for s in range(21, 30))
    assert m['stops']['1']['review']
    assert 'ticket' in m['stops']['14']['status']['en'].lower()
    assert 'monday' in m['stops']['19']['status']['en'].lower()
    source = ROOT / 'utils/import_data/wanping_final.json'
    assert m['provenance']['package_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_free_route_excludes_paid_admissions_and_full_route_includes_them():
    m = published()
    routes = {r['id']: r for r in m['routes']}
    free, full = routes['free'], routes['full']
    assert free['ticket_cny'] == 0
    assert {4, 14}.isdisjoint(free['stops'])
    assert {4, 14} <= set(full['stops'])
    assert set(free['stops']) <= set(full['stops'])
    assert full['ticket_cny'] == 50  # 官方参考成人价：桥20+登城30，非承诺当天报价
    for r in [free, full]:
        assert 20 in r['stops'] and 19 not in r['stops']  # 整馆与基本陈列不能重复计时
        assert r['note']['zh'] and r['sources']
        assert r['path'] and r['legs']
    # OSM明确标为城墙的道路不能被免费线当作穿行捷径。
    assert 27035588 not in free['way_ids']
    assert 27035564 not in free['way_ids']  # 卢沟桥桥面


def test_assistant_receives_the_same_admission_and_route_constraints_as_visitors():
    m = published()
    material = llm.museum_material(m)
    assert '50' in material and '0' in material
    assert '周一' in material and '半景画' in material
    assert routes_note(m) in material


def routes_note(m):
    return next(r['note']['zh'] for r in m['routes'] if r['id'] == 'free')
