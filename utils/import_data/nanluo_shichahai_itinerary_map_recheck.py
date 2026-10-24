"""针对线路图状态互斥意见及短起终点标记复核，不重传原有地图几何。"""
import json
import re
import nanluo_shichahai_pipeline as pipeline
from nanluo_shichahai_itinerary_map_audit import HERE, ROOT, KEY, review


def main():
    pipeline.setup()
    js=(ROOT/'web_api/tour/app.js').read_text()
    def fn(name):
        start=js.index('  function '+name+'(');nxt=re.search(r'^  function ',js[start+12:],re.M)
        return js[start:start+12+nxt.start()]if nxt else js[start:]
    def between(a,b):return js[js.index(a):js.index(b)]
    prior=json.loads((HERE/f'{KEY}_itinerary_map_audit.json').read_text())['result']
    museums=[json.loads(path.read_text())for path in (ROOT/'web_api/tour/data').glob('*.json')]
    user=('复核首轮状态互斥意见及两项显示修正。首轮声称当前可先点普通路线再点主题复现，但当前南锣什刹海routes=[]；其它两个景区没有itineraries，openMuseum每次重建st，themeId=null，故该跨类型序号冲突并非当前可重现缺陷。'
          '仍按建议加了状态互斥：主题页及地图chips的两个主题入口都先routeId=none；collectionView原本就stopTour。普通路线分支先清themeId并重建底图，再设routeId。'
          '另将互动地图边缘容易截断的“地铁起终点”长标记缩为S/E；详情先列完整的S起点与E终点站名。图和PNG不变。'
          '本地92项pytest及修改前20场景已通过；修改后完整20场景正在再跑。只复核本项闭环及相关显示逻辑，不重审16图生成器或原历史资料。\nPRIOR\n'+json.dumps(prior,ensure_ascii=False)+
          '\nCURRENT DATA MODES\n'+json.dumps([dict(key=m['key'],routes=len(m['routes']),themes=len(m.get('itineraries',[])))for m in museums],ensure_ascii=False)+
          '\nSTATE INIT\n'+between('    st = {','    restore();')+
          '\nTHEME ENTRY\n'+between('    $("collection-themes").addEventListener("click"','    $("collection-search").addEventListener')+
          '\nMAP CHIPS\n'+between('    $("chips").addEventListener','    $("locate").addEventListener')+
          '\nCOMPLETE RELATED FUNCTIONS\n'+fn('collectionView')+fn('themeSelection')+fn('route')+fn('updateSpots')+fn('updateRoute')+
          '\nSHORT ENDPOINT LABELS\n'+between('    var themed = themeSelection();\n    if (themed) {','    if (!isCollection()) addLabel'))
    review('你是独立发布复核者。用当前实际数据和完整相关函数判断具体意见是否解决，不假定当前不存在的数据组合。没有新问题则findings为空。',user,'audit_itinerary_map_recheck','itinerary_map_recheck')


if __name__=='__main__':main()
