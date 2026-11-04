"""Fetch alternative source pages for records whose original sources were insufficient."""
import hashlib
import json
from pathlib import Path

import httpx
from boston_summer_st_package import TextExtractor

HERE=Path(__file__).resolve().parent
PAGES=[
    {'seq':29,'url':'https://www.massconvention.com/about-us/press-release/boston-convention-exhibition-center-to-be-renamed-the-thomas-michael-menino'},
    {'seq':45,'url':'https://www.downtownboston.org/business/high-street-place-food-hall/'},
    {'seq':46,'url':'https://www.fortpointboston.com/2007/01/flour-bakery-open-for-business.html'},
]


def main():
    items=[]
    with httpx.Client(follow_redirects=True,timeout=25,headers={'User-Agent':'AriTourResearch/1.0 (+https://tour.arimuseum.org/)'}) as client:
        for page in PAGES:
            try:
                response=client.get(page['url'])
                extractor=TextExtractor()
                if response.status_code==200:
                    extractor.feed(response.text)
                body=' '.join(extractor.parts)
                items.append({**page,'status':response.status_code,'final_url':str(response.url),
                              'title':' '.join(extractor.title_parts),'text':body[:50000],
                              'raw_sha256':hashlib.sha256(response.content).hexdigest()})
            except httpx.HTTPError as exc:
                items.append({**page,'status':None,'error':str(exc),'text':''})
            print(page['seq'],items[-1]['status'],len(items[-1]['text']),flush=True)
    (HERE/'boston_summer_st_fallback_sources.json').write_text(
        json.dumps({'status':'candidate sources; require independent review','items':items},ensure_ascii=False,indent=2)+'\n','utf-8')


if __name__=='__main__':main()
