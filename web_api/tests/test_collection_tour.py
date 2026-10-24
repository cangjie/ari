"""清单发布的关键契约：不漏原表内容，不伪造地图与营业，问答和页面同源。"""
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from app import tour_qa_llm as llm

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'utils/import_data'
KEY = 'nanluo_shichahai'


def collection():
    return json.loads((ROOT / f'web_api/tour/data/{KEY}.json').read_text(encoding='utf-8'))


def test_standalone_itinerary_maps_match_selected_origin_geometry_and_order():
    m=collection()
    manifest=json.loads((HERE/f'{KEY}_itinerary_maps.json').read_text())
    assert len(manifest['maps'])==16
    assert manifest['tour_sha256']==hashlib.sha256((ROOT/f'web_api/tour/data/{KEY}.json').read_bytes()).hexdigest()
    ns={'s':'http://www.w3.org/2000/svg'}
    for item in manifest['maps']:
        theme=next(t for t in m['itineraries']if t['id']==item['theme'])
        variant=next(v for v in theme['variants']if v['start_station']==item['start_station'])
        assert item['assets']==variant['map_assets']
        for ext in ['svg','png']:
            raw=(ROOT/'web_api/tour'/item['assets'][ext]).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==item[f'{ext}_sha256']
        tree=ET.fromstring((ROOT/'web_api/tour'/item['assets']['svg']).read_text())
        assert tree.attrib['viewBox']=='0 0 1200 1600'
        markers=tree.findall('.//s:g[@data-order]',ns)
        assert [int(n.attrib['data-seq'])for n in markers]==[s['seq']for s in theme['steps']]
        assert [int(n.attrib['data-order'])for n in markers]==list(range(1,len(markers)+1))
        line=tree.find('.//s:path[@id="walking-route"]',ns).attrib['d']
        points=[[float(v)for v in p.split()]for p in line[1:].split(' L')]
        assert len(points)==len(variant['path'])
        # 独立核对投影后的公共街道点落在线上，所有点在图框内，未把清单序号当顺序。
        for marker in markers:
            point=[float(marker.attrib['data-x']),float(marker.attrib['data-y'])]
            assert min(math.dist(point,p)for p in points)<.03
        assert all(70<=x<=1130 and 275<=y<=1045 for x,y in points)
        endpoints=tree.findall('.//s:g[@data-station]',ns)
        assert [n.attrib['data-station']for n in endpoints]==(['S/E']if variant['start_station']==variant['end_station']else['S','E'])
        assert not tree.findall('.//s:script',ns) and not tree.findall('.//s:image',ns)


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


def test_browse_map_preserves_original_points_and_gps_uses_separate_street_references():
    m = collection()
    assert m['mode'] == 'collection'
    assert not m['routes'] and m['default_route'] == 'none'
    assert m['map_mode'] == 'browse' and m['map']['water'] and m['map']['roads']
    assert 'area' not in m  # 清单坐标与GPS参考点分别保存。
    nav=m['navigation']
    assert len(nav['places'])==21 and nav['radius_m']==25
    assert nav['area']['basis']=='osm-snapshot-bbox' and nav['area']['buffer']==0
    assert nav['area']['source_sha256']==hashlib.sha256((HERE/nav['area']['source_file']).read_bytes()).hexdigest()
    steps={s['seq']:s for t in m['itineraries']for s in t['steps']}
    for p in nav['places']:
        seq=p['stops'][0];step=steps[seq]
        assert p['id']==m['stops'][str(seq)]['place']
        assert [p['lat'],p['lon']]==step['point'] and p['reference']==step['street_reference']
        assert abs(p['r']-25*m['canvas']['px_per_m'])<.000001
        assert p['name']['zh'].endswith('附近') and p['note']==step['reference_note']
        proj=m['proj'];e=(p['lon']-proj['lon0'])*proj['mlon'];n=(p['lat']-proj['lat0'])*proj['mlat']
        assert abs(p['x']-(proj['a']*e+proj['b']*n+proj['tx']))<.01
        assert abs(p['y']-(proj['c']*e+proj['d']*n+proj['ty']))<.01
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
    assert len(photos) == 60
    for p in m['places']:
        seq = p['stops'][0]
        assert bool(p['photo']) == (seq in photos)
        if seq in photos:
            photo = photos[seq]
            assert p['id'] == photo['identity_key']
            assert hashlib.sha256((ROOT / 'web_api/tour' / p['photo']).read_bytes()).hexdigest() == photo['sha256']
            assert p['photo_info']['source'] == photo['source']
    assert m['stops']['48']['photo'] and m['stops']['76']['photo']
    assert '平复帖' not in m['stops']['76']['photo_info']['caption']['zh']  # 建筑图不冒充帖原件。
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
    assert '主题步行方案' in material and 'GPS导览' in material and m['navigation']['policy']in material
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


def test_photo_expansion_preserves_originals_and_covers_all_shop_branches():
    m=collection()
    baseline=json.loads((HERE/f'{KEY}_photo_expansion_baseline.json').read_text())
    for filename,digest in baseline['files'].items():
        assert hashlib.sha256((HERE/filename).read_bytes()).hexdigest()==digest
    manifest=json.loads((HERE/f'{KEY}_tour_photos.json').read_text())
    photos={p['seq']:p for p in manifest['photos']}
    for old in baseline['photos']:
        assert photos[old['seq']]==old
    for stop in m['stops'].values():
        if stop['kind']=='shop':assert stop['photo']
    for p in manifest['supplementary_photos']:
        assert hashlib.sha256((ROOT/'web_api/tour'/p['path']).read_bytes()).hexdigest()==p['sha256']
    dp={p['seq']for p in manifest['photos']+manifest['supplementary_photos']if 'dianping.com' in p['source']['url']}
    assert dp=={85,86,87,88,89,90,91,95,96,97,98,100}
    assert {92,93,94,99}<=set(photos)  # 用户明确允许的四家官方实景图。
    assert '北京' in photos[58]['caption']['zh'] and '非泰州' in photos[58]['caption']['zh']


def test_shop_consumption_labels_are_separate_from_cultural_tiers():
    m=collection();shops=[s for s in m['stops'].values()if s['kind']=='shop']
    assert len({s['shop_category']for s in shops})==6
    assert all(s['shop_tags'] and s['shop_label_note'] for s in shops)
    assert {s['seq']for s in shops if '经济实惠' in s['shop_tags']}=={86,98}
    assert all('文艺' not in s.get('shop_tags',[])for s in shops if s['seq'] in [85,86,87,95,96,97,98])
    material=llm.museum_material(m)
    for s in shops:
        assert s['shop_category']in material and s['shop_label_note']in material


def test_four_themes_have_four_subway_origins_and_only_sourced_public_road_paths():
    import sys
    sys.path.insert(0,str(HERE))
    from tour_collection_experience import StreetGraph,meters
    m=collection();osm=json.loads((HERE/f'{KEY}_osm_data.json').read_text());graph=StreetGraph(osm)
    assert {t['name']for t in m['itineraries']}=={'经典游览线路','文艺观光线路','历史探索线路','穷游线路'}
    assert {s['id']for s in m['itinerary_stations']}=={'nanluo','shichahai','beihai','gulou'}
    assert len({s['source']['url']for s in m['itinerary_stations']})==4
    assert all(step['streets']for theme in m['itineraries']for step in theme['steps'])
    assert not m['routes'] and all('r' not in p for p in m['places'])
    for theme in m['itineraries']:
        assert len(theme['variants'])==4
        assert sum(s['minutes']for s in theme['steps'])>0
        for variant in theme['variants']:
            assert set(variant['way_ids'])<=set(graph.ways)
            assert variant['total_minutes']==variant['walk_minutes']+variant['stay_minutes']
            assert variant['walk_minutes']==round(variant['meters']/60)
            actual=sum(meters(a,b)for a,b in zip(variant['path_wgs84'],variant['path_wgs84'][1:]))
            assert abs(actual-variant['meters'])<2
            assert len(variant['legs'])==len(theme['steps'])+1
        # 不把道路仅有的端点当整条胡同位置；每一站都落在各自来源街段。
        for step in theme['steps']:
            ref=step['street_reference']
            assert ref.get('way_id') in graph.ways or ref.get('osm_node') in graph.nodes
    arts=next(t for t in m['itineraries']if t['id']=='arts')
    points={s['seq']:s['point']for s in arts['steps']}
    assert points[11]!=points[12] and points[12]!=points[31]
    history=next(t for t in m['itineraries']if t['id']=='history')
    assert {44,49,59}<={s['seq']for s in history['steps']}
    budget=next(t for t in m['itineraries']if t['id']=='budget')
    assert '门票0元' in budget['fee'] and all(s['seq']not in [49,59,68]for s in budget['steps'])
