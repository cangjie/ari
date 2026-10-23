"""公开HTTPS文件逐字节比对与只读问答检查；不发问题、不调模型、不写业务库。"""
import argparse
import datetime as dt
import hashlib
import json
import urllib.request
from pathlib import Path

import tls

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOUR = ROOT / 'web_api/tour'
ORIGIN = 'https://tour.snowmeet.top'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def get(path):
    request = urllib.request.Request(ORIGIN + path, headers={'User-Agent': 'Ari-release-check/1.0'})
    with urllib.request.urlopen(request, timeout=40, context=tls.ssl_ctx()) as response:
        raw = response.read()
        if response.status != 200:
            raise ValueError(f'{path}: HTTP {response.status}')
        return raw, response.headers.get('Content-Type'), response.headers.get('Cache-Control')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    catalog = json.loads((TOUR / 'catalog.json').read_text(encoding='utf-8'))['museums']
    files = ['index.html', 'app.js', 'app.css', 'catalog.json'] + [f'data/{k}.json' for k in catalog]
    result = dict(checked_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
                  commit=args.commit, origin=ORIGIN, catalog=catalog, files=[], qa_get=[],
                  business_database_written=False, online_questions_sent=0,
                  apk_rebuilt=False, android_device_tested=False)
    for relative in files:
        local = (TOUR / relative).read_bytes()
        remote, mime, cache = get('/' + relative)
        if remote != local:
            raise ValueError(f'{relative}: 公开文件与本地内容不一致')
        result['files'].append(dict(path=relative, status=200, bytes=len(remote),
                                    sha256=digest(remote), content_type=mime, cache_control=cache))
    for key in catalog:
        museum = json.loads((TOUR / f'data/{key}.json').read_text(encoding='utf-8'))
        pid = 'guomoruo' if key == 'nanluo_shichahai' else museum['places'][0]['id']
        raw, _, _ = get(f'/api/tour/{key}/places/{pid}/topics')
        payload = json.loads(raw)
        if not isinstance(payload.get('topics'), list) or not isinstance(payload.get('more'), bool):
            raise ValueError(f'{key}/{pid}: 问答列表格式异常')
        result['qa_get'].append(dict(museum=key, place=pid, status=200, visible_topics=len(payload['topics'])))
    collection = json.loads((TOUR / 'data/nanluo_shichahai.json').read_text(encoding='utf-8'))
    result['collection'] = dict(records=len(collection['stops']),
        shops=sum(s['kind'] == 'shop' for s in collection['stops'].values()), mode=collection['mode'],
        review=[s['seq'] for s in collection['stops'].values() if s['review']],
        workbook_sha256=collection['provenance']['workbook_sha256'])
    result['state'] = '公开HTTPS逐文件哈希与三处景区只读问答GET均通过'
    output = HERE / 'nanluo_shichahai_release_report.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(state=result['state'], files=len(files), catalog=catalog, **result['collection']), ensure_ascii=False))


if __name__ == '__main__':
    main()
