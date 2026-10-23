// 以共享资料/评分/审计JSON生成一个中英工作簿。运行依赖来自Codex的artifact-tool。
import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const here=process.argv[2];
if(!here||!path.isAbsolute(here))throw new Error('请传入utils/import_data的绝对路径');
const payload=JSON.parse(await fs.readFile(path.join(here,'nanluo_shichahai_export_data.json'),'utf8'));
const outDir=path.join(here,'exports');
await fs.mkdir(outDir,{recursive:true});
const wb=Workbook.create();
function col(i){let s='';for(i++;i;i=Math.floor((i-1)/26))s=String.fromCharCode(65+(i-1)%26)+s;return s;}
function visibleLen(t){return [...String(t??'')].reduce((n,c)=>n+(/[\u3400-\u9fff]/.test(c)?2:1),0);}
for(const [index,def]of payload.sheets.entries()){
  const ws=wb.worksheets.add(def.name), matrix=[def.headers,...def.rows],last=col(def.headers.length-1);
  const all=ws.getRange(`A1:${last}${matrix.length}`);
  all.values=matrix;
  all.format.font={name:'Arial',size:11,color:'#243447'};
  all.format.verticalAlignment='top';
  all.format.wrapText=true;
  ws.showGridLines=false;
  ws.freezePanes.freezeRows(1);
  if(index<2)ws.freezePanes.freezeColumns(3);
  else if(def.name==='特色商铺')ws.freezePanes.freezeColumns(2);
  for(let i=0;i<def.headers.length;i++)ws.getRange(`${col(i)}1:${col(i)}${matrix.length}`).format.columnWidth=def.widths[i];
  const head=ws.getRange(`A1:${last}1`);
  head.format.fill='#29445C';head.format.font={name:'Arial',size:11,bold:true,color:'#FFFFFF'};
  head.format.horizontalAlignment='center';head.format.verticalAlignment='center';head.format.rowHeight=34;
  for(let r=1;r<matrix.length;r++){
    const lines=Math.max(...matrix[r].map((v,c)=>String(v??'').split('\n').reduce((n,line)=>n+Math.max(1,Math.ceil(visibleLen(line)/Math.max(5,def.widths[c]-3))),0)));
    const row=ws.getRange(`A${r+1}:${last}${r+1}`);
    row.format.rowHeight=Math.max(30,lines*15+10);
    if(r%2===0)row.format.fill='#F1F4F6';
  }
  if(index<2){
    ws.tabColor='#29445C';
    ws.getRange(`A2:A${matrix.length}`).setNumberFormat('0');
    ws.getRange(`G2:G${matrix.length}`).setNumberFormat('0.0000');
    ws.getRange(`H2:N${matrix.length}`).setNumberFormat('0.0');
    ws.getRange(`G2:N${matrix.length}`).format.horizontalAlignment='right';
    ws.getRange(`F2:F${matrix.length}`).conditionalFormats.add('containsText',{text:'S',format:{fill:'#E8E1CC',font:{bold:true,color:'#5A461B'}}});
    ws.getRange(`O2:O${matrix.length}`).conditionalFormats.add('containsText',{text:index===0?'是':'Yes',format:{fill:'#FBE6D8',font:{bold:true,color:'#843D21'}}});
  }
  if(def.name==='特色商铺'){
    ws.getRange(`F2:F${matrix.length}`).setNumberFormat('0.0000');
    ws.getRange(`G2:G${matrix.length}`).conditionalFormats.add('containsText',{text:'是',format:{fill:'#FBE6D8',font:{bold:true,color:'#843D21'}}});
  }
  if(def.name!=='说明'){
    const table=ws.tables.add(`A1:${last}${matrix.length}`,true,`NanluoSheet${index+1}`);
    table.showFilterButton=true;
  }else ws.tabColor='#8D9BA6';
}
wb.recalculate();
const inspection=await wb.inspect({kind:'table',range:'zh-CN!A1:G8',include:'values',tableMaxRows:8,tableMaxCols:7,maxChars:4000});
console.log(inspection.ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:2000});
console.log(errors.ndjson);
for(const [index,def]of payload.sheets.entries()){
  const last=def.name==='说明'?'B':def.name==='同类组'?'G':def.name==='来源证据'?'E':def.name==='特色商铺'?'F':'G';
  const preview=await wb.render({sheetName:def.name,range:`A1:${last}${Math.min(7,def.rows.length+1)}`,scale:1,format:'png'});
  await fs.writeFile(path.join(outDir,`nanluo_shichahai_preview_${index+1}.png`),new Uint8Array(await preview.arrayBuffer()));
}
for(const name of ['zh-CN','en']){
  const preview=await wb.render({sheetName:name,range:'O1:R4',scale:1,format:'png'});
  await fs.writeFile(path.join(outDir,`nanluo_shichahai_preview_text_${name}.png`),new Uint8Array(await preview.arrayBuffer()));
  const reviewIndex=payload.sheets[0].rows.findIndex(row=>row[14]==='是');
  if(reviewIndex>=0){
    const row=reviewIndex+2;
    const review=await wb.render({sheetName:name,range:`O${row}:R${row}`,scale:1,format:'png'});
    await fs.writeFile(path.join(outDir,`nanluo_shichahai_preview_review_${name}.png`),new Uint8Array(await review.arrayBuffer()));
  }
}
const guo=payload.sheets[0].rows.findIndex(row=>row[0]===48)+2;
if(guo>=2){
  const preview=await wb.render({sheetName:'zh-CN',range:`A${guo}:G${guo}`,scale:1,format:'png'});
  await fs.writeFile(path.join(outDir,'nanluo_shichahai_preview_guomoruo.png'),new Uint8Array(await preview.arrayBuffer()));
}
const shopDetails=await wb.render({sheetName:'特色商铺',range:'H1:K4',scale:1,format:'png'});
await fs.writeFile(path.join(outDir,'nanluo_shichahai_preview_shop_details.png'),new Uint8Array(await shopDetails.arrayBuffer()));
const dest=path.join(outDir,payload.output);
if(payload.audited){
  const staged=dest.replace(/\.xlsx$/,'.partial.xlsx');
  await(await SpreadsheetFile.exportXlsx(wb)).save(staged);
  await fs.rename(staged,dest);
  console.log(dest);
}else console.log('layout_preview_only; previously delivered workbook preserved');
