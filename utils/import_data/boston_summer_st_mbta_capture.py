"""Capture MBTA GTFS stop and entrance records needed for the draft walks."""
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
URL = 'https://cdn.mbta.com/MBTA_GTFS.zip'
STATIONS = {'place-pktrm','place-dwnxg','place-crtst','place-conrd','place-sstat'}


def main():
    response = httpx.get(URL, timeout=90, follow_redirects=True,
                         headers={'User-Agent':'AriTourResearch/1.0 (+https://tour.arimuseum.org/)'})
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        raw = archive.read('stops.txt').decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(raw)))
    selected = [row for row in rows if row['stop_id'] in STATIONS or row['parent_station'] in STATIONS]
    if not selected:
        raise ValueError('No matching official MBTA station records')
    output = {'url':URL,'gtfs_sha256':hashlib.sha256(response.content).hexdigest(),
              'stops_txt_sha256':hashlib.sha256(raw.encode('utf-8')).hexdigest(),
              'stations':sorted(STATIONS),'records':selected}
    (HERE/'boston_summer_st_mbta_stops.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for row in selected:
        if row['location_type'] in {'1','2'}:
            print(row['stop_id'],row['parent_station'],row['location_type'],row['stop_name'],row['stop_lat'],row['stop_lon'],flush=True)


if __name__=='__main__':
    main()
