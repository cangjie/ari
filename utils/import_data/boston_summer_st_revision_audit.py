"""Independently review proposed revisions against captured full source pages."""
import hashlib
import json
from pathlib import Path

import claude_cli
import boston_summer_st_list as listing
from boston_summer_st_evidence_check import SCHEMA, SYSTEM

HERE = Path(__file__).resolve().parent
KEY = 'boston_summer_st'


def main():
    revision = json.loads((HERE/f'{KEY}_revision_draft.json').read_text('utf-8'))
    captures = json.loads((HERE/f'{KEY}_source_capture.json').read_text('utf-8'))['sources']
    captured = {x['url']: {'url':x['url'], 'text':x['source_text']}
                for x in captures if x.get('http_status') == 200 and x.get('source_text')}
    supplements = []
    for suffix in ('fallback_sources.json', 'supplement_sources.json', 'supplement_sources_2.json'):
        supplements.extend(json.loads((HERE/f'{KEY}_{suffix}').read_text('utf-8'))['items'])
    records = []
    for seq in revision['changed_seqs']:
        row = revision['rows'][seq-1]
        original = captured.get(row['source'])
        sources = [original] if original else []
        for extra in supplements:
            if (extra['seq'] == seq and extra.get('status') == 200 and extra.get('text')
                    and extra['url'] not in {x['url'] for x in sources}):
                sources.append({'url':extra['url'], 'text':extra['text']})
        # Include the original inventory source for revised descriptions too.
        old = captured.get(listing.rows[seq-1]['source'])
        if old and old['url'] not in {x['url'] for x in sources}:
            sources.append(old)
        records.append({'seq':seq, 'name':row['en'], 'description':row['en_desc'],
                        'address':row['address'], 'sources':sources})
    request = HERE/f'{KEY}_revision_audit_request.json'
    request.write_text(json.dumps({'system':SYSTEM, 'items':records}, ensure_ascii=False, indent=2)+'\n','utf-8')
    digest = hashlib.sha256(request.read_bytes()).hexdigest()
    output = HERE/f'{KEY}_revision_audit_results.json'
    saved = json.loads(output.read_text('utf-8')) if output.exists() else {'request_sha256':digest, 'items':[]}
    if saved['request_sha256'] != digest:
        raise ValueError('修订内容或来源已变化，不能复用旧复核')
    results = saved['items']
    print(f'Prepared {len(records)} revised records', flush=True)
    for start in range(0,len(records),6):
        batch=records[start:start+6]
        done={x['seq'] for x in results}
        if {x['seq'] for x in batch} <= done:
            continue
        if any(x['seq'] in done for x in batch):
            raise ValueError('修订复核断点包含不完整批次')
        answer,usage=claude_cli.ask(SYSTEM,json.dumps(batch,ensure_ascii=False),SCHEMA,
                                     model='claude-sonnet-5',effort='medium')
        by_seq={x['seq']:x for x in batch}
        if sorted(x['seq'] for x in answer['items']) != sorted(by_seq):
            raise ValueError('修订复核序号不完整')
        for item in answer['items']:
            available={x['url']:x['text'] for x in by_seq[item['seq']]['sources']}
            if item['quote'] and item['quote'] not in available.get(item['source_url'],''):
                item.update(quote='',source_url='',supported=False,address_supported=False,
                            reason='引文与来源不符，需人工复核。原结论：'+item['reason'])
            if not item['quote']:
                item['source_url']=''; item['supported']=False
            results.append(item)
        output.write_text(json.dumps({'request_sha256':digest,'model':'claude-sonnet-5','effort':'medium',
                                     'items':results,'complete':len(results)==len(records),'last_usage':usage},
                                    ensure_ascii=False,indent=2)+'\n','utf-8')
        print(f'Reviewed revisions {len(results)}/{len(records)}',flush=True)


if __name__=='__main__':
    main()
