"""以原Sonnet 5 medium复核主题GPS数据、浏览器生命周期及既有App桥接。"""
import json
import re
from nanluo_shichahai_itinerary_map_audit import HERE, ROOT, KEY, review
import nanluo_shichahai_pipeline as pipeline


FILES=['web_api/tour/app.js','web_api/app/tour_qa_llm.py','utils/import_data/tour_collection_experience.py',
       'utils/import_data/nanluo_shichahai_tour_data.py','utils/import_data/nanluo_shichahai_experience_data.py',
       'web_api/tour/data/nanluo_shichahai.json']


def main():
    pipeline.setup()
    data=json.loads((ROOT/f'web_api/tour/data/{KEY}.json').read_text());js=(ROOT/'web_api/tour/app.js').read_text()
    def fn(name):
        start=js.index('  function '+name+'(');nxt=re.search(r'^  function ',js[start+12:],re.M)
        return js[start:start+12+nxt.start()]if nxt else js[start:]
    names=['gpsData','gpsActive','gpsPlace','nativeTour','inArea','collectionView','layout','updateMe','updateMsgs','hitPlace','setPos','notify','startGeo','stopGeo','onFix','onGeoError']
    functions='\n'.join(fn(name)for name in names)
    bridge=js[js.index('  if (HOST) window.AriTour = {'):js.index('  function onHash(')]
    helper=(HERE/'tour_collection_experience.py').read_text();generator=helper[helper.index("    if getattr(config,'GPS_GUIDE',False):"):]
    engine=(ROOT/'android/app/src/main/java/top/snowmeet/tour/tour/GeofenceEngine.kt').read_text()
    engine=engine[engine.index('    fun onFix('):engine.index('        fun distance(')]
    nav=data['navigation']
    brief={k:nav[k]for k in ['area','entrance','radius_m','policy']}
    brief['places']=[dict(id=p['id'],seq=p['stops'][0],name=p['name']['zh'],r=p['r'])for p in nav['places']]
    user=('用户明确要求南锣鼓巷+什刹海四条线路像宛平城、伪满皇宫一样提供GPS导览。当前实现复用当前位置、跟随地图、靠近点提醒；不是新接外部地图API。'
          '原100条介绍、V3、Excel、37处浏览位置、照片、4×4路线几何顺序与时间不变。独立navigation保存21处已审步骤公共街道参考点、OSM线段参数；无借用建筑中心作新入口，提醒称“附近”。25米半径是明确标注的估计，精度门槛30米与1.2离开迟滞沿用现有机制。覆盖范围为OSM资料框，明确非行政边界。'
          'root mode仍collection、routes为空、无root area/r，未知条目不定位。选择主题后才启用GPS，回清单/主题页停止网页监听并HOST.leave；默认37点景点地图继续只浏览。'
          '原生安装包的TourData.parse不检查mode，网页nativeTour把navigation三项area/entrance/places覆盖到副本，key/proj/canvas/stops/card保持原样；从原生状态回传到网页，不同时启动网页GPS。原生生产代码未改，不重打APK；网络定位不触发到站。'
          '新浏览器GPS场景通过真实navigator.watchPosition+CDP输入验证：到附近、精度40米不新提醒、5米恢复、重复位置和超时恢复不重复、范围外灰点、拒绝授权、离开监听清理。App桥接模拟通过，21处payload供原parser解析；纯Kotlin适配测试正在运行。模型无图片像素，不称视觉或真机验收。完整21场景正在回归。'
          '只审新GPS数据与生命周期/桥接实际问题，不重审原地图、照片、商铺或评级。提供完整相关函数；原生onFix及parser原样供核对。\n'
          '\nDATA GENERATOR\n'+generator+'\nNAV DATA CONTRACT\n'+json.dumps(brief,ensure_ascii=False)+
          '\nCURRENT WEB FUNCTIONS\n'+functions+'\nHOST STATE BRIDGE\n'+bridge+
          '\nNATIVE PARSER (UNCHANGED)\n'+(ROOT/'android/app/src/main/java/top/snowmeet/tour/tour/TourData.kt').read_text()+
          '\nNATIVE ENGINE (UNCHANGED)\n'+engine+
          '\nQA POLICY INTEGRATION\n'+"if museum.get('navigation'): parts.append('## GPS导览\\n'+museum['navigation']['policy'])")
    review('你是独立GPS发布审查者。只根据提供的数据/当前完整函数查具体缺陷，考虑用户已授权GPS和现有机制。重要问题须指出可达触发路径；无实际问题findings为空。不要把估计半径或资料框误当宣称入口/行政边界。',
           user,'audit_collection_gps','gps_audit',scope='21 sourced vicinity points, Web GPS lifecycle and existing native payload compatibility',reviewed_files=FILES)


if __name__=='__main__':main()
