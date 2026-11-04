"""Calculate draft routes from saved public OSM streets and official MBTA points.

Outputs are research artifacts only: candidate POIs still require identity checks.
"""
import json
from pathlib import Path

from tour_collection_experience import StreetGraph, station_point
from tour_package_build import meters

HERE = Path(__file__).resolve().parent
STREETS = {
    2:['Tremont Street'], 3:['Beacon Street'], 4:['Tremont Street'], 5:['Tremont Street'],
    6:['Tremont Street'], 7:['School Street'], 8:['Washington Street'], 9:['Washington Street'],
    10:['Washington Street'], 11:['State Street'], 12:['Congress Street'],
    19:['Summer Street'], 20:['Summer Street'], 21:['Summer Street'], 22:['Congress Street'],
    24:['Sleeper Street'], 27:['Boston HarborWalk','Harborwalk'], 31:['Harbor Way'],
    32:['Harbor Way'], 36:['Summer Street'], 45:['High Street'], 46:['Farnsworth Street'],
    47:['Congress Street'], 50:['Summer Street'], 52:['Northern Avenue'],
}
ROUTES = {
    'sightseeing': {'start':'door-pktrm-tremontw','end':'door-crtst-north',
                    'steps':[2,3,4,5,6,7,8,9,10,11,12,19,20,22,24,31,32,27]},
    'food': {'start':'door-dwnxg-summer','end':'place-conrd',
             'steps':[9,36,45,19,20,22,46,47,31,50,52]},
}


def main():
    osm=json.loads((HERE/'boston_summer_st_osm.json').read_text())
    graph=StreetGraph(osm)
    places={r['seq']:r for r in json.loads((HERE/'boston_summer_st_geocode_capture.json').read_text())['items']}
    records={r['stop_id']:r for r in json.loads((HERE/'boston_summer_st_mbta_stops.json').read_text())['records']}
    snaps={}
    for seq,streets in STREETS.items():
        # Fort Point district is not the waterway's centre; this is a public-street
        # reference near the listed Boston Wharf building, not a district boundary.
        item=places[21] if seq==20 else places[seq]
        point=(item['lat'],item['lon'])
        reference_basis='nominatim candidate'
        if seq == 2:
            center=next(e for e in osm['elements'] if e['type']=='way' and e['id']==24677646)
            geometry=center['geometry']
            point=(sum(p['lat'] for p in geometry)/len(geometry),
                   sum(p['lon'] for p in geometry)/len(geometry))
            reference_basis='OSM Boston Common visitor information center (street reference only)'
        elif seq == 19:
            point=station_point({'gtfs_stop_id':'door-sstat-outmain'},graph,records)
            reference_basis='MBTA South Station Summer Street entrance'
        elif seq == 31:
            steps=next(e for e in osm['elements'] if e['type']=='way' and e['id']==1225708372)
            geometry=steps['geometry']
            point=(sum(p['lat'] for p in geometry)/len(geometry),
                   sum(p['lon'] for p in geometry)/len(geometry))
            reference_basis='OSM way 1225708372 Harbor Way steps'
        node=graph.nearest(point,streets)
        gap=meters(point,graph.nodes[node])
        if gap>260:
            raise ValueError(f'{seq}: closest named public street is {gap:.0f}m away')
        snaps[seq]={'node':node,'point':list(graph.nodes[node]),'streets':streets,'offset_m':round(gap,1),
                    'reference_basis':reference_basis,
                    'source_ref':graph.references.get(node,{'osm_node':node})}
    routes={}
    for name,route in ROUTES.items():
        start=station_point({'gtfs_stop_id':route['start']},graph,records)
        end=station_point({'gtfs_stop_id':route['end']},graph,records)
        start_node=graph.nearest(start);end_node=graph.nearest(end)
        connectors=[meters(start,graph.nodes[start_node]),meters(end,graph.nodes[end_node])]
        if max(connectors)>80:
            raise ValueError(f'{name}: transit connector too long: {connectors}')
        nodes=[start_node]+[snaps[s]['node'] for s in route['steps']]+[end_node]
        legs=[]
        for first,last in zip(nodes,nodes[1:]):
            chain,distance,ways=graph.leg(first,last)
            legs.append({'distance_m':round(distance,1),'path':[list(graph.nodes[n]) for n in chain],
                         'way_ids':sorted(set(ways))})
        routes[name]={**route,'connector_m':[round(x,1) for x in connectors],
                      'total_m':round(sum(x['distance_m'] for x in legs)+sum(connectors)), 'legs':legs}
        print(name, routes[name]['total_m'], 'm', len(legs),'legs',flush=True)
    result={'state':'draft_not_for_publication','note':'候选坐标、路网、照片和现场可达性尚未完成核验',
            'references':snaps,'routes':routes}
    (HERE/'boston_summer_st_draft_walks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')


if __name__=='__main__':
    main()
