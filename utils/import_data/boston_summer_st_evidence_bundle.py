"""Bind independent review evidence to exact saved HTTP source passages."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'


def load(suffix):
    return json.loads((HERE/f'{KEY}_{suffix}').read_text('utf-8'))


def main():
    captures=load('source_capture.json')['sources']
    sources=[{'url':x['url'],'text':x.get('source_text',''),'status':x.get('http_status'),
              'raw_sha256':x.get('raw_sha256'),'title':x.get('title',''),
              'origin':'source_capture.json'} for x in captures]
    for suffix in ('fallback_sources.json','supplement_sources.json','supplement_sources_2.json'):
        for x in load(suffix)['items']:
            sources.append({'url':x['url'],'text':x.get('text',''),'status':x.get('status'),
                            'raw_sha256':x.get('raw_sha256'),'title':x.get('title',''),
                            'origin':suffix})
    good=[x for x in sources if x['status']==200 and x['text'] and x['raw_sha256']]
    revision=load('revision_v3_draft.json')
    changed=set(revision['changed_seqs'])
    first=load('evidence_check_results.json'); second=load('evidence_recheck_results.json')
    revised=load('revision_audit_results.json'); follow=load('revision_followup_results.json')
    extra_review=load('v3_content_audit_results.json')
    for stem,report in [('evidence_check',first),('evidence_recheck',second),('revision_audit',revised),('revision_followup',follow),('v3_content_audit',extra_review)]:
        raw=(HERE/f'{KEY}_{stem}_request.json').read_bytes()
        if report['request_sha256']!=hashlib.sha256(raw).hexdigest():
            raise ValueError(f'{stem} 审核输入不匹配')
    decisions={x['seq']:('evidence_check',x) for x in first['items']}
    decisions.update({x['seq']:('evidence_recheck',x) for x in second['items']})
    decisions.update({x['seq']:('revision_audit',x) for x in revised['items'] if x['seq'] in changed})
    decisions.update({x['seq']:('revision_followup',x) for x in follow['items']})
    decisions.update({x['seq']:('v3_content_audit',x) for x in extra_review['items']})
    request=load('revision_followup_request.json')
    passages={p['id']:p for row in request['items'] for p in row['passages']}
    v3_request=load('v3_content_audit_request.json')
    v3_passages={p['id']:p for row in v3_request['items'] for p in row['passages']}
    items=[]
    for seq in range(1,len(revision['rows'])+1):
        origin,result=decisions[seq]
        if not result['supported'] or not result['address_supported']:
            raise ValueError(f'{seq}：简介或地址未核实')
        if origin=='v3_content_audit':
            excerpts=[v3_passages[p] for p in result['passage_ids']]
        elif origin=='revision_followup':
            excerpts=[passages[p] for p in result['passage_ids']]
        else:
            excerpts=[{'url':result['source_url'],'text':result['quote']}]
        evidence=[]
        for excerpt in excerpts:
            candidates=[x for x in good if x['url']==excerpt['url'] and excerpt['text'] in x['text']]
            if not candidates:
                raise ValueError(f'{seq}：来源原文与保存的HTTP正文不符')
            x=candidates[0]
            evidence.append({'url':x['url'],'quote':excerpt['text'],'title':x['title'],
                             'source_file':x['origin'],'raw_sha256':x['raw_sha256'],
                             'source_text_sha256':hashlib.sha256(x['text'].encode()).hexdigest()})
        items.append({'seq':seq,'audit':origin,'evidence':evidence})
    (HERE/f'{KEY}_verified_evidence_draft.json').write_text(
        json.dumps({'state':'draft; not a publication package','items':items},ensure_ascii=False,indent=2)+'\n','utf-8')
    print(f'{len(items)} records have verifiable saved source passages')


if __name__=='__main__':
    main()
