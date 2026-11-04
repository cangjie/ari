"""Recheck selected image authors and licenses against Wikimedia Commons metadata."""
import json
from datetime import datetime,timezone
from pathlib import Path

import httpx
from boston_summer_st_photos import API,HEADERS,strip_tags

HERE=Path(__file__).resolve().parent


def main():
    photos=json.loads((HERE/'boston_summer_st_photos.json').read_text('utf-8'))['photos']
    titles=['File:'+p['source']['title'] for p in photos]
    params={'action':'query','titles':'|'.join(titles),'prop':'imageinfo',
            'iiprop':'url|extmetadata|size|mime','format':'json','formatversion':2}
    with httpx.Client(headers=HEADERS,follow_redirects=True,timeout=45) as client:
        response=client.get(API,params=params);response.raise_for_status()
    pages=response.json().get('query',{}).get('pages',[])
    by_title={p['title']:p for p in pages}
    results=[]
    for photo,title in zip(photos,titles):
        page=by_title.get(title,{})
        info=page.get('imageinfo',[{}])[0];meta=info.get('extmetadata',{})
        artist=strip_tags(meta.get('Artist',{}).get('value',''))
        license_name=meta.get('LicenseShortName',{}).get('value','')
        license_url=meta.get('LicenseUrl',{}).get('value','')
        value={'seq':photo['seq'],'title':title,'page':info.get('descriptionurl'),
               'author':artist,'license':license_name,'license_url':license_url,
               'credit':strip_tags(meta.get('Credit',{}).get('value','')),
               'restrictions':strip_tags(meta.get('Restrictions',{}).get('value','')),
               'attribution_required':meta.get('AttributionRequired',{}).get('value'),
               'attribution':strip_tags(meta.get('Attribution',{}).get('value',''))}
        if (not info or artist!=photo['source']['author'] or license_name!=photo['source']['license']
                or info.get('descriptionurl')!=photo['source']['url']
                or license_url!=photo['source'].get('license_url','')):
            raise ValueError(f"{photo['seq']}：Commons 署名或许可与图片清单不匹配")
        results.append(value)
    out={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'provider':'Wikimedia Commons imageinfo',
         'items':results}
    (HERE/'boston_summer_st_photo_license_check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(f'Verified metadata for {len(results)} selected images')


if __name__=='__main__':main()
