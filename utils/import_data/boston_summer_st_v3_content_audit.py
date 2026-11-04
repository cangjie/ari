"""Verify the additional rating-sensitive revisions against indexed source passages."""
import hashlib
import json
from pathlib import Path

import claude_cli
from boston_summer_st_revision_followup import SYSTEM, SCHEMA

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'


def main():
    draft=json.loads((HERE/f'{KEY}_revision_v3_draft.json').read_text('utf-8'))
    previous=json.loads((HERE/f'{KEY}_v2_rating_audit_request.json').read_text('utf-8'))
    records=[]
    for previous_row in previous['items']:
        seq=previous_row['seq']
        if seq not in draft['v3_changed_seqs']:continue
        row=draft['rows'][seq-1]
        records.append({'seq':seq,'name':row['en'],'description':row['en_desc'],
                        'address':row['address'],'passages':previous_row['passages']})
    if set(x['seq'] for x in records)!=set(draft['v3_changed_seqs']):
        raise ValueError('来源复核范围不完整')
    path=HERE/f'{KEY}_v3_content_audit_request.json'
    path.write_text(json.dumps({'system':SYSTEM,'items':records},ensure_ascii=False,indent=2)+'\n','utf-8')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    output=HERE/f'{KEY}_v3_content_audit_results.json'
    saved=json.loads(output.read_text('utf-8')) if output.exists() else {'request_sha256':digest,'items':[]}
    if saved['request_sha256']!=digest:raise ValueError('复核输入已变化')
    results=saved['items']
    for start in range(0,len(records),5):
        batch=records[start:start+5];done={x['seq'] for x in results}
        if {x['seq'] for x in batch}<=done:continue
        if any(x['seq'] in done for x in batch):raise ValueError('复核断点不完整')
        answer,usage=claude_cli.ask(SYSTEM,json.dumps(batch,ensure_ascii=False),SCHEMA,
                                    model='claude-sonnet-5',effort='medium')
        by_seq={x['seq']:x for x in batch}
        if sorted(x['seq'] for x in answer['items'])!=sorted(by_seq):raise ValueError('复核覆盖不完整')
        for item in answer['items']:
            ids={p['id'] for p in by_seq[item['seq']]['passages']}
            if not item['passage_ids'] or any(p not in ids for p in item['passage_ids']):
                item.update(supported=False,address_supported=False,reason='引用来源片段无效。 '+item['reason'])
            results.append(item)
        output.write_text(json.dumps({'request_sha256':digest,'model':'claude-sonnet-5','effort':'medium',
                                     'items':results,'complete':len(results)==len(records),'last_usage':usage},
                                    ensure_ascii=False,indent=2)+'\n','utf-8')
        print(f'Checked additional revisions {len(results)}/{len(records)}',flush=True)


if __name__=='__main__':main()
