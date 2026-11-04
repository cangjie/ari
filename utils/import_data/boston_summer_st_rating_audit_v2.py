"""Independently review revised V3 scores against saved source passages."""
import argparse
import hashlib
import json
from pathlib import Path

import claude_cli

HERE = Path(__file__).resolve().parent
KEY = 'boston_summer_st'
SYSTEM = ('你是独立审计员，不重新打分。只依据给出的原始来源片段，检查简介或评分证据中的明确错误，'
          '以及会影响走廊内文化参观优先级的关键遗漏。营业、票价及开放状态未实时核实已统一披露，'
          '不要因此判错误。不要凭外部知识补证；每项错误或关键遗漏必须引用给定 passage id。')
SCHEMA = {'type':'object','properties':{'audits':{'type':'array','items':{
    'type':'object','properties':{'seq':{'type':'integer'},
    'found_factual_error':{'type':'boolean'},'error_note_zh':{'type':['string','null']},
    'missing':{'type':'array','items':{'type':'object','properties':{
        'zh':{'type':'string'},'tier_sensitive':{'type':'boolean'},
        'passage_ids':{'type':'array','items':{'type':'string'}}},
        'required':['zh','tier_sensitive','passage_ids'],'additionalProperties':False}},
    'error_passage_ids':{'type':'array','items':{'type':'string'}}},
    'required':['seq','found_factual_error','error_note_zh','missing','error_passage_ids'],
    'additionalProperties':False}}},'required':['audits'],'additionalProperties':False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--version', choices=['v2','v3'], default='v2')
    version=parser.parse_args().version
    revision_path=f'{KEY}_revision_v3_draft.json' if version=='v3' else f'{KEY}_revision_final_draft.json'
    revision=json.loads((HERE/revision_path).read_text('utf-8'))
    ratings_path=HERE/f'{KEY}_{version}_ratings.json'
    ratings=json.loads(ratings_path.read_text('utf-8'))
    fields=('id','zone','kind','zh','en','zh_desc','en_desc','address','relation','access','source','source_name','note')
    rating_input=[{k:row[k] for k in fields} for row in revision['rows']]
    input_hash=hashlib.sha256(json.dumps(rating_input,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if ratings.get('input_sha256') != input_hash:
        raise ValueError('评分与修订资料不匹配')
    revision_request=json.loads((HERE/f'{KEY}_revision_audit_request.json').read_text('utf-8'))
    changed_sources={x['seq']:x['sources'] for x in revision_request['items']}
    originals=json.loads((HERE/f'{KEY}_source_capture.json').read_text('utf-8'))['sources']
    by_url={x['url']:x['source_text'] for x in originals if x.get('http_status')==200 and x.get('source_text')}
    extras=[]
    for suffix in ('fallback_sources.json','supplement_sources.json','supplement_sources_2.json'):
        extras.extend(json.loads((HERE/f'{KEY}_{suffix}').read_text('utf-8'))['items'])
    scores={x['seq']:x for x in ratings['results']}
    if set(scores)!=set(range(1,54)):
        raise ValueError('新版评分覆盖不完整')
    records=[]
    for seq,row in enumerate(revision['rows'],1):
        sources=list(changed_sources.get(seq,[]))
        if row['source'] in by_url and row['source'] not in {x['url'] for x in sources}:
            sources.append({'url':row['source'],'text':by_url[row['source']]})
        for extra in extras:
            if extra['seq']==seq and extra.get('status')==200 and extra.get('text') and extra['url'] not in {x['url'] for x in sources}:
                sources.append({'url':extra['url'],'text':extra['text']})
        passages=[]
        for i,source in enumerate(sources):
            for offset in range(0,len(source['text']),1800):
                passages.append({'id':f'{seq}-{i}-{offset}','url':source['url'],
                                 'text':source['text'][max(0,offset-200):offset+2000]})
        score=scores[seq]
        records.append({'seq':seq,'name':row['en'],'description_zh':row['zh_desc'],
                        'description_en':row['en_desc'],'address':row['address'],
                        'rating':{k:score[k] for k in ['tier','core','evidence','confidence']},
                        'passages':passages})
    request=HERE/f'{KEY}_{version}_rating_audit_request.json'
    request.write_text(json.dumps({'system':SYSTEM,'rating_sha256':hashlib.sha256(ratings_path.read_bytes()).hexdigest(),
                                   'items':records},ensure_ascii=False,indent=2)+'\n','utf-8')
    digest=hashlib.sha256(request.read_bytes()).hexdigest()
    output=HERE/f'{KEY}_{version}_rating_audit_results.json'
    saved=json.loads(output.read_text('utf-8')) if output.exists() else {'request_sha256':digest,'audits':[]}
    if saved['request_sha256']!=digest:
        raise ValueError('新版评分审计输入已变化，不可复用断点')
    audits=saved['audits']
    for start in range(0,len(records),8):
        batch=records[start:start+8]; done={x['seq'] for x in audits}
        if {x['seq'] for x in batch} <= done:continue
        if any(x['seq'] in done for x in batch):raise ValueError('评分审计断点批次不完整')
        answer,usage=claude_cli.ask(SYSTEM,json.dumps(batch,ensure_ascii=False),SCHEMA,
                                     model='claude-sonnet-5',effort='medium')
        by_seq={x['seq']:x for x in batch}
        if sorted(x['seq'] for x in answer['audits'])!=sorted(by_seq):raise ValueError('评分审计覆盖不完整')
        for item in answer['audits']:
            available={x['id'] for x in by_seq[item['seq']]['passages']}
            if (item['found_factual_error'] and not item['error_passage_ids']) or any(x not in available for x in item['error_passage_ids']):
                raise ValueError(f"{item['seq']} 事实错误缺少原文依据")
            for missing in item['missing']:
                if not missing['passage_ids'] or any(x not in available for x in missing['passage_ids']):
                    raise ValueError(f"{item['seq']} 缺失项没有有效来源")
            audits.append(item)
        output.write_text(json.dumps({'request_sha256':digest,'model':'claude-sonnet-5','effort':'medium',
                                      'audits':audits,'complete':len(audits)==len(records),'last_usage':usage},
                                     ensure_ascii=False,indent=2)+'\n','utf-8')
        print(f'Reviewed scores {len(audits)}/{len(records)}',flush=True)


if __name__=='__main__':
    main()
