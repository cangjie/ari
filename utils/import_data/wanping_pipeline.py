#!/usr/bin/env python3
"""对宛平城本地来源清单复用现有 V3 与 slim 审计，不改生产业务数据。

模型、档位、评分权重、S-ness、审计提示词与 B/C 兜底均沿用原管线。
读写 llm_call 缓存；逐次调用失败即停，不自动重试。长任务还应套 llm_guard.py。
这是本地资料适配器，不代表已经执行标准登记、metadata 入库或线上接入。
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import audit_bc_guard as bc
import audit_meta as audit
import llm_cache
import tier_v3 as tier

HERE = Path(__file__).resolve().parent
CONTEXT = ('宛平城及周边主要参观点，位于北京市丰台区永定河畔。范围包括宛平城、卢沟桥、'
           '中国人民抗日战争纪念馆、中国人民抗日战争纪念雕塑园。宛平城为明代卫城，'
           '卢沟桥始建于金代；两者与1937年七七事变相关。城内有复建建筑与现代展陈，'
           '抗战馆基本陈列于2025年改陈。清单包含遗产地整体、建筑与展陈节点、碑刻和雕塑，'
           '父子节点之间有包含关系，不能视为互不重叠的站点。语境只限定对象与资料范围。')

def dump(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def setup():
    # 先确认能记账，再发任何请求；禁止缓存故障静默退化为实调。
    if llm_cache._connect() is None:raise RuntimeError('LLM缓存不可用，停止调用')
    original=llm_cache.call
    def no_retry(*a,**kw):
        kw['retries']=0
        return original(*a,**kw)
    llm_cache.call=no_retry
    tier.CODEX_CLI=('gpt-5.6-luna',dict(tier.STAGE_EFFORT))
    tier.MODEL='gpt-5.6-luna effort=high/medium/xhigh (codex-cli)'
    audit.CLAUDE_CLI='claude-sonnet-5'

def load():
    p=HERE/'wanping_site_data.json'
    data=json.loads(p.read_text('utf-8'))
    rows=data['rows']
    items=[dict(seq=r['source_seq'],name_en='',name_cn=r['name'],gallery='',
                category=r['object_type_hint']+('·复建建筑' if '复建' in r['editor_note'] and r['identity_key'] in {'county_office','post_station','xinglong_temple','gongji_camp'} else ''),
                description=r['description'],tier_old='') for r in rows]
    # 逐字出处只作来源资料，编者的风险说明不冒充已核实事实。
    evidence={r['source_seq']:'\n'.join('[FACT · 官方发布（未作来源等级映射）; '+e['retrieval_method']+'] '+e['url']+'\n'+e['quote'] for e in r['evidence']) for r in rows}
    return data,items,evidence,hashlib.sha256(p.read_bytes()).hexdigest()

def score(smoke=False, grouped=False):
    data,items,evidence,sha=load()
    if smoke:
        items=[x for x in items if x['seq'] in {1,2,16}]
    m=SimpleNamespace(key='wanping',context=CONTEXT)
    prefix='wanping_grouped' if grouped else ('wanping_smoke' if smoke else 'wanping')
    manifest=HERE/f'{prefix}_input_manifest.json'
    if manifest.exists() and json.loads(manifest.read_text('utf-8'))['input_sha256']!=sha:
        raise ValueError('输入已变化；先审查差异，不能把旧JSONL当新结果继续跑')
    dump(manifest,dict(input_sha256=sha,model=tier.MODEL,scope='smoke' if smoke else 'full'))
    s1=tier.stage1(None,m,items,HERE/('wanping_stage1.jsonl' if grouped else f'{prefix}_stage1.jsonl'),12,evidence)
    if grouped:
        policy=json.loads((HERE/'wanping_peer_groups.json').read_text('utf-8'))
        if policy['state']!='用户已确认':raise ValueError('同类组尚未确认')
        mapped={s:g for g,seqs in policy['groups'].items() for s in seqs}
        if set(mapped)!=set(range(20,30)):raise ValueError('归并范围必须恰为seq20–29')
        m.peer_merge={s:mapped.get(s,r['peer_group']) for s,r in s1.items()}
        s1=tier.apply_peer_merge(m,s1)
        dump(HERE/'wanping_grouped_stage1.json',s1)
        # 只承接成员集合与组名都没变的组；受影响十条必须重新计算CR。
        p2=HERE/f'{prefix}_stage2.jsonl'
        if not p2.exists():
            original=tier.read_done(HERE/'wanping_stage2.jsonl')
            for s,r in original.items():
                if s not in mapped:tier.append(p2,r)
    s2=tier.stage2(None,m,items,s1,HERE/f'{prefix}_stage2.jsonl',evidence)
    cr={s:0.5*r['Q']+0.3*r['D']+0.2*r['G'] for s,r in s2.items()}
    cores={s:tier.core_of(r,cr[s]) for s,r in s1.items()}
    cands=[s for s in cores if cores[s]>=8.5 and max(float(s1[s][d]) for d in tier.DIMS_WITH_ER if d in s1[s])>=9]
    if grouped and not (HERE/f'{prefix}_stage3.jsonl').exists():
        old={r['seq']:r for r in json.loads((HERE/'wanping_ratings.json').read_text('utf-8'))['results']}
        for s,r in tier.read_done(HERE/'wanping_stage3.jsonl').items():
            if s not in mapped and s in cands and cores[s]==old[s]['core']:
                tier.append(HERE/f'{prefix}_stage3.jsonl',r)
    s3=tier.stage3(None,m,items,cands,s1,cores,HERE/f'{prefix}_stage3.jsonl',evidence)
    results=[]
    for it in items:
        s=it['seq'];r=s1[s];t,reason=tier.tier_of(cores[s],r,s3.get(s))
        if t=='S' and r['confidence']=='low':t='A';reason+='；证据可信度low不得直接定S'
        results.append(dict(r,name=it['name_cn'],CR=cr[s],core=cores[s],tier=t,tier_reason=reason,
                            cr_reason=s2[s]['cr_reason'],sness_reason=s3.get(s,{}).get('sness_reason','')))
    result=dict(input_sha256=sha,model=tier.MODEL,scope='冒烟样本' if smoke else '全量',results=results)
    if grouped:
        result['grouping_note']='用户2026-10-15确认：基本陈列整体单列；八部分及英烈专区合为一组。仅重算seq20–29的CR及适用的S-ness；其余评分保留。'
        result['grouping_policy_sha256']=hashlib.sha256((HERE/'wanping_peer_groups.json').read_bytes()).hexdigest()
    dump(HERE/f'{prefix}_ratings.json',result)
    (HERE/f'{prefix}.model').write_text(tier.MODEL+'\n',encoding='utf-8')
    with (HERE/f'{prefix}_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['seq','name','object_type','peer_group','HS','IU','VI','VA','CE','ER','CR','core','tier','tier_reason','confidence','evidence','cr_reason','sness_reason']
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(results)
    print(json.dumps({'count':len(results),'tier':dict(Counter(r['tier'] for r in results)),
                      'groups':len({r['peer_group'] for r in results}),'results':[(r['seq'],r['name'],r['object_type'],r['ER'],r['core'],r['tier']) for r in results]},ensure_ascii=False),flush=True)

def run_audit():
    data,_,_,sha=load()
    rating_file='wanping_grouped_ratings.json' if (HERE/'wanping_grouped_ratings.json').exists() else 'wanping_ratings.json'
    scored=json.loads((HERE/rating_file).read_text('utf-8'))
    if scored['input_sha256']!=sha:raise ValueError('输入已变更，不能复用旧评分')
    ratings={r['seq']:r for r in scored['results']}
    extra_path=HERE/'wanping_audit_extra_evidence.json'
    extra=json.loads(extra_path.read_text('utf-8'))['evidence'] if extra_path.exists() else []
    items=[]
    for r in data['rows']:
        s=r['source_seq'];v=ratings[s]
        items.append(dict(seq=s,name_en='',name_zh=r['name'],gallery='',category=r['object_type_hint'],
                          description=r['description'],tier=v['tier'],v3=v,
                          meta=[dict(key='官方来源原文',text=e['quote'],source_key=e['source_id'],source=e['url'],confidence='high') for e in r['evidence']+[
                              x for x in extra if x['identity_key']==r['identity_key']]],
                          conf={},src_tier=None,missing=None))
    note=(f'本批{len(items)}条；原文来自丰台区政府、丰台时报、北京旅游网、抗战馆官网。'
          '保留多来源原文，不消解冲突。原文的发布年份不等于实时开放状态。'
          '没有逐件文物编号、当前楼层展厅号、现场坐标或完整原件/复制品清单。'
          '本次为本地资料包，尚未做生产metadata登记，输入中的来源摘录不代表已入库。'
          '审计对照可含评分后补充的官方原文，该部分不作为已完成重评分的依据。')
    p=HERE/'wanping_audit1_slim.jsonl'
    changed_seqs=[]
    if rating_file=='wanping_grouped_ratings.json':
        import shutil
        for name in ['wanping_audit1_slim.jsonl','wanping_audit_manifest.json','wanping_audit_launch_manifest.json']:
            original=HERE/(name+'.original_groups')
            if not original.exists():shutil.copy2(HERE/name,original)
        old={r['seq']:r for r in json.loads((HERE/'wanping_ratings.json').read_text('utf-8'))['results']}
        changed_seqs=[s for s,v in ratings.items() if any(v[k]!=old[s][k] for k in ['peer_group','CR','core','tier','cr_reason','sness_reason'])]
        if set(changed_seqs)!=set(range(20,30)):raise ValueError('评分变化范围不是已确认的十条，停止复审')
        dump(HERE/'wanping_audit_launch_manifest.json',dict(rating_file=rating_file,
             rating_sha256=hashlib.sha256((HERE/rating_file).read_bytes()).hexdigest(),input_sha256=sha,
             extra_evidence_sha256=hashlib.sha256(extra_path.read_bytes()).hexdigest() if extra_path.exists() else None,
             reaudit_seqs=changed_seqs,note='用户确认归并后的十条复审；其他29条保留原审计。'))
        subset=[it for it in items if it['seq'] in changed_seqs]
        patch=audit.stage1_slim(None,'claude-sonnet-5','medium',CONTEXT,note,subset,HERE/'wanping_grouped_audit_patch.jsonl',48,'wanping')
        if set(patch)!=set(changed_seqs):raise ValueError('复审输出范围错误')
        results=tier.read_done(HERE/'wanping_audit1_slim.jsonl.original_groups')
        results.update(patch)
        results=dict(sorted(results.items()))
    else:
        results=audit.stage1_slim(None,'claude-sonnet-5','medium',CONTEXT,note,items,p,48,'wanping')
    changed=0
    for s,r in results.items():
        if ratings[s]['tier'] not in {'B','C'}:continue
        for missing in r['missing']:
            if missing['tier_sensitive'] and not bc.could_reach_as(missing['zh']):
                missing.setdefault('tier_sensitive_raw',True);missing['tier_sensitive']=False;changed+=1
    p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results.values()),encoding='utf-8')
    dump(HERE/'wanping_audit_manifest.json',dict(input_sha256=sha,
         extra_evidence_sha256=hashlib.sha256(extra_path.read_bytes()).hexdigest() if extra_path.exists() else None,
         model='claude-sonnet-5 effort=medium (claude-cli)',rating_file=rating_file,
         rating_sha256=hashlib.sha256((HERE/rating_file).read_bytes()).hexdigest(),
         reaudit_seqs=changed_seqs,retained_audit_seqs=[s for s in results if s not in changed_seqs] if changed_seqs else [],
         mode='slim stage1; existing source excerpts only; no generated significance metadata to audit in stage3',
         count=len(results),bc_guard_downgraded=changed,
         factual_errors=[s for s,r in results.items() if r['found_factual_error']],
         review=[s for s,r in results.items() if r['found_factual_error'] or any(m['tier_sensitive'] for m in r['missing'])]))
    print('audit complete',len(results),'BC guard',changed,flush=True)

def translate():
    import codex_cli
    import translate_artwork as trans
    data,_,_,sha=load()
    p=HERE/'wanping_translations.json'
    translated=json.loads(p.read_text('utf-8')) if p.exists() else dict(input_sha256=sha,model='gpt-5.6-luna',effort='medium',source='AI翻译',values={})
    if translated['input_sha256']!=sha:raise ValueError('来源清单已变化，请先核对翻译输入')
    for kind,what in [('name','名称'),('description','简介'),('editor_note','资料说明')]:
        todo=list(dict.fromkeys(r[kind] for r in data['rows'] if r[kind] not in translated['values']))
        if not todo:continue
        system=trans.SYS_ZH2EN.format(what=what)
        user='逐条译成英文，共 %d 条：\n'%len(todo)+'\n'.join(f'[{i}] {t}' for i,t in enumerate(todo))
        schema=trans.SCHEMA_OF['zh2en'];want=set(range(len(todo)))
        def request():
            d,u=codex_cli.ask(system,user,schema,model='gpt-5.6-luna',effort='medium')
            return d,codex_cli.Usage(u)
        d=llm_cache.call(request,provider='openai_codex',model='gpt-5.6-luna',effort='medium',
                         stage='trans_wanping_'+kind,museum_key='wanping',scope=f'{len(todo)} unique texts',
                         system=system,user=user,schema=schema,retries=0,
                         validate=lambda x: len(x['items'])==len(want) and {r['i'] for r in x['items']}==want and all(r['en'].strip() for r in x['items']))
        for r in d['items']:translated['values'][todo[r['i']]]=dict(en=r['en'],confidence=r['confidence'],source='AI翻译')
        dump(p,translated)
        with (HERE/'wanping_translations.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['zh-CN','en','confidence','source','model','effort'])
            for zh,r in translated['values'].items():w.writerow([zh,r['en'],r['confidence'],r['source'],'gpt-5.6-luna','medium'])
        print('translated',kind,len(todo),flush=True)

def translate_audit():
    import sys
    import audit_translate
    sys.argv=['audit_translate.py','--out-dir',str(HERE),'--museum','wanping',
              '--provider','codex_cli','--model','gpt-5.6-luna','--size','100']
    audit_translate.main()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['smoke','tier','tier-grouped','audit','translate','audit-translate'])
    args=ap.parse_args();setup()
    if args.stage=='audit-translate':translate_audit()
    elif args.stage=='translate':translate()
    elif args.stage=='audit':run_audit()
    else:score(args.stage=='smoke',args.stage=='tier-grouped')

if __name__=='__main__':main()
