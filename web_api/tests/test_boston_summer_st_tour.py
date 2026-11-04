import json
import hashlib
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
    assert Counter(stop["tier"] for stop in data["stops"].values()) == {"S": 1, "A": 12, "B": 10, "C": 30}
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
    assert len(reviews) == 21
    shops = [stop for stop in data["stops"].values() if stop["kind"] == "shop"]
    assert all("未实时核实" in stop["status"]["zh"] for stop in shops)
    assert all("unverified" in stop["status"]["en"].lower() for stop in shops)


ROUTE_PHOTO_SEQS = {
    2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
    19, 20, 22, 24, 27,
}


def test_sourced_map_and_route_node_photos_are_bound_to_exact_records():
    data = generated()
    assert data["map_mode"] == "browse"
    assert data["canvas"]["w"] > 1000 and data["canvas"]["h"] > 500
    route_seqs = set().union(*(set(route['steps']) for route in
                               json.loads((IMPORT/'boston_summer_st_draft_walks.json').read_text())['routes'].values()))
    positioned = {place['stops'][0] for place in data['places'] if place.get('position')}
    assert route_seqs <= positioned
    assert "OpenStreetMap" in data["attribution"]["en"]
    for seq in ROUTE_PHOTO_SEQS:
        stop = data["stops"][str(seq)]
        assert stop["photo"] == f"img/boston_summer_st/{seq}.jpg"
        image = TOUR / stop["photo"]
        assert image.is_file()
        assert hashlib.sha256(image.read_bytes()).hexdigest() == stop["photo_info"]["sha256"]
        assert stop["photo_info"]["width"] >= 900
        assert stop["photo_info"]["height"] >= 500
        assert stop["photo_info"]["source"]["url"].startswith("https://")
        assert stop["photo_info"]["source"]["license"]
        assert "rights not stated" not in stop["photo_info"]["source"]["license"].lower()


def test_fixed_start_selection_preserves_existing_multi_start():
    from tour_collection_experience import selected_stations

    stations = {name: {"id": name} for name in ("park", "downtown", "harbor")}
    assert [s["id"] for s in selected_stations({"default_start": "park", "start_stations": ["park"]}, stations)] == ["park"]
    assert [s["id"] for s in selected_stations({"default_start": "park"}, stations)] == list(stations)
    import pytest
    with pytest.raises(ValueError):
        selected_stations({"default_start": "park", "start_stations": ["downtown"]}, stations)
    with pytest.raises(ValueError):
        selected_stations({"default_start": "park", "start_stations": ["park", "missing"]}, stations)


def test_unverified_editorial_quotes_block_release_build():
    import pytest
    from types import SimpleNamespace
    import boston_summer_st_tour_data as config
    import tour_collection_build
    legacy=SimpleNamespace(**{k:v for k,v in vars(config).items() if not k.startswith('__')})
    legacy.PACKAGE_PREFIX='boston_summer_st'
    legacy.RATING_INVENTORY_FILE=None
    with pytest.raises(ValueError, match="来源正文缺失或引文不属于保存的正文"):
        tour_collection_build.build("boston_summer_st", legacy)


def test_mbta_entrances_are_bound_to_official_stop_records():
    from tour_collection_experience import station_point
    import pytest
    records = {'door': {'stop_id': 'door', 'parent_station': 'place', 'location_type': '2',
                        'stop_lat': '42.35637', 'stop_lon': '-71.062321'}}
    graph = type('Graph', (), {'nodes': {3: (1.0, 2.0)}})()
    assert station_point({'gtfs_stop_id': 'door'}, graph, records) == (42.35637, -71.062321)
    assert station_point({'osm_node': 3}, graph, {}) == (1.0, 2.0)
    with pytest.raises(ValueError):
        station_point({'gtfs_stop_id': 'missing'}, graph, records)
    with pytest.raises(ValueError):
        station_point({'gtfs_stop_id': 'door', 'osm_node': 3}, graph, records)


def test_draft_walks_use_allowed_public_streets_and_keep_optional_food_optional():
    from tour_collection_experience import StreetGraph
    draft = json.loads((IMPORT/'boston_summer_st_draft_walks.json').read_text())
    graph = StreetGraph(json.loads((IMPORT/'boston_summer_st_osm.json').read_text()))
    assert draft['state'] == 'draft_not_for_publication'
    assert {31, 32} <= set(draft['routes']['sightseeing']['steps'])
    for route in draft['routes'].values():
        assert len(route['legs']) == len(route['steps']) + 1
        assert any(1225708372 in leg['way_ids'] for leg in route['legs'])
        assert all(set(leg['way_ids']) <= graph.ways.keys() for leg in route['legs'])
        assert all(len(leg['path']) >= 1 for leg in route['legs'])
    food = draft['routes']['food']
    assert {36, 45, 46, 47, 50, 52} <= set(food['steps'])
    assert not {48, 51, 53} & set(food['steps'])


def test_standalone_route_map_uses_destination_name_and_fits_long_legend():
    from tour_itinerary_maps import render
    steps=[{'seq':i,'point':[42.0+i*.0001,-71.0], 'name':{'zh':f'景点编号{i}'}} for i in range(1,20)]
    data={'name':{'zh':'波士顿 Summer Street'}, 'itinerary_map_brand':'波士顿 Summer Street',
          'itinerary_exit_note':'时长未计用餐和排队。车站出口以现场为准。', 'proj':{'lon0':-71,'lat0':42,'mlon':80000,'mlat':110000,
          'a':1,'b':0,'c':0,'d':-1,'tx':0,'ty':1000},
          'canvas':{'px_per_m':1}, 'map':{}, 'labels':[],
          'itinerary_stations':[{'id':'a','name':'Park Street'},{'id':'b','name':'Courthouse'}]}
    variant={'path':[[0,0],[200,400]],'start_station':'a','end_station':'b','meters':1000,
             'total_minutes':60,'stay_minutes':40,'walk_minutes':20}
    svg=render(data,{'name':'纯观光路线','steps':steps},variant,'#334455')
    assert 'ARI TRAVEL / 波士顿 Summer Street' in svg
    assert '北京南锣鼓巷' not in svg
    assert '地铁出口编号据 OSM' not in svg
    assert 'data-seq="19"' in svg
    import re
    legend = svg.split('游览顺序 · 19站', 1)[1].split('M45 1470', 1)[0]
    ys=[float(y) for y in re.findall(r'<text x="[^"]+" y="([\d.]+)" font-size="(?:19|20|21|22|23)"', legend)]
    assert ys and max(ys) < 1470


def test_route_map_spreads_duplicate_pins_and_keeps_english_words_together():
    from tour_itinerary_maps import spread_pins, wrap_compact_label
    result=spread_pins([[100,400],[100,400],[105,402]], [(100,400)], (45,250,1110,820))
    assert len(set(map(tuple,result))) == 3
    import math
    assert all(math.dist(a,b)>=45 for i,a in enumerate(result) for b in result[i+1:])
    assert wrap_compact_label('Harbor Way 绿地',18) == ['Harbor Way 绿地']


def test_street_reference_requires_exact_saved_osm_geometry():
    from tour_collection_media import street_reference_point
    import pytest
    element={'type':'way','id':10,'tags':{'highway':'footway','name':'Summer Street'},
             'geometry':[{'lat':42.0,'lon':-71.0},{'lat':42.001,'lon':-71.0}]}
    ref={'point':[42.0005,-71.0], 'streets':['Summer Street'],
         'source_ref':{'way_id':10,'segment':[[42.0,-71.0],[42.001,-71.0]],'fraction':.5}}
    assert street_reference_point(ref,{('way',10):element}) == (42.0005,-71.0)
    bad={**ref,'point':[42.0005,-70.9]}
    with pytest.raises(ValueError):
        street_reference_point(bad,{('way',10):element})
    private={**element,'tags':{'highway':'footway','access':'private','name':'Summer Street'}}
    with pytest.raises(ValueError):
        street_reference_point(ref,{('way',10):private})
    subdivided={**ref,'point':[42.0006,-71.0],
                'source_ref':{'way_id':10,'segment':[[42.0002,-71.0],[42.001,-71.0]],'fraction':.5}}
    assert street_reference_point(subdivided,{('way',10):element}) == (42.0006,-71.0)
    node={'type':'node','id':2,'lat':42.0,'lon':-71.0}
    way={**element,'nodes':[2,3]}
    noderef={'point':[42.0,-71.0],'streets':['Summer Street'],'source_ref':{'osm_node':2}}
    assert street_reference_point(noderef,{('node',2):node,('way',10):way}) == (42.0,-71.0)
    with pytest.raises(ValueError):
        street_reference_point(noderef,{('node',2):node})


def test_draft_boston_media_cannot_be_published(tmp_path):
    import pytest
    from types import SimpleNamespace
    from tour_collection_media import augment
    manifest=tmp_path/'draft.json'
    manifest.write_text('{"state":"draft_not_for_publication"}')
    with pytest.raises(ValueError, match='仍是草案'):
        augment({'key':'boston_summer_st'}, SimpleNamespace(MEDIA_MANIFEST=str(manifest)))


def test_rating_keeps_original_inventory_hash_and_checks_published_content():
    import pytest
    from tour_collection_build import verify_inventory_rating
    fields = ('id','zone','kind','zh','en','zh_desc','en_desc','address','relation','access','source','source_name','note')
    item = dict(zip(fields, ['T1','zone','site','中文','English','介绍','description','address',
                             'walk','public','https://example.org','source','']))
    digest = hashlib.sha256(json.dumps([item], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    row = {'source_seq':1,'identity_key':'t1','name':'中文','description':'介绍',
           'address':'address','aliases':['English'],'area':'zone'}
    verify_inventory_rating({'input_sha256':digest},{'rows':[item]},{'rows':[row]})
    with pytest.raises(ValueError, match='评分清单与发布资料不一致'):
        verify_inventory_rating({'input_sha256':digest},{'rows':[item]},{'rows':[{**row,'address':'other'}]})
    with pytest.raises(ValueError, match='评分输入与清单不一致'):
        verify_inventory_rating({'input_sha256':'not-the-hash'},{'rows':[item]},{'rows':[row]})
    with pytest.raises(ValueError, match='双语内容与评分清单不一致'):
        verify_inventory_rating({'input_sha256':digest},{'rows':[item]},{'rows':[row]},
                                {'values':{'中文':{'en':'English'},'介绍':{'en':'different'}}})


def test_boston_route_assets_match_itineraries_and_saved_hashes():
    import xml.etree.ElementTree as ET
    from PIL import Image
    data=generated()
    manifest=json.loads((IMPORT/'boston_summer_st_itinerary_maps.json').read_text())
    assert manifest['tour_sha256']==hashlib.sha256((TOUR/'data'/'boston_summer_st.json').read_bytes()).hexdigest()
    assert len(manifest['maps'])==2
    ns={'s':'http://www.w3.org/2000/svg'}
    for entry in manifest['maps']:
        theme=next(t for t in data['itineraries'] if t['id']==entry['theme'])
        variant=next(v for v in theme['variants'] if v['start_station']==entry['start_station'])
        assert entry['assets']==variant['map_assets']
        for ext in ('svg','png'):
            path=TOUR/entry['assets'][ext]
            assert hashlib.sha256(path.read_bytes()).hexdigest()==entry[f'{ext}_sha256']
        with Image.open(TOUR/entry['assets']['png']) as image:
            assert image.size==(1200,1600)
        svg=ET.fromstring((TOUR/entry['assets']['svg']).read_text())
        markers=svg.findall('.//s:g[@data-order]',ns)
        assert [int(x.attrib['data-seq']) for x in markers]==[x['seq'] for x in theme['steps']]
        assert [int(x.attrib['data-order']) for x in markers]==list(range(1,len(markers)+1))
        assert len(svg.find('.//s:path[@id="walking-route"]',ns).attrib['d'])>100
        assert 1225708372 in variant['way_ids']

