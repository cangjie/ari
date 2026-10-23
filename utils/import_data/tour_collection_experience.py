"""清单的商铺标签与主题步行方案；与原生到站路线分开。"""
import heapq
import json
import math
from pathlib import Path
from tour_package_build import meters

HERE = Path(__file__).resolve().parent


def inside(point, polygon):
    x,y=point; hit=False
    for (a,b),(c,d) in zip(polygon, polygon[1:]+polygon[:1]):
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:hit=not hit
    return hit


class StreetGraph:
    """只求室外接驳；排除院区内部步道，不穿收费馆或学校抄近路。"""
    def __init__(self, osm):
        self.nodes={e['id']:(e['lat'],e['lon']) for e in osm['elements'] if e['type']=='node'}
        self.ways={};self.adj={};self.references={}
        compounds=[]
        for e in osm['elements']:
            tags=e.get('tags',{})
            if e['type']=='way' and (tags.get('tourism')=='museum' or tags.get('amenity') in ['school','university','place_of_worship']):
                ring=[(q['lat'],q['lon']) for q in e.get('geometry',[])]
                if len(ring)>3 and ring[0]==ring[-1]:compounds.append(ring)
        allowed={'footway','pedestrian','path','steps','residential','service','tertiary','secondary','primary','unclassified','living_street'}
        for e in osm['elements']:
            tags=e.get('tags',{})
            if (e['type']!='way' or tags.get('highway') not in allowed or tags.get('area')=='yes'
                    or tags.get('access') in ['private','no','customers'] or tags.get('foot') in ['private','no']
                    or tags.get('tunnel')=='yes' or tags.get('indoor')=='yes'):
                continue
            ids=e.get('nodes',[])
            if not ids or any(n not in self.nodes for n in ids):continue
            pairs=[]
            for a,b in zip(ids,ids[1:]):
                pa,pb=self.nodes[a],self.nodes[b]
                middle=((pa[0]+pb[0])/2,(pa[1]+pb[1])/2)
                if any(inside(middle,poly) for poly in compounds):continue
                cost=meters(pa,pb)
                pairs.append((a,b,cost))
            if pairs:
                self.ways[e['id']]=e
                for a,b,cost in pairs:
                    self.adj.setdefault(a,[]).append((b,cost,e['id']))
                    self.adj.setdefault(b,[]).append((a,cost,e['id']))

    def nearest(self, point, names=None):
        # 道路可能只有两个端点；不能把相邻胡同都吸到同一个路口。
        # 在原道路线段上插入计算节点，保留way及线段参数，不伪称OSM原节点。
        mlon=111320*math.cos(math.radians(point[0]));mlat=111320
        closest=None
        for a,edges in list(self.adj.items()):
            for b,cost,way in edges:
                if a>b or (names and self.ways[way].get('tags',{}).get('name') not in names):continue
                pa,pb=self.nodes[a],self.nodes[b]
                dx=(pb[1]-pa[1])*mlon;dy=(pb[0]-pa[0])*mlat
                length=dx*dx+dy*dy
                t=max(0,min(1,((point[1]-pa[1])*mlon*dx+(point[0]-pa[0])*mlat*dy)/length)) if length else 0
                projected=(pa[0]+t*(pb[0]-pa[0]),pa[1]+t*(pb[1]-pa[1]))
                candidate=(meters(point,projected),a,b,way,t,projected)
                if closest is None or candidate[0]<closest[0]:closest=candidate
        if closest is None:raise ValueError(f'缺少已记录公开街道 {names}')
        distance,a,b,way,t,projected=closest
        if t<1e-9:return a
        if t>1-1e-9:return b
        node=min(0,min(self.nodes))-1
        self.nodes[node]=projected
        self.references[node]=dict(way_id=way,segment=[list(self.nodes[a]),list(self.nodes[b])],fraction=t)
        self.adj[a]=[e for e in self.adj[a] if not(e[0]==b and e[2]==way)]
        self.adj[b]=[e for e in self.adj[b] if not(e[0]==a and e[2]==way)]
        da,db=meters(self.nodes[a],projected),meters(projected,self.nodes[b])
        self.adj[a].append((node,da,way));self.adj[b].append((node,db,way))
        self.adj[node]=[(a,da,way),(b,db,way)]
        return node

    def leg(self, start, end):
        queue=[(0,start)];best={start:0};prev={}
        while queue:
            cost,node=heapq.heappop(queue)
            if cost!=best[node]:continue
            if node==end:break
            for nxt,length,way in self.adj[node]:
                trial=cost+length
                if trial<best.get(nxt,float('inf')):
                    best[nxt]=trial;prev[nxt]=(node,way);heapq.heappush(queue,(trial,nxt))
        if end not in best:raise ValueError(f'主题线路的公共道路不连通 {start}→{end}')
        chain=[end];ways=[]
        while chain[-1]!=start:
            node,way=prev[chain[-1]];chain.append(node);ways.append(way)
        return list(reversed(chain)),best[end],list(reversed(ways))


def augment(data, config):
    filename=getattr(config,'EXPERIENCE_MANIFEST',None)
    if not filename:return
    import tour_build as base
    from tour_collection_media import sha
    manifest=json.loads((HERE/filename).read_text())
    labels_path=HERE/manifest['labels_file']
    labels=json.loads(labels_path.read_text())
    for row in labels['items']:
        stop=data['stops'][str(row['seq'])]
        if stop['kind']!='shop' or stop['place']!=row['identity_key']:raise ValueError('商铺标签身份不符')
        stop.update(shop_category=row['category'],shop_tags=row['tags'],shop_label_note=row['reason'])
    data['shop_label_policy']=labels['policy']
    osm=json.loads((HERE/manifest['osm_file']).read_text())
    graph=StreetGraph(osm)
    stations={};connectors={}
    for station in manifest['stations']:
        node=station['osm_node'];point=graph.nodes[node];snap=graph.nearest(point)
        distance=meters(point,graph.nodes[snap])
        if distance>40:raise ValueError(f'地铁站室外接驳超过40米 {station["id"]}: {distance}')
        stations[station['id']]={**station,'point':list(point),'street_node':snap,'connector_m':round(distance,1)}
        connectors[station['id']]=distance
    places={p['stops'][0]:p for p in data['places']}
    themes=[]
    proj=data['proj']
    def xy(point):
        lat,lon=point;e=(lon-proj['lon0'])*proj['mlon'];n=(lat-proj['lat0'])*proj['mlat']
        return [round(proj['a']*e+proj['b']*n+proj['tx'],2),round(proj['c']*e+proj['d']*n+proj['ty'],2)]
    for theme in manifest['themes']:
        steps=[]
        for item in theme['steps']:
            place=places[item['seq']]
            if not place.get('position'):raise ValueError(f'主题主站缺来源位置 {item["seq"]}')
            names=item.get('streets')
            if not names:raise ValueError(f'主题主站必须显式登记公共街道名称 {item["seq"]}')
            node=graph.nearest((place['lat'],place['lon']), names)
            if meters((place['lat'],place['lon']),graph.nodes[node])>260:raise ValueError('主题街道参考点离对应场所太远')
            steps.append({**item,'name':data['stops'][str(item['seq'])]['name'],
                          'street_node':node,'point':list(graph.nodes[node]),
                          'street_reference':graph.references.get(node,dict(osm_node=node)),
                          'reference_note':'路线到附近公共街道参考点；不代表场馆或商铺入口。'})
        variants=[]
        for station in stations.values():
            end=stations[theme['end_station']]
            sequence=[station['street_node']]+[s['street_node'] for s in steps]+[end['street_node']]
            legs=[];points=[station['point']];all_ways=set()
            total=connectors[station['id']]+connectors[end['id']]
            for a,b in zip(sequence,sequence[1:]):
                ids,distance,ways=graph.leg(a,b);total+=distance;all_ways.update(ways)
                points += [graph.nodes[n] for n in ids]
                legs.append(dict(meters=round(distance),minutes=round(distance/60,1),way_ids=sorted(set(ways))))
            points.append(end['point'])
            walk=round(round(total)/60);stay=sum(s['minutes'] for s in steps)
            variants.append(dict(start_station=station['id'],end_station=end['id'],meters=round(total),
                                 walk_minutes=walk,stay_minutes=stay,total_minutes=walk+stay,
                                 path=[xy(p) for p in points],path_wgs84=[list(p) for p in points],
                                 way_ids=sorted(all_ways),legs=legs))
        themes.append({**theme,'steps':steps,'variants':variants})
    data.update(itineraries=themes,itinerary_stations=list(stations.values()),itinerary_policy=manifest['policy'])
    data['provenance'].update(experience_sha256=sha(HERE/filename),shop_labels_sha256=sha(labels_path))
