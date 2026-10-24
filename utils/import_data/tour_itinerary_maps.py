"""从共享导览 JSON 生成有顺序、地铁起终点和图例的独立 SVG 路线图。

tour_build.py 后运行本脚本，再用 tour_itinerary_maps.mjs 栅格化 PNG。
--check 只读核对 SVG 内容与 PNG 哈希；不重新检索、不改路线和原景点位置。
"""
import argparse
import hashlib
import json
import math
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOUR = HERE.parents[1] / 'web_api/tour'
COLORS = ['#916326', '#3f7063', '#8b4b42', '#385f83']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(data, point):
    p = data['proj']; lat, lon = point
    e = (lon-p['lon0'])*p['mlon']; n = (lat-p['lat0'])*p['mlat']
    return [p['a']*e+p['b']*n+p['tx'], p['c']*e+p['d']*n+p['ty']]


def render(data, theme, variant, color):
    """底图、线与参考点用同一相似投影，完整路线自动适配到图框。"""
    width, height = 1200, 1600
    box = (45, 250, 1110, 820)
    path = variant['path']
    left, right = min(p[0] for p in path)-65, max(p[0] for p in path)+65
    top, bottom = min(p[1] for p in path)-65, max(p[1] for p in path)+65
    k = min(box[2]/(right-left), box[3]/(bottom-top))
    ox = box[0]+(box[2]-(right-left)*k)/2-left*k
    oy = box[1]+(box[3]-(bottom-top)*k)/2-top*k
    xy = lambda p: [round(ox+p[0]*k, 2), round(oy+p[1]*k, 2)]
    stations = {s['id']:s for s in data['itinerary_stations']}
    start, end = stations[variant['start_station']], stations[variant['end_station']]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           f'<title id="title">{escape(theme["name"])} · {escape(start["name"])}出发</title>',
           '<desc id="desc">数字为游览顺序，S为地铁起点，E为地铁终点。路线沿已记录的公共道路；标点为附近街道参考点，并非检票入口。</desc>',
           '<style>text{font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;fill:#282e2b}.small{font-size:21px}.muted{fill:#65716b}.num{font-size:23px;fill:white;font-weight:700;text-anchor:middle;dominant-baseline:central}</style>',
           '<rect width="1200" height="1600" fill="#faf8f3"/>',
           '<text x="45" y="49" font-size="21" letter-spacing="3" class="muted">ARI TRAVEL / 北京南锣鼓巷 · 什刹海</text>',
           f'<text x="45" y="112" font-size="45" font-weight="700">{escape(theme["name"])}</text>',
           f'<text x="45" y="157" font-size="25">S {escape(start["name"])} → E {escape(end["name"])}'+('（同站往返）' if start['id']==end['id'] else '')+'</text>',
           f'<text x="45" y="198" font-size="24" class="muted">约 {variant["meters"]/1000:.1f} 公里 · 估计 {variant["total_minutes"]//60}小时{variant["total_minutes"]%60}分（停留 {variant["stay_minutes"]} + 步行 {variant["walk_minutes"]} 分钟）</text>',
           f'<rect x="45" y="250" width="1110" height="820" rx="14" fill="#f0f2ed"/>',
           '<defs><clipPath id="map-clip"><rect x="45" y="250" width="1110" height="820" rx="14"/></clipPath></defs>',
           '<g clip-path="url(#map-clip)">',
           f'<g transform="translate({ox:.6f} {oy:.6f}) scale({k:.8f})">']
    for layer, attrs in [('woods','fill="#e3ebdf"'), ('water','fill="#c9dee2" stroke="#a4c0c7" stroke-width="1"'),
                         ('blocks','fill="#dedfd7" stroke="#c4c9bf" stroke-width=".7"'),
                         ('roads','fill="none" stroke="#fffefa" stroke-width="6"'),
                         ('paths','fill="none" stroke="#ced4ca" stroke-width="1.2"')]:
        out.append(f'<path d="{data["map"].get(layer, "")}" {attrs}/>')
    out.append('</g>')
    for label in data['labels']:
        x,y=xy([label['x'], label['y']])
        if box[0]+65<x<box[0]+box[2]-65 and box[1]+30<y<box[1]+box[3]-30:
            out.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-size="23" class="muted">{escape(label["t"]["zh"])}</text>')
    route = 'M'+' L'.join(f'{x} {y}' for x,y in map(xy,path))
    out += [f'<path id="route-halo" d="{route}" fill="none" stroke="#fffefa" stroke-width="12" stroke-linejoin="round" stroke-linecap="round"/>',
            f'<path id="walking-route" d="{route}" fill="none" stroke="{color}" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>']
    # 少量箭头按原折线前进方向放置；不把全部路口都画成箭头。
    lengths=[math.dist(a,b) for a,b in zip(path,path[1:])]; total=sum(lengths)
    for frac in [.2,.45,.7,.9]:
        target=total*frac; sofar=0
        for i,length in enumerate(lengths):
            if length and sofar+length>=target:
                a,b=path[i:i+2]; f=(target-sofar)/length
                x,y=xy([a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f])
                angle=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
                out.append(f'<path d="M-9 -7 L0 0 L-9 7" transform="translate({x} {y}) rotate({angle})" fill="none" stroke="white" stroke-width="3"/>')
                break
            sofar+=length
    for order,step in enumerate(theme['steps'],1):
        x,y=xy(project(data,step['point']))
        out.append(f'<g data-order="{order}" data-seq="{step["seq"]}" data-x="{x}" data-y="{y}"><title>{order}. {escape(step["name"]["zh"])}</title><circle cx="{x}" cy="{y}" r="22" fill="{color}" stroke="white" stroke-width="3"/><text class="num" x="{x}" y="{y}">{order}</text></g>')
    endpoints=[('S/E',path[0])] if start['id']==end['id'] else [('S',path[0]),('E',path[-1])]
    for label,point in endpoints:
        x,y=xy(point)
        out.append(f'<g data-station="{label}"><rect x="{x-29}" y="{y-23}" width="58" height="46" rx="8" fill="#283e36" stroke="white" stroke-width="3"/><text class="num" x="{x}" y="{y}" style="font-size:20px">{label}</text></g>')
    out += ['</g>', '<path d="M1110 327 V277 M1102 291 L1110 277 L1118 291" fill="none" stroke="#344f47" stroke-width="3"/><text x="1110" y="352" text-anchor="middle" font-size="22">北</text>']
    # 与地图相同投影比例的标尺；不是截图缩放后写死的距离。
    scale_m=200 if 200*data['canvas']['px_per_m']*k<220 else 100
    scale_px=scale_m*data['canvas']['px_per_m']*k
    out += [f'<path d="M75 1020 v10 h{scale_px:.2f} v-10" fill="none" stroke="#344f47" stroke-width="3"/><text x="75" y="1010" class="small">{scale_m} 米</text>',
            f'<text x="45" y="1113" font-size="25" font-weight="700">游览顺序 · {len(theme["steps"])}站</text>',
            '<text x="1155" y="1113" text-anchor="end" class="small muted">圆点为附近街道参考点</text>']
    # 两列保留足够宽度给原始全名；最长名称分两行，不截断身份。
    for index,step in enumerate(theme['steps']):
        x=45+(index%2)*570; y=1156+(index//2)*64
        out.append(f'<circle cx="{x+17}" cy="{y-5}" r="17" fill="{color}"/><text x="{x+17}" y="{y-5}" class="num" style="font-size:19px">{index+1}</text>')
        name=step['name']['zh']; parts=[name[i:i+20] for i in range(0,len(name),20)]
        for j,part in enumerate(parts):
            out.append(f'<text x="{x+43}" y="{y+j*25}" font-size="23">{escape(part)}</text>')
    out += ['<path d="M45 1470 H1155" stroke="#ccd3c8"/>',
            '<text x="45" y="1504" class="small muted">公共道路步行示意；出入口、过街设施、场所开放与预约请以现场为准。</text>',
            '<text x="45" y="1536" class="small muted">时长未计用餐和排队。地铁出口编号据 OSM，临时封闭以现场为准。</text>',
            '<text x="45" y="1572" font-size="19" class="muted">地图 © OpenStreetMap 贡献者 · ODbL · openstreetmap.org/copyright</text>',
            '<text x="1155" y="1572" text-anchor="end" font-size="19" class="muted">tour.snowmeet.top</text>', '</svg>']
    return '\n'.join(out)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--museum',required=True); parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    data_path=TOUR/'data'/f'{args.museum}.json'; data=json.loads(data_path.read_text())
    manifest_path=HERE/f'{args.museum}_itinerary_maps.json'
    previous=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    maps=[]
    for index,theme in enumerate(data['itineraries']):
        for variant in theme['variants']:
            svg=render(data,theme,variant,COLORS[index%len(COLORS)])
            path=TOUR/variant['map_assets']['svg']
            if args.check:
                assert path.read_text()==svg, path
            else:
                path.write_text(svg)
            maps.append(dict(theme=theme['id'],start_station=variant['start_station'],default=variant['start_station']==theme['default_start'],
                             assets=variant['map_assets'],svg_sha256=digest(path)))
    manifest=dict(museum=data['key'],tour_sha256=digest(data_path),width=1200,height=1600,maps=maps)
    # PNG 记录由浏览器导出器生成；SVG 重建后旧栅格图不可冒充当前图。
    if args.check:
        for item,old in zip(maps,previous['maps'],strict=True):
            assert all(old[k]==v for k,v in item.items())
            assert digest(TOUR/item['assets']['png'])==old['png_sha256']
        assert previous['tour_sha256']==manifest['tour_sha256']
    else:
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(maps)} SVG maps '+('and PNG hashes verified' if args.check else 'generated; rasterize PNG next'))


if __name__=='__main__':main()
