"""Recheck unresolved items against complete saved pages and additional sources."""
import hashlib
import json
from pathlib import Path

import claude_cli
from boston_summer_st_evidence_check import SCHEMA, SYSTEM

HERE = Path(__file__).resolve().parent
KEY = 'boston_summer_st'


def main():
    original = json.loads((HERE/f'{KEY}_evidence_check_request.json').read_text('utf-8'))['items']
    first = json.loads((HERE/f'{KEY}_evidence_check_results.json').read_text('utf-8'))
    if not first['complete']:
        raise ValueError('初次审计尚未完成')
    unresolved = {x['seq'] for x in first['items'] if not x['supported'] or not x['address_supported']}
    capture = json.loads((HERE/f'{KEY}_source_capture.json').read_text('utf-8'))['sources']
    by_url = {x['url']: x for x in capture}
    fallback = json.loads((HERE/f'{KEY}_fallback_sources.json').read_text('utf-8'))['items']
    extra = json.loads((HERE/f'{KEY}_supplement_sources.json').read_text('utf-8'))['items']
    records = []
    for row in original:
        if row['seq'] not in unresolved:
            continue
        sources = []
        for old in row['sources']:
            source = by_url.get(old['url'])
            if source and source.get('http_status') == 200 and source.get('source_text'):
                sources.append({'url': old['url'], 'text': source['source_text']})
        for candidate in fallback + extra:
            if (candidate['seq'] == row['seq'] and candidate.get('status') == 200 and candidate.get('text')
                    and candidate['url'] not in {s['url'] for s in sources}):
                sources.append({'url': candidate['url'], 'text': candidate['text']})
        records.append({**row, 'sources': sources})
    request = HERE/f'{KEY}_evidence_recheck_request.json'
    request.write_text(json.dumps({'system': SYSTEM, 'items': records}, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    digest = hashlib.sha256(request.read_bytes()).hexdigest()
    output = HERE/f'{KEY}_evidence_recheck_results.json'
    saved = json.loads(output.read_text('utf-8')) if output.exists() else {'request_sha256': digest, 'items': []}
    if saved['request_sha256'] != digest:
        raise ValueError('复核来源已变化，不可复用断点')
    results = saved['items']
    print(f'Prepared {len(records)} unresolved records with complete available source text', flush=True)
    for start in range(0, len(records), 6):
        batch = records[start:start+6]
        done = {x['seq'] for x in results}
        if {x['seq'] for x in batch} <= done:
            continue
        if any(x['seq'] in done for x in batch):
            raise ValueError('复核断点包含不完整批次')
        answer, usage = claude_cli.ask(SYSTEM, json.dumps(batch, ensure_ascii=False), SCHEMA,
                                       model='claude-sonnet-5', effort='medium')
        by_seq = {x['seq']: x for x in batch}
        if sorted(x['seq'] for x in answer['items']) != sorted(by_seq):
            raise ValueError('复核序号不完整')
        for item in answer['items']:
            sources = {x['url']: x['text'] for x in by_seq[item['seq']]['sources']}
            if item['quote'] and item['quote'] not in sources.get(item['source_url'], ''):
                item.update(quote='', source_url='', supported=False, address_supported=False,
                            reason='引文与来源不符，需人工复核。原结论：'+item['reason'])
            if not item['quote']:
                item['source_url'] = ''
                item['supported'] = False
            results.append(item)
        output.write_text(json.dumps({'request_sha256': digest, 'model': 'claude-sonnet-5', 'effort': 'medium',
                                      'items': results, 'complete': len(results) == len(records),
                                      'last_usage': usage}, ensure_ascii=False, indent=2)+'\n', 'utf-8')
        print(f'Rechecked {len(results)}/{len(records)}', flush=True)


if __name__ == '__main__':
    main()
