#!/usr/bin/env python3
"""将已保存的点评/文旅工具结果转成有取得方式标记的增补证据，不调用模型。"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path

P=Path(__file__).resolve().parent;KEY='nanluo_shichahai'
def load(n):return json.loads((P/(KEY+n)).read_text())
def dump(n,d):(P/(KEY+n)).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def plain(s):return re.sub(r'【\d+†([^】]+)】',lambda m:m[1].split('†')[0],s)

def main():
    capture=load('_source_capture.json');saved={s['id']:s for s in capture['sources']}
    failures=[]
    for f in sorted(P.glob(KEY+'_shops_tool_capture_*.json')):
        for r in json.loads(f.read_text())['records']:
            j=r['job'];raw=r['result'].get('value','');sid=j['id']
            if not isinstance(raw,str) or 'not accessible via this tool' in raw or 'Failed to fetch' in raw:
                failures.append(dict(source_id=sid,url=j['url'],reason=raw));continue
            lines=[plain(m[1]) for m in re.finditer(r'^L\d+: ?(.*)$',raw,re.M)]
            first=next((i for i,t in enumerate(lines) if j['needle'] in t),None)
            if first is None:raise ValueError('对象名未出现在已返回正文：'+sid)
            lines=lines[first:]
            stop=next((i for i,t in enumerate(lines) if any(k in t for k in ['附近商户','关于我们','原创声明','征文启事','友情链接'])),len(lines))
            text='\n'.join(lines[:stop]).strip()
            if len(text)<12:raise ValueError('可用对象正文过短：'+sid)
            saved[sid]=dict(id=sid,url=j['url'],retrieved_on='2026-10-23',status='ok',title=raw.splitlines()[0],
                text=text,raw_sha256=None,snapshot_sha256=digest(raw),extracted_text_sha256=digest(text),
                source_kind=j['kind'],retrieval_method='web_tool_open_parsed_text',
                text_scope='returned_tool_lines_after_merchant_or_article_heading_before_navigation_footer',
                tool_capture_file=f.name,source_tier=4 if 'platform' in j['kind'] else 2,
                confidence='medium' if 'platform' in j['kind'] else 'high',
                currency_note='工具返回的网页快照，不是美团/点评App实时营业保证。')
    # 已索引的结果与网页正文严格分开；打不开不重试、不冒充取得了HTTP正文。
    index_jobs=[
        ('dp_fuhuazhai_index','https://www.dianping.com/shop/77241850/photos/album','platform_search_excerpt'),
        ('shop_jingshan_design_index','https://www.sohodd.com/?p=97102','design_search_excerpt'),
        ('shop_yiduo_qunar_index','https://touch.go.qunar.com/poi/3555160?from=androidqq','platform_search_excerpt'),
    ]
    research=[(f,json.loads(f.read_text())) for f in sorted(P.glob(KEY+'_shops_web_research*.json'))]
    for sid,url,kind in index_jobs:
        found=[]
        for f,pack in research:
            for run in pack['search_runs']:
                text=run.get('value','') if isinstance(run,dict) else ''
                if not isinstance(text,str):continue
                for block in text.split('--------------------------------------------------------------------------------'):
                    if '('+url+')' in block:found.append((f,block.strip()))
        if not found:raise ValueError('没有已保存索引摘录：'+url)
        f,raw=max(found,key=lambda pair:len(pair[1]))
        text='\n'.join(raw.splitlines()[2:]).strip()
        saved[sid]=dict(id=sid,url=url,retrieved_on='2026-10-23',status='ok',title=raw.splitlines()[0],
            text=text,raw_sha256=None,snapshot_sha256=digest(raw),extracted_text_sha256=digest(text),
            source_kind=kind,retrieval_method='web_search_index_excerpt',tool_capture_file=f.name,
            text_scope='search_tool_returned_excerpt_not_full_page',source_tier=4,confidence='medium',
            currency_note='索引摘录，不能据抓取日期推断门店当天营业。')
    capture['sources']=list(saved.values());capture['retrieval_method']='mixed: original verified HTTP captures plus explicitly labelled web-tool parsed text / indexed excerpts'
    dump('_source_capture.json',capture)
    dump('_shops_source_access.json',dict(failed_open_attempts=failures,policy='失败保留；用已有索引时独立登记取得方式，无自动重试或访问验证绕过。'))
    rows=load('_candidates.json');existing={r['identity_key'] for r in rows['rows']}
    # 既有规范名仍供模型识别同一对象，展示名补上用户熟悉的「故居」，序号48保持不变。
    guo=next(r for r in rows['rows'] if r['identity_key']=='guomoruo')
    guo['display_name']='郭沫若故居（郭沫若纪念馆）';guo['aliases']=['郭沫若故居','郭沫若纪念馆']
    common='具体经营门店，不把品牌创立年当作本分店或建筑年代；平台星级、人均和菜品为第三方页面快照，不能直接换算V3评级。现场营业、菜单、价格和体验项目仍待出行前核实。'
    # key、名称、区域、父级、业态、来源、定位词、来源记载地址、特色及边界说明。
    shops=[
        ('wenyu','文宇奶酪（南锣鼓巷店）','南锣鼓巷','nanluo','奶酪甜品',['dp_wenyu_photos','nl_overview'],'文宇奶酪','南锣鼓巷49号（文旅旧文记载）','京式奶酪、奶卷及双皮奶','不把宫廷传承的宣传描述当作本分店建筑年代。'),
        ('fangzhuan','方砖厂69号炸酱面（方砖厂胡同店）','南锣鼓巷','nanluo','京味面食',['dp_fangzhuan_album','shop_news2026'],'方砖厂69号','方砖厂胡同1号（点评登记）','炸酱面与胡同餐饮体验','69号是品牌名；点评本店地址为1号，不将店名当门牌。品牌获奖信息不自动归到本店。'),
        ('jingxiu','景秀餐厅（南锣鼓巷店）','南锣鼓巷','nanluo','胡同家常菜',['dp_jingxiu_photos','shop_jingxiu_address','shop_news2026'],'景秀餐厅','东棉花胡同36号（携程登记）','家常菜与中戏周边餐饮记忆','1992年为报道所述店史，不推定房屋为1992年原构。'),
        ('beiping','北平花园·潮玩萌牙·北平咖啡（南锣鼓巷胡同店）','南锣鼓巷','nanluo','花园咖啡',['dp_beiping_photos','shop_beiping_address'],'北平','南锣鼓巷113-2号（携程登记）','咖啡、华夫饼和旅舍前庭休憩','点评使用组合店名，携程名含青年旅舍；本条只整理门店，不另扩旅舍住宿业务。'),
        ('tangfang','糖房咖啡（南锣鼓巷店）','南锣鼓巷','nanluo','咖啡简餐',['dp_tangfang_main'],'糖房咖啡','南锣鼓巷，完整门牌在公开页面被遮挡','精品咖啡、茶饮及简餐','不据店名推断古代糖坊，不混为什刹海的其他同名店。公开页4.3分、48元/人为采集快照。'),
        ('jingshan','京扇子（南锣鼓巷店）','南锣鼓巷','nanluo','扇艺零售',['dp_jingshan_photos','shop_jingshan_design_index'],'京扇子','南锣鼓巷6号（2018年设计报道；现址待复核）','扇子零售与当代店铺空间设计','不与日本京扇堂混淆；旧设计报道说明的是当时空间，不承诺当前陈设未变。'),
        ('yiduo','一朵一果（南锣鼓巷店）','南锣鼓巷','nanluo','纸品文具',['dp_yiduo_album','shop_yiduo_industry','shop_yiduo_qunar_index'],'一朵一果','南锣鼓巷45号（点评登记；其他资料为41号或41-2号）','明信片、手账纸品与城市纪念品','同品牌在南锣曾有两家门店；45号、41号和41-2号不默认为同一门店，不把其他分店制作体验搬来。'),
        ('jiaquer','家雀儿手作文创店（南锣鼓巷）','南锣鼓巷','nanluo','手作文创',['shop_news2026'],'家雀儿','南锣鼓巷主街；2026年报道未列具体门牌','手作瓷瓶、木质动物摆件及手绘葫芦','据2026年3月街区报道定位；没有对应点评完整商户页，不填星级、人均或精确地址。'),
        ('qingsong','青松造物（南锣鼓巷设计师共创空间）','南锣鼓巷','nanluo','设计文创',['shop_news2026'],'青松造物','南锣鼓巷主街；2026年报道未列具体门牌','陶瓷、剪纸、印章及手绘文创','报道列商品，不等于每天提供手作课程，也不推定每件商品有非遗认证。'),
        ('qiaoke','巧克玩家（南锣鼓巷）','南锣鼓巷','nanluo','创意巧克力礼品',['shop_news2026'],'巧克玩家','南锣鼓巷主街；2026年报道未列具体门牌','天坛祈年殿、长城等建筑造型巧克力','只介绍2026年报道中的创意商品，不把城市地标缩小模型当文物原件。'),
        ('kaorouji','烤肉季饭庄（什刹海店）','什刹海','shichahai','京味烤肉',['dp_kaorouji_album','shop_kaorouji_official','sh_bridges','sh_autumn'],'烤肉季','前海东沿14号','北京烤肉、清真炒菜与银锭桥畔饮食文化','点评记录为同址宴会厅，只作地址对照，不拆成第二家餐厅。1848年为品牌史，不等于现楼原构。'),
        ('qingyun','庆云楼饭庄（什刹海店）','什刹海','shichahai','京鲁风味饭庄',['dp_qingyun_album','dp_qingyun_photos'],'庆云楼','前海东沿22号庆云楼2层（银锭桥旁）','抓炒里脊、干炸小丸子与炙子烤肉','不依据顾客评论将现楼认定为清代原构，店史与建筑年代分开。点评人均123元为快照。'),
        ('yaerli','清真·鸦儿李记·涮肉（什刹海店）','什刹海','shichahai','铜锅涮肉',['dp_yaerli_photos','sh_autumn'],'鸦儿李记','什刹海周边；本轮可读来源未列完整门牌','涮肉、麻酱小料及北京清真餐饮','只按本分店整理，菜单推荐数不是菜品质量证明；不凭品牌名推断鸦儿胡同具体门牌。'),
        ('huguosi','护国寺小吃（地安门店）','什刹海','shichahai','北京小吃',['dp_huguosi_album'],'护国寺小吃','地安门外大街180号','地安门街区的北京小吃门店','与护国寺总店、新街口店区分；未取得本店完整实时菜单，不把别店菜品默认搬来。点评人均28元为快照。'),
        ('postoffice','大清邮政信柜（什刹海邮政所）','什刹海','yandai','邮政文创体验',['shop_postoffice'],'大清邮政信柜','烟袋斜街53号','邮政主题文创、明信片及印章体验','2011年开业、2021年报道重张的现代主题邮局，不称清代原建邮局；旧体验项目及展示藏品不承诺仍在。'),
        ('fuhuazhai','富华斋饽饽铺（护国新天地店）','周边衔接','nearby','传统糕点礼品',['dp_fuhuazhai_index'],'富华斋','护国寺街85号护国新天地商场一层底商（点评索引记载）','传统饽饽与糕点伴手礼','位于既有护国寺街周边衔接范围；只取得点评索引，未取得详情正文，不把店名中的宫廷宣传当历史身份认证。人均56元为索引快照。'),
    ]
    # 根据已有候选的真实键设置父级，避免凭名称创建重复整体。
    actual={r['name']:r['identity_key'] for r in rows['rows']}
    parents={'nanluo':next(r['identity_key'] for r in rows['rows'] if r['name']=='南锣鼓巷历史文化街区'),
             'shichahai':next(r['identity_key'] for r in rows['rows'] if r['identity_key']=='shichahai'),
             'yandai':next(r['identity_key'] for r in rows['rows'] if r['name']=='烟袋斜街'),
             'nearby':''}
    for key,name,area,parent,kind,ids,anchor,address,feature,note in shops:
        identity='shop_'+key
        if identity in existing:continue
        assert all(sid in saved and saved[sid]['status']=='ok' for sid in ids),(key,ids)
        rows['rows'].append(dict(identity_key=identity,name=name,area=area,parent_key=parents[parent],object_type_hint='node',source_ids=ids,
            anchor=anchor,editor_note=common+'\n'+note,entry_kind='特色商铺',shop_kind=kind,address=address,specialty=feature))
    if '本次增补南锣鼓巷' not in rows['scope']:rows['scope']+=' 本次增补南锣鼓巷、什刹海及已列周边衔接范围内的16家特色经营门店，商铺按具体分店识别。'
    dump('_candidates.json',rows)
    dump('_shops_selection.json',dict(count=len(shops),excluded=[
        dict(name='创可贴8南锣鼓巷店',reason='找到明确闭店报道，不作为当前商铺新增。',url='https://www.lifeweek.com.cn/h5/article/detail.do?artId=174649'),
        dict(name='敬人纸语／过客等旧攻略门店',reason='本轮未取得足够近期门店材料，不凭旧攻略补成当前可去的门店。'),
        dict(name='猫的天空之城／吉兔坊',reason='检索主要命中外地或范围外分店，不移植到南锣鼓巷。')],identity_policy='郭沫若故居与郭沫若纪念馆为同一对象，保留原序号48，不新增重复记录。'))
    print('shops_prepared',len(shops),'total_candidates',len(rows['rows']),'new_sources',len(saved)-57)

if __name__=='__main__':main()
