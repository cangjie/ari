import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import process from 'node:process';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root=process.env.BOSTON_REPO_ROOT || process.cwd();
const dir=`${root}/utils/import_data`;
const base=`${dir}/exports/波士顿Summer Street周边景点与商铺_双语清单_V3评级版.xlsx`;
const isDraft=process.argv.includes('--draft');
const outDir=isDraft?'/private/tmp/ari-boston-local-preview':(process.env.BOSTON_WORKBOOK_DIR || `${dir}/exports`);
const draft=JSON.parse(await fs.readFile(`${dir}/boston_summer_st_revision_v3_draft.json`,'utf8'));
const ratingBytes=await fs.readFile(`${dir}/boston_summer_st_v3_ratings.json`);
const rating=JSON.parse(ratingBytes.toString('utf8'));
const audit=JSON.parse(await fs.readFile(`${dir}/boston_summer_st_v3_rating_audit_results.json`,'utf8'));
const evidence=JSON.parse(await fs.readFile(`${dir}/boston_summer_st_verified_evidence_draft.json`,'utf8'));
const auditBytes=await fs.readFile(`${dir}/boston_summer_st_v3_rating_audit_request.json`);
const hash=x=>createHash('sha256').update(x).digest('hex');
if ((!audit.complete && !isDraft) || audit.request_sha256!==hash(auditBytes)
    || JSON.parse(auditBytes.toString('utf8')).rating_sha256!==hash(ratingBytes)
    || rating.results.length!==53 || draft.rows.length!==53) throw new Error('评级或独立审计不完整或不匹配');
const scoreById=new Map(rating.results.map(r=>[r.id,r]));
const byId=new Map(draft.rows.map(r=>[r.id,r]));
const evidenceBySeq=new Map(evidence.items.map(r=>[r.seq,r.evidence]));
const reviewSeqs=new Set(audit.audits.filter(a=>a.found_factual_error || a.missing.some(m=>m.tier_sensitive)).map(a=>a.seq));
function sourceInfo(seq,row){
  const entries=evidenceBySeq.get(seq);if(!entries?.length)throw new Error(`missing evidence ${seq}`);
  const urls=[...new Set(entries.map(x=>x.url))],first=entries[0];
  return {url:urls[0],title:urls[0]===row.source?row.source_name:first.title||row.source_name,additional:urls.slice(1)};
}
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(base));
const text=(s)=>s ?? '';
function rationale(s){return [s.evidence,`同类比较：${s.cr_reason}`,s.tier_reason].filter(Boolean).join('；');}
for (const name of ['zh-CN','en','特色商铺']) {
  const sheet=wb.worksheets.getItem(name), ids=sheet.getRange(`A2:A${name==='特色商铺'?22:54}`).values;
  ids.forEach((entry,i)=>{
    const id=entry[0], row=byId.get(id), s=scoreById.get(id), n=i+2;
    if(!row || !s)throw new Error(`missing ${name} ${id}`);
    const src=sourceInfo(s.seq,row);
    let note=name==='en'?text(sheet.getRange(`M${n}`).values[0][0]):text(row.note);
    if(id==='P09' && name==='en')note='The current building website uses 263 Summer St.; the rooftop sign is subject to current conditions.';
    if(src.additional.length)note+=(note?'\n':'')+(name==='en'?'Additional sources: ':'补充来源：')+src.additional.join(' ; ');
    if(reviewSeqs.has(s.seq))note+=(note?'\n':'')+(name==='en'?'Rating flagged for further review.':'评级依据仍有补充资料，等级待复核。');
    if(name==='en'){
      sheet.getRange(`D${n}:G${n}`).values=[[row.en,row.zh,row.en_desc,row.address]];
    } else {
      sheet.getRange(`D${n}:G${n}`).values=[[row.zh,row.en,row.zh_desc,row.address]];
    }
    sheet.getRange(`M${n}`).values=[[note]];
    sheet.getRange(`J${n}:L${n}`).values=[[src.title,src.url,46329]];
    sheet.getRange(`N${n}:Q${n}`).values=[[s.tier,s.core,s.confidence,rationale(s)]];
  });
}
const trail=wb.worksheets.getItem('自由之路16站');
for(let i=1;i<=11;i++){
  const n=i+1,id=`T${String(i).padStart(2,'0')}`,row=byId.get(id),s=scoreById.get(id);
  trail.getRange(`C${n}:D${n}`).values=[[row.zh,row.en]];
  trail.getRange(`F${n}:H${n}`).values=[[row.address,row.zh_desc,sourceInfo(s.seq,row).url]];
  trail.getRange(`J${n}:K${n}`).values=[[s.tier,s.core]];
}
const detail=wb.worksheets.getItem('V3评分明细');
for(const s of rating.results){
  const row=byId.get(s.id),d=s.dimensions,n=s.seq+1;
  detail.getRange(`A${n}:R${n}`).values=[[s.id,row.zh,s.tier,s.core,d.HS,d.IU,d.VI,d.VA,d.CE,d.ER,
    s.CR,s.object_type,s.peer_group,s.confidence,s.evidence,s.cr_reason,text(s.sness?.sness_reason),s.tier_reason]];
}
const notes=wb.worksheets.getItem('说明');
notes.getRange('B2').values=[['覆盖 Summer Street 从 Downtown Crossing 到海港区，并包括步行可衔接的自由之路市中心站点。']];
notes.getRange('B6').values=[['本表使用修订后的资料与 V3 文化参观优先级；路线距离与现场通行条件以导览和现场为准。']];
notes.getRange('B7').values=[['照片不嵌入本表；导览照片、署名与授权信息单独管理。']];
notes.getRange('B8').values=[['2026-11-03']];
notes.getRange('B9').values=[['来源、评分输入与独立核查记录保留在项目资料中。']];
notes.getRange('B11').values=[[isDraft?'本地草案：评分独立审计尚未完成，暂不能用于发布；营业情况须另核。':`等级衡量本走廊文化参观优先级。独立审计提示 ${reviewSeqs.size} 条可结合更多资料复核评级，已在各行标出；营业情况须另核。`]];
notes.getRange('B14').values=[['SABC'.split('').map(x=>`${x}${rating.counts[x]||0}`).join(' / ')]];
wb.recalculate();
for(const [name,range] of [['zh-CN','A1:H8'],['en','A1:H8'],['特色商铺','A1:H7'],
                           ['自由之路16站','A1:H7'],['说明','A1:B10'],['V3评分明细','A1:H8']]){
  const blob=await wb.render({sheetName:name,range,scale:1,format:'png'});
  await fs.writeFile(`/private/tmp/ari-boston-v3-${name}.png`,new Uint8Array(await blob.arrayBuffer()));
}
console.log((await wb.inspect({kind:'table',range:'zh-CN!A1:Q4',include:'values,formulas',tableMaxRows:4,tableMaxCols:17,maxChars:3000})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},summary:'formula errors'})).ndjson);
await fs.mkdir(outDir,{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(`${outDir}/波士顿Summer Street周边_双语V3评级.xlsx`);
console.log(`SAVED ${outDir}/波士顿Summer Street周边_双语V3评级.xlsx`);
