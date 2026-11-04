"""Restore native filters and changed hyperlinks omitted by the spreadsheet exporter."""
import html
import argparse
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'exports'/'波士顿Summer Street周边_双语V3评级.xlsx'
MS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--draft',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.draft and args.output:raise ValueError('草案和自定义输出不能同时指定')
    if args.draft:
        OUT=Path('/private/tmp/ari-boston-local-preview/波士顿Summer Street周边_双语V3评级.xlsx')
    elif args.output:
        OUT=args.output
    rows=json.loads((HERE/'boston_summer_st_revision_v3_draft.json').read_text('utf-8'))['rows']
    evidence=json.loads((HERE/'boston_summer_st_verified_evidence_draft.json').read_text('utf-8'))['items']
    urls={x['seq']:x['evidence'][0]['url'] for x in evidence}
    shops=[r for r in rows if r['id'].startswith('S')]
    by_id={r['id']:r for r in rows}
    seqs={r['id']:i for i,r in enumerate(rows,1)}
    links={1:{f'K{i+2}':urls[i+1] for i,r in enumerate(rows)},
           2:{f'K{i+2}':urls[i+1] for i,r in enumerate(rows)},
           3:{f'K{i+2}':urls[seqs[r['id']]] for i,r in enumerate(shops)},
           4:{f'H{i+1}':urls[seqs[f'T{i:02d}']] for i in range(1,12)}}
    filters={1:'A1:Q54',2:'A1:Q54',3:'A1:Q22',4:'A1:K17',5:'A1:B14',6:'A1:R54'}
    temporary=OUT.with_suffix('.repair-tmp')
    with zipfile.ZipFile(OUT) as source,zipfile.ZipFile(temporary,'w') as dest:
        data={entry.filename:source.read(entry.filename) for entry in source.infolist()}
        for index,ref in filters.items():
            name=f'xl/worksheets/sheet{index}.xml'
            xml=data[name].decode('utf-8')
            if re.search(r'<(?:\w+:)?autoFilter\b',xml):
                raise ValueError(f'{name} already has a filter; check exporter before repair')
            match=re.search(r'</(?P<prefix>\w+:)?sheetData>',xml)
            if not match:raise ValueError(f'{name} lacks sheetData')
            tag=(match.group('prefix') or '')+'autoFilter'
            xml=xml[:match.end()]+f'<{tag} ref="{ref}" />'+xml[match.end():]
            if index in links:
                root=ET.fromstring(xml)
                rel_ids={h.attrib['ref']:h.attrib[f'{{{REL}}}id']
                         for h in root.findall(f'{{{MS}}}hyperlinks/{{{MS}}}hyperlink')}
                relname=f'xl/worksheets/_rels/sheet{index}.xml.rels'
                rels=data[relname].decode('utf-8')
                if len(set(rel_ids.values()))!=len(rel_ids):
                    raise ValueError(f'{name} has shared hyperlink relationships')
                for cell,url in links[index].items():
                    if not url.startswith('https://') or cell not in rel_ids:
                        raise ValueError(f'{name} invalid hyperlink {cell}')
                    rid=re.escape(rel_ids[cell])
                    pattern=r'<Relationship\b(?=[^>]*\bId="'+rid+r'")[^>]*/>'
                    def replace(match):
                        tag=match.group(0)
                        return re.sub(r'Target="[^"]*"',f'Target="{html.escape(url,quote=True)}"',tag,count=1)
                    rels,count=re.subn(pattern,replace,rels,count=1)
                    if count!=1:raise ValueError(f'{name} hyperlink target not found: {cell}')
                data[relname]=rels.encode('utf-8')
            data[name]=xml.encode('utf-8')
        for entry in source.infolist():dest.writestr(entry,data[entry.filename])
    os.replace(temporary,OUT)
    print('Restored six filters and source hyperlink targets')


if __name__=='__main__':main()
