"""以既定 Sonnet 5 medium 独立复核新线路图与网页接入，不重评历史资料。"""
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
import claude_cli
import llm_cache
import nanluo_shichahai_pipeline as pipeline
from wanping_tour_audit import SCHEMA

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]; KEY='nanluo_shichahai'


def main():
    pipeline.setup()
    data=json.loads((ROOT/f'web_api/tour/data/{KEY}.json').read_text())
    overview=[dict(id=t['id'],name=t['name'],steps=[dict(seq=s['seq'],name=s['name']['zh'],point=s['point'])for s in t['steps']],
                   starts=[v['start_station']for v in t['variants']],end=t['end_station'])for t in data['itineraries']]
    ui_diff=subprocess.check_output(['git','diff','--','web_api/tour/app.js','web_api/tour/app.css','web_api/tour/index.html'],cwd=ROOT,text=True)
    user=('用户指出之前只有文字/隐藏互动连线，缺少可直接查看保存的游览线路图。当前为四主题×四起点16张SVG与16张1200×1600PNG。'
          '共享JSON的路线、顺序、道路来源、距离、停留与步行时间保持上一轮审计值；本轮只是新增map_assets路径。原100介绍、V3、Excel、37个原位置和所有照片保持不变。'
          '图的数字是线路游览顺序，点落在原steps.point公共街道参考点；不是场所入口。图有S/E、同站合并、箭头、标尺、名称图例及开放边界。'
          '网页每条主题直接显示预览，四起点切换对应图，提供SVG放大与PNG保存。互动地图只显示主题站点，标在steps.point；全部景点仍显示原位置与清单序号。'
          '模型只收代码和文字，不收图片像素；助手另已查看四默认图及16图联系表。不要称模型视觉验图。'
          '92项pytest已通过、3项真实数据库测试未启用；完整20场景浏览器检查正在运行，未提前宣称通过。'
          '审核范围为新SVG/PNG生成正确性、身份顺序/来源传递、地图UI回归。指出可定位的实际缺陷，不把同站往返或既有固定次序当新需求。\n'
          '\nGENERATOR\n'+(HERE/'tour_itinerary_maps.py').read_text()+
          '\nRASTERIZER\n'+(HERE/'tour_itinerary_maps.mjs').read_text()+
          '\nUI DIFF\n'+ui_diff+'\nTHEMES\n'+json.dumps(overview,ensure_ascii=False)+
          '\nSTATIONS (unchanged OSM/metro sources already audited)\n'+json.dumps([{k:s[k]for k in ['id','name','point']}for s in data['itinerary_stations']],ensure_ascii=False))
    system='你是独立发布审查者。只依据提供的当前代码与数据核查实际风险。按schema返回findings和assessment；不改评级，不进行未授权外部操作。没有实际问题时findings为空。'
    review(system,user,'audit_itinerary_map_delivery','itinerary_map_audit')


def review(system,user,stage,suffix):
    if len(user)>28000:raise ValueError(len(user))
    request=dict(system=system,user=user,schema=SCHEMA)
    (HERE/f'{KEY}_{suffix}_request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
    print(len(user),'chars; claude-sonnet-5 medium; no retry',flush=True)
    def call():
        old=os.environ['PATH'];real='/Users/cangjie/Library/Application Support/Claude/claude-code/2.1.308/a93ded4b1b47/claude.app/Contents/MacOS/claude'
        with tempfile.TemporaryDirectory(prefix='ari_route_map_audit_')as folder:
            wrapper=Path(folder)/'claude';wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(real)+' --safe-mode "$@"\n');wrapper.chmod(0o755);os.environ['PATH']=folder+os.pathsep+old
            try:result,usage=claude_cli.ask(system,user,SCHEMA,'claude-sonnet-5','medium')
            finally:os.environ['PATH']=old
        return result,claude_cli.Usage(usage)
    result=llm_cache.call(call,provider='anthropic_cli',model='claude-sonnet-5',effort='medium',stage=stage,museum_key=KEY,system=system,user=user,schema=SCHEMA,scope='16 independent route maps and shared Web integration',retries=0,validate=lambda r:isinstance(r.get('findings'),list)and bool(r.get('assessment')))
    report=dict(model='claude-sonnet-5',effort='medium',tour_sha256=hashlib.sha256((ROOT/f'web_api/tour/data/{KEY}.json').read_bytes()).hexdigest(),
                map_manifest_sha256=hashlib.sha256((HERE/f'{KEY}_itinerary_maps.json').read_bytes()).hexdigest(),result=result)
    if suffix.endswith('recheck'):
        report['reviewed_files']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in ['web_api/tour/app.js','web_api/tour/app.css','web_api/tour/index.html','utils/import_data/tour_itinerary_maps.py','utils/import_data/tour_itinerary_maps.mjs']}
    (HERE/f'{KEY}_{suffix}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
