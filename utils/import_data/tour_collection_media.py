"""给完整清单附加有出处的浏览地图和照片；不派生路线、热区或到站承诺。"""
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def water_rings(element):
    """按outer/inner分组连接way端点；断环或缺成员时阻止发布。"""
    if element['type'] == 'way':
        groups = {'outer': [element.get('geometry', [])]}
    else:
        groups = {'outer': [], 'inner': []}
        for member in element.get('members', []):
            role = member.get('role')
            if role in groups:
                groups[role].append(member.get('geometry', []))
    result = []
    for role, pieces in groups.items():
        pieces = [[(p['lat'], p['lon']) for p in piece] for piece in pieces]
        if any(len(piece) < 2 for piece in pieces):
            raise ValueError(f"水体成员缺几何：{element['id']}")
        while pieces:
            chain = pieces.pop(0)
            while chain[0] != chain[-1]:
                for i, piece in enumerate(pieces):
                    if chain[-1] == piece[0]:
                        chain += piece[1:]
                        pieces.pop(i)
                        break
                    if chain[-1] == piece[-1]:
                        chain += list(reversed(piece))[1:]
                        pieces.pop(i)
                        break
                else:
                    raise ValueError(f"水体边界无法闭合：{element['id']} role={role}")
            if len(chain) < 4:
                raise ValueError('水体环少于三个顶点')
            result.append((chain, role))
    return result


def augment(data, config):
    import tour_build as base
    key = data['key']
    if not getattr(config, 'MEDIA_MANIFEST', None):
        return
    manifest_path = HERE / config.MEDIA_MANIFEST
    manifest = json.loads(manifest_path.read_text('utf-8'))
    osm_path = HERE / manifest['osm_file']
    osm = json.loads(osm_path.read_text('utf-8'))
    if sha(osm_path) != manifest['osm_sha256'] or sha(HERE / manifest['raw_file']) != osm['raw_sha256']:
        raise ValueError('OSM原始资料或规范化快照校验失败')
    elements = {(e['type'], e['id']): e for e in osm['elements']}
    south, west, north, east = osm['bbox']
    T = SimpleNamespace(ORIGIN=(south, west), ROTATE_DEG=0, PX_PER_M=.55)
    pr = base.Projection(T)
    pr.tx = 35
    pr.ty = (north-south)*base.M_PER_DEG_LAT*T.PX_PER_M+35
    w = math.ceil((east-west)*pr.mlon*T.PX_PER_M+70)
    h = math.ceil(pr.ty+35)
    layers = {k: [] for k in ['roads', 'paths', 'water', 'woods', 'walls', 'track', 'blocks']}
    # 水体用relation的完整环，避免把关系的组成way误当封闭湖面。
    for e in osm['elements']:
        tags = e.get('tags', {})
        layer = None
        if tags.get('natural') == 'water' or tags.get('water') in ('lake', 'pond'):
            if e['type'] == 'relation' and e['id'] not in manifest['water_relations']:
                continue  # 仅画已验证完整的三海；不猜框外北海等关系的缺失成员。
            layer = 'water'
        elif e['type'] == 'way' and tags.get('highway') in base.ROAD_KINDS | base.PATH_KINDS | {'living_street'}:
            if tags.get('area') != 'yes':
                layer = 'roads' if tags.get('highway') in base.ROAD_KINDS else 'paths'
        elif e['type'] == 'way' and tags.get('building') and tags.get('name'):
            layer = 'blocks'
        elif e['type'] == 'way' and tags.get('leisure') in ('park', 'garden'):
            layer = 'woods'
        if layer:
            rings = [(ring, 'outer') for ring in base.el_rings(e)]
            if layer == 'water':
                rings = water_rings(e)
            for ring, role in rings:
                closed = len(ring) > 3 and ring[0] == ring[-1]
                if not closed and layer == 'water':
                    raise ValueError(f"水体环未闭合，须核实并拼接来源几何后再发布：{e['type']}/{e['id']} role={role}")
                if layer in ('blocks', 'woods') and not closed:
                    continue
                pts = [pr.xy(*p) for p in ring]
                if layer == 'water':
                    signed = sum(x1*y2-x2*y1 for (x1,y1),(x2,y2) in zip(pts,pts[1:]))
                    if (signed > 0) != (role == 'outer'):
                        pts.reverse()  # SVG nonzero填充：内环反向保留岛屿。
                if layer in ('roads', 'paths'):
                    layers[layer].extend(base.path_d(line) for line in base.clip_line(pts, w, h, 0))
                else:
                    layers[layer].append(base.path_d(pts, close=True))
    by_seq = {p['stops'][0]: p for p in data['places']}
    used = set()
    for entry in manifest['positions']:
        seq = entry['seq']
        if seq in used or seq not in by_seq or by_seq[seq]['id'] != entry['identity_key']:
            raise ValueError(f'地图身份错误：{seq}')
        used.add(seq)
        e = elements[tuple(entry['osm'])]
        if e.get('tags', {}).get('name') != entry['osm_name']:
            raise ValueError(f'地图来源名称变化：{seq}')
        if entry['basis'] == 'street-midpoint':
            g = e['geometry']
            lengths = [math.hypot((q['lat']-p['lat'])*base.M_PER_DEG_LAT,
                                 (q['lon']-p['lon'])*pr.mlon) for p, q in zip(g, g[1:])]
            remaining = sum(lengths)/2
            for p, q, length in zip(g, g[1:], lengths):
                if length and remaining <= length:
                    t = remaining/length
                    lat, lon = p['lat']+t*(q['lat']-p['lat']), p['lon']+t*(q['lon']-p['lon'])
                    break
                remaining -= length
            else:
                raise ValueError('街巷没有有效长度')
            note = '街段参考点，非街巷入口；放大地图可查看。'
        elif entry['basis'] == 'feature-center':
            lat, lon = base.el_center(e)
            note = '建筑或院区轮廓中心，非检票入口。'
        elif entry['basis'] == 'poi':
            if e['type'] != 'node':
                raise ValueError('POI必须是来源中的独立节点')
            lat, lon = e['lat'], e['lon']
            note = '来源标记的位置，具体入口请按现场指示。'
        else:
            raise ValueError('未登记的坐标口径')
        if not (south < lat < north and west < lon < east):
            raise ValueError(f'地点超出地图资料范围：{seq}')
        x, y = pr.xy(lat, lon)
        by_seq[seq].update(x=round(x, 2), y=round(y, 2), lat=lat, lon=lon, lp='b',
                          min_zoom=entry.get('min_zoom', 0),
                          position=dict(basis=entry['basis'], osm=entry['osm'],
                                        source=dict(title='OpenStreetMap · '+entry['osm_name'],
                                                    url=f"https://www.openstreetmap.org/{e['type']}/{e['id']}"),
                                        note=note))
        # 无r（热区半径）：浏览地图不被原生定位解析，也不会触发到站。
    labels = []
    for typ, eid in manifest['labels']:
        e = elements[(typ, eid)]
        lat, lon = base.el_center(e)
        x, y = pr.xy(lat, lon)
        labels.append(dict(kind='road', t=dict(zh=e['tags']['name'], en=e['tags'].get('name:en', '')),
                           x=round(x, 1), y=round(y, 1)))
    data.update(map_mode='browse', canvas=dict(w=w, h=h, north=0, px_per_m=.55),
                proj=pr.as_json(), map={k: ' '.join(v) for k, v in layers.items()}, labels=labels,
                entrance=dict(x=w/2, y=h/2, name=dict(zh='地图中心', en='Map center')),
                attribution=dict(zh='地图 © OpenStreetMap 贡献者 · ODbL · 位置仅供浏览',
                                 en='© OpenStreetMap contributors · ODbL · map browsing'))
    photo_path = HERE / manifest['photo_manifest']
    photo_manifest = json.loads(photo_path.read_text('utf-8'))
    photos = photo_manifest['photos']
    seen = set()
    for photo in photos:
        seq = photo['seq']
        if (seq in seen or seq not in by_seq or photo['identity_key'] != by_seq[seq]['id']
                or photo['path'] != f'img/{key}/{seq}.jpg'
                or sha(base.TOUR_DIR / photo['path']) != photo['sha256']):
            raise ValueError(f'照片身份或哈希不符：{seq}')
        seen.add(seq)
        info = {k: photo[k] for k in ['caption', 'source', 'sha256', 'photographed_on', 'width', 'height']}
        for obj in [by_seq[seq], data['stops'][str(seq)]]:
            obj.update(photo=photo['path'], photo_info=info)
    for photo in photo_manifest.get('supplementary_photos', []):
        seq=photo['seq']
        if (seq not in by_seq or photo['identity_key']!=by_seq[seq]['id']
                or photo['path']!=f'img/{key}/{seq}-dp.jpg'
                or sha(base.TOUR_DIR/photo['path'])!=photo['sha256']):
            raise ValueError(f'补充照片身份或哈希不符：{seq}')
        info={k:photo[k] for k in ['caption','source','sha256','photographed_on','width','height']}
        data['stops'][str(seq)].setdefault('supplementary_photos',[]).append(dict(path=photo['path'],info=info))
    data['card']['cover'] = by_seq[manifest['cover_seq']]['photo']
    data['provenance'].update(media_sha256=sha(manifest_path), osm_sha256=sha(osm_path),
                              photos_sha256=sha(photo_path))
