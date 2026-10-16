"""宛平城发布契约：免费线路不能引导付费，审过的资料不能在发布时漏掉。"""
import hashlib
import importlib
import json
import sys
from pathlib import Path

from app import tour_qa_llm as llm

ROOT = Path(__file__).resolve().parents[2]
TOUR = ROOT / 'web_api/tour'


def published():
    path = TOUR / 'data/wanping.json'
    assert path.exists(), '宛平城尚未发布到共享导览数据'
    return json.loads(path.read_text())


def test_collected_photos_have_local_files_and_subject_specific_sources():
    m = published()
    assert m['card']['cover'], '首页必须有已收录的宛平城照片'
    for seq in [1, 2, 4, 5, 8, 14, 15, 16, 19, 31, 32, 39]:
        stop = m['stops'][str(seq)]
        assert stop['photo'], stop['name']['zh']
        info = stop['photo_info']
        assert info['caption']['zh'] and info['source']['url'].startswith('https://')
        file = TOUR / stop['photo']
        assert file.is_file() and file.stat().st_size < 600 * 1024
        assert hashlib.sha256(file.read_bytes()).hexdigest() == info['sha256']
    assert m['stops']['14']['photo'] != m['stops']['15']['photo']
    # 馆外观不能冒充2025年基本陈列或其室内展区的照片。
    assert all(m['stops'][str(seq)]['photo'] is None for seq in range(20, 30))
    assert all('外观' in m['stops'][str(seq)]['photo_info']['caption']['zh'] for seq in [19, 39])
    assert '宛平县署' in m['stops']['8']['photo_info']['caption']['zh']


def test_reordering_records_does_not_turn_a_lion_into_the_bridge_cover():
    scripts = str(ROOT / 'utils/import_data')
    sys.path.insert(0, scripts)
    try:
        builder = importlib.import_module('tour_package_build')
        rows = {r['source_seq']: r for r in json.loads((ROOT / 'utils/import_data/wanping_final.json').read_text())['rows']}
        photos = {p['seq']: p for p in json.loads((ROOT / 'utils/import_data/wanping_tour_photos.json').read_text())['photos']}
        # 同一份显式封面配置在两种展示顺序下都必须指向整桥，而不是石狮。
        for seqs in [[14, 15, 16, 17, 18, 39], [15, 14, 16, 17, 18, 39]]:
            assert builder.select_cover('bridge', seqs, rows, photos, {'bridge': 14}) == 14
    finally:
        sys.path.remove(scripts)


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
