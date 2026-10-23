#!/usr/bin/env python3
"""核对版本和覆盖后合并本地资料，生成工作簿输入；不连接数据库、不写xlsx。"""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='nanluo_shichahai'
def load(n):return json.loads((HERE/(KEY+n)).read_text('utf-8'))
def sha(n):return hashlib.sha256((HERE/(KEY+n)).read_bytes()).hexdigest()
def display(r):return r.get('display_name',r['name'])

def platform_reference(row,captured):
    refs=[];refs_en=[]
    platform=[captured[sid] for sid in row['source_ids'] if 'platform' in captured[sid].get('source_kind','')]
    for s in platform:
        if 'dianping.com' not in s['url']:continue
        prices=re.findall(r'(?:人均\s*[:：]?\s*[¥￥]|[¥￥])(\d+(?:\.\d+)?)\s*(?:/人)?',s['text'])
        # 相册菜品标签中的单价不作人均；仅商户头部的明确人均/每人标记可用。
        if '人均' not in s['text'] and not re.search(r'[¥￥]\d+(?:\.\d+)?/人',s['text']):prices=[]
        for value in dict.fromkeys(prices[:1]):
            refs.append('人均'+value+'元');refs_en.append('CNY '+value+' per person')
        if s['id']=='dp_tangfang_main':refs.append('平台评分4.3/5');refs_en.append('Platform score 4.3/5')
    if platform:
        label='点评索引' if all(s['retrieval_method']=='web_search_index_excerpt' for s in platform) else '平台网页'
        return label+'快照；'+'；'.join(dict.fromkeys(refs))+('；' if refs else '')+'实时营业和价格未核实', 'Web/index snapshot; '+('; '.join(dict.fromkeys(refs_en))+'; ' if refs_en else '')+'live business status and prices not verified'
    return '文旅报道定位，未取得点评完整商户页；实时营业未核实','Located in a tourism report; full Dianping merchant page unavailable; live business status not verified'

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--draft',action='store_true',help='显式导出未完成全量独立审计的工作版');draft=ap.parse_args().draft
    source=load('_site_data.json');rating=load('_ratings.json');tr=load('_translations.json')
    source_sha=sha('_site_data.json')
    am=dict(input_sha256=source_sha,rating_sha256=sha('_ratings.json'),audit_source_sha256=sha('_audit_source_data.json'),model='claude-sonnet-5 effort=medium (claude-cli)') if draft else load('_audit_manifest.json')
    if any(x['input_sha256']!=source_sha for x in [rating,am,tr]):raise ValueError('资料、评分、审计、翻译版本不一致')
    if am['rating_sha256']!=sha('_ratings.json'):raise ValueError('审计对应评分已变更')
    if rating.get('grouping_sha256')!=sha('_peer_groups.json'):raise ValueError('评分使用的同类组版本已变化')
    audit_source=load('_audit_source_data.json')
    if am['audit_source_sha256']!=sha('_audit_source_data.json') or audit_source['input_sha256']!=source_sha:raise ValueError('审计原文版本不一致')
    audit_refs={r['seq']:r['evidence'] for r in audit_source['rows']}
    finding_file=HERE/(KEY+'_audit_finding_sources.json')
    if finding_file.exists():
        finding=load('_audit_finding_sources.json')
        packet_name=finding.get('audit_packets_file',KEY+'_audit_packets.json')
        if packet_name not in {KEY+'_audit_packets.json',KEY+'_audit_packets_before_guomoruo_cr_fix.json'}:raise ValueError('未知的审计输入包引用')
        packet_sha=hashlib.sha256((HERE/packet_name).read_bytes()).hexdigest()
        if finding['input_sha256']!=source_sha or finding['audit_packets_sha256']!=packet_sha:raise ValueError('审计发现的来源关联版本已变')
        for r in finding['rows']:
            seen={e['source_id'] for e in audit_refs[r['seq']]}
            audit_refs[r['seq']].extend(e for e in r['evidence'] if e['source_id'] not in seen)
    raw=[] if draft else [json.loads(s) for s in (HERE/(KEY+'_audit1_slim.jsonl')).read_text('utf-8').splitlines()]
    audits={r['seq']:r for r in raw};scores={r['seq']:r for r in rating['results']};wanted={r['source_seq'] for r in source['rows']}
    if len(scores)!=len(wanted) or set(scores)!=wanted or (not draft and (len(raw)!=len(wanted) or set(audits)!=wanted)):raise ValueError('结果漏行、重复或多行')
    names={r['identity_key']:display(r) for r in source['rows']};groups={g:f'PG{i:02}' for i,g in enumerate(sorted({r['peer_group'] for r in scores.values()}),1)}
    captured={s['id']:s for s in load('_source_capture.json')['sources'] if s['status']=='ok'}
    def en(text):return tr['values'][text]['en'] if text else ''
    zh_header=['序号','参观点名称','区域','关联整体','对象类型','Tier','Core','HS','IU','VI','VA','CE','ER','CR','需复核','审计原因与资料缺口','简介（AI整理）','编者说明','来源页面','当前开放状态','评分模型','审计模型','同类组','评分依据','CR理由','S-ness理由','身份键']
    en_header=['Seq','Place or object','Area','Related whole','Object type','Tier','Core','HS','IU','VI','VA','CE','ER','CR','Needs review','Audit notes and evidence gaps','Introduction (AI translation)','Editorial notes (AI translation)','Source pages','Current access','Scoring model','Auditor','Peer group code','Identity key']
    zh_header+=['条目性质','地址（来源记载）','店铺特色','平台参考（网页快照）']
    en_header+=['Entry kind','Address as recorded by sources','Shop features','Platform reference (web snapshot)']
    if draft:
        zh_header[1]='参观点名称（独立审计未完成）';en_header[1]='Place or object (audit pending)'
    zh=[];eng=[];final=[];cjk=[];merchant_rows=[]
    areas={'南锣鼓巷':'Nanluoguxiang','什刹海':'Shichahai','周边衔接':'Nearby connections'}
    for r in source['rows']:
        s=r['source_seq'];v=scores[s];a=audits.get(s)
        if draft:
            review=None;az='全量独立审计尚未完成，不能按“无需复核”解读。';ae='Independent audit is incomplete; no review conclusion is available.'
        else:
            required=[(a.get('error_note_zh'),a.get('error_note_en'))]+[(x['zh'],x.get('en')) for x in a['missing']]
            if any(z and not e for z,e in required):raise ValueError(f'{s}:审计自由文本缺英译')
            review=a['found_factual_error'] or any(x['tier_sensitive'] for x in a['missing'])
            az='\n'.join(([a['error_note_zh']] if a.get('error_note_zh') else [])+[x['zh'] for x in a['missing']])
            ae='\n'.join(([a['error_note_en']] if a.get('error_note_en') else [])+[x['en'] for x in a['missing']])
        nums=[round(v['core'],4)]+[v[k] for k in ['HS','IU','VI','VA','CE','ER']]+[round(v['CR'],4)]
        urls='\n'.join(dict.fromkeys(e['url'] for e in r['evidence']+audit_refs[s]))
        shop=r.get('entry_kind')=='特色商铺';pz,pe=platform_reference(r,captured) if shop else ('','')
        flag='未审计' if draft else ('是' if review else '否')
        zh.append([s,display(r),r['area'],names.get(r['parent_key'],''),v['object_type'],v['tier']]+nums+[flag,az,r['description'],r['editor_note'],urls,r['status'],rating['model'],am['model']+('（全量待完成）' if draft else ''),v['peer_group'],v['evidence'],v['cr_reason'],v['sness_reason'],r['identity_key']]+['特色商铺' if shop else '文化参观点',r.get('address',''),r.get('specialty',''),pz])
        row=[s,en(display(r)),areas[r['area']],en(names.get(r['parent_key'],'')),v['object_type'],v['tier']]+nums+['Not audited' if draft else ('Yes' if review else 'No'),ae,en(r['description']),en(r['editor_note']),urls,('Live business status, menu, prices and activities not verified.' if shop else 'Current access not verified; historical arrangements are not a live opening guarantee.'),rating['model'],am['model']+(' (pending)' if draft else ''),groups[v['peer_group']],r['identity_key']]+['Specialty shop' if shop else 'Cultural place or object',en(r.get('address','')),en(r.get('specialty','')),pe]
        if shop:merchant_rows.append([s,display(r),r['area'],r['shop_kind'],v['tier'],round(v['core'],4),flag,r['specialty'],r['address'],pz,r['status'],urls,'2026-10-23'])
        for i in [1,3,15,16,17,25,26,27]:
            if re.search(r'[\u3400-\u9fff]',str(row[i] or '')):cjk.append([s,i+1])
        eng.append(row);final.append(dict(r,rating=v,audit=a,needs_review=review,audit_evidence=audit_refs[s]))
    if cjk:raise ValueError('英文主要文本仍有中文残留：'+str(cjk))
    refs=[];quoted_pages=set()
    for r in source['rows']:
        used=set()
        for e in r['evidence']:
            # 同一网页只展示一次简短引文，其余条目保留逐条来源定位；完整核验记录在本地证据文件。
            quote=e['quote'][:20] if e['url'] not in quoted_pages else '见该页关于本条对象的说明；完整逐字核验短引保存在本地证据记录。'
            usage='原文短引节选；信息整理及审计' if e['url'] not in quoted_pages else '同页其他条目的来源定位'
            refs.append([r['source_seq'],display(r),e['source_id'],e['url'],quote,usage,e['retrieval_method'],e['source_sha256'],'2026-10-23']);used.add(e['source_id']);quoted_pages.add(e['url'])
        for e in audit_refs[r['source_seq']]:
            if e['source_id'] not in used:refs.append([r['source_seq'],display(r),e['source_id'],e['url'],'未选作整理短引；独立审计使用已保存的来源文本，取得方式另列。','审计补充来源',e['retrieval_method'],e['source_sha256'],'2026-10-23'])
    original={r['seq']:r for r in map(json.loads,(HERE/(KEY+'_stage1.jsonl')).read_text('utf-8').splitlines())}
    peers=[[groups[v['peer_group']],v['peer_group'],r['source_seq'],display(r),v['object_type'],names.get(r['parent_key'],''),original[r['source_seq']]['peer_group']] for r in source['rows'] for v in [scores[r['source_seq']]]]
    counts=dict(Counter(r['rating']['tier'] for r in final));review=None if draft else [r['source_seq'] for r in final if r['needs_review']];errors=None if draft else [r['source_seq'] for r in final if r['audit']['found_factual_error']]
    notes=[['范围',source['scope']],['采集日期','2026-10-23'],['条目与评级',f"{len(final)}条；"+' / '.join(f'{k}{counts.get(k,0)}' for k in ['S','A','B','C'])],['需复核','独立审计未完成，尚无结论' if draft else f'{len(review)}条；序号：'+','.join(map(str,review))],['整理方式','中文简介由gpt-5.6-luna依据本轮保存的官方网页整理，不是逐字官方原文。来源页面及原件哈希逐条列出；每篇展示一次不超过20字的短引节选，完整逐字核验记录另保存在本地证据数据。'],['对象关系','site为整体景区或街区，node为建筑、街巷等节点，object为实物。整体与组成部分有包含关系；84条不是84个互不重叠的路线站点。'],['当前开放','历史报道、宗教活动、文物保护名录或活化计划不等于今日可入内；居民院落、校园及办公场所不默认开放。'],['周边衔接','钟鼓楼、德胜门箭楼、护国寺街故居明确标为周边衔接，未并入南锣鼓巷或什刹海水域本体。'],['英文','英文名称、简介和资料说明原译为Luna；17段按中文作词句、专名和铭文转写校正，保留原译文。均为AI翻译，不标为官方英文或人工校对。'],['信息模型','gpt-5.6-luna effort=medium (codex-cli)'],['评分模型',rating['model']],['独立审计',am['model']+'；slim；'+('全量尚未完成，Claude额度提示2026-10-23 14:20恢复。' if draft else '审计不改评级。')],['复核口径','复核列按影响优先参观判断的资料缺口或事实错误导出；其他资料缺口仍列在审计说明。B/C沿用既有规则兜底，模型原标记保存在本地审计记录。开放状态另列。'],['字段含义','HS历史/艺术/遗产重要性，IU本地身份与不可替代性，VI视觉与空间冲击，VA游客体验吸引力，CE文化/教育/叙事价值，ER整体关系与景观价值，CR类别代表性；按既有V3.0不同对象类型加权。'],['状态','资料和评分已完成；独立审计'+('未完成。' if draft else '已完成。')+'尚未导入生产业务表或发布导览。'],['图片、路线与坐标','本轮未制作路线、采集现场坐标或为每个条目下载独立图片；缺项保持缺席。'],['候选待补',str(len(source['pending']))+'条未形成有效来源的候选；如有则列在下方。']]
    notes.extend([[p['name'],p['reason']] for p in source['pending']])
    payload=dict(sheets=[dict(name='zh-CN',headers=zh_header,rows=zh,widths=[8,36,16,30,12,8,10,8,8,8,8,8,8,8,11,72,85,80,70,48,35,38,36,80,70,70,28]),dict(name='en',headers=en_header,rows=eng,widths=[8,40,23,38,12,8,10,8,8,8,8,8,8,8,12,85,95,85,70,65,35,38,22,28]),dict(name='来源证据',headers=['序号','参观点','来源标识','来源页面','原文短引或来源说明','用途','取得方式','原始响应SHA-256','取得日期'],rows=refs,widths=[8,36,30,80,75,24,35,70,14]),dict(name='同类组',headers=['组代码','同类组','序号','参观点','对象类型','关联整体','阶段一原组名'],rows=peers,widths=[12,42,9,40,14,36,42]),dict(name='说明',headers=['项目','内容'],rows=notes,widths=[25,130])],output='展品_北京南锣鼓巷及什刹海.xlsx')
    payload['sheets'][0]['widths'] += [14,65,55,65]
    payload['sheets'][1]['widths'] += [23,80,70,75]
    payload['sheets'][2]['headers'][7]='证据快照SHA-256'
    payload['sheets'].insert(2,dict(name='特色商铺',headers=['序号','商铺名称','区域','业态','Tier','Core','需复核','特色','地址（来源记载）','平台参考（非实时）','经营状态边界','来源页面','采集日期'],rows=merchant_rows,widths=[8,46,16,24,8,10,11,55,65,65,65,80,14]))
    revisions=len(load('_translation_repair.json')['changes'])
    replacements={
        '整理方式':'中文简介由gpt-5.6-luna依据已保存资料整理；来源包括官方文旅网页、点评等平台页面及索引摘录。取得方式和证据快照哈希逐条列出，工具解析文本不冒充HTTP原始响应。每篇仅展示一次不超过20字短引。',
        '对象关系':f'site为整体景区或街区，node为建筑、街巷或具体经营门店，object为实物。整体与组成部分有包含关系；{len(final)}条不是{len(final)}个互不重叠的路线站点。',
        '英文':f'原译为Luna medium；累计{revisions}段按中文作专名、方位、混字和铭文转写校正，原译及变更记录保留。均为AI翻译，不标为官方英文或人工校对。',
        '独立审计':am['model']+'；slim；'+('全量尚未完成。' if draft else '全量完成，审计不改评级。'),
    }
    for row in notes:
        if row[0] in replacements:row[1]=replacements[row[0]]
    notes.extend([
        ['特色商铺',f'增补{len(merchant_rows)}家具体经营门店，已并入中英文总表，商铺页便于查看特色、地址与平台快照。平台星级和人均不直接换算为V3分数。'],
        ['分店与经营状态','品牌创立年不等于分店或建筑年代；不移植其他分店菜单。索引与平台公开页可能滞后，价格、菜单、营业和体验项目均需出行前核实。'],
        ['郭沫若故居','原第48条郭沫若纪念馆即同一处故居；展示名补全为郭沫若故居（郭沫若纪念馆），没有新增重复记录。'],
        ['同类比较',f'沿用V3.0规则与模型；旧84条同类组保持，新增经营节点按业态和功能统一为6组，全表共{len(groups)}组。同类商铺不按片区拆组。'],
    ])
    payload['audited']=not draft
    (HERE/(KEY+'_export_data.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (HERE/(KEY+'_final.json')).write_text(json.dumps(dict(input_sha256=source_sha,state='独立审计待完成' if draft else '独立审计完成',models={'information':'gpt-5.6-luna medium','rating':rating['model'],'audit':None if draft else am['model'],'planned_audit':am['model']},rows=final),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    old=load('_v1_snapshot.json');old_scores={r['seq']:r for r in json.loads(old['files'][KEY+'_ratings.json']['text'])['results']}
    changes=[dict(seq=r['source_seq'],name=display(r),previous=old_scores[r['source_seq']]['tier'],current=r['rating']['tier']) for r in final if r['source_seq'] in old_scores and old_scores[r['source_seq']]['tier']!=r['rating']['tier']]
    summary=dict(audit_state='pending' if draft else 'complete',audited_records=0 if draft else len(final),records=len(final),tier=counts,types=dict(Counter(r['rating']['object_type'] for r in final)),evidence_records=len(refs),verified_short_quotes=sum(len(r['evidence']) for r in source['rows']),displayed_short_quotes=len(quoted_pages),needs_review=review,factual_errors=errors,english_cjk_residual=cjk,pending=len(source['pending']),added_shops=len(merchant_rows),shop_tier=dict(Counter(row[4] for row in merchant_rows)),previous_records=84,changed_existing_tiers=changes,guomoruo=dict(seq=48,name=next(display(r) for r in source['rows'] if r['source_seq']==48),tier=scores[48]['tier']))
    (HERE/(KEY+'_export_report.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
