"""首轮输出上限/人工中止后，缩小输入复核最终地图和照片发布；同型号档位，不自动重试。"""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import claude_cli
import llm_cache
import nanluo_shichahai_pipeline as pipeline
from wanping_tour_audit import SCHEMA
from nanluo_shichahai_media_audit import SYSTEM

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
KEY='nanluo_shichahai'


def main():
    pipeline.setup()
    diagnosis=json.loads((HERE/f'{KEY}_media_audit_diagnosis.json').read_text('utf-8'))
    user=('前轮没有有效结论，不能当作合格审查。现已定位：CLI后台插件下载耗时；单次模型回复达到32000输出token上限，之后仍未得结构化结论，执行助手主动中止整轮并保留失败缓存。'
          '本请求改为最终生成器、共享页面变更、37个精简位置绑定、10个精简照片绑定；不重传原始街道折线和冗余哈希，不改变Sonnet 5 medium或schema。'
          '请只检查具体的实际错误与兼容性；不需要逐个重新计算坐标或重新评分。没有照片像素可看，不声称模型视觉验图。'
          '最终代码已修正水体site重复与内环方向、聚焦后顶栏滚动、照片原宽显示；忽略迟到GPS回调。'
          '问答仅补可见位置口径/出处和图注，并明确没有传图；原有两馆材料逐字一致。87项pytest、17个浏览器场景通过；新增GPS回调检查另复测通过。真机未验、未部署、线上不发问。\n')
    user+='FILE tour_collection_media.py\n'+(HERE/'tour_collection_media.py').read_text('utf-8')
    paths=['web_api/tour/app.js','web_api/tour/app.css','web_api/tour/index.html','web_api/app/tour_qa_llm.py','utils/import_data/tour_collection_build.py']
    user+='\nCURRENT PATCH\n'+subprocess.run(['git','diff','HEAD','--',*paths],cwd=ROOT,capture_output=True,check=True,encoding='utf-8').stdout
    m=json.loads((ROOT/f'web_api/tour/data/{KEY}.json').read_text('utf-8'))
    binding=json.loads((HERE/f'{KEY}_tour_media.json').read_text('utf-8'))
    positions={p['stops'][0]:p for p in m['places']if 'x'in p}
    table=[]
    for r in binding['positions']:
        p=positions[r['seq']]
        table.append(dict(seq=r['seq'],id=p['id'],name=p['name']['zh'],osm=r['osm'],osm_name=r['osm_name'],basis=r['basis'],lat=p['lat'],lon=p['lon'],note=p['position']['note']))
    photos=json.loads((HERE/f'{KEY}_tour_photos.json').read_text('utf-8'))['photos']
    photo_table=[{k:p[k]for k in ['seq','identity_key','caption','source','image_url','width','height']}for p in photos]
    user+='\nPOSITIONS\n'+json.dumps(table,ensure_ascii=False,separators=(',',':'))
    user+='\nPHOTOS\n'+json.dumps(photo_table,ensure_ascii=False,separators=(',',':'))
    user+='\nBOUNDARIES\n'+json.dumps(dict(total_records=100,unknown_positions=63,without_photos=90,mode=m['mode'],map_mode=m['map_mode'],planning=m['planning'],routes=m['routes'],no_area='area'not in m,no_arrival_radii=all('r'not in p for p in m['places']),rejected_position_matches=binding['note']),ensure_ascii=False)
    if len(user)>35000:raise ValueError(f'final review too large {len(user)}')
    (HERE/f'{KEY}_media_audit_final_request.json').write_text(json.dumps(dict(system=SYSTEM,user=user,schema=SCHEMA),ensure_ascii=False,indent=2)+'\n')
    print(f'{len(user)} chars; claude-sonnet-5 medium; zero retries; empty setting-sources',flush=True)
    def call():
        # 仅隔离本次调用的用户/项目插件设置；订阅keychain认证照常；不改公共provider或用户配置。
        real=shutil.which('claude');old_path=os.environ['PATH']
        with tempfile.TemporaryDirectory(prefix='ari_media_audit_cli_')as folder:
            wrapper=Path(folder)/'claude'
            wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(real)+' --setting-sources \'\' "$@"\n');wrapper.chmod(0o755)
            os.environ['PATH']=folder+os.pathsep+old_path
            try:result,usage=claude_cli.ask(SYSTEM,user,SCHEMA,model='claude-sonnet-5',effort='medium')
            finally:os.environ['PATH']=old_path
        return result,claude_cli.Usage(usage)
    result=llm_cache.call(call,provider='anthropic_cli',model='claude-sonnet-5',effort='medium',stage='audit_tour_media_final',museum_key=KEY,system=SYSTEM,user=user,schema=SCHEMA,scope='reduced final media publication review after diagnosed output-cap abort',retries=0,validate=lambda r:isinstance(r.get('findings'),list)and bool(r.get('assessment')))
    (HERE/f'{KEY}_media_audit_final.json').write_text(json.dumps(dict(model='claude-sonnet-5',effort='medium',tour_sha256=hashlib.sha256((ROOT/f'web_api/tour/data/{KEY}.json').read_bytes()).hexdigest(),request_sha256=hashlib.sha256(user.encode()).hexdigest(),result=result),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
