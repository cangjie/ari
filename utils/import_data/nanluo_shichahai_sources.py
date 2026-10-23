#!/usr/bin/env python3
"""南锣鼓巷＋什刹海：保存已定位的公开官方网页，不调用模型、不写业务库。"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from html.parser import HTMLParser
from tls import ssl_ctx

HERE = Path(__file__).resolve().parent
CAPTURE = HERE / 'nanluo_shichahai_source_capture.json'

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip=0;self.parts=[];self.links=[];self.anchor=None;self.title=False;self.title_parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript','iframe'}:self.skip+=1
        if tag=='title':self.title=True
        if tag=='a':self.anchor={'href':dict(attrs).get('href'),'text':''}
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript','iframe'}:self.skip=max(0,self.skip-1)
        if tag=='title':self.title=False
        if tag=='a' and self.anchor:
            if self.anchor['href']:self.links.append(self.anchor)
            self.anchor=None
    def handle_data(self,text):
        if self.skip:return
        text=text.strip()
        if not text:return
        self.parts.append(text)
        if self.title:self.title_parts.append(text)
        if self.anchor:self.anchor['text']+=text
# id, URL。来源身份不由域名推导为当前开放状态。
SOURCES = [
 ('nl_overview','https://s.visitbeijing.com.cn/attraction/101328'),
 ('nl_history','https://www.visitbeijing.com.cn/article/47QlRwplMKC?device=amp'),
 ('nl_streets','https://csglw.beijing.gov.cn/sdhjjs/sdhjjsxc/jxhtxc/201912/t20191204_839606.html'),
 ('nl_community','https://www.bjdch.gov.cn/ztzl/dcqjdfw/jdsqgkjs/202301/t20230111_3036178.html'),
 ('maoer','https://www.beijing.gov.cn/shipin/bjfq/23772.html'),
 ('maodun','https://www.beijing.gov.cn/renwen/rwzyd/gdwh/mdgj/202107/t20210708_2432100.html'),
 ('qibaishi','https://www.beijing.gov.cn/renwen/sy/whkb/201901/t20190114_1865118.html'),
 ('keyuan','https://wwj.beijing.gov.cn/bjww/362771/362782/dlphdwbdwdbhfwjjkdd/548457/index.html'),
 ('sengwang','https://wwj.beijing.gov.cn/bjww/362771/362782/dqphdwbdwdbhfwjjkdd/548634/index.html'),
 ('shajing','https://wwj.beijing.gov.cn/bjww/362690/362730/zbgg19/631495/index.html'),
 ('juer','https://www.bjdch.gov.cn/ywdt/dcyw/202311/t20231108_3297236.html'),
 ('hutong_renewal','https://www.bjdch.gov.cn/ywdt/mtgz/202008/t20200810_2967960.html'),
 ('sh_overview','https://xcszb.bjxch.gov.cn/xxxq/pnidpv19079.html'),
 ('sh_sights','https://www.visitbeijing.com.cn/article/4NjY2r2DT0q?device=amp'),
 ('sh_culture','https://www.bjxch.gov.cn/xcfw/whfw/xxxq/pnidpv736426.html'),
 ('sh_local','https://www.bjxch.gov.cn/xcfw/whfw/xxxq/pnidpv736473.html'),
 ('sh_route','https://www.bjxch.gov.cn/rwxc/xxxq/pnidpv954519.html'),
 ('sh_bridges','https://www.beijing.gov.cn/ywdt/yaowen/202310/t20231003_3270193.html'),
 ('sh_autumn','https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202609/t20260910_4857944.html'),
 ('guanghua','https://www.bjxch.gov.cn/xcfw/whfw/xxxq/pnidpv737621.html'),
 ('guangfu','https://www.bjxch.gov.cn/zt/schjmp/xxxq/pnidpv932670.html'),
 ('huoshen','https://www.bjxch.gov.cn/zt/schjmp/xxxq/pnidpv932676.html'),
 ('guoshoujing','https://wwj.beijing.gov.cn/bjww/362771/362773/546517/index.html'),
 ('guoshoujing_new','https://www.beijing.gov.cn/tsbj/sxym/202310/t20231008_3271623.html'),
 ('wanning','https://wwj.beijing.gov.cn/bjww/362760/362767/2020nwhhzrycr/10812184/10815278/index.html'),
 ('guomoruo','https://www.beijing.gov.cn/renwen/rwzyd/gdwh/gmrjng/202107/t20210713_2435614.html'),
 ('songqingling','https://www.beijing.gov.cn/renwen/rwzyd/202011/t20201123_2143317.html'),
 ('zhonggulou','https://www.beijing.gov.cn/renwen/rwzyd/gdwh/zgl/202107/t20210708_2431999.html'),
 ('gulou_detail','https://wwj.beijing.gov.cn/bjww/362760/362770/1757494/index.html'),
 ('wetland','https://fgw.beijing.gov.cn/gzdt/fgzs/mtbdx/bzwlxw/202212/t20221220_2880867.htm'),
 ('yuer','https://www.beijing.gov.cn/shipin/bjfq/23950.html'),
 ('qingwang','https://xcszb.bjxch.gov.cn/xxxq/pnidpv19078.html'),
 ('taobeile','https://www.bjxch.gov.cn/xcfw/whfw/xxxq/pnidpv737633.html'),
 ('gongwang_overview','https://www.beijing.gov.cn/renwen/rwzyd/lyjq/5A/gwf/202210/t20221018_2838434.html'),
 ('gongwang_guide','https://www.pgm.org.cn/pgm/daolan/daolan.shtml'),
 ('gongwang_history','https://www.pgm.org.cn/pgm/mtgz/201911/e3eb6b71a1384742a285792ecf740659.shtml'),
 ('gongwang_theatre','https://www.pgm.org.cn/pgm/wfjd/201402/4eef66b81a1a429f8d529bc0b117c201.shtml'),
 ('gongwang_fu','https://www.pgm.org.cn/pgm/wfjd/201402/531f0043f14947a98b096a335e26439f.shtml'),
 ('gongwang_gate','https://www.pgm.org.cn/pgm/wfjd/201402/da3066c6a7bf4cc485fe198958f46114.shtml'),
 ('gongwang_list','https://www.pgm.org.cn/pgm/wfjd/wfjdpic_list.shtml'),
 ('desheng_bridge','https://www.bjxch.gov.cn/xcfw/whfw/xxxq/pnidpv737672.html'),
 ('meilanfang','https://wwj.beijing.gov.cn/bjww/wwjzzcslm/1737418/1738088/1742745/545808/index.html'),
 ('sh_renewal','https://www.bjxch.gov.cn/xcdt/xxxq/pnidpv974918.html'),
 ('sh_temple_renewal','https://www.bjxch.gov.cn/xcdt/xxxq/pnidpv966867.html'),
]

def dump(obj):
    tmp=CAPTURE.with_suffix('.new')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(CAPTURE)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--only',action='append',default=[])
    ap.add_argument('--gongwang-details',action='store_true',help='只抓已保存官方景点列表中的详情链接')
    args=ap.parse_args()
    data=json.loads(CAPTURE.read_text('utf-8')) if CAPTURE.exists() else dict(
        collected_on='2026-10-23',retrieval_method='HTTP with certificate verification; extracted text and SHA-256',sources=[])
    saved={s['id']:s for s in data['sources']}
    jobs=[] if args.gongwang_details else list(SOURCES)
    if args.gongwang_details:
        listing=saved['gongwang_list']
        if listing['status']!='ok':raise ValueError('恭王府景点列表尚未成功取得')
        known={u for _,u in SOURCES}
        for link in listing['links']:
            href=link['href']
            if re.fullmatch(r'/pgm/wfjd/\d{6}/[a-z0-9]+\.shtml',href):
                url='https://www.pgm.org.cn'+href
                if url not in known:
                    jobs.append(('pgm_'+href.rsplit('/',1)[1].split('.')[0][:12],url));known.add(url)
    for sid,url in jobs:
        if args.only and sid not in args.only:continue
        if sid in saved:
            print(sid,'cached',saved[sid]['status'],flush=True);continue
        start=time.monotonic()
        source=dict(id=sid,url=url,retrieved_on='2026-10-23')
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'ari research source collection/1.0'})
            with urllib.request.urlopen(req,context=ssl_ctx(),timeout=18) as response:
                raw=response.read(4_000_000)
                encoding=response.headers.get_content_charset()
                source['http_status']=response.status
            if not encoding:
                m=re.search(br'charset=[\s\"\x27]*([a-zA-Z0-9_-]+)',raw[:10000])
                encoding=m.group(1).decode('ascii') if m else 'utf-8'
            html=raw.decode(encoding,errors='strict')
            parser=TextParser();parser.feed(html)
            title=' '.join(parser.title_parts) or sid
            # 保存全文，避免按不可靠CSS选择器静默丢正文。
            text='\n'.join(parser.parts)
            if len(text)<100 or any(x in text[:1500] for x in ['人机验证','Access Denied','CAPTCHA']):
                raise ValueError('未取得可用正文，不绕过访问验证')
            source.update(status='ok',title=title,encoding=encoding,raw_sha256=hashlib.sha256(raw).hexdigest(),
                          text=text,html=html,links=parser.links)
        except Exception as e:
            source.update(status='error',error=f'{type(e).__name__}: {e}')
        source['elapsed_seconds']=round(time.monotonic()-start,2)
        saved[sid]=source;data['sources']=list(saved.values());dump(data)
        print(sid,source['status'],len(source.get('text','')),source.get('error',''),flush=True)
        time.sleep(1)
    print('capture',sum(s['status']=='ok' for s in saved.values()),'/',len(saved),flush=True)

if __name__=='__main__':main()
