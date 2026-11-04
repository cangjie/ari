"""Rerate the independently checked, evidence-enriched inventory in new checkpoints."""
import hashlib
import json
from pathlib import Path

import boston_summer_st_list as listing
import boston_summer_st_rate as rating
from boston_summer_st_rate_revision import verify_base

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'


def main():
    base=verify_base()
    draft=json.loads((HERE/f'{KEY}_revision_v3_draft.json').read_text('utf-8'))
    request_path=HERE/f'{KEY}_v3_content_audit_request.json'
    request=json.loads(request_path.read_text('utf-8'))
    result=json.loads((HERE/f'{KEY}_v3_content_audit_results.json').read_text('utf-8'))
    changed=set(draft['v3_changed_seqs'])
    if (not result['complete'] or result['request_sha256']!=hashlib.sha256(request_path.read_bytes()).hexdigest()
            or len(result['items'])!=len(changed) or {x['seq'] for x in result['items']}!=changed
            or any(not x['supported'] or not x['address_supported'] for x in result['items'])):
        raise ValueError('新增评级依据尚未通过独立复核')
    for row in request['items']:
        item=draft['rows'][row['seq']-1]
        if (row['name'],row['description'],row['address'])!=(item['en'],item['en_desc'],item['address']):
            raise ValueError('新增复核输入与清单不一致')
    if any(draft['rows'][i-1]!=base['rows'][i-1] for i in set(range(1,54))-changed):
        raise ValueError('其他条目在复核后被修改')
    listing.rows=draft['rows']
    rating.PREFIX=f'{KEY}_v3'
    rating.main()


if __name__=='__main__':main()
