"""把已审计的本地资料包发布为共享导览JSON；不要求先重灌全库。

复用tour_build的投影与OSM绘图。策划路线沿公开OSM道路连接，原始摘录、
评级和审计按稳定序号保留；包含关系与费用由景区配置明确登记。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import heapq
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_cover(key, seqs, rows, photos, explicit):
    if key in explicit:
        seq = explicit[key]
        if seq not in seqs or seq not in photos:
            raise ValueError(f'{key}的封面必须是本地点已收录的图片')
        return seq
    return next((s for s in seqs if rows[s]['parent_key'] == '' and s in photos), None)


def meters(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    return 12742000 * math.asin(math.sqrt(math.sin(dp / 2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl / 2)**2))


class WalkingGraph:
    def __init__(self, osm, D, free=False):
        self.nodes = {e['id']: (e['lat'], e['lon']) for e in osm['elements'] if e['type'] == 'node'}
        self.adj = {}
        for el in osm['elements']:
            t = el.get('tags', {})
            if (el['type'] != 'way' or t.get('highway') not in D.ALLOW_HIGHWAYS
                    or el['id'] in D.DENIED_WAYS or (free and el['id'] in D.PAID_WAYS)
                    or t.get('access') in {'private', 'no'} or t.get('foot') == 'no'
                    or t.get('area') == 'yes' or '城墙' in t.get('name', '')):
                continue
            for a, b in zip(el['nodes'], el['nodes'][1:]):
                if a not in self.nodes or b not in self.nodes:
                    continue
                cost = meters(self.nodes[a], self.nodes[b])
                self.adj.setdefault(a, []).append((b, cost, el['id']))
                self.adj.setdefault(b, []).append((a, cost, el['id']))
        self.max_connector = D.CONNECTOR_MAX_M

    def snap(self, point):
        n = min(self.adj, key=lambda n: meters(point, self.nodes[n]))
        if meters(point, self.nodes[n]) > self.max_connector:
            raise ValueError(f'{point} 距已记录公开步道超过{self.max_connector}米，不能编造连接')
        return n

    def leg(self, a, b):
        if a == b:
            return [a], 0, []
        start, end = self.snap(a), self.snap(b)
        queue, best, previous = [(0, start)], {start: 0}, {}
        while queue:
            cost, n = heapq.heappop(queue)
            if cost != best[n]:
                continue
            if n == end:
                break
            for nxt, length, way in self.adj[n]:
                trial = cost + length
                if trial < best.get(nxt, float('inf')):
                    best[nxt] = trial
                    previous[nxt] = (n, way)
                    heapq.heappush(queue, (trial, nxt))
        if end not in best:
            raise ValueError(f'OSM公开道路不连通：{a} -> {b}')
        chain, ways = [end], []
        while chain[-1] != start:
            prev, way = previous[chain[-1]]
            chain.append(prev)
            ways.append(way)
        points = [a] + [self.nodes[n] for n in reversed(chain)] + [b]
        length = best[end] + meters(a, self.nodes[start]) + meters(b, self.nodes[end])
        return points, length, list(reversed(ways))


def build(mk, D, T, base):
    source_path = HERE / D.DATA_PACKAGE
    package = json.loads(source_path.read_text('utf-8'))
    translation = json.loads((HERE / D.TRANSLATIONS).read_text('utf-8'))
    access_path = HERE / D.ACCESS
    access = json.loads(access_path.read_text('utf-8'))
    rating_path = HERE / package['rating_file']
    rating = json.loads(rating_path.read_text('utf-8'))
    manifest = json.loads((HERE / f'{mk}_audit_manifest.json').read_text('utf-8'))
    source_sha = sha(HERE / f'{mk}_site_data.json')
    if not all(x['input_sha256'] == source_sha for x in [package, translation, rating, manifest]):
        raise ValueError('资料包、评分、审计、翻译的来源版本不一致')
    if manifest['rating_sha256'] != sha(rating_path):
        raise ValueError('当前评分版本未经对应审计')
    ratings = {r['seq']: r for r in rating['results']}
    audits = {r['seq']: r for r in map(json.loads, (HERE / f'{mk}_audit1_slim.jsonl').read_text('utf-8').splitlines())}
    rows = {r['source_seq']: r for r in package['rows']}
    if len(rows) != len(package['rows']) or any(r['rating'] != ratings[s] or r['audit'] != audits[s] for s, r in rows.items()):
        raise ValueError('资料包与当前评分/审计不一致或序号重复')
    assigned = [s for p in D.PLACES for s in p[6]]
    if len(assigned) != len(set(assigned)) or set(assigned) != set(rows):
        raise ValueError('必须为每条资料登记且仅登记一个所在地点')

    def en(text):
        return translation['values'][text]['en']

    tour_translation_path = HERE / D.TOUR_TRANSLATIONS
    tour_translation = json.loads(tour_translation_path.read_text('utf-8'))

    def tour_en(text):
        return tour_translation['values'][text]['en']

    def l2(pair):
        return dict(zh=pair[0], en=tour_en(pair[0]))

    osm_path = HERE / f'{mk}_osm_data.json'
    osm = json.loads(osm_path.read_text('utf-8'))
    elements = {f"{e['type']}/{e['id']}": e for e in osm['elements']}
    proj = base.Projection(T)
    south, west, north, east = T.AREA_BBOX
    ring = [(south, west), (north, west), (north, east), (south, east), (south, west)]
    raw = [proj.xy(*p) for p in ring]
    pad = T.CANVAS_MARGIN_PX + T.AREA_BUFFER_M * T.PX_PER_M
    proj.tx, proj.ty = pad - min(p[0] for p in raw), pad - min(p[1] for p in raw)
    area = [proj.xy(*p) for p in ring]
    width, height = math.ceil(max(p[0] for p in area) + pad), math.ceil(max(p[1] for p in area) + pad)
    places, stops, coordinates = [], {}, {}
    photo_manifest_path = HERE / D.PHOTO_MANIFEST if getattr(D, 'PHOTO_MANIFEST', None) else None
    photo_manifest = json.loads(photo_manifest_path.read_text('utf-8')) if photo_manifest_path else {}
    photo_entries = {p['seq']: p for p in photo_manifest.get('photos', [])}
    if len(photo_entries) != len(photo_manifest.get('photos', [])) or not set(photo_entries) <= set(rows):
        raise ValueError('图片序号重复或不属于当前资料包')
    for seq, entry in photo_entries.items():
        if entry['identity_key'] != rows[seq]['identity_key'] or entry['path'] != base.photo_of(mk, seq):
            raise ValueError(f'图片与条目身份不一致：{seq}')
        if sha(base.TOUR_DIR / entry['path']) != entry['sha256']:
            raise ValueError(f'图片文件校验失败：{seq}')

    def photo(seq):
        return photo_entries[seq]['path'] if seq in photo_entries else None

    def photo_info(seq):
        p = photo_entries.get(seq)
        return {k: p[k] for k in ['caption', 'source', 'sha256', 'photographed_on']} if p else None
    for key, zh, eng, osm_id, radius, lp, seqs in D.PLACES:
        lat, lon = base.el_center(elements[osm_id])
        x, y = proj.xy(lat, lon)
        if not base.in_poly((x, y), area):
            raise ValueError(f'{key} 不在导览范围内')
        coordinates[key] = (lat, lon)
        # 资料图只用于它所对应的整体，不把整体照片下放到碑刻、城门等子节点。
        cover_seq = select_cover(key, seqs, rows, photo_entries, getattr(D, 'PLACE_PHOTOS', {}))
        places.append(dict(id=key, name=dict(zh=zh, en=tour_en(zh)), lat=lat, lon=lon,
                           x=round(x, 1), y=round(y, 1), r=radius*T.PX_PER_M, r_m=radius,
                           lp=lp, osm=osm_id, photo=photo(cover_seq), photo_info=photo_info(cover_seq), stops=seqs))
        for seq in seqs:
            r = rows[seq]
            included = D.INCLUDED_IN.get(seq)
            note = r['editor_note']
            note_en = en(note)
            if included or seq not in D.DWELL:
                note += D.ATTACHMENT_NOTE
                note_en += tour_en(D.ATTACHMENT_NOTE)
            status = D.STATUS.get(seq, D.DEFAULT_STATUS)
            stops[str(seq)] = dict(seq=seq, place=key, name=dict(zh=r['name'], en=en(r['name'])),
                tier=r['rating']['tier'], core=r['rating']['core'], dwell=D.DWELL.get(seq, 0),
                included_in=included, status=dict(zh=status, en=tour_en(status)),
                intro=[p.strip() for p in re.split(r'[\r\n]+', r['description']) if p.strip()],
                source=dict(zh='官方发布原文摘录；逐条出处见下方', en='Official source excerpts; references below'),
                sources=[dict(title=e['source_id'], url=e['url']) for e in r['evidence']],
                borrowed=dict(zh=note, en=note_en),
                photo=photo(seq), photo_info=photo_info(seq), objects=[],
                review=r['audit'].get('error_note_zh') if r['needs_review'] else None)

    routes = []
    for definition in D.ROUTES:
        selected = definition['stops']
        if len(selected) != len(set(selected)) or not set(selected) <= set(rows):
            raise ValueError('路线序号重复或不存在')
        graph = WalkingGraph(osm, D, free=definition['ticket_cny'] == 0)
        keys = [D.ENTRANCE] + [stops[str(s)]['place'] for s in selected] + [D.ENTRANCE]
        legs, line, geographic, way_ids = [], [], [], []
        for a, b in zip(keys, keys[1:]):
            points, distance, ways = graph.leg(coordinates[a], coordinates[b])
            line += [[round(v, 1) for v in proj.xy(*p)] for p in points]
            geographic += [list(p) for p in points]
            way_ids += ways
            legs.append(dict(start=a, end=b, meters=round(distance, 1), minutes=round(distance/D.WALK_M_PER_MIN, 2)))
        distance = sum(leg['meters'] for leg in legs)
        walk = round(distance / D.WALK_M_PER_MIN, 1)
        stay = sum(stops[str(s)]['dwell'] for s in selected)
        routes.append(dict(id=definition['id'], label=l2(definition['label']), budget=definition['budget'],
            stops=selected, ticket_cny=definition['ticket_cny'], fee=l2(definition['fee']),
            note=l2(definition['note']), sources=access['sources'],
            total=round(stay+walk, 1), stay=stay, walk=walk, distance_m=round(distance),
            path=line, path_wgs84=geographic, legs=legs, way_ids=sorted(set(way_ids))))
        if stay + walk > definition['budget']:
            raise ValueError('路线超出策划时间预算')

    layers, _, _ = base.build_map(osm, T, proj, area, width, height)
    # 导览范围框不能画成“文物城墙”；只画OSM实际城墙几何。
    layers['walls'] = ' '.join(base.path_d([proj.xy(p['lat'], p['lon']) for p in el['geometry']])
                              for el in osm['elements'] if el['type'] == 'way' and el.get('tags', {}).get('barrier') == 'wall')
    entrance = next(p for p in places if p['id'] == D.ENTRANCE)
    data = dict(key=mk, generated=dt.date.today().isoformat(), name=l2(T.NAME),
        card={**{k: l2(T.CARD[k]) for k in ['city', 'district', 'type', 'short', 'desc', 'hours_note']},
              'hours': T.CARD['hours'], 'cover': photo(1)},
        opening=dict(zh=access['opening']['zh'], en=tour_en(access['opening']['zh'])),
        planning=dict(zh=access['planning']['zh'], en=tour_en(access['planning']['zh'])),
        access_sources=access['sources'],
        canvas=dict(w=width, h=height, north=T.ROTATE_DEG, px_per_m=T.PX_PER_M), proj=proj.as_json(),
        area=dict(poly=[[round(x, 1), round(y, 1)] for x, y in area], buffer=T.AREA_BUFFER_M*T.PX_PER_M,
                  osm=None, basis='editorial-tour-envelope'),
        walk=dict(detour=1, m_per_min=D.WALK_M_PER_MIN, method='osm-walking-graph'),
        entrance={k: entrance[k] for k in ['lat', 'lon', 'x', 'y']}, map=layers, labels=[], places=places,
        stops=stops, routes=routes, default_route=T.DEFAULT_ROUTE,
        attribution=dict(zh='地图 © OpenStreetMap 贡献者 · 连线仅供步行顺序参考', en='© OpenStreetMap contributors; orientation only'),
        provenance=dict(package=D.DATA_PACKAGE, package_sha256=sha(source_path), source_sha256=source_sha,
                        rating_sha256=sha(rating_path), access_sha256=sha(access_path), osm_sha256=sha(osm_path),
                        tour_translations_sha256=sha(tour_translation_path),
                        checked_on=access['checked_on'], business_database_written=False))
    if photo_manifest_path:
        data['provenance']['photos_sha256'] = sha(photo_manifest_path)
    data['entrance']['name'] = l2(D.ENTRANCE_NAME)
    return data, [f'{mk}: {len(places)} 个有依据的到达点；{len(stops)} 条资料。'] + [
        f"{r['label']['zh']}: {r['total']}分钟（停留{r['stay']} + 步行{r['walk']}）；参考门票{r['ticket_cny']}元" for r in routes]
