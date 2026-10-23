"""只复核本轮四项important及对应修正，不重跑既有历史/评级审计。"""
import hashlib,json,os,re,shlex,tempfile
from pathlib import Path
import claude_cli,llm_cache
import nanluo_shichahai_pipeline as pipeline
from wanping_tour_audit import SCHEMA
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];KEY='nanluo_shichahai'


def main():
    pipeline.setup()
    def load(s):return json.loads((HERE/f'{KEY}_{s}.json').read_text())
    prior=[dict(stage=stage,**r)for stage in ['sources','routes','ui']for r in load('expansion_audit_'+stage)['result']['findings']if r['severity']=='important']
    disposition=load('expansion_review_disposition')
    metro=[]
    for row in load('metro_station_sources_v2'):
        text=row.get('text','');i=text.find('首末车时间')
        metro.append(dict(name=row['name'],url=row['url'],status=row.get('status'),encoding=row.get('encoding'),sha256=row.get('sha256'),text=text[max(0,i-80):i+850]))
    manifest=load('experience')
    js=(ROOT/'web_api/tour/app.js').read_text()
    def fn(name):
        start=js.index('  function '+name+'(');nxt=re.search(r'^  function ',js[start+12:],re.M)
        return js[start:start+12+nxt.start()]if nxt else js[start:]
    helper=(HERE/'tour_collection_experience.py').read_text();graph=helper[:helper.index('\ndef augment')]
    graph+='\n'+helper[helper.index('        for item in theme['):helper.index('        variants=[]')]
    context=('只复核已审四项important是否闭环及修复相关回归。其它60图/16商铺/标签已在首轮覆盖，不重审。'
      '95旧宴会厅相册AWS独立网络亦404；已改饭庄本店507776，HTTP200，album地址前海东沿14号与本条一致，新图为助手目视过的门面。'
      '53已直接HTTP读取Commons文件页，真实许可CC0，API一致，完整HTML和哈希留存；不要按摄影者一般习惯推翻具体文件许可。'
      '92图注已统一北京旅游网；99既有审计介绍和留存HTTP正文明确2021。'
      '地铁旧官网站目录href本身404，不照抄坏链；搜索取得各站xltcx具体页并逐页HTTP200。网站实际GB2312，原UTF8解码失败非网络封锁，现保存原编码和全文。'
      '全部主站显式登记streets白名单；通用构建对缺省街名直接拒绝。四站各用本线路具体页面，不再共用6号线链接。'
      '同站首尾按用户保留四起点，UI注明同站往返。地图按所选路线bounds缩放居中，屏幕3px主题描边；地图摘要补停留/步行细分。'
      '原37处位置、100介绍、V3、Excel、旧10图不变，无GPS热区或到站提醒。主站是附近公共街道参考点，非检票入口。'
      '91项pytest通过、3项真库未启用；之前20个浏览器场景通过，修正后同套回归正在跑，不提前宣称通过。\n')
    user=(context+'\nPRIOR IMPORTANT\n'+json.dumps(prior,ensure_ascii=False)+
          '\nDISPOSITION AND PRIMARY EVIDENCE\n'+json.dumps(disposition,ensure_ascii=False)+
          '\nMETRO HTTP EVIDENCE\n'+json.dumps(metro,ensure_ascii=False)+
          '\nCURRENT METRO CONFIG\n'+json.dumps(manifest['stations'],ensure_ascii=False)+
          '\nEXPLICIT STREET INPUT\n'+json.dumps([dict(name=t['name'],steps=[dict(seq=s['seq'],streets=s['streets'])for s in t['steps']])for t in manifest['themes']],ensure_ascii=False)+
          '\nGRAPH AND STREET VALIDATION\n'+graph+'\nCURRENT UI\n'+fn('collectionView')+fn('renderThemes'))
    system='你是独立发布复核者。只核对有效审查的具体意见和当前完整相关证据/函数，识别实际缺陷，返回findings和assessment。不把已给定证据说成未提供，不增设假想要求。没有图片像素，不称模型视觉验图。模型Claude Sonnet 5 medium。'
    if len(user)>23000:raise ValueError(len(user))
    (HERE/f'{KEY}_expansion_recheck_request.json').write_text(json.dumps(dict(system=system,user=user,schema=SCHEMA),ensure_ascii=False,indent=2)+'\n')
    print(len(user),'chars; claude-sonnet-5 medium safe-mode; no retry',flush=True)
    def call():
        old=os.environ['PATH'];real='/Users/cangjie/Library/Application Support/Claude/claude-code/2.1.308/a93ded4b1b47/claude.app/Contents/MacOS/claude'
        with tempfile.TemporaryDirectory(prefix='ari_expansion_final_')as folder:
            wrapper=Path(folder)/'claude';wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(real)+' --safe-mode "$@"\n');wrapper.chmod(0o755);os.environ['PATH']=folder+os.pathsep+old
            try:result,usage=claude_cli.ask(system,user,SCHEMA,'claude-sonnet-5','medium')
            finally:os.environ['PATH']=old
        return result,claude_cli.Usage(usage)
    result=llm_cache.call(call,provider='anthropic_cli',model='claude-sonnet-5',effort='medium',stage='audit_collection_expand_recheck',museum_key=KEY,system=system,user=user,schema=SCHEMA,scope='four important findings and related UI fixes',retries=0,validate=lambda r:isinstance(r.get('findings'),list)and bool(r.get('assessment')))
    (HERE/f'{KEY}_expansion_recheck.json').write_text(json.dumps(dict(model='claude-sonnet-5',effort='medium',tour_sha256=hashlib.sha256((ROOT/f'web_api/tour/data/{KEY}.json').read_bytes()).hexdigest(),result=result),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
