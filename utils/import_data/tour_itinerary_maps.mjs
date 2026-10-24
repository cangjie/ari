// 在本机 Chrome 中按 SVG 原尺寸生成 PNG，等待字体完成，不取页面缩略截图。
// node utils/import_data/tour_itinerary_maps.mjs <museum>
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {setTimeout as sleep} from 'node:timers/promises';

const here=fileURLToPath(new URL('.',import.meta.url)),tour=resolve(here,'../../web_api/tour');
const key=process.argv[2];
if(!/^[a-z0-9_]+$/.test(key||''))throw new Error('Supply a museum key');
const manifestPath=join(here,`${key}_itinerary_maps.json`);
const manifest=JSON.parse(await readFile(manifestPath,'utf8'));
const profile=await mkdtemp(join(tmpdir(),'ari-route-maps-'));
const chrome=spawn(process.env.CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new','--remote-debugging-port=9334',`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check','--hide-scrollbars','about:blank'],{stdio:'ignore'});
let ws;
try{
  let version;
  for(let i=0;i<60;i++){
    try{version=await(await fetch('http://127.0.0.1:9334/json/version')).json();break;}catch{await sleep(200);}
  }
  if(!version)throw new Error('Chrome did not start');
  const target=await(await fetch('http://127.0.0.1:9334/json/new?about:blank',{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok,bad)=>{ws.addEventListener('open',ok);ws.addEventListener('error',bad);});
  let id=0;const pending=new Map();
  ws.addEventListener('message',ev=>{const m=JSON.parse(ev.data);if(pending.has(m.id)){const {ok,bad}=pending.get(m.id);pending.delete(m.id);m.error?bad(new Error(JSON.stringify(m.error))):ok(m.result);}});
  const send=(method,params={})=>new Promise((ok,bad)=>{const request=++id;pending.set(request,{ok,bad});ws.send(JSON.stringify({id:request,method,params}));});
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:manifest.width,height:manifest.height,deviceScaleFactor:1,mobile:false});
  for(const item of manifest.maps){
    const svg=await readFile(join(tour,item.assets.svg));
    if(createHash('sha256').update(svg).digest('hex')!==item.svg_sha256)throw new Error('SVG hash changed');
    await send('Page.navigate',{url:pathToFileURL(join(tour,item.assets.svg)).href});
    const expected=JSON.stringify(item.assets.svg.split('/').pop());let ready=false;
    for(let i=0;i<60;i++){
      const r=await send('Runtime.evaluate',{expression:`location.pathname.endsWith(${expected}) && document.readyState==='complete' && document.documentElement.tagName==='svg'`,returnByValue:true});
      if(r.result.value){ready=true;break;}await sleep(100);
    }
    if(!ready)throw new Error('SVG failed to load '+item.assets.svg);
    const fonts=await send('Runtime.evaluate',{expression:'document.fonts.ready.then(()=>new Promise(ok=>requestAnimationFrame(()=>requestAnimationFrame(()=>ok(true)))))',awaitPromise:true,returnByValue:true});
    if(fonts.exceptionDetails)throw new Error('Fonts failed');
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:manifest.width,height:manifest.height,scale:1}});
    const png=Buffer.from(shot.data,'base64');await writeFile(join(tour,item.assets.png),png);
    item.png_sha256=createHash('sha256').update(png).digest('hex');
    console.log(item.assets.png,png.length);
  }
  manifest.rasterizer=version.Browser;
  await writeFile(manifestPath,JSON.stringify(manifest,null,2)+'\n');
}finally{
  ws?.close();
  if(chrome.exitCode===null){const stopped=new Promise(ok=>chrome.once('exit',ok));chrome.kill();await stopped;}
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
