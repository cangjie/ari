"""Run V3 stages in separate checkpoints after revised evidence passes review."""
import hashlib
import json
from pathlib import Path

import boston_summer_st_list as listing
import boston_summer_st_rate as rating

HERE = Path(__file__).resolve().parent
KEY = 'boston_summer_st'


def verify_base():
    revision = json.loads((HERE/f'{KEY}_revision_final_draft.json').read_text('utf-8'))
    request_path = HERE/f'{KEY}_revision_audit_request.json'
    request = json.loads(request_path.read_text('utf-8'))
    result = json.loads((HERE/f'{KEY}_revision_audit_results.json').read_text('utf-8'))
    followup_path = HERE/f'{KEY}_revision_followup_request.json'
    followup = json.loads(followup_path.read_text('utf-8'))
    followup_result = json.loads((HERE/f'{KEY}_revision_followup_results.json').read_text('utf-8'))
    repeated = {x['seq'] for x in followup['items']}
    original_results = []
    for stem in ('evidence_check', 'evidence_recheck'):
        original_path = HERE/f'{KEY}_{stem}_request.json'
        original = json.loads((HERE/f'{KEY}_{stem}_results.json').read_text('utf-8'))
        if not original['complete'] or original['request_sha256'] != hashlib.sha256(original_path.read_bytes()).hexdigest():
            raise ValueError('原清单来源审计输入不一致或未完成')
        original_results.append(original)
    original_by_seq = {x['seq']:x for x in original_results[0]['items']}
    original_by_seq.update({x['seq']:x for x in original_results[1]['items']})
    unchanged = set(range(1, len(revision['rows'])+1)) - set(revision['changed_seqs'])
    if (set(original_by_seq) != set(range(1, len(revision['rows'])+1))
            or any(not original_by_seq[s]['supported'] or not original_by_seq[s]['address_supported'] for s in unchanged)
            or any(revision['rows'][s-1] != listing.rows[s-1] for s in unchanged)):
        raise ValueError('未修订的条目未通过独立核验或已变化')
    if (not result['complete'] or result['request_sha256'] != hashlib.sha256(request_path.read_bytes()).hexdigest()
            or len(result['items']) != len(revision['changed_seqs'])
            or set(x['seq'] for x in result['items']) != set(revision['changed_seqs'])
            or followup_result['request_sha256'] != hashlib.sha256(followup_path.read_bytes()).hexdigest()
            or len(followup_result['items']) != len(repeated)
            or set(x['seq'] for x in followup_result['items']) != repeated
            or any(not x['supported'] or not x['address_supported'] for x in result['items'] if x['seq'] not in repeated)
            or any(not x['supported'] or not x['address_supported'] for x in followup_result['items'])):
        raise ValueError('修订来源尚未全部通过独立核验，不能重评')
    for entry in [x for x in request['items'] if x['seq'] not in repeated] + followup['items']:
        row = revision['rows'][entry['seq']-1]
        if (entry['name'], entry['description'], entry['address']) != (row['en'], row['en_desc'], row['address']):
            raise ValueError('修订内容与独立审计输入不一致')
    return revision


def main():
    revision = verify_base()
    listing.rows = revision['rows']
    rating.PREFIX = f'{KEY}_v2'
    rating.main()


if __name__ == '__main__':
    main()
