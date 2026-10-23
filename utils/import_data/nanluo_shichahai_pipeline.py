#!/usr/bin/env python3
"""南锣鼓巷＋什刹海本地资料包：沿用宛平城的模型、V3与slim审计。

仅写来源文件、结果文件和llm_call缓存，不登记生产馆、不重灌业务表。
信息整理模型只看到已保存官方原文；评分和审计不允许使用工具补证据。
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import audit_bc_guard as bc
import audit_meta as audit
import codex_cli
import llm_cache
import tier_v3 as tier

HERE=Path(__file__).resolve().parent
KEY='nanluo_shichahai'
CONTEXT=('北京市旧城北部的南锣鼓巷与什刹海地区。南锣鼓巷清单包含主街、16条支巷及名人旧居、'
         '王府和四合院；什刹海包含前海、后海、西海及沿岸寺观、桥梁、王府、纪念馆。'
         '钟鼓楼、德胜门箭楼和护国寺街故居作为标明的周边衔接。恭王府包含官网介绍的府邸及花园节点。'
         '整体、组成部分、历史原址、现存建筑、现代改造项目分别识别；清单不是互不重叠的路线站点。'
         '街巷仍有居住、学校和其他使用功能，资料中的历史用途不代表今日允许入内。语境只限定范围，不预设评级。')

def load(name):return json.loads((HERE/name).read_text('utf-8'))
def dump(name,obj):
    p=HERE/name;t=p.with_suffix(p.suffix+'.new')
    t.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');t.replace(p)
def sha(name):return hashlib.sha256((HERE/name).read_bytes()).hexdigest()
def norm(s):return re.sub(r'\s+','',s)
def evidence_sha(source):return source.get('raw_sha256') or source['snapshot_sha256']
def retrieval(source):return source.get('retrieval_method','verified_HTTP_extracted_text')

def setup():
    if llm_cache._connect() is None:raise RuntimeError('LLM缓存不可用，禁止实调')
    import claude_cli
    # 先留存provider返回，再做缓存校验，避免校验失败时付费答案也一起丢失。
    def instrument(module,provider):
        ask=module.ask
        def recorded(*a,**kw):
            result,usage=ask(*a,**kw)
            system=kw.get('system',a[0] if len(a)>0 else '')
            user=kw.get('user',a[1] if len(a)>1 else '')
            schema=kw.get('schema',a[2] if len(a)>2 else {})
            model=kw.get('model',a[3] if len(a)>3 else '')
            effort=kw.get('effort',a[4] if len(a)>4 else '')
            tier.append(HERE/(KEY+'_provider_responses.jsonl'),dict(provider=provider,model=model,effort=effort,system_sha256=hashlib.sha256(system.encode()).hexdigest(),user_sha256=hashlib.sha256(user.encode()).hexdigest(),schema=schema,response=result,usage=usage))
            return result,usage
        module.ask=recorded
    instrument(codex_cli,'openai_codex');instrument(claude_cli,'anthropic_cli')
    original=llm_cache.call
    def no_retry(*a,**kw):
        kw['retries']=0
        result=original(*a,**kw)
        key=llm_cache.cache_key(kw['provider'],kw['model'],kw.get('effort'),kw['system'],kw['user'],kw['schema'])
        tier.append(HERE/(KEY+'_llm_responses.jsonl'),dict(cache_key=key,provider=kw['provider'],model=kw['model'],effort=kw.get('effort'),stage=kw['stage'],response=result))
        with llm_cache._connect().cursor() as c:
            c.execute('SELECT id FROM llm_call WHERE cache_key=%s',(key,))
            if not c.fetchone():raise RuntimeError('本次成功答案未写入缓存，已本地留存，停止后续调用')
        return result
    llm_cache.call=no_retry
    tier.CODEX_CLI=('gpt-5.6-luna',dict(tier.STAGE_EFFORT))
    tier.MODEL='gpt-5.6-luna effort=high/medium/xhigh (codex-cli)'
    audit.CLAUDE_CLI='claude-sonnet-5'

def candidates():
    rows=load(KEY+'_candidates.json')['rows']
    if len({r['identity_key'] for r in rows})!=len(rows):raise ValueError('候选身份键重复')
    p=HERE/(KEY+'_seq_map.csv');mapping={}
    if p.exists():
        with p.open(encoding='utf-8',newline='') as f:mapping={r['identity_key']:int(r['source_seq']) for r in csv.DictReader(f)}
    for r in rows:
        if r['identity_key'] not in mapping:mapping[r['identity_key']]=max(mapping.values(),default=0)+1
        r['source_seq']=mapping[r['identity_key']]
    if len(set(mapping.values()))!=len(mapping):raise ValueError('序号重复')
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['identity_key','source_seq']);w.writerows(sorted(mapping.items(),key=lambda p:p[1]))
    return rows

def source_context(source,anchor):
    text=source['text']
    if len(text)<=2500:return text
    hits=[m.start() for m in re.finditer(re.escape(anchor),text)]
    if not hits:return text
    # 所有命中取上下文，合并重叠区间；原始全文在capture内，不被截断覆盖。
    intervals=[]
    for p in hits:
        start=max(0,p-100);end=min(len(text),p+1500)
        if intervals and start<=intervals[-1][1]:intervals[-1][1]=max(end,intervals[-1][1])
        else:intervals.append([start,end])
    return '\n[以下为同一原文另一处]\n'.join(text[a:b] for a,b in intervals)

def extract(max_batches=0):
    rows=candidates();sources={s['id']:s for s in load(KEY+'_source_capture.json')['sources'] if s['status']=='ok'}
    done=tier.read_done(HERE/(KEY+'_information.jsonl'))
    system=('你是文化遗产与街区经营节点资料整理员。只依据逐条附上的已保存来源，不用模型记忆补事实，不调用工具。'
            '为每个指定对象整理中文简介和资料说明；用自己的措辞简述，不大段照抄。简介约120–350字，资料薄时如实简短。'
            '仅概述指定对象，不把周边场所事实搬给本条。每条至少一条可逐字核对的短引文（10–50字，连续原文，不加省略号），'
            'source_id必须选该条输入中的来源。不得把原始整体图、地址、开放时间代理为内部节点信息。'
            '不消解来源冲突：历史年份、建筑保存、尺寸、原件/复制品等有矛盾时分别说明来源；传说保留“据传”。'
            '官方旧文原有错误照实呈现并写入资料说明，不悄悄替其改正。当前开放不能从历史报道推断。'
            '商铺资料包括文旅报道、平台商户页及索引摘录，逐条区分取得方式；点评用户推荐和平台评分不是官方历史认定。'
            '只整理指定分店；品牌创立年不当作本分店或现存建筑年代，其他门店的菜单、奖项、手作活动不可移植。'
            '索引遮挡或未列的门牌、营业时间留未知；不能把“休息中”理解为永久停业，也不能把页面存续说成当天营业。'
            'description为AI整理，不冒充官方原文。editor_note补充资料边界，不给价值评级，不暗示重要性。'
            '确实没有对应身份来源时supported=false、description留空、evidence为空，明确写原因。所有seq恰返一次。')
    completed_batches=0
    for start in range(0,len(rows),8):
        part=[r for r in rows[start:start+8] if r['source_seq'] not in done]
        if not part:continue
        packet=[]
        for r in part:
            refs=[dict(source_id=sid,url=sources[sid]['url'],text=source_context(sources[sid],r['anchor']),source_kind=sources[sid].get('source_kind','official_page'),retrieval_method=retrieval(sources[sid])) for sid in r['source_ids'] if sid in sources]
            packet.append(dict(seq=r['source_seq'],name=r['name'],parent_key=r['parent_key'],type_hint=r['object_type_hint'],editorial_boundary=r['editor_note'],sources=refs))
        seqs=[r['source_seq'] for r in part]
        string={'type':'string'}
        ev={'type':'object','properties':{'source_id':string,'quote':string},'required':['source_id','quote'],'additionalProperties':False}
        item={'type':'object','properties':{'seq':{'type':'integer','enum':seqs},'supported':{'type':'boolean'},'description':string,'editor_note':string,'evidence':{'type':'array','items':ev}},'required':['seq','supported','description','editor_note','evidence'],'additionalProperties':False}
        schema={'type':'object','properties':{'items':{'type':'array','items':item}},'required':['items'],'additionalProperties':False}
        user=json.dumps(packet,ensure_ascii=False)
        def request():
            result,usage=codex_cli.ask(system,user,schema,'gpt-5.6-luna','medium')
            return result,codex_cli.Usage(usage)
        def validate(d):
            returned=[r['seq'] for r in d.get('items',[])]
            if sorted(returned)!=sorted(seqs):raise ValueError('信息整理漏返或重复序号')
            return True
        result=llm_cache.call(request,provider='openai_codex',model='gpt-5.6-luna',effort='medium',stage='source_information',museum_key=KEY,seqs=seqs,scope=f'{seqs[0]}–{seqs[-1]}',system=system,user=user,schema=schema,validate=validate)
        for r in result['items']:
            target=next(t for t in part if t['source_seq']==r['seq'])
            good=[];rejected=[]
            for e in r['evidence']:
                sid=e['source_id']
                if sid in target['source_ids'] and sid in sources and len(norm(e['quote']))>=8 and norm(e['quote']) in norm(sources[sid]['text']):good.append(e)
                else:rejected.append(e)
            # 保留原始答案及未通过的引文，禁止将无法核对的摘录当证据。
            r['evidence_raw']=r['evidence'];r['evidence']=good;r['rejected_evidence']=rejected
            if r['supported'] and (not good or not r['description'].strip()):r['supported']=False;r['support_failure']='缺可逐字核对引文或简介'
            tier.append(HERE/(KEY+'_information.jsonl'),r);done[r['seq']]=r
        print('information',seqs,'supported',sum(x['supported'] for x in result['items']),flush=True)
        completed_batches+=1
        if max_batches and completed_batches>=max_batches:
            print('batch_limit_reached',max_batches,flush=True);return
    build()

def build():
    rows=candidates();info=tier.read_done(HERE/(KEY+'_information.jsonl'))
    sources={s['id']:s for s in load(KEY+'_source_capture.json')['sources'] if s['status']=='ok'}
    wanted={r['source_seq'] for r in rows}
    if set(info)!=wanted:raise ValueError('信息整理未完整覆盖候选')
    final=[];pending=[]
    for r in rows:
        data=info[r['source_seq']]
        if not data['supported']:
            pending.append(dict(r,reason=data.get('support_failure') or data['editor_note']));continue
        evidence=[]
        for e in data['evidence']:
            s=sources[e['source_id']]
            ref=dict(e,url=s['url'],retrieval_method=retrieval(s),source_context=source_context(s,r['anchor']),source_sha256=evidence_sha(s))
            if 'source_kind' in s:ref.update(source_kind=s['source_kind'],source_tier=s.get('source_tier'),confidence=s.get('confidence'))
            evidence.append(ref)
        final.append(dict(r,description=data['description'],editor_note=r['editor_note']+'\n'+data['editor_note'],evidence=evidence,
                          description_source=('gpt-5.6-luna medium依据保存的文旅与平台资料整理；不是商户官方逐字介绍' if r.get('entry_kind') else 'gpt-5.6-luna medium依据保存官方网页整理；不是官方逐字原文'),status=('平台/文旅网页有记录；现场营业、菜单、价格及体验项目未实时核实' if r.get('entry_kind') else '当前开放未核实；历史安排不作实时承诺'),image_url=None,coordinates=None))
    if not final or len(final)<0.85*len(rows):raise ValueError('有来源的条目填充率不足85%，先解决来源身份，禁止评分')
    accepted={r['identity_key'] for r in final}
    for r in final:
        if r['parent_key'] and r['parent_key'] not in accepted:raise ValueError('父节点缺失：'+r['identity_key'])
    data=dict(museum_key=KEY,name='北京南锣鼓巷及什刹海',collected_on='2026-10-23',scope=load(KEY+'_candidates.json')['scope'],
              models={'information':'gpt-5.6-luna effort=medium (codex-cli)','rating':'gpt-5.6-luna high/medium/xhigh (codex-cli)','audit':'claude-sonnet-5 effort=medium (claude-cli), slim'},
              capture_sha256=sha(KEY+'_source_capture.json'),information_sha256=sha(KEY+'_information.jsonl'),rows=final,pending=pending,state='来源资料已整理，未入生产业务表')
    dump(KEY+'_site_data.json',data)
    print('source_check',len(final),'accepted',len(pending),'pending','types',dict(Counter(r['object_type_hint'] for r in final)),flush=True)

def inputs():
    data=load(KEY+'_site_data.json');rows=data['rows']
    items=[dict(seq=r['source_seq'],name_en='',name_cn=r['name'],gallery='',category=r['object_type_hint']+'·'+r['area'],description=r['description']+'\n资料说明：'+r['editor_note'],tier_old='') for r in rows]
    evidence={r['source_seq']:'\n\n'.join(('['+e.get('source_kind','official_page')+' · 已保存网页/索引快照，平台评价不是官方历史认证; '+e['url']+']\n' if 'source_kind' in e else '[FACT · 已保存官方网页原文; '+e['url']+']\n')+e['source_context'] for e in r['evidence']) for r in rows}
    return data,items,evidence,sha(KEY+'_site_data.json')

def group_peers():
    data,_,_,source_sha=inputs();s1=tier.read_done(HERE/(KEY+'_stage1.jsonl'))
    if set(s1)!={r['source_seq'] for r in data['rows']}:raise ValueError('阶段一尚未完成')
    # 增补商铺时保留旧84条已固定的同类组；仅为新增对象定组，再按完整人口跑CR。
    snapshot=HERE/(KEY+'_v1_snapshot.json')
    if snapshot.exists() and len(s1)>84:
        before=json.loads(load(snapshot.name)['files'][KEY+'_peer_groups.json']['text'])
        fixed=before['groups'];todo=[r for r in data['rows'] if str(r['source_seq']) not in fixed]
        seqs=[r['source_seq'] for r in todo]
        system=('沿用既有V3.0“本地同类对象相互比较”的定义，为新增的具体经营门店统一同类组。'
                '旧条目的分组已经固定，只返回新增seq；按对象形态、功能和业态分组，等义组名统一，不按评分、资料长短或分批拆组。'
                '新商铺如与旧组性质相同可以使用旧组名；餐饮、纸品工艺零售、咖啡休憩、邮政文化体验等依其性质区分，不与街区整体或历史建筑混成一个组。'
                '不要改评分、类型或旧对象分组。所有指定seq恰返一次。')
        user=json.dumps(dict(fixed_groups=sorted(set(fixed.values())),new_items=[dict(seq=r['source_seq'],name=r['name'],object_type=s1[r['source_seq']]['object_type'],shop_kind=r.get('shop_kind'),peer_group_raw=s1[r['source_seq']]['peer_group']) for r in todo]),ensure_ascii=False)
        item={'type':'object','properties':{'seq':{'type':'integer','enum':seqs},'peer_group':{'type':'string'}},'required':['seq','peer_group'],'additionalProperties':False}
        schema={'type':'object','properties':{'items':{'type':'array','items':item},'reason':{'type':'string'}},'required':['items','reason'],'additionalProperties':False}
        def request():
            d,u=codex_cli.ask(system,user,schema,'gpt-5.6-luna','medium');return d,codex_cli.Usage(u)
        def valid(d):return sorted(x['seq'] for x in d['items'])==seqs and all(x['peer_group'].strip() for x in d['items'])
        result=llm_cache.call(request,provider='openai_codex',model='gpt-5.6-luna',effort='medium',stage='peer_groups_extension',museum_key=KEY,seqs=seqs,scope='extend fixed v1 groups for all new merchant nodes before full CR',system=system,user=user,schema=schema,validate=valid)
        groups=dict(fixed);groups.update({str(x['seq']):x['peer_group'] for x in result['items']})
        proposed=dict(groups);adjustments=[]
        review_path=HERE/(KEY+'_shops_group_review.json')
        if review_path.exists():
            reviewed=load(review_path.name)
            if reviewed['input_sha256']!=source_sha:raise ValueError('商铺分组复核输入已变')
            adjustments=reviewed['adjustments']
            for change in adjustments:
                s=str(change['seq'])
                if groups[s]!=change['before']:raise ValueError('模型原始分组与复核记录不一致')
                groups[s]=change['after']
        types={}
        for seq,group in groups.items():types.setdefault(group,set()).add(s1[int(seq)]['object_type'])
        if any(len(t)>1 for t in types.values()):raise ValueError('新增分组混合了不同object_type')
        dump(KEY+'_peer_groups.json',dict(input_sha256=source_sha,stage1_sha256=sha(KEY+'_stage1.jsonl'),model='gpt-5.6-luna effort=medium (codex-cli)',state='旧84条分组保持；新增门店模型提议后按功能复核；未标为用户逐组审定',previous_groups_sha256=load(snapshot.name)['files'][KEY+'_peer_groups.json']['sha256'],reason=result['reason'],groups=groups,groups_model_raw=proposed,review_adjustments=adjustments))
        print('peer_groups_extended',len(groups),'groups',len(set(groups.values())),flush=True);return
    packet=[dict(seq=r['source_seq'],name=r['name'],object_type=s1[r['source_seq']]['object_type'],parent_key=r['parent_key'],original_peer_group=s1[r['source_seq']]['peer_group']) for r in data['rows']]
    system=('按照既有V3.0阶段二“同馆或本地同类对象相互比较”的含义，检查全量条目的同类组名称。'
            '当前阶段一分批命名，等义组名可能不同。统一这类重复组名，让同类对象进入同一个比较组，不按批次划界。'
            '保持不同object_type分开，整体和组成节点不混组。按对象的性质、形态、功能判断同类，不按评级、分数或资料长短分组；本任务不提供分数。'
            '不必把不同性质的遗产强行归为一组，也不必因相同类型对象位于不同胡同或不同片区就拆组。'
            '不改seq、名称、对象类型或评分，只返每个seq的统一peer_group。所有seq恰返一次。')
    seqs=sorted(s1)
    item={'type':'object','properties':{'seq':{'type':'integer','enum':seqs},'peer_group':{'type':'string'}},'required':['seq','peer_group'],'additionalProperties':False}
    schema={'type':'object','properties':{'items':{'type':'array','items':item},'reason':{'type':'string'}},'required':['items','reason'],'additionalProperties':False}
    user=json.dumps(packet,ensure_ascii=False)
    def request():
        d,u=codex_cli.ask(system,user,schema,'gpt-5.6-luna','medium');return d,codex_cli.Usage(u)
    def validate(d):
        if sorted(r['seq'] for r in d.get('items',[]))!=seqs:return False
        types={}
        for r in d['items']:
            if not r['peer_group'].strip():return False
            types.setdefault(r['peer_group'],set()).add(s1[r['seq']]['object_type'])
        return all(len(v)==1 for v in types.values())
    result=llm_cache.call(request,provider='openai_codex',model='gpt-5.6-luna',effort='medium',stage='peer_groups',museum_key=KEY,seqs=seqs,scope='full population; normalize stage1 group labels before CR',system=system,user=user,schema=schema,validate=validate)
    dump(KEY+'_peer_groups.json',dict(input_sha256=source_sha,stage1_sha256=sha(KEY+'_stage1.jsonl'),model='gpt-5.6-luna effort=medium (codex-cli)',state='模型全量统一同类组；未标作用户逐组审定',reason=result['reason'],groups={str(r['seq']):r['peer_group'] for r in result['items']}))
    print('peer_groups',len(set(r['peer_group'] for r in result['items'])),result['reason'],flush=True)

def score(stage,smoke=False):
    data,items,evidence,source_sha=inputs()
    if smoke:items=[r for r in items if r['seq'] in [1,18,63]]
    m=SimpleNamespace(key=KEY,context=CONTEXT)
    prefix=KEY+('_smoke' if smoke else '')
    manifest=HERE/(prefix+'_input_manifest.json')
    if manifest.exists() and load(manifest.name)['input_sha256']!=source_sha:raise ValueError('输入变动，禁止沿用旧评分JSONL')
    dump(manifest.name,dict(input_sha256=source_sha,model=tier.MODEL,seqs=[r['seq'] for r in items]))
    p1=HERE/(prefix+'_stage1.jsonl');p2=HERE/(prefix+'_stage2.jsonl');p3=HERE/(prefix+'_stage3.jsonl')
    s1=tier.stage1(None,m,items,p1,12,evidence)
    if stage=='tier1':
        print('stage1_complete',len(s1),'groups',dict(Counter(r['peer_group'] for r in s1.values())),flush=True);return
    policy=HERE/(KEY+'_peer_groups.json')
    if policy.exists():
        pol=load(policy.name)
        if pol['input_sha256']!=source_sha:raise ValueError('同类组对应的输入版本已变')
        m.peer_merge={int(k):v for k,v in pol['groups'].items()}
        if set(m.peer_merge)!=set(s1):raise ValueError('同类组未逐件完整覆盖')
        s1=tier.apply_peer_merge(m,s1)
    # 已确认的同姓对象混淆：只修正包含两人的CR请求，其他组的已付费答案保持可复用。
    original_stage2_user=tier.stage2_user
    def identity_checked_user(museum,group,seqs,by_seq,stage1,evidence_rows):
        user=original_stage2_user(museum,group,seqs,by_seq,stage1,evidence_rows)
        if 45 in seqs and 48 in seqs:
            user+='\n\n身份核对：seq45为郭守敬纪念馆（汇通祠），对应元代郭守敬、天文历法与城市水利；seq48为郭沫若纪念馆（郭沫若故居），对应近现代郭沫若、文学史学及故居生活。两者不是同一人或同一馆。此前seq48的CR理由误贴了郭守敬的科学水利叙事，本次须依据各自原文重新比较，逐条核对seq、姓名和理由；不预设分数或档位。'
        return user
    tier.stage2_user=identity_checked_user
    s2=tier.stage2(None,m,items,s1,p2,evidence)
    cr={s:0.5*r['Q']+0.3*r['D']+0.2*r['G'] for s,r in s2.items()}
    cores={s:tier.core_of(r,cr[s]) for s,r in s1.items()}
    cands=[s for s in cores if cores[s]>=8.5 and max(float(s1[s][d]) for d in tier.DIMS_WITH_ER if d in s1[s])>=9]
    s3=tier.stage3(None,m,items,cands,s1,cores,p3,evidence)
    results=[]
    for it in items:
        s=it['seq'];r=s1[s];t,reason=tier.tier_of(cores[s],r,s3.get(s))
        if t=='S' and r['confidence']=='low':t='A';reason+='；证据可信度low不得直接定S'
        results.append(dict(r,name=it['name_cn'],CR=cr[s],core=cores[s],tier=t,tier_reason=reason,cr_reason=s2[s]['cr_reason'],sness_reason=s3.get(s,{}).get('sness_reason','')))
    dump(prefix+'_ratings.json',dict(input_sha256=source_sha,model=tier.MODEL,grouping_sha256=sha(policy.name) if policy.exists() else None,results=results))
    with (HERE/(prefix+'_review.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        fields=['seq','name','object_type','peer_group','HS','IU','VI','VA','CE','ER','CR','core','tier','tier_reason','confidence','evidence','cr_reason','sness_reason']
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(results)
    print('ratings',len(results),dict(Counter(r['tier'] for r in results)),flush=True)

def run_audit(smoke=False,prepare_only=False):
    prefix=KEY+('_smoke' if smoke else '')
    data,_,_,source_sha=inputs();scored=load(prefix+'_ratings.json')
    if scored['input_sha256']!=source_sha:raise ValueError('评分输入已变')
    ratings={r['seq']:r for r in scored['results']};items=[];audit_sources=[]
    if smoke:data['rows']=[r for r in data['rows'] if r['source_seq'] in ratings]
    captured={s['id']:s for s in load(KEY+'_source_capture.json')['sources'] if s['status']=='ok'}
    for r in data['rows']:
        s=r['source_seq'];v=ratings[s]
        # 审计看到已关联的全部原文，不受信息整理模型选择了哪条短引文的限制。
        # 戏楼另给馆方转载的2019年媒体文章，与2014年景点页的面积口径独立对照。
        ids=list(dict.fromkeys(r['source_ids']+(['gongwang_history'] if r['identity_key']=='gongwang_theatre' else [])))
        refs=[dict(source_id=sid,url=captured[sid]['url'],source_context=captured[sid]['text'],source_sha256=evidence_sha(captured[sid]),retrieval_method=captured[sid].get('retrieval_method','verified_HTTP_extracted_full_text'),source_kind=captured[sid].get('source_kind','official_page'),confidence=captured[sid].get('confidence','high')) for sid in ids if sid in captured]
        audit_sources.append(dict(seq=s,evidence=refs))
        items.append(dict(seq=s,name_en='',name_zh=r['name'],gallery='',category=r['object_type_hint'],description=r['description']+'\n编者说明：'+r['editor_note'],tier=v['tier'],v3=v,
                          meta=[dict(key='来源文本引用（'+e['source_kind']+'；'+e['retrieval_method']+'）',text='见本批共享来源索引 ['+e['source_id']+'] 的已保存文本；只使用与本对象身份对应的事实。索引摘录不冒充全文，平台评价不作官方认定。',source_key=e['source_id'],source=e['url'],confidence=e['confidence']) for e in refs],conf={},src_tier=None,missing=None))
    note=(f'本批{len(items)}条；来自本轮保存的北京市政府、东城/西城政府、文物局、文旅部门和恭王府官网。'
          '简介由gpt-5.6-luna依据来源整理，metadata注明原文或索引的取得方式，须核对整理内容是否忠实，不只检查来源内部矛盾。'
          '历史报道、展陈旧版本和现在开放是不同信息。多来源冲突保留，不当作已解决。'
          '没有现场坐标、完整图片、逐件馆藏号或所有私人宅院的进入权限；本轮是本地资料包，未生产登记。'
          '审计另见已关联的全部原文，含整理模型未选作短引文的来源；戏楼增加馆方转载的旧媒体文章对照。该补充不冒充已经重评分。'
          '本轮另有特色商铺，来源含大众点评商户页、网页工具返回文本和索引摘录，均注明取得方式；不把平台星级当V3评级，不能将品牌历史、其他分店地址或菜单移植到指定门店。'
          '以下共享来源索引是本批条目引用的全部已保存文本；每篇只放一次，条目metadata中的source_id与索引对应。'
          '完整网页可能含导航或同文中的其他地点，须按条目身份和父子关系核对，不把别处的事实搬到本条。')
    dump(prefix+'_audit_source_data.json',dict(input_sha256=source_sha,capture_sha256=sha(KEY+'_source_capture.json'),rows=audit_sources))
    # 同一官方长文会支持多个胡同/建筑。每批放一次完整正文，避免反复复制上下文，
    # 保留全文比按命中处截取更利于发现原文自身的矛盾；模型、判据和48件批次不变。
    out=HERE/(prefix+'_audit1_slim.jsonl');completed=audit.read_done(out)
    binding_path=HERE/(KEY+'_audit_resume_binding.json')
    if binding_path.exists() and not smoke:
        binding=load(binding_path.name)
        if binding['input_sha256']!=source_sha or binding['current_rating_sha256']!=sha(prefix+'_ratings.json'):raise ValueError('复用审计的评级版本已变')
        for rec in binding['reused_records']:
            s=rec['seq']
            actual=hashlib.sha256(json.dumps(completed[s],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if actual!=rec['audit_record_sha256']:raise ValueError('复用的审计记录已变：'+str(s))
    pending=[it for it in items if it['seq'] not in completed]
    packets=[];refmap={r['seq']:r['evidence'] for r in audit_sources}
    for start in range(0,len(pending),48):
        chunk=pending[start:start+48]
        ids=list(dict.fromkeys(e['source_id'] for it in chunk for e in refmap[it['seq']]))
        shared='\n\n'.join('['+sid+'] '+captured[sid]['url']+'；取得方式：'+retrieval(captured[sid])+'；类型：'+captured[sid].get('source_kind','official_page')+'\n'+captured[sid]['text'] for sid in ids)
        packets.append(dict(seqs=[it['seq'] for it in chunk],source_ids=ids,note=note+'\n\n共享来源索引：\n'+shared))
    if packets:dump(prefix+'_audit_packets.json',dict(input_sha256=source_sha,mode='shared_saved_source_text_once_per_48_items',packets=packets))
    if prepare_only:
        print('audit_prepared',len(items),'packets',[(len(p['seqs']),len(p['source_ids']),len(p['note'])) for p in packets],flush=True)
        return
    results=completed
    for packet in packets:
        chunk=[it for it in items if it['seq'] in packet['seqs']]
        results=audit.stage1_slim(None,'claude-sonnet-5','medium',CONTEXT,packet['note'],chunk,out,48,KEY)
    changed=0
    for s,r in results.items():
        if ratings[s]['tier'] not in {'B','C'}:continue
        for x in r['missing']:
            if x['tier_sensitive'] and not bc.could_reach_as(x['zh']):x.setdefault('tier_sensitive_raw',True);x['tier_sensitive']=False;changed+=1
    (HERE/(prefix+'_audit1_slim.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results.values()),encoding='utf-8')
    dump(prefix+'_audit_manifest.json',dict(input_sha256=source_sha,rating_sha256=sha(prefix+'_ratings.json'),audit_source_sha256=sha(prefix+'_audit_source_data.json'),audit_packets_sha256=sha(prefix+'_audit_packets.json'),source_packaging='shared_saved_source_text_once_per_48_items',model='claude-sonnet-5 effort=medium (claude-cli)',mode='slim',count=len(results),bc_guard_downgraded=changed,
         reused_audit_binding_sha256=sha(binding_path.name) if binding_path.exists() and not smoke else None,
         factual_errors=[s for s,r in results.items() if r['found_factual_error']],review=[s for s,r in results.items() if r['found_factual_error'] or any(x['tier_sensitive'] for x in r['missing'])]))
    print('audit_complete',len(results),'facts',[s for s,r in results.items() if r['found_factual_error']],flush=True)

def translate():
    import translate_artwork as trans
    data,_,_,source_sha=inputs();name=KEY+'_translations.json'
    translated=load(name) if (HERE/name).exists() else dict(input_sha256=source_sha,model='gpt-5.6-luna',effort='medium',source='AI翻译',values={})
    if translated['input_sha256']!=source_sha:raise ValueError('翻译来源版本已变化')
    for kind,what in [('name','名称'),('display_name','展示名称'),('description','简介'),('editor_note','资料说明'),('shop_kind','商铺业态'),('address','地址与来源说明'),('specialty','商铺特色')]:
        todo=list(dict.fromkeys(r[kind] for r in data['rows'] if r.get(kind) and r[kind] not in translated['values']))
        for start in range(0,len(todo),35):
            part=todo[start:start+35];system=trans.SYS_ZH2EN.format(what=what)
            user='逐条译成英文，共 %d 条：\n'%len(part)+'\n'.join(f'[{i}] {t}' for i,t in enumerate(part))
            schema=trans.SCHEMA_OF['zh2en']
            def request():
                d,u=codex_cli.ask(system,user,schema,'gpt-5.6-luna','medium');return d,codex_cli.Usage(u)
            def validate(d):
                if sorted(x['i'] for x in d['items'])!=list(range(len(part))):raise ValueError('译文索引不完整')
                if not all(x['en'].strip() for x in d['items']):raise ValueError('译文为空')
                return True
            result=llm_cache.call(request,provider='openai_codex',model='gpt-5.6-luna',effort='medium',stage='trans_artwork_local_'+kind,museum_key=KEY,scope=f'{kind} {start}–{start+len(part)}',system=system,user=user,schema=schema,validate=validate)
            for x in result['items']:translated['values'][part[x['i']]]=dict(en=x['en'],confidence=x['confidence'],source='AI翻译')
            dump(name,translated);print('translated',kind,start+len(part),'/',len(todo),flush=True)
    with (HERE/(KEY+'_translations.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['zh-CN','en','confidence','source','model','effort','revision'])
        for zh,r in translated['values'].items():w.writerow([zh,r['en'],r['confidence'],'AI翻译','gpt-5.6-luna','medium',r.get('revision','')])

def translate_audit():
    import audit_translate
    # 与宛平城相同入口：翻译走Codex，审计本身仍是Claude。
    ask=audit.ask
    def explicit_effort(client,model,system,user,name,schema,effort=None,**kw):
        return ask(client,model,system,user,name,schema,effort or 'medium',**kw)
    audit.ask=explicit_effort
    import sys
    sys.argv=['audit_translate.py','--museum',KEY,'--out-dir',str(HERE),'--provider','codex_cli','--model','gpt-5.6-luna','--size','100']
    audit_translate.main()

def repair_translations():
    """仅对已识别译文问题作确定性更正；不重试已失败的模型修订请求。"""
    name=KEY+'_translations.json';d=load(name);changes=[]
    substitutions={
        '蜗蜗居':'Wowoju', '整理ates':'summarizes', '整理ed':'summarized', '南锣鼓巷2******':'Nanluoguxiang 2******', '“凸”-shaped':'stepped and projecting',
        '静含太古':'Jing han tai gu', '秀挹恒春':'Xiu yi heng chun',
        '同德延釐':'Tong de yan xi', '棣华轩':'Dihua Xuan',
        '“子”':'“zi (children)”', '“才”':'“cai (talent)”', '“寿”':'“shou (longevity)”',
        '“田”':'“tian (fields)”', '“福”':'“fu (blessings)”', '“乐峰”':'“Le Feng”', '“独”':'“Du”',
        'Baoji Street':'Baojia Street', 'Yao’er Hutong':'Ya’er Hutong',
        'two two-story halls remain on the eastern route':'a two-storey hall remains on the eastern route',
        'Dicu Rock':'Dicui Rock', 'Yinan Hall':'Yin’an Hall',
        'Prince Tao’s Residence':'Beile Zaitao’s Residence', 'Prince Tao Zai Tao':'Beile Zaitao',
        '子':'zi (children)', '才':'cai (talent)', '寿':'shou (longevity)', '田':'tian (fields)',
    }
    for z,r in d['values'].items():
        before=r['en'];after=before
        for old,new in substitutions.items():after=after.replace(old,new)
        if '德胜门箭楼位于' in z and '坐南朝北' in z:
            after=after.replace('The arrow tower faces south','The arrow tower faces north')
            after=after.replace('Its roof is a green-glazed tile roof with double eaves and a hip-and-gable form, edged with glazed tiles.','It has a double-eaved hip-and-gable roof with green-glazed tile edging.')
        if '蒋介石北平行辕旧址即' in z and '坐北朝南' in z:
            after=after.replace('oriented north–south','facing south')
        if before!=after:
            r['en']=after;r['revision']='Codex依给定中文作专名、方位、混字及铭文转写的确定性校正；无新增模型调用'
            changes.append(dict(zh=z,before=before,after=after))
    residual=[z for z,r in d['values'].items() if re.search(r'[\u3400-\u9fff]',r['en'])]
    if residual:raise ValueError('仍有汉字残留，先核对：'+str(residual))
    if not changes:print('translation_repair:no_new_changes');return
    dump(name,d)
    previous=load(KEY+'_translation_repair.json') if (HERE/(KEY+'_translation_repair.json')).exists() else {}
    all_changes=previous.get('changes',[])+changes
    runs=previous.get('revision_runs',[])+[dict(input_sha256=d['input_sha256'],new_changes=len(changes))]
    dump(KEY+'_translation_repair.json',dict(original_model='gpt-5.6-luna medium',revision_method='Codex依据已保存中文与原译文作确定性词句校正，不冒充人工校对或新的Luna输出',failed_model_repair=dict(call_id=3872,reason='初版返回未通过校验，原响应未被旧llm_cache保存，未重试；错误行保留，不能反推具体缺陷或完整token用量'),changes=all_changes,revision_runs=runs))
    with (HERE/(KEY+'_translations.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['zh-CN','en','confidence','source','model','effort','revision'])
        for zh,r in d['values'].items():w.writerow([zh,r['en'],r['confidence'],'AI翻译','gpt-5.6-luna','medium',r.get('revision','')])
    print('translation_repair_complete',len(changes),'zero additional calls',flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['extract','build','smoke','smoke-audit','tier1','groups','tier','audit','audit-prepare','translate','translation-repair','audit-translate'])
    ap.add_argument('--batches',type=int,default=0,help='信息整理本次最多新增几批，0为全部')
    args=ap.parse_args()
    if args.stage=='build':build();return
    if args.stage=='translation-repair':repair_translations();return
    if args.stage=='audit-prepare':run_audit(prepare_only=True);return
    setup()
    if args.stage=='extract':extract(args.batches)
    elif args.stage=='groups':group_peers()
    elif args.stage=='smoke':score('tier',True)
    elif args.stage in {'tier','tier1'}:score(args.stage)
    elif args.stage=='audit':run_audit()
    elif args.stage=='smoke-audit':run_audit(True)
    elif args.stage=='translate':translate()
    else:translate_audit()

if __name__=='__main__':main()
