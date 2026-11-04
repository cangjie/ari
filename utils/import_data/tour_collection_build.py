"""已审计资料包的清单发布模式；没有定位依据时不生成地图、热区或路线。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inventory_rating(ratings, inventory, source, translations=None):
    """Bind a score to its actual inventory input without rewriting its hash."""
    fields = ('id', 'zone', 'kind', 'zh', 'en', 'zh_desc', 'en_desc', 'address',
              'relation', 'access', 'source', 'source_name', 'note')
    rows = inventory['rows']
    payload = [{k: row[k] for k in fields} for row in rows]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if ratings['input_sha256'] != digest:
        raise ValueError('评分输入与清单不一致')
    source_rows = {row['source_seq']: row for row in source['rows']}
    if len(source_rows) != len(rows) or set(source_rows) != set(range(1, len(rows)+1)):
        raise ValueError('评分清单与发布资料覆盖不一致')
    for seq, item in enumerate(rows, 1):
        row = source_rows[seq]
        if (row['identity_key'] != item['id'].lower() or row['name'] != item['zh']
                or row['description'] != item['zh_desc'] or row['address'] != item['address']
                or item['en'] not in row.get('aliases', []) or row['area'] != item['zone']):
            raise ValueError(f'{seq}：评分清单与发布资料不一致')
        if translations is not None:
            values = translations['values']
            if any(values.get(zh, {}).get('en') != en for zh, en in
                   [(item['zh'], item['en']), (item['zh_desc'], item['en_desc'])]):
                raise ValueError(f'{seq}：双语内容与评分清单不一致')


def build(key, config):
    prefix = getattr(config, 'PACKAGE_PREFIX', key)
    def path(suffix):
        return HERE / f'{prefix}_{suffix}'

    def load(suffix):
        return json.loads(path(suffix).read_text('utf-8'))

    package = load('final.json')
    ratings = load('ratings.json')
    manifest = load('audit_manifest.json')
    translations = load('translations.json')
    source = load('site_data.json')
    source_sha = sha(path('site_data.json'))
    if package['state'] != '独立审计完成' or any(
        data['input_sha256'] != source_sha for data in [package, manifest, translations]
    ):
        raise ValueError('必须使用同一来源版本的完整已审资料包')
    if getattr(config, 'RATING_INVENTORY_FILE', None):
        verify_inventory_rating(ratings, json.loads((HERE / config.RATING_INVENTORY_FILE).read_text('utf-8')), source, translations)
    elif ratings['input_sha256'] != source_sha:
        raise ValueError('评分资料与来源不一致')
    if manifest['rating_sha256'] != sha(path('ratings.json')):
        raise ValueError('当前评分版本未经对应独立审计')
    if manifest['audit_source_sha256'] != sha(path('audit_source_data.json')):
        raise ValueError('审计原文版本已变化')
    if ratings.get('grouping_sha256', manifest.get('rating_grouping_sha256')) != sha(path('peer_groups.json')):
        raise ValueError('当前同类组与评分不一致')
    audits_raw = [json.loads(line) for line in path('audit1_slim.jsonl').read_text('utf-8').splitlines() if line.strip()]
    audits = {r['seq']: r for r in audits_raw}
    scores = {r['seq']: r for r in ratings['results']}
    rows = {r['source_seq']: r for r in package['rows']}
    wanted = {r['source_seq'] for r in source['rows']}
    if (len(rows) != len(package['rows']) or len(audits) != len(audits_raw)
            or set(rows) != wanted or set(audits) != wanted or set(scores) != wanted):
        raise ValueError('发布资料与来源、评分、审计的序号覆盖不一致')
    if any(r['rating'] != scores[s] or r['audit'] != audits[s] for s, r in rows.items()):
        raise ValueError('发布资料包与当前评分或审计不一致')
    capture = {r['id']: r for r in load('source_capture.json')['sources'] if r['status'] == 'ok'}
    if getattr(config, 'REQUIRE_VERIFIED_EVIDENCE', False):
        for row in source['rows']:
            for evidence in row['evidence']:
                saved = capture.get(evidence['source_id'])
                if (not saved or saved.get('http_status') != 200
                        or saved.get('retrieval_method') != 'verified_HTTP_extracted_text'
                        or not evidence.get('quote')
                        or evidence['quote'] not in saved.get('source_text', '')):
                    raise ValueError(f"{row['source_seq']}：来源正文缺失或引文不属于保存的正文")

    def bilingual(text):
        return dict(zh=text, en=translations['values'][text]['en']) if text else dict(zh='', en='')

    def label(row):
        return row.get('display_name', row['name'])

    identities = {r['identity_key']: r for r in rows.values()}
    if len(identities) != len(rows) or any(not re.fullmatch(r'[a-z0-9_]{1,64}', k) for k in identities):
        raise ValueError('资料身份重复或不能作为稳定地点标识')
    areas = getattr(config, 'AREAS', {
        '南锣鼓巷': 'Nanluoguxiang', '什刹海': 'Shichahai', '周边衔接': 'Nearby connections'
    })
    places, stops = [], {}
    for seq, row in rows.items():
        audit = row['audit']
        review = audit['found_factual_error'] or any(m['tier_sensitive'] for m in audit['missing'])
        if review != row['needs_review']:
            raise ValueError(f'{seq}：复核标记不一致')
        review_text = '\n'.join(([audit['error_note_zh']] if audit.get('error_note_zh') else [])
                                + [m['zh'] for m in audit['missing'] if m['tier_sensitive']])
        if review and getattr(config, 'PUBLIC_REVIEW_SUMMARY', False):
            review_text = '评级依据还有可补充的历史或参观资料，等级待复核；请结合来源判断。'
        refs = {}
        for evidence in row['evidence'] + row.get('audit_evidence', []):
            saved = capture[evidence['source_id']]
            if saved['url'] != evidence['url']:
                raise ValueError(f'{seq}：来源链接不一致')
            refs[evidence['url']] = dict(title=saved.get('title') or evidence['source_id'], url=evidence['url'])
        parent = identities.get(row['parent_key'])
        if row['parent_key'] and parent is None:
            raise ValueError(f'{seq}：关联整体不存在')
        shop = row.get('entry_kind') == '特色商铺'
        platform_zh, platform_en = config.platform_reference(row, capture) if shop else ('', '')
        places.append(dict(id=row['identity_key'], name=bilingual(label(row)), stops=[seq], photo=None))
        stops[str(seq)] = dict(
            seq=seq, place=row['identity_key'], name=bilingual(label(row)),
            aliases=row.get('aliases', []), tier=row['rating']['tier'], core=row['rating']['core'],
            kind='shop' if shop else 'culture', area=dict(zh=row['area'], en=areas[row['area']]),
            related=bilingual(label(parent)) if parent else None,
            dwell=None, status=dict(zh=row['status'], en=config.STATUS_EN[row['status']]),
            intro=[p.strip() for p in re.split(r'[\r\n]+', row['description']) if p.strip()],
            intro_en=bilingual(row['description'])['en'],
            source=dict(zh='依据官方文旅及平台资料整理（AI整理），逐条出处见下方',
                        en='AI summary of saved official tourism and platform sources; references below'),
            sources=list(refs.values()), borrowed=bilingual(row['editor_note']),
            address=bilingual(row.get('address', '')), specialty=bilingual(row.get('specialty', '')),
            shop_kind=bilingual(row.get('shop_kind', '')), platform=dict(zh=platform_zh, en=platform_en),
            photo=None, objects=[], review=review_text if review else None,
        )
    data = dict(
        key=key, mode='collection', generated=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat(),
        name=config.NAME, card={**config.CARD, 'cover': None}, opening=config.OPENING,
        planning=config.PLANNING, places=places, stops=stops, routes=[], default_route='none',
        provenance=dict(package=f'{prefix}_final.json', package_sha256=sha(path('final.json')),
                        source_sha256=source_sha, rating_sha256=sha(path('ratings.json')),
                        audit_sha256=sha(path('audit1_slim.jsonl')), translations_sha256=sha(path('translations.json')),
                        workbook_sha256=load('verification_report.json')['workbook_sha256'],
                        checked_on=getattr(config, 'CHECKED_ON', '2026-10-23'), business_database_written=False),
    )
    from tour_collection_media import augment
    augment(data, config)
    from tour_collection_experience import augment as experiences
    experiences(data, config)
    return data, [f'{key}: {len(stops)} 条已审资料；完整清单；可选来源地图与照片，无虚构停留时间或路线。']
