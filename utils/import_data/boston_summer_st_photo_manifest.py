"""Build the reviewed Boston photo manifest from individually inspected candidates."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
KEY='boston_summer_st'
REQUIRED={2,3,4,5,6,7,8,9,10,11,12,19,20,22,24,27}
ALLOWED_LICENSES={'Public domain','CC BY 2.0','CC BY 3.0','CC BY 4.0',
                  'CC BY-SA 2.0','CC BY-SA 3.0','CC BY-SA 4.0'}


def main():
    candidates=json.loads((HERE/f'{KEY}_commons_photo_candidates.json').read_text('utf-8'))
    review=json.loads((HERE/f'{KEY}_photo_review.json').read_text('utf-8'))
    checked=json.loads((HERE/f'{KEY}_photo_license_check.json').read_text('utf-8'))
    checked_by_seq={item['seq']:item for item in checked['items']}
    accepted=set(review['accepted_subject_candidates'])
    selected=[]
    for item in candidates['photos']:
        if item['seq'] not in accepted:
            continue
        source=item['source']
        verification=checked_by_seq.get(item['seq'],{})
        if (source.get('license') not in ALLOWED_LICENSES or not source.get('author')
                or not source.get('url','').startswith('https://commons.wikimedia.org/')
                or (source['license'] != 'Public domain' and not source.get('license_url','').startswith('https://'))
                or verification.get('author')!=source['author'] or verification.get('license')!=source['license']
                or verification.get('page')!=source['url'] or verification.get('restrictions')):
            raise ValueError(f'图片许可或署名不完整：{item["seq"]}')
        path=ROOT/'web_api'/'tour'/item['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError(f'图片文件不匹配：{item["seq"]}')
        item['source']['changes']='按比例缩放、转换为 JPEG'
        selected.append(item)
    if len({p['seq'] for p in selected}) != len(selected) or not REQUIRED <= {p['seq'] for p in selected}:
        raise ValueError('主要景点照片不完整或序号重复')
    output={'status':'subject visually reviewed; Commons authors and license metadata rechecked',
            'license_checked_at_utc':checked['checked_at_utc'],
            'photos':sorted(selected,key=lambda p:p['seq']), 'supplementary_photos':[],
            'approved_without_photo':[21,31,32],
            'food_photo_policy':'Unlicensed food venue photos may be omitted.'}
    (HERE/f'{KEY}_photos.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(selected)} photos have reviewed subjects and verified Commons metadata')


if __name__=='__main__':main()
