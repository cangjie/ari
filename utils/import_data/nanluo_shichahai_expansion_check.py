"""只读发布核对：原资料不变、61图哈希、4×4主题方案；--public检查线上同源文件。"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path
from tls import ssl_ctx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
TOUR=ROOT/'web_api/tour'
KEY='nanluo_shichahai'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--public',action='store_true')
    parser.add_argument('--report-prefix',default='expansion');args=parser.parse_args()
    baseline=json.loads((HERE/f'{KEY}_photo_expansion_baseline.json').read_text())
    for name,digest in baseline['files'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
    manifest=json.loads((HERE/f'{KEY}_tour_photos.json').read_text());photos=manifest['photos']+manifest['supplementary_photos']
    data=json.loads((TOUR/f'data/{KEY}.json').read_text())
    assert len([s for s in data['stops'].values()if s['photo']])==60
    assert sum(bool(s['photo'])for s in data['stops'].values()if s['kind']=='shop')==16
    assert len(data['itineraries'])==4 and all(len(t['variants'])==4 for t in data['itineraries'])
    maps=json.loads((HERE/f'{KEY}_itinerary_maps.json').read_text())
    assert maps['tour_sha256']==hashlib.sha256((TOUR/f'data/{KEY}.json').read_bytes()).hexdigest()
    map_assets=[p for row in maps['maps']for p in row['assets'].values()]
    assert len(map_assets)==32 and len(set(map_assets))==32
    for row in maps['maps']:
        for ext,path in row['assets'].items():assert hashlib.sha256((TOUR/path).read_bytes()).hexdigest()==row[f'{ext}_sha256']
    current=[{k:v for k,v in p.items()if k not in ['photo','photo_info','supplementary_photos']}for p in data['places']]
    assert current==baseline['positions'],'旧地图37位置或身份发生未预期变化'
    for photo in baseline['photos']:
        assert hashlib.sha256((TOUR/photo['path']).read_bytes()).hexdigest()==photo['sha256']
    assets=[];api=[]
    if args.public:
        files=['index.html','app.js','app.css','catalog.json','data/wmhg.json','data/wanping.json',f'data/{KEY}.json']+[p['path']for p in photos]+map_assets
        def check(path):
            expected=(TOUR/path).read_bytes();req=urllib.request.Request('https://tour.snowmeet.top/'+path,headers={'User-Agent':'ari-expansion-check/1.0','Cache-Control':'no-cache'})
            with urllib.request.urlopen(req,context=ssl_ctx(),timeout=40)as res:body=res.read();status=res.status
            assert body==expected,path
            return dict(path=path,status=status,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),matches_local=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5)as pool:assets=list(pool.map(check,files))
        for key,pid in [('wmhg','tongde'),('wanping','east_gate'),(KEY,'guomoruo')]:
            with urllib.request.urlopen(f'https://tour.snowmeet.top/api/tour/{key}/places/{pid}/topics',context=ssl_ctx(),timeout=30)as res:
                value=json.load(res);assert isinstance(value.get('topics'),list);api.append(dict(key=key,place=pid,status=res.status,read_only_get=True))
    report=dict(checked_on=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
                commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),public=args.public,
                url='https://tour.snowmeet.top/#'+KEY,records=100,photo_records=60,published_images=len(photos),
                image_bytes=sum(p['bytes']for p in photos),shops_with_photos=16,dianping_shops=12,authorized_official_shops=[92,93,94,99],
                map_positions=37,themes=[dict(name=t['name'],variants=len(t['variants']),default=next(v for v in t['variants']if v['start_station']==t['default_start']))for t in data['itineraries']],
                standalone_maps=16,svg_maps=16,png_maps=16,
                gps=dict(points=len(data['navigation']['places']),radius_m=data['navigation']['radius_m'],area_basis=data['navigation']['area']['basis'])if data.get('navigation')else None,
                source_rating_workbook_unchanged=True,old_10_photos_unchanged=True,public_assets=assets,public_qa=api,
                public_posts_sent=0,apk_rebuilt=False,android_device_verified=False,nginx_changed=False)
    # 报告无需再复制每个折点；完整有出处几何在同源JSON里。
    for theme in report['themes']:
        for key in ['path','path_wgs84','way_ids','legs']:theme['default'].pop(key,None)
    if not args.public:report['worktree_base_commit']=report.pop('commit')
    suffix=args.report_prefix+('_public_report'if args.public else '_local_report')
    (HERE/f'{KEY}_{suffix}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f"60/100 records; 16/16 shops; {len(photos)} photos ({report['image_bytes']} bytes); 4 themes × 4 starts; 16 SVG + 16 PNG maps; {len(assets)} public exact matches; {len(api)} read-only QA lists")


if __name__=='__main__':main()
