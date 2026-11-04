"""Prepare street-reference map candidate from reviewed saved OSM geometries."""
import json
from pathlib import Path

from tour_collection_media import sha, street_reference_point

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'
EXPECTED={3:'Massachusetts State House',4:'Park Street Church',5:'Granary Burying Ground',
          6:'Kings Chapel',7:'Boston Latin School Site',8:'Old Corner Bookstore',
          9:'Old South Meeting House',10:'Old State House',11:'Boston Massacre Site',
          12:'Faneuil Hall',21:'263, Summer Street',22:'Boston Tea Party',24:'64, Sleeper Street',
          27:'Institute of Contemporary Art',32:'Harbor Way',36:'Tatte',45:'High Street Place',
          46:'12, Farnsworth Street',47:'Row 34',50:'450, Summer Street',52:'Harpoon Brewery'}


def main():
    draft=json.loads((HERE/f'{KEY}_draft_walks.json').read_text('utf-8'))
    osm_path=HERE/f'{KEY}_osm.json';osm=json.loads(osm_path.read_text('utf-8'))
    elements={(e['type'],e['id']):e for e in osm['elements']}
    geocodes={r['seq']:r for r in json.loads((HERE/f'{KEY}_geocode_capture.json').read_text('utf-8'))['items']}
    revision=json.loads((HERE/f'{KEY}_revision_v3_draft.json').read_text('utf-8'))
    refs=draft['references'];checks=[]
    for key,ref in refs.items():
        seq=int(key);street_reference_point(ref,elements)
        if ref['offset_m']>120:raise ValueError(f'{seq}: 参考点离候选位置过远')
        if seq in EXPECTED:
            if EXPECTED[seq].casefold() not in geocodes[seq]['display_name'].casefold():
                raise ValueError(f'{seq}: 位置候选名称不匹配')
            basis=geocodes[seq]['source_url']
        elif seq==2:
            poi=elements[('way',24677646)]
            if poi['tags'].get('name')!='Visitor Information Center at Boston Common':raise ValueError('游客中心身份不符')
            basis='https://www.openstreetmap.org/way/24677646'
        elif seq==19:
            if ref['reference_basis']!='MBTA South Station Summer Street entrance':raise ValueError('南站入口依据不符')
            basis='https://cdn.mbta.com/MBTA_GTFS.zip'
        elif seq==20:
            if geocodes[21]['display_name'].find('263, Summer Street')<0:raise ValueError('Fort Point参考点身份不符')
            basis=geocodes[21]['source_url']
        elif seq==31:
            source=ref['source_ref']
            if source.get('way_id')!=1225708372 or elements[('way',1225708372)]['tags'].get('highway')!='steps':
                raise ValueError('夏街阶梯参考点不符')
            basis='https://www.openstreetmap.org/way/1225708372'
        else:raise ValueError(f'{seq}: 未登记身份核验依据')
        checks.append({'seq':seq,'identity_key':revision['rows'][seq-1]['id'].lower(),
                       'identity_source':basis,'offset_m':ref['offset_m']})
    reviewed={'state':'verified_for_publication','references':refs,
              'policy':'保存的公开街道几何和候选地点身份已核；参考点并非入口，未作现场通行或定位验收。',
              'checks':checks}
    ref_path=HERE/f'{KEY}_street_references.json'
    ref_path.write_text(json.dumps(reviewed,ensure_ascii=False,indent=2)+'\n','utf-8')
    manifest={'osm_file':osm_path.name,'raw_file':f'{KEY}_osm_overpass_raw.json',
              'osm_sha256':sha(osm_path),'water_relations':[],
              'street_reference_file':ref_path.name,'street_reference_sha256':sha(ref_path),
              'positions':[{'seq':x['seq'],'identity_key':x['identity_key'],'basis':'street-reference'} for x in checks],
              'labels':[],'photo_manifest':f'{KEY}_photos.json','cover_seq':2,
              'state':'draft_not_for_publication'}
    out=HERE/f'{KEY}_media_candidate.json'
    out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(f'{len(checks)} saved street references validated; media manifest remains a draft')


if __name__=='__main__':main()
