"""Capture additional official pages for unresolved evidence; no release side effects."""
import asyncio
import argparse
import hashlib
import json
from pathlib import Path

import httpx
from boston_summer_st_package import TextExtractor

HERE = Path(__file__).resolve().parent
PAGES = [
    (1, 'https://www.thefreedomtrail.org/visit/experience-freedom-trail-now-visitor-resource'),
    (2, 'https://www.thefreedomtrail.org/visit/directions-parking'),
    (3, 'https://www.thefreedomtrail.org/trail-sites/massachusetts-state-house'),
    (6, 'https://www.thefreedomtrail.org/trail-sites/kings-chapel-kings-chapel-burying-ground'),
    (7, 'https://www.thefreedomtrail.org/trail-sites/boston-latin-school-sitebenjamin-franklin-statue'),
    (8, 'https://www.thefreedomtrail.org/trail-sites/old-corner-bookstore'),
    (9, 'https://www.thefreedomtrail.org/trail-sites/old-south-meeting-house'),
    (10, 'https://www.thefreedomtrail.org/trail-sites/old-state-house'),
    (11, 'https://www.thefreedomtrail.org/trail-sites/boston-massacre-site'),
    (12, 'https://www.thefreedomtrail.org/trail-sites/faneuil-hall'),
    (17, 'https://www.normanbleventhalpark.org/about-us/history-of-post-office-square/'),
    (30, 'https://laughboston.com/'),
    (42, 'https://www.brattlebookshop.com/about'),
    (50, 'https://www.coquetteboston.com/'),
]
ROUND_TWO = [
    (2, 'https://home.nps.gov/places/freedom-trail-start.htm'),
    (17, 'https://www.bostonplans.org/news-calendar/news-updates/2014/06/11/american-planning-association-honors-norman-b-leve'),
    (18, 'https://www.rosekennedygreenway.org/planning-for-2010-b/'),
    (19, 'https://dl.tufts.edu/concern/images/m900p408q'),
    (19, 'https://www.bostonmagazine.com/property/2019/11/14/south-station-history/'),
    (19, 'https://www.amtrak.com/stations/bos'),
    (22, 'https://www.bostonteapartyship.com/tea-room'),
    (26, 'https://www.bostonharbornow.org/what-we-do/explore/harborwalk/'),
    (32, 'https://www.fieldoperations.net/project/harbor-way'),
]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--round-two', action='store_true')
    args = parser.parse_args()
    pages = ROUND_TWO if args.round_two else PAGES
    async with httpx.AsyncClient(follow_redirects=True, timeout=25,
                                headers={'User-Agent': 'AriTourResearch/1.0 (+https://tour.arimuseum.org/)'}) as client:
        async def get(seq, url):
            try:
                response = await client.get(url)
                parser = TextExtractor()
                if response.status_code == 200:
                    parser.feed(response.text)
                return dict(seq=seq, url=url, status=response.status_code,
                            final_url=str(response.url), title=' '.join(parser.title_parts),
                            text=' '.join(parser.parts)[:50000],
                            raw_sha256=hashlib.sha256(response.content).hexdigest())
            except httpx.HTTPError as exc:
                return dict(seq=seq, url=url, status=None, text='', error=str(exc))
        items = await asyncio.gather(*(get(seq, url) for seq, url in pages))
    target = 'boston_summer_st_supplement_sources_2.json' if args.round_two else 'boston_summer_st_supplement_sources.json'
    (HERE/target).write_text(
        json.dumps({'state': 'draft; requires source review', 'items': items}, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print([(x['seq'], x['status'], len(x['text'])) for x in items])


if __name__ == '__main__':
    asyncio.run(main())
