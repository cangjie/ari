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


def test_reading_collection_does_not_claim_coordinates_routes_or_dwell():
    m = collection()
    assert m['mode'] == 'collection'
    assert not m['routes'] and m['default_route'] == 'none'
    assert not {'proj', 'entrance', 'canvas', 'area', 'map'} & m.keys()
    assert all(not {'lat', 'lon', 'x', 'y', 'r'} & p.keys() for p in m['places'])
    assert all(s['dwell'] is None for s in m['stops'].values())


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
