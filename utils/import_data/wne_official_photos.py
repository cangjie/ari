#!/usr/bin/env python3
"""WNE official photos: resize previously captured originals; attach to matching places.

User confirmed school authorization in chat on 2026-11-13. Permission text and any
conditions were not supplied. Source pages and original/published hashes are retained.
Originals live in the ignored exports folder; published assets are local JPEGs.
"""
from __future__ import annotations
import hashlib
import json
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOUR = ROOT / 'web_api/tour'
ORIGINALS = HERE / 'exports/wne_official_originals'
MANIFEST = HERE / 'wne_official_photo_manifest.json'

# ID, image URL, page documenting the image, accurate bilingual caption, use
CHOICES = [
 ('wne_welcome_center','https://wne.edu/images/news/z-delbridge-welcome-center_tn.jpg','https://wne.edu/news/2021/02/ug-open-house-03-06.cfm','访客中心外观，学校 2021 年报道配图','Welcome Center exterior, from a 2021 university report','cover'),
 ('wne_deliso_hall','https://wne.edu/images/news/z-spring-2023_tn.png','https://wne.edu/news/2023/05/2023-incoming-class.cfm','Deliso Hall 外观，学校 2023 年报道配图','Deliso Hall exterior, from a 2023 university report','cover'),
 ('wne_herman_hall','https://wne.edu/news/2024/04/z-herman-hall-door-2_ss.png','https://wne.edu/news/2024/04/arts-and-sciences-senior-awards-2024.cfm','Herman Hall 入口，学校 2024 年报道配图','Herman Hall entrance, from a 2024 university report','cover'),
 ('wne_sleith_hall','https://wne.edu/images/news/z-sleith_tn.png','https://wne.edu/news/2020/10/coe-senior-awards.cfm','Sleith Hall 外观，学校 2020 年报道配图','Sleith Hall exterior, from a 2020 university report','cover'),
 ('wne_csp','https://wne.edu/pharmacy-and-health-sciences/become-a-student/img/plan-a-visit-tn.png','https://wne.edu/pharmacy-and-health-sciences/become-a-student/index.cfm','科学与药学中心外观','Center for the Sciences and Pharmacy exterior','cover'),
 ('wne_art_gallery','https://wne.edu/art-gallery/img/art-gallery-header.png','https://wne.edu/art-gallery/index.cfm','学校艺术画廊页面的作品局部配图','Artwork detail on the university art gallery page','cover'),
 ('wne_damour_library','https://wne.edu/libraries/img/damour-library-tn.png','https://wne.edu/libraries/index.cfm','学校 D’Amour 图书馆介绍页配图','Image accompanying the university D’Amour Library description','cover'),
 ('wne_blake_law_center','https://wne.edu/libraries/img/law-library-tn.png','https://wne.edu/libraries/index.cfm','学校法学图书馆介绍页配图；并非整栋楼外观','Image accompanying the university Law Library description; not an exterior view','cover'),
 ('wne_university_commons','https://wne.edu/become-a-student/why-wne/img/dining.png','https://wne.edu/become-a-student/why-wne/campus.cfm','学校校园介绍页的餐饮区配图','Dining area image on the university campus page','cover'),
 ('wne_sleith_bio','https://wne.edu/engineering/departments/biomedical-engineering/img/Students_in_lab.jpg','https://wne.edu/engineering/departments/biomedical-engineering/labs-and-facilities.cfm','学校生物医学工程实验室页面配图；未标明具体房号','Image on the university biomedical engineering lab page; room number not identified','supplement'),
]


def sha(data): return hashlib.sha256(data).hexdigest()


def build():
    from PIL import Image, ImageOps
    records = []
    for ident, url, page, zh, en, use in CHOICES:
        raw = (ORIGINALS / (ident + '.original')).read_bytes()
        im = ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert('RGB')
        im.thumbnail((1200, 1200))
        buf = BytesIO(); im.save(buf, format='JPEG', quality=85, optimize=True)
        payload = buf.getvalue()
        rel = 'img/wne_campus/official_' + ident + '.jpg'
        (TOUR / rel).write_bytes(payload)
        records.append({'id': ident, 'place': 'wne_sleith_hall' if ident == 'wne_sleith_bio' else ident,
                        'role': use, 'file': rel, 'original_url': url, 'source_page': page,
                        'original_sha256': sha(raw), 'sha256': sha(payload), 'width': im.width, 'height': im.height,
                        'caption': {'zh': zh, 'en': en}})
    MANIFEST.write_text(json.dumps({'authorization': '用户于 2026-11-13 确认已取得学校授权；未提供授权文件及条件',
                                   'photos': records}, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print('generated', len(records), 'official photos')


def apply_photos(data):
    records = json.loads(MANIFEST.read_text('utf-8'))['photos']
    places = {p['id']: p for p in data['places']}
    stops = {s['place']: s for s in data['stops'].values()}
    for rec in records:
        path = TOUR / rec['file']
        if sha(path.read_bytes()) != rec['sha256']:
            raise ValueError('official photo hash mismatch: ' + str(path))
        info = {'caption': rec['caption'], 'source': {'title': 'Western New England University',
                'url': rec['source_page'], 'license': '学校授权', 'changes': '缩放并转换为 JPEG'},
                'sha256': rec['sha256'], 'photographed_on': None, 'width': rec['width'], 'height': rec['height']}
        if rec['role'] == 'cover':
            places[rec['place']].update({'photo': rec['file'], 'photo_info': info})
            stops[rec['place']].update({'photo': rec['file'], 'photo_info': info})
        else:
            stops[rec['place']]['supplementary_photos'] = [{'path': rec['file'], 'info': info}]
    return data


if __name__ == '__main__': build()
