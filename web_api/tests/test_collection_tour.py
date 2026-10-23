"""清单发布的关键契约：不漏原表内容，不伪造地图与营业，问答和页面同源。"""
import hashlib
import json
from collections import Counter
from pathlib import Path

from app import tour_qa_llm as llm

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'utils/import_data'
KEY = 'nanluo_shichahai'


def collection():
    return json.loads((ROOT / f'web_api/tour/data/{KEY}.json').read_text(encoding='utf-8'))


def test_every_audited_record_keeps_its_identity_description_and_rating():
    m = collection()
    package = json.loads((HERE / f'{KEY}_final.json').read_text(encoding='utf-8'))
    assert len(m['places']) == len(m['stops']) == len(package['rows']) == 100
    for row in package['rows']:
        s = m['stops'][str(row['source_seq'])]
        assert s['place'] == row['identity_key']
        assert s['name']['zh'] == row.get('display_name', row['name'])
        assert '\n'.join(s['intro']) == row['description']
        assert s['tier'] == row['rating']['tier'] and s['core'] == row['rating']['core']
        assert s['status']['zh'] == row['status']
        assert s['borrowed']['zh'] == row['editor_note']
        assert set(e['url'] for e in row['evidence']) <= {e['url'] for e in s['sources']}
    assert Counter(s['tier'] for s in m['stops'].values()) == dict(S=8, A=32, B=35, C=25)
    assert m['provenance']['package_sha256'] == hashlib.sha256((HERE / f'{KEY}_final.json').read_bytes()).hexdigest()


def test_browse_map_keeps_unlocated_records_and_does_not_claim_arrival_or_routes():
    m = collection()
    assert m['mode'] == 'collection'
    assert not m['routes'] and m['default_route'] == 'none'
    assert m['map_mode'] == 'browse' and m['map']['water'] and m['map']['roads']
    assert 'area' not in m  # 无定位范围，不交给原生到站引擎。
    positions = [p for p in m['places'] if 'x' in p]
    assert len(positions) == 37
    assert all('r' not in p for p in m['places'])
    assert all(p['position']['source']['url'].startswith('https://www.openstreetmap.org/') for p in positions)
    assert all('x' not in p for p in m['places'] if p['id'] in ['qibaishi', 'gongwang_xijin', 'shop_huguosi'])
    assert all(s['dwell'] is None for s in m['stops'].values())


def test_photo_files_match_subject_manifest_without_borrowing_parent_photos():
    m = collection()
    manifest = json.loads((HERE / f'{KEY}_tour_photos.json').read_text('utf-8'))
    photos = {p['seq']: p for p in manifest['photos']}
    assert len(photos) == 10
    for p in m['places']:
        seq = p['stops'][0]
        assert bool(p['photo']) == (seq in photos)
        if seq in photos:
            photo = photos[seq]
            assert p['id'] == photo['identity_key']
            assert hashlib.sha256((ROOT / 'web_api/tour' / p['photo']).read_bytes()).hexdigest() == photo['sha256']
            assert p['photo_info']['source'] == photo['source']
    assert m['stops']['48']['photo'] and not m['stops']['76']['photo']
    material = llm.museum_material(m)
    for p in m['places']:
        if p.get('position'):
            assert p['position']['note'] in material
            assert p['position']['source']['url'] in material
        if p.get('photo_info'):
            assert p['photo_info']['caption']['zh'] in material
    assert '没有向回答模型传入图片' in material


def test_shops_and_guomoruo_are_searchable_without_merging_branches():
    m = collection()
    shops = [s for s in m['stops'].values() if s['kind'] == 'shop']
    assert len(shops) == 16
    assert all(s['address']['zh'] and s['specialty']['zh'] and s['platform']['zh'] for s in shops)
    guo = m['stops']['48']
    assert guo['place'] == 'guomoruo' and guo['tier'] == 'A'
    assert guo['name']['zh'] == '郭沫若故居（郭沫若纪念馆）'
    assert '1号' in m['stops']['86']['address']['zh']
    assert '遮挡' in m['stops']['89']['address']['zh']  # 平台遮挡的门牌不能猜。
    assert not m['stops']['100']['related']  # 富华斋不属于梅兰芳纪念馆。


def test_visitor_and_assistant_share_review_and_merchant_boundaries():
    m = collection()
    flagged = [s['seq'] for s in m['stops'].values() if s['review']]
    assert flagged == [76]
    assert '故宫' in m['stops']['76']['review']
    material = llm.museum_material(m)
    for s in m['stops'].values():
        assert s['name']['zh'] in material
        for f in ['address', 'specialty', 'platform']:
            if s[f]['zh']:
                assert s[f]['zh'] in material
    assert '建议停留约 None' not in material and '建议停留约 0' not in material
    assert '本清单未提供已核实的路线或停留时间' in material
    assert '平台口碑与消费信息另列' in material
    assert 'Core 7.3510' in material  # 页面显示的分数也必须进入问答材料。


def test_axis_towers_are_not_confused_with_the_same_named_lama_temple_towers():
    m = collection()
    for p in m['places']:
        if p['id'] in ('gulou', 'zhonglou'):
            assert 116.389 < p['lon'] < 116.391
            assert 39.938 < p['lat'] < 39.942
    a, b = [next(p for p in m['places'] if p['id'] == key) for key in ('heizhima', 'houyuanensi')]
    assert (a['lat'], a['lon']) != (b['lat'], b['lon'])


def test_three_lakes_have_complete_outer_rings_and_island_holes():
    import sys
    sys.path.insert(0, str(HERE))
    from tour_collection_media import water_rings
    source = json.loads((HERE / f'{KEY}_osm_data.json').read_text('utf-8'))
    elements = {e['id']: e for e in source['elements'] if e['type'] == 'relation'}
    for eid in [409777, 11518929, 12746173]:
        rings = water_rings(elements[eid])
        assert any(role == 'outer' for _, role in rings)
        assert any(role == 'inner' for _, role in rings)
        assert all(ring[0] == ring[-1] for ring, _ in rings)
    # 四边形由两条方向相反的边界way组成；连接后保留完整面积，不静默丢湖。
    def geometry(points):
        return [{'lat': a, 'lon': b} for a, b in points]
    lake = dict(type='relation', id=1, members=[
        dict(role='outer', geometry=geometry([(0, 0), (0, 2), (2, 2)])),
        dict(role='outer', geometry=geometry([(0, 0), (2, 0), (2, 2)]))])
    rings = water_rings(lake)
    assert len(rings) == 1 and rings[0][0][0] == rings[0][0][-1]
    ring = rings[0][0]
    assert abs(sum(x*y2-x2*y for (x,y),(x2,y2) in zip(ring,ring[1:])))/2 == 4
    import pytest
    lake['members'].pop()
    with pytest.raises(ValueError, match='无法闭合'):
        water_rings(lake)
