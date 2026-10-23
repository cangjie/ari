"""逐张目视并核对来源后采纳的增补清单；只对原件作等比编码。"""
import hashlib
import io
import json
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

HERE=Path(__file__).resolve().parent
KEY='nanluo_shichahai'
TOUR=HERE.parents[1]/'web_api/tour'


def main():
    def load(suffix):return json.loads((HERE/f'{KEY}_{suffix}.json').read_text())
    manifest=load('tour_photos')
    baseline=load('photo_expansion_baseline')
    # 重放时也从旧十张起步；不覆盖旧图和旧原件。
    manifest['photos']=baseline['photos']
    downloads=[]
    for suffix in ['photo_expand_downloads','photo_expand_downloads2','photo_expand_downloads3','photo_expand_downloads4','photo_dp_downloads','photo_dp_beiping','photo_dp_kaorouji_tool','photo_mei_beijing_download','photo_kaorouji_current_downloads']:
        downloads+=load(suffix)
    downloads+=load('photo_commons_downloads_v2')['downloads']
    candidates={(r['source_id'],r['index']):r for r in downloads if r['status']=='ok'}
    choices={
      4:('juer',9,'雨儿胡同公共街段','Yuer Hutong public street'),
      18:('hotel_lusongyuan',0,'侣松园宾馆门面（板厂胡同22号，僧王府相关院落的现用途资料图；非整座王府）','Lusongyuan Hotel frontage, a historically associated courtyard; not the entire princely residence'),
      42:('guangfu',4,'广福观门面','Guangfu Temple facade'),43:('huoshen',4,'火德真君庙山门','Huode Zhenjun Temple gate'),
      44:('guanghua',4,'广化寺门面','Guanghua Temple facade'),45:('guoshoujing_new',3,'郭守敬纪念馆院落入口建筑','Guo Shoujing Memorial courtyard gateway'),
      46:('wetland_district',4,'西海湿地公园湖畔栈道（旧资料图）','Xihai Wetland Park boardwalk, archival view'),
      47:('guoshoujing_new',11,'郭守敬纪念馆内郭守敬塑像','Statue of Guo Shoujing at the memorial'),
      52:('taobeile',4,'涛贝勒府院落建筑（资料图）','Building at Tao Beile Residence, archival view'),
      85:('dp_wenyu_photos',0,'文宇奶酪南锣鼓巷店门面（点评资料图）','Wenyu Dairy, Nanluoguxiang branch frontage'),
      86:('dp_fangzhuan',0,'方砖厂胡同店门面（点评资料图，品牌69号不作门牌）','Fangzhuanchang branch frontage; brand name is not the street number'),
      87:('dp_jingxiu_photos',3,'景秀餐厅南锣鼓巷店门面（点评资料图）','Jingxiu Restaurant branch frontage'),
      88:('dp_beiping_current',0,'北平花园·北平咖啡南锣鼓巷店华夫饼（点评现页组合名称含MUA摩造汉堡，非实时菜单）','Waffle at Beiping Garden Cafe; platform composite name includes MUA Burger; archival menu image'),
      89:('dp_tangfang',2,'糖房咖啡南锣鼓巷店平台饮品资料图','Tangfang Cafe Nanluoguxiang branch drinks, platform image'),
      90:('dp_jingshan_photos',0,'京扇子南锣鼓巷店扇子陈列（点评资料图）','Jing Shanzi branch fan display'),
      91:('dp_yiduo_photos',1,'一朵一果南锣鼓巷店平台商品陈列（不代表另一分店的体验项目）','Yiduo Yiguo branch merchandise; no activities inferred for other branches'),
      92:('shop_news2026',10,'家雀儿手作文创店门面（北京旅游网报道）','Sparrow craft shop frontage, official Beijing Tourism report'),
      93:('shops_newspaper',2,'青松造物设计师共创空间门面（北京日报客户端转载东城报道）','Chillson Creation storefront, Dongcheng report'),
      94:('shops_newspaper',11,'巧克玩家南锣鼓巷店门面（北京日报客户端转载东城报道）','Choc Player Nanluoguxiang branch frontage, Dongcheng report'),
      95:('dp_kaorouji_current',1,'烤肉季饭庄门面（前海东沿14号，对应点评门店资料图）','Kaorouji Restaurant frontage, 14 Qianhai Dongyan; matching platform branch'),
      97:('dp_yaerli_photos',0,'鸦儿李记什刹海店涮肉资料图（点评，非实时菜单）','Yaer Liji Shichahai branch sliced meat, archival platform image'),
      98:('dp_huguosi',0,'护国寺小吃地安门店门面（点评资料图）','Huguosi Snacks Dianmen branch frontage'),
      99:('shop_postoffice',6,'大清邮政信柜门面与投信场景（2021年政府报道）','Imperial Post frontage and mailing scene, 2021 district report'),
      100:('dp_fuhuazhai',2,'富华斋护国新天地店门面（点评资料图）','Fuhuazhai Huguo Xintiandi branch frontage'),
    }
    pgm=['gongwang_theatre','gongwang_fu','gongwang_gate','pgm_022d6e98911c','pgm_4bd8662d0183','pgm_773022ec88aa','pgm_d19e8da03c12','pgm_3930a3d27bd5','pgm_ee3370b43e57','pgm_a239768aa384','pgm_fa52f16a3d33','pgm_b16f60cfa64f','pgm_98ce2006cadb','pgm_7fe6bc643944','pgm_55325015c416','pgm_0de26d7a36e8']
    rows={r['source_seq']:r for r in load('final')['rows']}
    for seq,sid in enumerate(pgm,69):
        choices[seq]=(sid,4,rows[seq]['name']+'（恭王府官网资料图）',rows[seq]['name']+' — palace museum source image')
    for r in load('photo_commons_downloads_v2')['downloads']:
        if r['seq']==58:continue  # 首次召回的是泰州同名馆，拒绝。
        choices[r['seq']]=(r['source_id'],0,rows[r['seq']]['name']+'（历史资料图）',rows[r['seq']]['identity_key'].replace('_',' ')+' — archival photo')
    choices[58]=('commons_58_beijing',0,'北京梅兰芳纪念馆入口（护国寺街旧居，非泰州同名馆）','Mei Lanfang Memorial House in Beijing, not the Taizhou museum')
    settings=manifest['jpeg']
    sources={s['id']:s for s in load('source_capture')['sources']}
    for suffix in ['photo_expand_sources','photo_expand_sources3','photo_expand_sources4']:
        sources.update({s['id']:s for s in load(suffix)})
    def entry(seq,choice,extra=False):
        sid,index,zh,en=choice;candidate=candidates[(sid,index)]
        raw=(HERE/candidate['original']).read_bytes()
        im=ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB');im.thumbnail((settings['max_edge'],settings['max_edge']))
        encoded=io.BytesIO();im.save(encoded,format='JPEG',quality=settings['quality'],optimize=settings['optimize'],progressive=settings['progressive'])
        body=encoded.getvalue();path=f'img/{KEY}/{seq}'+('-dp' if extra else '')+'.jpg';target=TOUR/path
        if target.exists() and target.read_bytes()!=body:
            if seq in {p['seq']for p in baseline['photos']}:raise ValueError(f'禁止覆盖旧发布图：{path}')
            # 本轮尚未上线的候选更换也留存，不混进原十张线上资产。
            draft=HERE/'exports'/f'{KEY}_draft_{seq}_{hashlib.sha256(target.read_bytes()).hexdigest()[:12]}.jpg'
            if not draft.exists():draft.write_bytes(target.read_bytes())
        target.write_bytes(body)
        title='北京旅游网' if any(t in candidate['source_url'] for t in ['visitbeijing']) else '北京市政府或区政府'
        author=None;photographed=None;license_info=None
        if sid.startswith('dp_'):
            title='大众点评 · 对应门店公开相册'
        elif sid=='shops_newspaper':title='北京日报客户端 · 北京东城官方发布'
        elif sid.startswith('commons_'):
            metadata=candidate['metadata']
            def value(key):
                raw=metadata.get(key,{}).get('value','')
                return BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)if '<'in raw else raw
            author=value('Artist');license_info=dict(name=value('LicenseShortName'),url=value('LicenseUrl'))
            title=f'Wikimedia Commons · {author} · {license_info["name"]}'
            date=value('DateTimeOriginal');photographed=date[:10] if len(date)>=10 and date[4]=='-' and date[7]=='-' else None
        elif sid.startswith(('pgm_','gongwang_')):title='恭王府博物馆官网'
        elif sid=='juer':title='北京市东城区人民政府'
        elif sid in ['guanghua','guangfu','huoshen','taobeile','wetland_district','shop_postoffice']:title='北京市西城区人民政府'
        elif sid=='guoshoujing_new':title='北京市人民政府门户网站'
        return dict(seq=seq,identity_key=rows[seq]['identity_key'],caption=dict(zh=zh,en=en),path=path,
                    source=dict(title=title,url=candidate['source_url']),image_url=candidate['url'],
                    photographer=author,photographed_on=photographed,license=license_info,checked_on='2026-10-24',
                    match_basis='执行助手逐张查看画面并与具体来源主体、门店身份或馆方单节点页面核对；不按泛化关键词自动配图。图片不作实时经营、开放或菜单承诺。',
                    source_capture=dict(source_id=sid,index=index),
                    original=dict(path=candidate['original'],sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)),
                    sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),width=im.width,height=im.height)
    for seq,choice in sorted(choices.items()):manifest['photos'].append(entry(seq,choice))
    manifest['supplementary_photos']=[entry(96,('dp_qingyun_photos',2,'庆云楼什刹海店点评菜品资料图（非实时菜单）','Qingyunlou Shichahai branch food, archival platform image'),extra=True)]
    assert len(manifest['photos'])==60 and len({r['seq']for r in manifest['photos']})==60
    manifest.update(checked_on='2026-10-24',note='60/100条有匹配主体的图片；16家商铺全部配图，其中12家含大众点评图，4家按用户授权用官方实景图。保留原10张及全部失败候选。共61张发布图，宋庆龄故居既有展陈图保留。Commons作者与许可随图展示。明确请勿转载的SIPA、通用推荐图、泰州梅兰芳纪念馆等误召回不发布。')
    (HERE/f'{KEY}_tour_photos.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    rejected=dict(checked_on='2026-10-24',items=[dict(source='hutong_walk、hutong_memory大部分候选',reason='SIPA明确请勿转载，或照片为五道营、砖塔、史家等其他胡同，不借给本清单'),dict(source='Commons:Mei Lanfang Memorial Museum 20260610.jpg',reason='图与描述均为泰州市梅兰芳纪念馆，非北京护国寺街故居；已改用北京对应照片'),dict(source='大众点评photos/album的多店重复5张图片',reason='通用推荐模块，不是对应门店照片；改用带门店alt及公开photo条目的页面'),dict(source='juer索引6/7',reason='玉河水道，不误配帽儿胡同')])
    (HERE/f'{KEY}_photo_expansion_review.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2)+'\n')
    print('60 records; 61 JPEGs; shops 16/16; original 10 unchanged',flush=True)


if __name__=='__main__':main()
