#!/usr/bin/env python3
"""Walking legs for the Greater Boston day routes, computed on the OpenStreetMap pedestrian network.

Input: a raw Overpass JSON of pedestrian-accessible ways for the route area (fetch it with the
query in boston_area_osm_fetch.py; keep the raw file out of the repository, it is about 40 MB).
Output: boston_area_walk_legs.json, one record per consecutive stop pair in every day of every route,
with the road distance, a walking-minute estimate at 60 m per minute, and the polyline on the network.

Method: each stop is snapped to its nearest network node; the shortest path (Dijkstra on distance)
joins the two snapped nodes; the connector distances from the stop to its node are added. A leg whose
road distance exceeds TRANSIT_LIMIT_M is marked for public transit and gets no walking minutes.
Walking minutes are estimates; they are not timed walks.

Run: python3 boston_area_walk.py --raw /path/to/boston_area_overpass_raw.json
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
from datetime import date
from pathlib import Path

import boston_area_routes as routes_mod

HERE = Path(__file__).resolve().parent
OUT = HERE / "boston_area_walk_legs.json"
WALK_SPEED_M_PER_MIN = 60
TRANSIT_LIMIT_M = 2000
MAX_SNAP_M = 80


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def load_graph(raw_path: Path):
    data = json.loads(raw_path.read_text("utf-8"))
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in data["elements"] if e["type"] == "node"}
    adj: dict[int, list[tuple[int, float]]] = {}
    for e in data["elements"]:
        if e["type"] != "way":
            continue
        ids = [n for n in e["nodes"] if n in nodes]
        for a, b in zip(ids, ids[1:]):
            if a == b:
                continue
            d = haversine_m(*nodes[a], *nodes[b])
            adj.setdefault(a, []).append((b, d))
            adj.setdefault(b, []).append((a, d))
    return nodes, adj


def snap(point, nodes):
    best, best_d = None, float("inf")
    lat, lon = point
    for nid, (nlat, nlon) in nodes.items():
        if abs(nlat - lat) > 0.002 or abs(nlon - lon) > 0.003:
            continue
        d = haversine_m(lat, lon, nlat, nlon)
        if d < best_d:
            best, best_d = nid, d
    return best, best_d


def shortest(src, dst, adj):
    dist = {src: 0.0}
    prev = {}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            break
        if d > dist.get(u, float("inf")):
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if dst not in dist:
        return None, None
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return dist[dst], list(reversed(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="append", required=True, help="Overpass JSON; repeat for each area")
    args = ap.parse_args()
    rows = {row["id"]: row for row in routes_mod.inventory.rows}
    geo = json.loads(routes_mod.GEO.read_text("utf-8"))["items"]
    nodes, adj = {}, {}
    for raw in args.raw:
        part_nodes, part_adj = load_graph(Path(raw))
        nodes.update(part_nodes)
        adj.update(part_adj)
    print(f"graph nodes {len(nodes)}, adjacency entries {len(adj)}", flush=True)
    snap_cache: dict[str, tuple] = {}
    legs = []
    for route in routes_mod.ROUTES:
        for day_index, day in enumerate(route["days"], 1):
            stops = [s for s, _, _ in day["stops"]]
            for a, b in zip(stops, stops[1:]):
                for sid in (a, b):
                    if sid not in snap_cache:
                        p = (geo[sid]["result"]["lat"], geo[sid]["result"]["lon"])
                        node, gap = snap(p, nodes)
                        snap_cache[sid] = (node, gap, p)
                na, ga, pa = snap_cache[a]
                nb, gb, pb = snap_cache[b]
                straight = haversine_m(*pa, *pb)
                record = {"route": route["id"], "day": day_index, "from": a, "to": b,
                          "straight_m": round(straight), "snap_m": [round(ga), round(gb)]}
                if na is None or nb is None or ga > MAX_SNAP_M or gb > MAX_SNAP_M:
                    # Off the network, or nearest node too far: keep the straight line, never invent a walk.
                    mode = "transit" if straight > TRANSIT_LIMIT_M else "straight_unsnapped"
                    record.update(mode=mode, road_m=None, minutes_estimate=None, polyline=[pa, pb])
                else:
                    road, path = shortest(na, nb, adj)
                    if road is None:
                        # The two snapped nodes are in different network components (a gap in OSM or a
                        # pedestrian barrier). Far apart: treat as transit; near: keep straight, flagged.
                        mode = "transit" if straight > TRANSIT_LIMIT_M else "straight_no_path"
                        record.update(mode=mode, road_m=None, minutes_estimate=None, polyline=[pa, pb])
                    else:
                        total = road + ga + gb
                        if total > TRANSIT_LIMIT_M:
                            record.update(mode="transit", road_m=round(total), minutes_estimate=None,
                                          polyline=[pa, pb])
                        else:
                            record.update(mode="walk", road_m=round(total),
                                          minutes_estimate=round(total / WALK_SPEED_M_PER_MIN),
                                          polyline=[pa] + [nodes[n] for n in path] + [pb])
                legs.append(record)
                print(f"{route['id']} d{day_index} {a}->{b}: {record['mode']} road={record.get('road_m')} "
                      f"straight={record['straight_m']} snap={record['snap_m']}", flush=True)
    OUT.write_text(json.dumps({
        "captured_on": date.today().isoformat(),
        "provider": "OpenStreetMap Overpass (pedestrian highway ways), Dijkstra on distance",
        "walk_speed_m_per_min": WALK_SPEED_M_PER_MIN, "transit_limit_m": TRANSIT_LIMIT_M,
        "max_snap_m": MAX_SNAP_M, "legs": legs,
    }, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
