"""Build a source-bound release candidate after all independent checks complete."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'
PREFIX=KEY+'_v3'
WORKBOOK=HERE/'exports'/'波士顿Summer Street周边_双语V3评级.xlsx'


def read(name):return json.loads((HERE/name).read_text('utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(name,obj):
    path=HERE/name
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n','utf-8')
    return path


def main():
    import tour_collection_build as build
    revision=read(KEY+'_revision_v3_draft.json');rating=read(PREFIX+'_ratings.json')
    evidence=read(KEY+'_verified_evidence_draft.json')['items']
    audit=read(PREFIX+'_rating_audit_results.json');audit_request=HERE/(PREFIX+'_rating_audit_request.json')
    request=read(audit_request.name)
    if (not audit['complete'] or audit['request_sha256']!=digest(audit_request)
            or request['rating_sha256']!=digest(HERE/(PREFIX+'_ratings.json'))
            or len(audit['audits'])!=53 or {x['seq'] for x in audit['audits']}!=set(range(1,54))):
        raise ValueError('评级独立审计不完整或版本不一致')
    if not WORKBOOK.is_file():raise ValueError('缺少通过验证的新版双语评级表')
    resolutions_path=HERE/(PREFIX+'_audit_resolutions.json')
    resolutions=read(resolutions_path.name) if resolutions_path.exists() else {'items':[]}
    resolution_by_seq={x['seq']:x for x in resolutions['items']}
    errors=[x for x in audit['audits'] if x['found_factual_error']]
    for error in errors:
        decision=resolution_by_seq.get(error['seq'],{})
        if decision.get('disposition')!='false_positive' or not decision.get('reason'):
            raise ValueError(f"{error['seq']}：独立审计报告事实错误，尚未解决")

    groups=read(PREFIX+'_rating_groups.json')
    if (groups['input_sha256']!=rating['input_sha256']
            or groups['stage1_sha256']!=digest(HERE/(PREFIX+'_rating_stage1.jsonl'))
            or any(groups['groups'].get(str(x['seq']))!=x['peer_group'] for x in rating['results'])):
        raise ValueError('评分与同类组或阶段一断点不一致')
    old=read(KEY+'_site_data.json');old_rows={x['source_seq']:x for x in old['rows']}
    sourcefiles={}
    for suffix in ('source_capture.json','fallback_sources.json','supplement_sources.json','supplement_sources_2.json'):
        raw=read(KEY+'_'+suffix)
        sourcefiles[suffix]=raw['sources'] if 'sources' in raw else raw['items']
    evidence_by_seq={x['seq']:x for x in evidence}
    sources=[];source_lookup={};new_rows=[]
    translations=read(KEY+'_translations.json')['values']
    for seq,item in enumerate(revision['rows'],1):
        original=old_rows[seq];row=dict(original);refs=[]
        for ev in evidence_by_seq[seq]['evidence']:
            candidates=sourcefiles[ev['source_file']]
            match=next((x for x in candidates if x['url']==ev['url']
                        and hashlib.sha256(x.get('source_text',x.get('text','')).encode()).hexdigest()==ev['source_text_sha256']
                        and x.get('raw_sha256')==ev['raw_sha256']),None)
            if not match:raise ValueError(f'{seq}：来源快照已改变')
            text=match.get('source_text',match.get('text',''))
            if not ev['quote'] or ev['quote'] not in text:raise ValueError(f'{seq}：引文不在来源中')
            key=(ev['url'],ev['source_text_sha256'])
            if key not in source_lookup:
                sid=f'source_{len(sources)+1:03}'
                source_lookup[key]=sid
                sources.append(dict(id=sid,status='ok',url=ev['url'],title=ev['title'] or ev['url'],
                                    http_status=200,retrieval_method='verified_HTTP_extracted_text',
                                    source_text=text,raw_sha256=ev['raw_sha256'],
                                    captured_in=ev['source_file']))
            refs.append(dict(source_id=source_lookup[key],url=ev['url'],quote=ev['quote']))
        row.update(name=item['zh'],display_name=item['zh'],area=item['zone'],aliases=[item['en']],
                   description=item['zh_desc'],address=item['address'],anchor=item['address'],
                   evidence=refs,source_ids=list(dict.fromkeys(x['source_id'] for x in refs)))
        if item['id'].startswith('S'):
            row.update(specialty=item['zh_desc'],shop_kind=item['kind'])
        if item['note']:row['editor_note']=item['note']
        for zh,en in [(item['zh'],item['en']),(item['zh_desc'],item['en_desc']),(item['address'],item['address'])]:
            translations[zh]={'en':en,'confidence':'editorial','source':'已核资料的双语编辑'}
        if seq==21:
            translations[item['note']]={'en':'The current building website uses 263 Summer St.; the rooftop sign is subject to current conditions.',
                                       'confidence':'editorial','source':'已核资料的双语编辑'}
        new_rows.append(row)
    capture_path=dump(PREFIX+'_source_capture.json',{'captured_on':'2026-11-03','sources':sources})
    site={**old,'rows':new_rows,'capture_sha256':digest(capture_path),
          'information_sha256':hashlib.sha256(json.dumps(new_rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
          'state':'独立审计完成'}
    build.verify_inventory_rating(rating,revision,site,{'values':translations})
    source_path=dump(PREFIX+'_site_data.json',site);source_sha=digest(source_path)
    peer_path=dump(PREFIX+'_peer_groups.json',{'rating_input_sha256':rating['input_sha256'],
                    'groups':[{'seq':x['seq'],'identity_key':new_rows[x['seq']-1]['identity_key'],
                               'peer_group':x['peer_group']} for x in rating['results']]})
    audit_by_seq={x['seq']:x for x in audit['audits']}
    slim=[];final_rows=[];scores={x['seq']:x for x in rating['results']}
    for row in new_rows:
        seq=row['source_seq'];finding=audit_by_seq[seq]
        missing=[{'zh':x['zh'],'tier_sensitive':x['tier_sensitive'],'passage_ids':x['passage_ids']}
                 for x in finding['missing']]
        if finding['found_factual_error']:
            decision=resolution_by_seq[seq]
            missing.append({'zh':'独立审计提示：'+str(finding['error_note_zh'])+'；复核：'+decision['reason'],
                            'tier_sensitive':True,'passage_ids':finding['error_passage_ids']})
        record={'seq':seq,'missing':missing,'found_factual_error':False,'error_note_zh':None,
                'top_missing_zh':None,'top_missing_en':None,
                'independent_original':finding,'resolution':resolution_by_seq.get(seq)}
        slim.append(record)
        final_rows.append({**row,'rating':scores[seq],'audit':record,'audit_evidence':[],
                           'needs_review':any(x['tier_sensitive'] for x in missing)})
    slim_path=HERE/(PREFIX+'_audit1_slim.jsonl')
    slim_path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in slim),'utf-8')
    dump(PREFIX+'_final.json',{'input_sha256':source_sha,'state':'独立审计完成',
                               'models':site['models'],'rows':final_rows})
    dump(PREFIX+'_translations.json',{'input_sha256':source_sha,'model':'bilingual editorial inventory',
                                       'source':'已核双语清单','values':translations})
    # Retain the full unmodified independent packet and decision file separately.
    audit_source=HERE/(PREFIX+'_audit_source_data.json')
    audit_source.write_bytes(audit_request.read_bytes())
    dump(PREFIX+'_audit_manifest.json',{'input_sha256':source_sha,'rating_sha256':digest(HERE/(PREFIX+'_ratings.json')),
         'rating_grouping_sha256':digest(peer_path),'audit_source_sha256':digest(audit_source),
         'independent_results_sha256':digest(HERE/(PREFIX+'_rating_audit_results.json')),
         'resolution_sha256':digest(resolutions_path) if resolutions_path.exists() else None,
         'model':'claude-sonnet-5 effort=medium','count':53,
         'review':[x['seq'] for x in slim if any(m['tier_sensitive'] for m in x['missing'])]})
    dump(PREFIX+'_verification_report.json',{'key':KEY,'count':53,'tiers':rating['counts'],
         'workbook_sha256':digest(WORKBOOK),'business_database_written':False,
         'production_questions_posted':0,'android_apk_rebuilt':False,'nginx_changed':False})
    print(f'Candidate package prepared with {len(sources)} saved source snapshots; release checks remain')


if __name__=='__main__':main()
