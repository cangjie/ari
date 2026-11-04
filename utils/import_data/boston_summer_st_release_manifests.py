"""Validate offline sources and prepare manifests for release candidate builds."""
import json
from pathlib import Path

from boston_summer_st_media_candidate import main as check_media
from tour_collection_media import sha
from tour_collection_experience import StreetGraph,station_point
from tour_package_build import meters

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'


def main():
    audit=json.loads((HERE/f'{KEY}_v3_rating_audit_results.json').read_text('utf-8'))
    request=HERE/f'{KEY}_v3_rating_audit_request.json'
    if not audit['complete'] or audit['request_sha256']!=sha(request):
        raise ValueError('最终评级独立审计未完成')
    check_media()
    media=json.loads((HERE/f'{KEY}_media_candidate.json').read_text('utf-8'))
    photos=json.loads((HERE/f'{KEY}_photos.json').read_text('utf-8'))
    license_check=json.loads((HERE/f'{KEY}_photo_license_check.json').read_text('utf-8'))
    accepted={p['seq'] for p in photos['photos']};checked={p['seq'] for p in license_check['items']}
    if (len(accepted)!=len(photos['photos']) or accepted!=checked or accepted & {21,31,32}
            or photos.get('approved_without_photo')!=[21,31,32]):
        raise ValueError('图片复核或已批准的无图例外不一致')
    for photo in photos['photos']:
        path=HERE.parents[1]/'web_api'/'tour'/photo['path']
        if sha(path)!=photo['sha256']:raise ValueError(f"照片哈希不符 {photo['seq']}")
    media.update(state='verified_for_publication',photo_sha256=sha(HERE/media['photo_manifest']))
    experience=json.loads((HERE/f'{KEY}_experience.json').read_text('utf-8'))
    if {t['id'] for t in experience['themes']}!={'sightseeing','food'}:
        raise ValueError('缺少两条指定路线')
    by_theme={t['id']:t for t in experience['themes']}
    if not {31,32}<={x['seq'] for x in by_theme['sightseeing']['steps']}:
        raise ValueError('观光路线遗漏允许无图的节点')
    if not any(x['seq']==20 and 21 in x.get('related',[]) for x in by_theme['sightseeing']['steps']):
        raise ValueError('波士顿码头标牌未保留在相关路线点')
    labels_path=HERE/experience['labels_file'];labels=json.loads(labels_path.read_text('utf-8'))
    if len(labels['items'])!=21 or len({x['identity_key'] for x in labels['items']})!=21:
        raise ValueError('商铺分类覆盖错误')
    osm_path=HERE/experience['osm_file'];osm=json.loads(osm_path.read_text('utf-8'));graph=StreetGraph(osm)
    transit_path=HERE/experience['transit_file'];transit=json.loads(transit_path.read_text('utf-8'))
    records={x['stop_id']:x for x in transit['records']}
    if len(records)!=len(transit['records']):raise ValueError('MBTA 出入口记录重复')
    for station in experience['stations']:
        point=station_point(station,graph,records);node=graph.nearest(point)
        if meters(point,graph.nodes[node])>40:raise ValueError(f"车站接驳过远 {station['id']}")
    experience.update(state='verified_for_publication',labels_sha256=sha(labels_path),
                      osm_sha256=sha(osm_path),transit_sha256=sha(transit_path),
                      offline_check_note='公开来源与模型核验；不代表真机或现场通行验收。')
    for suffix,value in [('media_release.json',media),('experience_release.json',experience)]:
        (HERE/f'{KEY}_{suffix}').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(f"Prepared release candidate manifests: {len(media['positions'])} map references, {len(accepted)} photos, 2 routes")


if __name__=='__main__':main()
