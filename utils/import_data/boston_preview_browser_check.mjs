import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import process from 'node:process';
const root=process.env.BOSTON_REPO_ROOT || process.cwd();
const base=process.env.BOSTON_PREVIEW_BASE || 'http://127.0.0.1:64202/';
const preview=JSON.parse(await fs.readFile(`${root}/web_api/tour/data/boston_summer_st.json`,'utf8'));
const sample=preview.navigation.places.find(p=>p.id==='t01');
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
  const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,
    geolocation:{latitude:42.356,longitude:-71.062},permissions:['geolocation']});
  const page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${base}?fix=${sample.lat},${sample.lon},5`,{waitUntil:'domcontentloaded'});
  await page.locator('[data-open="boston_summer_st"]').waitFor();
  await page.locator('[data-open="boston_summer_st"]').click();
  await page.locator('#collection-count').waitFor();
  const all=await page.locator('#collection-count').innerText();
  if(!all.includes('53 / 53'))throw new Error(`unexpected collection count ${all}`);
  await page.selectOption('#collection-kind','shop');
  const shops=await page.locator('#collection-count').innerText();
  if(!shops.includes('21 / 53'))throw new Error(`unexpected shop count ${shops}`);
  await page.selectOption('#collection-kind','all');
  await page.locator('.collection-item[data-place="t01"]').click();
  await page.locator('#sheet-body .tour-photo img').waitFor();
  const credit=await page.locator('#sheet-body .tour-photo figcaption').innerText();
  if(!credit.includes('作者：') || !credit.includes('许可：'))throw new Error('photo credit missing');
  await page.locator('#sheet [data-close]').click();
  for(const id of ['p09','p19','p20']){
    await page.locator(`.collection-item[data-place="${id}"]`).click();
    if(await page.locator('#sheet-body .tour-photo img').count())throw new Error(`unexpected photo ${id}`);
    if(await page.locator('#sheet-body [data-show-map]').count()!==1)throw new Error(`missing map button ${id}`);
    await page.locator('#sheet [data-close]').click();
  }
  await page.locator('#view-themes').click();
  const themes=await page.locator('.theme-card h3').allTextContents();
  if(themes.length!==2 || !themes.includes('纯观光路线') || !themes.includes('观光＋美食路线'))throw new Error(`unexpected themes ${themes}`);
  const starts=await page.locator('[data-theme-start]').count();
  if(starts!==2 || await page.locator('[data-theme-start]:disabled').count()!==2)throw new Error('fixed starts missing');
  for(const id of ['sightseeing','food']){
    const card=page.locator(`.theme-card[data-theme="${id}"]`);
    const dims=await card.evaluate(async el=>{
      const svg=el.querySelector('.theme-map-preview img');svg.loading='eager';await svg.decode();
      const png=new Image();png.src=el.querySelector('[download]').href;await png.decode();
      return [svg.naturalWidth,png.naturalWidth,png.naturalHeight];
    });
    if(dims.join(',')!=='1200,1200,1600')throw new Error(`route assets invalid ${id} ${dims}`);
  }
  await page.locator('[data-theme-map="sightseeing"]').click();
  if(!await page.locator('#mapwrap').isVisible())throw new Error('route map did not open');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('附近'));
  const accurateStatus=await page.locator('#status').innerText();
  if(errors.length)throw new Error(`page errors: ${errors.join('; ')}`);
  await context.close();
  const low=await browser.newContext({viewport:{width:390,height:844}}), lowPage=await low.newPage();
  await lowPage.goto(`${base}?fix=${sample.lat},${sample.lon},80`,{waitUntil:'domcontentloaded'});
  await lowPage.locator('[data-open="boston_summer_st"]').click();
  await lowPage.locator('#view-themes').click();
  await lowPage.locator('[data-theme-map="sightseeing"]').click();
  await lowPage.waitForFunction(()=>document.querySelector('#status').textContent.includes('定位精度较低'));
  const inaccurateStatus=await lowPage.locator('#status').innerText();
  await low.close();
  const native=await browser.newContext({viewport:{width:390,height:844}});
  await native.addInitScript(()=>{
    window.__host={ready:null,payload:null,watch:0};
    navigator.geolocation.watchPosition=()=>{window.__host.watch++;throw new Error('Unexpected browser GPS');};
    window.AriHost={catalog(text){window.__host.payload=JSON.parse(text);return true;},
      visitorId(){return 'native-visitor-00000001';},ready(k){window.__host.ready=k;},leave(){window.__host.ready=null;}};
  });
  const nativePage=await native.newPage();
  await nativePage.goto(`${base}#boston_summer_st`,{waitUntil:'domcontentloaded'});
  await nativePage.locator('#view-themes').waitFor({state:'visible'});
  const nativeCount=await nativePage.evaluate(()=>window.__host.payload.find(x=>x.key==='boston_summer_st').places.length);
  if(nativeCount!==24)throw new Error(`native navigation count ${nativeCount}`);
  await nativePage.locator('#view-themes').click();
  await nativePage.locator('[data-theme-map="sightseeing"]').click();
  const hostReady=await nativePage.evaluate(()=>window.__host.ready);
  if(hostReady!=='boston_summer_st')throw new Error(`native bridge ready ${hostReady}`);
  const nativeStatus=await nativePage.evaluate(()=>{
    const point=window.__host.payload.find(x=>x.key==='boston_summer_st').places[0],now=Date.now();
    window.AriTour.state({museum:'boston_summer_st',status:'live',x:point.x,y:point.y,acc:5,inside:point.id,
                          connectedAt:now-100,history:[{pid:point.id,at:now}]});
    return document.querySelector('#status').textContent;
  });
  if(!nativeStatus.includes('附近') || await nativePage.evaluate(()=>window.__host.watch)!==0)throw new Error(`native location ${nativeStatus}`);
  console.log(JSON.stringify({all,shops,themes,starts,photoCredit:true,approvedMissingPhotos:3,routeMapVisible:true,
                              accurateStatus,inaccurateStatus,nativeCount,nativeStatus,pageErrors:errors.length}));
  await native.close();
} finally {await browser.close();}
