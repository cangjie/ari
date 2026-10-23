// 导览站的浏览器验收：用无头 Chrome 模拟手机视口与 GPS，把页面真跑一遍。
//
//   node web_api/tests/tour_browser_check.mjs                  # 全部场景
//   node web_api/tests/tour_browser_check.mjs live outside     # 只跑点名的
//   SHOTS=/某个目录 node web_api/tests/tour_browser_check.mjs   # 另存每个场景的截图
//   BASE=https://tour.snowmeet.top node …                      # 对着线上跑（默认自己起一个本地静态服务）
//
// pytest 那边（test_tour.py）只管数据对不对得上；页面的定位、到站、手势在这里验。
// 介绍抽屉里的「游客互动」也在这里验：自己起的本地服务带一个假的 /api/tour/ 接口（不连库、不调模型），
// 对着线上跑时 qa 场景只看列表能不能载入，不发帖 —— 发了就是一条留在线上的公开问答。
// 定位用 Chrome DevTools Protocol 的 Emulation.setGeolocationOverride 喂给浏览器，
// 页面拿到它走的是真实的 navigator.geolocation.watchPosition，不是 ?fix= 那条旁路。
//
// 依赖：Node 22 以上（用内置的 WebSocket 与 fetch）、本机装有 Chrome。没有别的依赖。
// Chrome 不在默认位置时用 CHROME=/路径 指定。任一断言不过，退出码 1。
//
// 注意：浏览器不允许给非 HTTPS、非 localhost 的源授予定位权限，
// 所以 BASE 指向 http:// 的公网地址时，要授权的场景都会失败 —— 那是浏览器的规矩，不是页面的问题。

import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFile, writeFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const TOUR_DIR = fileURLToPath(new URL("../tour/", import.meta.url));
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const SHOTS = process.env.SHOTS || "";
const DEBUG_PORT = 9333;
// 公网冷启动可能比自带本地服务慢；超时必须明确报加载失败，不能继续对未加载页面断言。
const LOAD_TIMEOUT_MS = Number(process.env.LOAD_TIMEOUT_MS || (process.env.BASE ? 60000 : 20000));
const IMAGE_TIMEOUT_MS = Number(process.env.IMAGE_TIMEOUT_MS || (process.env.BASE ? 90000 : 12000));
const MIME = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".woff2": "font/woff2", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp" };

// 几个有出处的位置（WGS-84）。同德殿等取自 wmhg_route_data.POINTS
const TONGDE = [43.90398, 125.34323], QINMIN = [43.90412, 125.34226], SHRINE = [43.90323, 125.34420];
const JIXI = [43.90359, 125.34239], BEIJING = [39.9163, 116.3972], NEARBY = [43.9010, 125.3440];
const GCJ_TONGDE = [43.906420, 125.349804];     // 同德殿加偏成国测局坐标后的值

let BASE = process.env.BASE || "";
let LOCAL = false;          // 用的是自己起的本地服务（带假的问答接口）
let failures = 0;
let catalogOverride = null;

// 假的问答接口的状态。mode：ok 正常 / off 接口不存在（404）/ down 列表报 500
const stub = { mode: "ok", topics: {}, nextId: 1, posts: 0 };

function stubSeed(place, rows) {
  stub.topics[place] = rows.map((r) => ({ id: stub.nextId++, visitor: "someone-else-0000", public: true,
    created_at: new Date(Date.now() - 3600e3).toISOString(), ...r }));
}

async function stubApi(req, res, url) {
  const send = (status, body) => {
    res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
    res.end(JSON.stringify(body));
  };
  const m = url.pathname.match(/^\/api\/tour\/([a-z0-9_]+)\/places\/([a-z0-9_]+)\/topics$/);
  if (!m || stub.mode === "off") return send(404, { error_code: "place_not_found", message: "没有这个地点。" });
  const list = stub.topics[m[2]] || (stub.topics[m[2]] = []);
  const me = req.headers["x-visitor"] || "";
  const view = (t) => ({ id: t.id, question: t.question, answer: t.answer, status: "answered",
    mine: t.visitor === me, public: t.public, created_at: t.created_at });

  if (req.method === "GET") {
    if (stub.mode === "down") return send(500, {});
    const limit = Number(url.searchParams.get("limit") || 20);
    const before = Number(url.searchParams.get("before") || Infinity);
    const rows = list.filter((t) => t.id < before && (t.public || t.visitor === me)).sort((a, b) => b.id - a.id);
    return send(200, { topics: rows.slice(0, limit).map(view), more: rows.length > limit });
  }
  let raw = "";
  for await (const chunk of req) raw += chunk;
  const question = JSON.parse(raw).question;
  stub.posts++;
  await sleep(700);                                   // 留出时间看「思考中」
  if (question.includes("失败")) return send(502, { error_code: "answer_failed", message: "导览助手暂时没有答上来，请稍后再试。" });
  const t = { id: stub.nextId++, question, answer: "答：" + question, visitor: me,
    public: !question.includes("广告"), created_at: new Date().toISOString() };
  list.push(t);
  return send(200, { topic: view(t), duplicate: false });
}

function check(ok, what, got) {
  if (!ok) failures++;
  console.log(`  ${ok ? "✓" : "✗"} ${what}${ok ? "" : `  —— 实际：${JSON.stringify(got)}`}`);
}

async function startStatic() {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    if (url.pathname.startsWith("/api/")) return stubApi(req, res, url);
    if (url.pathname === '/catalog.json' && catalogOverride) {
      res.writeHead(200, {'Content-Type':'application/json', 'Cache-Control':'no-store'});
      res.end(JSON.stringify({museums: catalogOverride})); return;
    }
    const path = normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, "");
    try {
      const body = await readFile(join(TOUR_DIR, path || "index.html"));
      res.writeHead(200, { "Content-Type": MIME[extname(path || "index.html")] || "application/octet-stream" });
      res.end(body);
    } catch { res.writeHead(404); res.end("not found"); }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  return { server, url: `http://127.0.0.1:${server.address().port}` };
}

class Page {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.errors = [];
    ws.addEventListener("message", (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id);
        this.pending.delete(m.id);
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
      } else if (m.method === "Runtime.exceptionThrown") {
        this.errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
      } else if (m.method === "Log.entryAdded" && m.params.entry.level === "error") {
        this.errors.push(`${m.params.entry.text} ${m.params.entry.url || ""}`);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expr) {
    const r = await this.send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  }
  click(sel) {
    return this.eval(`(function(){var e=document.querySelector(${JSON.stringify(sel)});` +
      `if(!e) throw new Error('找不到 ' + ${JSON.stringify(sel)}); e.click(); return true})()`);
  }
  // 权限：granted / denied / null（不设）。fix：[纬度, 经度, 精度米]
  async geo(permission, fix) {
    await this.send("Browser.resetPermissions");
    if (permission === "granted") await this.send("Browser.grantPermissions", { origin: BASE, permissions: ["geolocation"] });
    if (permission === "denied") await this.send("Browser.setPermission", { origin: BASE, permission: { name: "geolocation" }, setting: "denied" });
    if (fix) await this.moveTo(fix);
    else await this.send("Emulation.clearGeolocationOverride");
  }
  async moveTo(fix, wait = 0) {
    await this.send("Emulation.setGeolocationOverride", { latitude: fix[0], longitude: fix[1], accuracy: fix[2] ?? 8 });
    if (wait) await sleep(wait);
  }
  // 打开页面并等它稳定下来：地图页要等到底栏不再是「正在定位…」
  async open(path) {
    await this.send("Page.navigate", { url: BASE + "/" });
    await sleep(300);
    await this.eval("try { localStorage.clear() } catch (e) {}");
    await this.send("Page.navigate", { url: "about:blank" });
    await sleep(100);
    await this.send("Page.navigate", { url: BASE + path });
    const want = path.includes("#")
      ? "!document.getElementById('tour').hidden && (!document.getElementById('collection').hidden || !['', '正在定位…'].includes(document.getElementById('status').textContent))"
      : "!!document.querySelector('#cards .card') || document.getElementById('cards').textContent.includes('暂无')";
    let loaded = false;
    for (let i = 0; i < LOAD_TIMEOUT_MS / 250; i++) {
      if (await this.eval(want).catch(() => false)) { loaded = true; break; }
      await sleep(250);
    }
    if (!loaded) throw new Error('页面在' + LOAD_TIMEOUT_MS + 'ms内未完成加载：' + await this.eval("document.getElementById('cards').textContent"));
    await sleep(500);
  }
  state() {
    return this.eval(`JSON.stringify({
      status: document.getElementById('status').textContent,
      visited: document.getElementById('visited').textContent,
      grey: document.getElementById('me').classList.contains('off'),
      button: document.getElementById('locate-label').textContent,
      disabled: document.getElementById('locate').disabled,
      banner: document.getElementById('banner').classList.contains('show') ? document.getElementById('banner-title').textContent : null,
      summary: document.getElementById('route-summary').textContent,
      marks: Array.from(document.querySelectorAll('.spot .spot-num')).map(function (e) { return e.textContent }).join(' '),
      sheet: document.getElementById('sheet').classList.contains('show') ? document.querySelector('#sheet-body h2').textContent : null,
      map: document.getElementById('pan').style.transform + ' ' + document.getElementById('base').getAttribute('width')
    })`).then(JSON.parse);
  }
  touch(type, points) {
    return this.send("Input.dispatchTouchEvent", { type, touchPoints: points.map(([x, y], id) => ({ x, y, id })) });
  }
  async shot(name) {
    if (!SHOTS) return;
    const r = await this.send("Page.captureScreenshot", { format: "png" });
    await mkdir(SHOTS, { recursive: true });
    await writeFile(join(SHOTS, name + ".png"), Buffer.from(r.data, "base64"));
  }
}

const SCENES = {
  async catalog(p) {
    if (!LOCAL) return;
    const script = await p.send('Page.addScriptToEvaluateOnNewDocument', {source: `
      window.AriHost = {catalog: function(text) {window.__catalog = JSON.parse(text).map(function(m){return m.key}); return true;},
        visitorId: function(){return 'native-visitor-00000001';}, ready: function(){}, leave: function(){}};
    `});
    try {
      for (const keys of [['wmhg'], ['wanping','wmhg'], ['nanluo_shichahai','wmhg','wanping'], ['nanluo_shichahai'], []]) {
        catalogOverride = keys;
        await p.open('/');
        const shown = await p.eval("Array.from(document.querySelectorAll('[data-open]')).map(function(e){return e.dataset.open})");
        check(JSON.stringify(shown) === JSON.stringify(keys), '服务器控制景区增减及顺序：' + keys.join(','), shown);
        const mapped = keys.filter((k) => k !== 'nanluo_shichahai');
        check(JSON.stringify(await p.eval('window.__catalog')) === JSON.stringify(mapped), '有坐标的景区同步给原生定位；纯清单仍在Web可见');
      }
    } finally {catalogOverride = null; await p.send('Page.removeScriptToEvaluateOnNewDocument', {identifier:script.identifier});}
  },
  async collection(p) {
    await p.open('/#nanluo_shichahai');
    check(await p.eval("!document.getElementById('collection').hidden && document.getElementById('mapwrap').hidden"), '已审清单可直接打开，未伪装成地图');
    check(await p.eval("document.querySelectorAll('.collection-item').length === 100"), '全部100条均可浏览');
    await p.shot('collection-all');
    await p.eval("document.getElementById('collection-kind').value='shop'; document.getElementById('collection-kind').dispatchEvent(new Event('change')); true");
    check(await p.eval("document.querySelectorAll('.collection-item').length === 16"), '特色商铺筛出16条');
    await p.eval("document.getElementById('collection-tier').value='A'; document.getElementById('collection-tier').dispatchEvent(new Event('change')); true");
    check(await p.eval("document.querySelectorAll('.collection-item').length === 1 && !!document.querySelector('[data-place=shop_kaorouji]')"), '商铺与A级筛选可以组合');
    await p.eval("document.getElementById('collection-area').value='南锣鼓巷'; document.getElementById('collection-area').dispatchEvent(new Event('change')); true");
    check(await p.eval("document.querySelectorAll('.collection-item').length === 0"), '区域条件与类别、评级同时生效');
    await p.eval("document.getElementById('collection-area').value='all'; document.getElementById('collection-tier').value='all'; document.getElementById('collection-tier').dispatchEvent(new Event('change')); true");
    await p.shot('collection-shops');
    await p.eval("document.querySelector('[data-place=shop_kaorouji]').click(); true");
    check(await p.eval("document.getElementById('sheet').classList.contains('show')"), '商铺详情抽屉实际可见');
    let detail = await p.eval("document.getElementById('sheet-body').innerText");
    check(detail.includes('A 级') && detail.includes('前海东沿14号') && detail.includes('平台参考') && !detail.includes('建议停留'), '商铺展示原评级、地址、平台信息，不编造停留时间', detail);
    check(await p.eval("!document.querySelector('#sheet-body .next')"), '清单前后翻阅不冒充步行导航');
    await p.shot('collection-shop-detail');
    await p.click('#sheet [data-close]');
    await p.eval("document.getElementById('collection-kind').value='all'; document.getElementById('collection-search').value='郭沫若'; document.getElementById('collection-search').dispatchEvent(new Event('input')); true");
    check(await p.eval("document.querySelectorAll('.collection-item').length === 1 && !!document.querySelector('[data-place=guomoruo]')"), '郭沫若故居可按常用名称找到，未重复新增');
    await p.click('[data-place=guomoruo]');
    detail = await p.eval("document.getElementById('sheet-body').innerText");
    check(detail.includes('第 48 条') && detail.includes('A 级') && detail.includes('郭沫若故居'), '郭沫若第48条与Excel一致');
    await p.shot('collection-guomoruo');
    await p.click('#sheet [data-close]');
    await p.eval("document.getElementById('collection-search').value='锡晋斋'; document.getElementById('collection-search').dispatchEvent(new Event('input')); document.querySelector('[data-place=gongwang_xijin]').click(); true");
    detail = await p.eval("document.getElementById('sheet-body').innerText");
    check(detail.includes('待复核') && detail.includes('故宫'), '保留锡晋斋与平复帖的审计提示');
    await p.click('#sheet [data-close]');
    await p.eval("document.getElementById('collection-search').value='故宫'; document.getElementById('collection-search').dispatchEvent(new Event('input')); true");
    check(await p.eval("!!document.querySelector('[data-place=gongwang_xijin]')"), '审计提示中的关键词也可搜索');
    await p.eval("document.getElementById('collection-search').value='不存在的zzzz'; document.getElementById('collection-search').dispatchEvent(new Event('input')); true");
    check(await p.eval("document.getElementById('collection-items').textContent.includes('没有符合')"), '搜索空结果可恢复');
    await p.click('#back');
    await sleep(600);
    check(await p.eval("!document.getElementById('list').hidden && document.getElementById('cards').textContent.includes('南锣鼓巷')"), '返回首页保留新旧目的地');
    await p.eval("document.querySelector('[data-open=nanluo_shichahai]').scrollIntoView(); true");
    await p.shot('collection-home-entry');
    await p.click('[data-open=nanluo_shichahai]');
    await sleep(250);
    check(await p.eval("!document.getElementById('collection').hidden && document.querySelectorAll('.collection-item').length === 100"), '首页新增入口可进入完整清单');
  },
  async collection_host(p) {
    // 浏览器内的桥接模拟可检查本地及公开页面；不发帖，也不冒充真机验收。
    const script = await p.send('Page.addScriptToEvaluateOnNewDocument', {source: `
      window.__collectionHost = {ready:null, left:0, watch:0};
      navigator.geolocation.watchPosition = function(){window.__collectionHost.watch++; throw new Error('Unexpected GPS');};
      window.AriHost = {catalog:function(text){var a=JSON.parse(text); window.__collectionHost.keys=a.map(function(m){return m.key;});
        return a.every(function(m){return m.proj && m.entrance && m.canvas && m.area && m.places.every(function(p){return p.r>0;});});},
        visitorId:function(){return 'native-visitor-00000001';}, ready:function(k){window.__collectionHost.ready=k;},
        leave:function(){window.__collectionHost.ready=null;window.__collectionHost.left++;}};
    `});
    try {
      await p.open('/#nanluo_shichahai');
      check(await p.eval("document.querySelectorAll('.collection-item').length === 100 && !document.getElementById('collection').hidden"), '旧App桥接下也能浏览全部100条');
      check(await p.eval("window.__collectionHost.watch === 0 && window.__collectionHost.ready === null && !window.__collectionHost.keys.includes('nanluo_shichahai')"), '纯清单不启动定位，也不会使旧App几何解析失败');
      await p.click('#view-map');
      check(await p.eval("!document.getElementById('mapwrap').hidden && document.querySelectorAll('.spot').length === 37 && window.__collectionHost.watch === 0 && window.__collectionHost.ready === null"), 'App桥接中可浏览37处地图参考点，不调用原生到站');
      await p.click('#view-list');
      await p.click('[data-place=guomoruo]');
      check(await p.eval("AriTour.back() && !document.getElementById('sheet').classList.contains('show')"), 'App返回键收起清单详情');
      await p.eval("location.hash='wmhg'; true");
      await sleep(300);
      check(await p.eval("window.__collectionHost.ready === 'wmhg' && document.getElementById('collection').hidden && !document.getElementById('mapwrap').hidden"), '从清单切回原有地图仍能请求原生导览');
      await p.eval("location.hash='nanluo_shichahai'; true");
      await sleep(300);
      check(await p.eval("window.__collectionHost.ready === null && window.__collectionHost.left > 0 && !document.getElementById('collection').hidden"), '地图转回清单会退出当前原生景区');
    } finally { await p.send('Page.removeScriptToEvaluateOnNewDocument', {identifier:script.identifier}); }
  },
  async waiting_marker(p) {
    const script = await p.send('Page.addScriptToEvaluateOnNewDocument', {source: `
      navigator.geolocation.watchPosition = function(){return 987654;};
      navigator.geolocation.clearWatch = function(){};
    `});
    try {
      await p.open('/');
      await p.click('[data-open=wmhg]');
      await sleep(150);
      check(await p.eval("!document.getElementById('me').hidden && document.getElementById('me').classList.contains('off')"), '首次尚无fix时保留灰色圆点，不提前显示有效定位');
      check(await p.eval("document.getElementById('status').textContent.includes('正在定位')"), '等待首次fix时明确显示正在定位');
      await p.shot('waiting-marker');
    } finally { await p.send('Page.removeScriptToEvaluateOnNewDocument', {identifier:script.identifier}); }
  },
  async collection_map_view(p) {
    await p.open('/#nanluo_shichahai');
    const point = await p.eval("(function(){var r=document.getElementById('view-map').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()");
    await p.touch('touchStart', [point]);
    await p.touch('touchEnd', []);
    await sleep(250);
    const state = await p.eval("({mapVisible:!document.getElementById('mapwrap').hidden,headerY:document.querySelector('.topbar').getBoundingClientRect().y,tabsY:document.getElementById('collection-views').getBoundingClientRect().y,scrollY:scrollY})");
    check(state.mapVisible && state.headerY >= 0 && state.tabsY >= 0 && state.scrollY === 0, '真实触摸打开地图后标题与切换栏均可见', state);
    await p.shot('collection-map-touch');
    await p.click('#view-list');
    check(await p.eval("!document.getElementById('collection').hidden && document.querySelectorAll('.collection-item').length===100"), '地图可返回完整清单');
  },
  async collection_media(p) {
    await p.open('/?debug=1#nanluo_shichahai');
    check(await p.eval("!document.getElementById('collection-views').hidden"), '清单与地图切换入口可见');
    await p.click('#view-map');
    check(await p.eval("!document.getElementById('mapwrap').hidden && document.getElementById('collection').hidden && document.querySelectorAll('.spot').length === 37"), '地图只标37处已登记位置');
    check(await p.eval("document.getElementById('me').hidden && document.getElementById('bell').hidden && document.querySelector('.bottombar').hidden"), '参考地图不显示假定位或到站控件');
    await p.eval("AriTourDebug.error('timeout'); true");
    check(await p.eval("AriTourDebug.snapshot().status === 'waiting' && document.getElementById('me').hidden"), '切换后迟到的GPS错误不进入浏览地图');
    check(await p.eval("document.getElementById('ly-water').getAttribute('d').length > 1000 && document.getElementById('credit').textContent.includes('OpenStreetMap')"), '湖面轮廓及地图署名已载入');
    await p.shot('collection-map');
    await p.eval("document.querySelector('[aria-label=\"郭沫若故居（郭沫若纪念馆）\"]').click(); true");
    check(await p.eval("document.getElementById('sheet-body').innerText.includes('来源标记的位置') && !!document.querySelector('[data-show-map=guomoruo]')"), '地图点开郭沫若详情，带位置口径和来源');
    await p.click('[data-show-map=guomoruo]');
    check(await p.eval("!document.getElementById('sheet').classList.contains('show') && document.querySelector('[aria-label=\"郭沫若故居（郭沫若纪念馆）\"]').getBoundingClientRect().left > 0"), '详情可聚焦地图位置');
    await sleep(150);
    check(await p.eval("document.querySelector('.topbar').getBoundingClientRect().top >= 0 && !document.getElementById('collection-views').hidden"), '聚焦位置后标题及清单切换仍可见');
    await p.shot('collection-map-focus');
    await p.click('#view-list');
    check(await p.eval("document.querySelectorAll('.collection-item').length === 100 && !document.getElementById('collection').hidden"), '返回清单仍完整保留100条');
    const photos = JSON.parse(await readFile(join(TOUR_DIR, '../../utils/import_data/nanluo_shichahai_tour_photos.json'), 'utf8')).photos;
    for (const photo of photos) {
      await p.eval(`document.querySelector('[data-place="${photo.identity_key}"]').click(); true`);
      const decoded = await p.eval("Promise.all(Array.from(document.querySelectorAll('#sheet-body .tour-photo img')).map(function(i){return i.decode().then(function(){return i.naturalWidth>0;}).catch(function(){return false;});}))");
      check(decoded.length === 1 && decoded[0], `第${photo.seq}条资料图实际解码成功`, decoded);
      check(await p.eval("!!document.querySelector('#sheet-body .tour-photo figcaption a')"), '图片带可查阅来源');
      if (photo.seq === 48) await p.shot('collection-photo-guomoruo');
      await p.click('#sheet [data-close]');
    }
    await p.click('#back');
    await sleep(400);
    await p.click('[data-open=wmhg]');
    check(await p.eval("document.getElementById('collection-views').hidden && !document.getElementById('me').hidden"), '切回既有地图恢复定位控件');
  },
  async wanping(p) {
    const m = JSON.parse(await readFile(join(TOUR_DIR, 'data/wanping.json'), 'utf8'));
    const east = m.places.find((item) => item.id === 'east_gate');
    await p.geo('granted', [east.lat, east.lon, 5]);
    await p.open('/');
    const cards = await p.eval("document.getElementById('cards').innerText");
    check(cards.includes('伪满皇宫') && cards.includes('宛平城'), '清单同时显示长春和北京景区', cards);
    await p.eval("document.querySelector('[data-open=wanping]').click(); true");
    await sleep(800);
    let state = await p.state();
    check(state.status.includes('顺治门'), '宛平城GPS到达东门', state.status);
    check(state.summary.includes('0 元'), '默认免费线显示零门票', state.summary);
    await p.eval("document.getElementById('route-details').open = true; true");
    const detail = await p.eval("document.getElementById('route-detail-body').innerText");
    check(detail.includes('不登城墙') && detail.includes('周一') && detail.includes('半景画'), '免费边界、闭馆日和预约分别说明', detail);
    await p.eval("document.getElementById('route-details').open = false; document.querySelector('[aria-label=\"卢沟桥\"]').click(); true");
    const offRoute = await p.eval("document.querySelector('#sheet-body .next small').innerText");
    check(offRoute.includes('直线') && !offRoute.includes('分钟'), '路线外无道路分段时，不把直线距离当步行时长', offRoute);
    await p.eval("document.querySelector('#sheet [data-close]').click(); true");
    const pathFree = await p.eval("document.getElementById('ly-route').getAttribute('d')");
    await p.eval("document.querySelector('[data-route=full]').click(); true");
    state = await p.state();
    check(state.summary.includes('50 元'), '全面线显示参考门票', state.summary);
    check(await p.eval("document.getElementById('ly-route').getAttribute('d')") !== pathFree, '全面线画出不同的步行线');
    await p.eval("document.getElementById('route-details').open = true; true");
    check((await p.eval("document.getElementById('route-detail-body').innerText")).includes('石狮'), '全面线说明含桥面与碑刻');
    await p.eval("document.getElementById('route-details').open = false; document.querySelector('[aria-label=\"卢沟桥\"]').click(); true");
    const nextWalk = await p.eval("document.querySelector('#sheet-body .next small').innerText");
    check(nextWalk.includes('17 分钟'), '卢沟桥到雕塑园使用约1公里的道路距离，不能用约400米直线代替', nextWalk);
    await p.eval("document.getElementById('route-details').open = false; document.querySelector('[aria-label=\"中国人民抗日战争纪念馆\"]').click(); true");
    const sheet = await p.eval("document.getElementById('sheet-body').innerText");
    check(sheet.includes('英烈') && sheet.includes('时间已计入整体'), '馆内分区完整展示但不重复计时', sheet.slice(0, 300));
    check((await p.eval("document.querySelectorAll('#sheet-body .source a').length")) > 0, '介绍保留可打开的官方出处');
    await p.shot('wanping-museum');
    await p.eval("document.querySelector('#sheet [data-close]').click(); true");
    await sleep(400);
    await p.eval("document.getElementById('map').dispatchEvent(new WheelEvent('wheel', {deltaY: 1800, clientX: 195, clientY: 400, bubbles: true, cancelable: true})); true");
    await p.shot('wanping-full');
  },
  async photos(p) {
    const m = JSON.parse(await readFile(join(TOUR_DIR, 'data/wanping.json'), 'utf8'));
    await p.open('/');
    const cover = await p.eval("document.querySelector('[data-open=wanping] img')?.getAttribute('src')");
    check(cover === m.card.cover && !!cover, '宛平城首页使用已收录的照片', cover);
    await p.eval("document.querySelector('[data-open=wanping]').click(); true");
    for (const id of ['east_gate', 'war_museum', 'square', 'main_street', 'west_gate', 'bridge', 'sculpture_park']) {
      const place = m.places.find((item) => item.id === id);
      await p.eval(`document.querySelector('[aria-label=${JSON.stringify(place.name.zh)}]').click(); true`);
      const paths = [...new Set([place.photo, ...place.stops.map((s) => m.stops[s].photo)].filter(Boolean))];
      // lazy图片只有滚入视口才加载，逐张滚动后检查真实解码结果。
      for (const path of paths) {
        const exists = await p.eval(`!!document.querySelector('#sheet-body img[src=${JSON.stringify(path)}]')`);
        if (!exists) { check(false, '照片已渲染：' + path); continue; }
        await p.eval(`document.querySelector('#sheet-body img[src=${JSON.stringify(path)}]')?.scrollIntoView(); true`);
        let ok = false;
        for (let i = 0; i < Math.ceil(IMAGE_TIMEOUT_MS / 150); i++) {
          ok = await p.eval(`(function(){var im=document.querySelector('#sheet-body img[src=${JSON.stringify(path)}]');return !!im && im.complete && im.naturalWidth>0})()`);
          if (ok) break;
          await sleep(150);
        }
        check(ok, '照片实际载入：' + path);
      }
      const credit = await p.eval("Array.from(document.querySelectorAll('#sheet-body figure figcaption a')).every(function(a){return a.href.startsWith('https:') && a.textContent.includes('图片出处')}) && document.querySelectorAll('#sheet-body figure figcaption a').length");
      check(credit >= paths.length, '各照片旁展示对应出处：' + id, credit);
      await p.shot('photos-' + id);
      await p.eval("document.querySelector('#sheet [data-close]').click(); true");
    }
  },
  async host(p) {
    if (!LOCAL) return;
    const script = await p.send("Page.addScriptToEvaluateOnNewDocument", { source: `
      window.__hostWatch = 0;
      navigator.geolocation.watchPosition = function () { window.__hostWatch++; throw new Error('host must not start browser GPS'); };
      window.AriHost = { catalog: function () { return true; }, museums: function () { return '["wmhg"]'; }, visitorId: function () { return 'native-visitor-00000001'; },
        ready: function (key) { window.__hostReady = key; }, leave: function () { window.__hostLeft = true; }, requestLocation: function () {} };
    ` });
    try {
      await p.send("Page.navigate", { url: BASE + "/?debug=1#wmhg" });
      for (let i = 0; i < 80 && !(await p.eval("!!window.AriTour && window.__hostReady === 'wmhg'")); i++) await sleep(100);
      const museum = JSON.parse(await readFile(join(TOUR_DIR, "data/wmhg.json"), "utf8"));
      const place = museum.places.find((item) => item.id === "tongde");
      const now = Date.now();
      const snapshot = { museum: museum.key, status: "live", x: place.x, y: place.y, acc: 5, inside: place.id, connectedAt: now - 5,
        history: [{ pid: place.id, at: now, museum: museum.key }] };
      await p.eval(`AriTour.state(${JSON.stringify(snapshot)}); true`);
      let state = await p.state();
      check(state.status === "位于「同德殿」热区" && state.visited.startsWith("已游览 1 /"), "host：原生状态显示到站并记消息", state);
      await p.eval(`AriTour.state(${JSON.stringify(snapshot)}); true`);
      check((await p.state()).visited.startsWith("已游览 1 /"), "host：重复状态不重复记消息");
      check((await p.eval("window.__hostWatch")) === 0, "host：不启动浏览器定位");
      await p.eval("AriTour.open('tongde'); true");
      check((await p.state()).sheet === "同德殿", "host：原生通知可以打开介绍");
      check(await p.eval("AriTour.back()"), "host：返回键先收介绍");
      await p.eval("AriTour.back(); true"); await sleep(150);
      check(await p.eval("window.__hostLeft === true && document.getElementById('tour').hidden"), "host：再返回到目的地列表");
    } finally { await p.send("Page.removeScriptToEvaluateOnNewDocument", { identifier: script.identifier }); }
  },
  async fixture(p) {
    if (!LOCAL) return;
    const museum = JSON.parse(await readFile(join(TOUR_DIR, "data/wmhg.json"), "utf8"));
    await p.geo("granted", TONGDE);
    await p.open("/?debug=1#" + museum.key);
    const projection = museum.proj;
    const inverse = (x, y) => {
      const dx = x - projection.tx, dy = y - projection.ty, determinant = projection.a * projection.d - projection.b * projection.c;
      return [projection.lat0 + (-projection.c * dx + projection.a * dy) / determinant / projection.mlat,
        projection.lon0 + (projection.d * dx - projection.b * dy) / determinant / projection.mlon];
    };
    const samples = [];
    for (const place of museum.places) {
      for (const offset of [2.0, 0, 1.05, 1.19, 1.21, 2.5, 0]) {
        const [lat, lon] = inverse(place.x + place.r * offset, place.y);
        samples.push({ lat, lon, acc: offset === 2.5 ? 40 : 5 });
      }
      const [lat, lon] = inverse(place.x, place.y);
      samples.push({ lat, lon, acc: 31 }, { error: "timeout" }, { lat, lon, acc: 5 });
    }
    samples.unshift({ lat: BEIJING[0], lon: BEIJING[1], acc: 5 });
    samples.push({ lat: BEIJING[0], lon: BEIJING[1], acc: 5 });
    const cases = [];
    for (const sample of samples) {
      if (sample.error) await p.eval(`AriTourDebug.error(${JSON.stringify(sample.error)}); true`);
      else {
        await p.moveTo([sample.lat, sample.lon, sample.acc]);
        let arrived = false;
        for (let i = 0; i < 100; i++) {
          const raw = await p.eval("AriTourDebug.snapshot().raw");
          if (raw && Math.abs(raw.lat - sample.lat) < 1e-9 && Math.abs(raw.lon - sample.lon) < 1e-9 && raw.acc === sample.acc) { arrived = true; break; }
          await sleep(50);
        }
        if (!arrived) throw new Error("浏览器没有收到夹具定位");
      }
      const state = await p.eval("AriTourDebug.snapshot()");
      cases.push({ ...sample, expected: { status: state.status, inside: state.inside, x: state.x, y: state.y } });
    }
    const output = fileURLToPath(new URL("../../android/testdata/geofence_cases.json", import.meta.url));
    await mkdir(fileURLToPath(new URL("../../android/testdata/", import.meta.url)), { recursive: true });
    await writeFile(output, JSON.stringify({ museum: museum.key, generated_by: "Chrome watchPosition + app.js", cases }, null, 2) + "\n");
    check(cases.length > 150, "实际浏览器生成到站状态夹具", cases.length);
  },
  async list(p) {
    await p.geo(null, null);
    await p.open("/");
    const text = await p.eval("document.getElementById('cards').innerText");
    check(text.includes("伪满皇宫") && /\d+ 处热区/.test(text), "列表页有伪满皇宫的卡片与热区数", text);
    await p.shot("list");
  },

  async live(p) {
    await p.geo("granted", TONGDE);
    await p.open("/#wmhg");
    let s = await p.state();
    check(s.status === "位于「同德殿」热区" && !s.grey, "在同德殿：圆点亮，底栏写所在热区", s);
    check(s.banner === "同德殿" && s.visited.startsWith("已游览 1 /"), "弹出横幅并记一次游览", s);
    check(s.button === "回到我的位置" && !s.disabled, "按钮可用", s);
    await p.shot("live");

    await p.click("#banner"); await sleep(600);
    s = await p.state();
    check(s.sheet === "同德殿" && s.banner === null, "点横幅打开介绍，横幅收起", s);
    await p.shot("sheet");
    await p.click("#sheet [data-goto]"); await sleep(500);
    check((await p.state()).sheet !== "同德殿", "「下一处」换到路线上的下一个地点", await p.state());
    await p.click("#backdrop"); await sleep(500);

    await p.moveTo(QINMIN, 1200);
    check((await p.state()).status === "位于「勤民楼」热区", "走到勤民楼", await p.state());
    await p.moveTo(SHRINE, 1200);
    s = await p.state();
    check(s.status.includes("建国神庙") && s.visited.startsWith("已游览 3 /"), "走到花园里的建国神庙（重叠的热区取最近的）", s);

    // 浏览器在两次定位之间会报一次「暂时拿不到位置」。它不该让同一处再提醒一遍
    await p.moveTo([SHRINE[0], SHRINE[1], 7], 1200);
    check((await p.state()).visited.startsWith("已游览 3 /"), "信号闪一下不重复计数", await p.state());

    await p.moveTo([JIXI[0], JIXI[1], 80], 1200);
    s = await p.state();
    check(s.status === "定位精度较低 · ±80 米" && s.visited.startsWith("已游览 3 /"), "精度 80 米：圆点动，不触发到站", s);
  },

  async outside(p) {
    await p.geo("granted", BEIJING);
    await p.open("/#wmhg");
    let s = await p.state();
    check(s.grey && s.disabled && /^不在景区范围内 · 距入口 \d+ 公里$/.test(s.status), "在北京：圆点灰，按钮禁用，写明距离", s);
    await p.shot("outside");
    await p.moveTo(NEARBY, 1200);
    s = await p.state();
    check(s.grey && /^不在景区范围内 · 距入口 \d+ 米$/.test(s.status), "院外两百米：仍是灰的", s);
    await p.moveTo(TONGDE, 1200);
    check(!(await p.state()).grey, "走进院子后圆点变亮", await p.state());
  },

  async denied(p) {
    await p.geo("denied", null);
    await p.open("/#wmhg");
    const s = await p.state();
    check(s.grey && s.status === "未获得定位授权" && s.button === "重新授权" && !s.disabled, "拒绝授权：圆点灰，按钮变成重新授权", s);
  },

  async routes(p) {
    await p.geo("granted", BEIJING);
    await p.open("/#wmhg");
    const data = JSON.parse(await p.eval("fetch('data/wmhg.json').then(function (r) { return r.text() })"));
    for (const r of data.routes) {
      await p.click(`#chips [data-route="${r.id}"]`); await sleep(250);
      const s = await p.state();
      check(s.summary.startsWith(`${r.stops.length} 站 · 约 ${r.total} 分钟`), `路线 ${r.id}：摘要与数据一致`, s.summary);
      const last = Math.max(...s.marks.split(" ").flatMap((m) => m.split(/[·–]/)).map(Number).filter(Boolean));
      check(last === r.stops.length, `路线 ${r.id}：标记编号排到 ${r.stops.length}`, s.marks);
    }
    await p.click('#chips [data-route="none"]'); await sleep(250);
    const s = await p.state();
    check(s.marks.split(" ").length === data.places.length && s.marks.startsWith("01 02"), "不显示路线：标记按地点顺序编号", s.marks);
  },

  async params(p) {
    await p.geo("denied", null);                  // 调试参数不经过浏览器定位，拒绝授权也照样有位置
    await p.open(`/?fix=${TONGDE}#wmhg`);
    check((await p.state()).status === "位于「同德殿」热区", "?fix= 给的位置与真实定位走同一条路", await p.state());
    await p.open(`/?fix=${BEIJING}#wmhg`);
    check((await p.state()).grey, "?fix= 在北京：圆点灰", await p.state());

    await p.open("/?sim=1#wmhg");
    let s = await p.state();
    check(s.button === "模拟游览" && !s.grey, "?sim=1：底栏是模拟游览", s);
    await p.click("#locate"); await sleep(6000);
    s = await p.state();
    check(s.button === "暂停" && s.visited.startsWith("已游览 1 /"), "模拟游览走到第一站", s);
    const icons = await p.eval("[getComputedStyle(document.getElementById('locate-icon-go')).display, getComputedStyle(document.getElementById('locate-icon-pause')).display].join('/')");
    check(icons === "none/block", "游览中显示暂停图标", icons);
  },

  async gcj(p) {
    await p.geo("granted", GCJ_TONGDE);
    await p.open("/#wmhg");
    check((await p.state()).grey, "国测局坐标不换算：偏出院外，圆点灰", await p.state());
    await p.open("/?crs=gcj02#wmhg");
    check((await p.state()).status === "位于「同德殿」热区", "加 ?crs=gcj02：回到同德殿", await p.state());
  },

  async touch(p) {
    await p.geo("granted", BEIJING);
    await p.open("/#wmhg");
    let before = (await p.state()).map;
    await p.touch("touchStart", [[200, 500]]);
    for (let i = 1; i <= 8; i++) await p.touch("touchMove", [[200 - i * 15, 500 - i * 20]]);
    await p.touch("touchEnd", []); await sleep(200);
    check((await p.state()).map !== before, "单指拖动：地图跟着走", await p.state());

    await p.touch("touchStart", [[120, 450], [280, 450]]);
    for (let i = 1; i <= 6; i++) await p.touch("touchMove", [[120 + i * 10, 450], [280 - i * 10, 450]]);
    await p.touch("touchEnd", []); await sleep(200);
    const small = Number((await p.state()).map.split(" ").pop());
    await p.touch("touchStart", [[180, 450], [220, 450]]);
    for (let i = 1; i <= 8; i++) await p.touch("touchMove", [[180 - i * 15, 450], [220 + i * 15, 450]]);
    await p.touch("touchEnd", []); await sleep(200);
    const big = Number((await p.state()).map.split(" ").pop());
    check(small < big, "双指捏合缩小、张开放大", { small, big });

    const spot = JSON.parse(await p.eval(`(function () {
      var m = document.getElementById('map').getBoundingClientRect(), hit = null;
      document.querySelectorAll('.spot').forEach(function (sp) {
        var b = sp.querySelector('.spot-num').getBoundingClientRect(), x = b.left + b.width / 2, y = b.top + b.height / 2;
        if (!hit && x > m.left + 20 && x < m.right - 20 && y > m.top + 110 && y < m.bottom - 20) hit = [x, y, sp.getAttribute('aria-label')];
      });
      return JSON.stringify(hit);
    })()`));
    await p.touch("touchStart", [[spot[0], spot[1]]]); await p.touch("touchEnd", []); await sleep(600);
    check((await p.state()).sheet === spot[2], `点按标记「${spot[2]}」打开它的介绍`, await p.state());
    await p.click("#backdrop"); await sleep(400);

    before = (await p.state()).map;
    await p.touch("touchStart", [[300, 85]]);
    for (let i = 1; i <= 6; i++) await p.touch("touchMove", [[300 - i * 25, 85]]);
    await p.touch("touchEnd", []); await sleep(300);
    const scrolled = await p.eval("document.getElementById('chips').scrollLeft");
    check(scrolled > 0 && (await p.state()).map === before, "横滑路线条：路线条滚动，地图不动", { scrolled });
  },

  // 介绍抽屉里的「游客互动」
  async qa(p) {
    const view = () => p.eval(`JSON.stringify((function () {
      var box = document.getElementById('qa');
      if (!box || box.hidden) return { shown: false };
      var items = Array.from(document.querySelectorAll('#qa-list .qa-item'));
      return {
        shown: true, title: box.querySelector('h4').textContent, count: items.length,
        first: items[0] ? items[0].innerText : '', list: document.getElementById('qa-list').innerText,
        thinking: !!document.querySelector('#qa-list .qa-thinking'), more: !!document.querySelector('[data-qa-more]'),
        notice: document.getElementById('qa-notice').textContent, input: document.getElementById('qa-input').value,
        sending: document.getElementById('qa-send').disabled,
        tags: document.querySelectorAll('#qa-list img, #qa-list b, #qa-list script').length
      };
    })())`).then(JSON.parse);
    const type = (text) => p.eval(`(function () { var i = document.getElementById('qa-input'); i.value = ${JSON.stringify(text)};
      i.dispatchEvent(new Event('input', { bubbles: true })); return true })()`);
    const submit = () => p.eval("document.getElementById('qa-form').requestSubmit(), true");
    // 打开同德殿的介绍，等互动一块有了结果。返回「刚点开那一刻这一块显示了没有」
    const openTongde = async (expectShown = true) => {
      await p.geo("granted", BEIJING);
      await p.open("/#wmhg");
      // 点开与取样放在同一段脚本里：分两次往返的话，本机的假接口早就答完了
      const atOnce = await p.eval(`(function () { document.querySelector('.spot[aria-label="同德殿"]').click();
        var box = document.getElementById('qa'); return !!box && !box.hidden })()`);
      for (let i = 0; i < (expectShown ? 40 : 6); i++) {
        const s = await view();
        if (s.shown && (s.count || s.notice || /还没有人提问/.test(s.list))) break;
        await sleep(250);
      }
      return atOnce;
    };

    // 无头浏览器的页面默认不算「有焦点」，focus() 不触发 focusin；打开之后才和真机上点进输入框一样
    await p.send("Emulation.setFocusEmulationEnabled", { enabled: true });

    if (!LOCAL) {
      await openTongde();
      const s = await view();
      check(s.shown && s.title === "游客互动" && !/载入不了/.test(s.notice), "线上：互动一块在，列表能载入（不发帖）", s);
      return;
    }

    try {
      stub.mode = "ok"; stub.topics = {}; stub.posts = 0;
      stubSeed("tongde", [
        ...Array.from({ length: 21 }, (_, i) => ({ question: `第 ${i + 1} 个问题`, answer: `第 ${i + 1} 个回答` })),
        { question: '<img src=x onerror="window.__xss=1">同德殿是哪年建的？', answer: "<b>1938 年</b>建成。\n第二行" },
      ]);
      const early = await openTongde();
      let s = await view();
      check(!early && s.shown && s.title === "游客互动", "介绍下面有「游客互动」，拿到列表之后才显示", { early, shown: s.shown });
      check(s.count === 20 && s.more, "载入最新的 20 条，还有更早的", { count: s.count, more: s.more });
      check(s.first.includes("游客提问") && s.first.includes("导览助手"), "别人的提问标「游客提问」，回答标「导览助手」", s.first);
      const xss = await p.eval("typeof window.__xss");
      check(s.tags === 0 && xss === "undefined" && s.first.includes("<img src=x") && s.first.includes("<b>1938 年</b>"),
        "问题与回答里的 HTML 原样显示成文字，不变成元素", { tags: s.tags, xss, first: s.first });
      const below = await p.eval(`(function () { var q = document.getElementById('qa').getBoundingClientRect().top;
        var src = document.querySelectorAll('#sheet-body .source'), nx = document.querySelector('#sheet-body .next');
        return src[src.length - 1].getBoundingClientRect().bottom <= q && (!nx || q < nx.getBoundingClientRect().top) })()`);
      check(below, "位置在「介绍出处」之后、「前往下一处」之前", below);

      const steady = await p.eval(`(function () { document.getElementById('qa-input').focus(); return new Promise(function (ok) {
        setTimeout(function () {
          var i = document.getElementById('qa-input').getBoundingClientRect(), sh = document.getElementById('sheet').getBoundingClientRect();
          ok(JSON.stringify({ y: Math.round(i.top), focused: document.hasFocus(), app: document.getElementById('app').scrollTop, top: document.querySelector('.topbar').getBoundingClientRect().top,
            msgs: document.getElementById('msgs').getBoundingClientRect().top >= window.innerHeight,
            input: i.top >= sh.top && i.bottom <= window.innerHeight * 0.55 }));
        }, 600); }) })()`).then(JSON.parse);
      check(steady.app === 0 && steady.top === 0 && steady.msgs && steady.input,
        "点进输入框：输入框挪到屏幕上半截，外层页面不跟着滚", steady);
      await p.eval("document.getElementById('qa-input').blur(), true");

      await p.click("[data-qa-more]"); await sleep(500);
      s = await view();
      check(s.count === 22 && !s.more, "「更早的提问」把剩下的取回来", { count: s.count, more: s.more });

      await type("溥仪在这里住过吗？"); await submit(); await sleep(250);
      s = await view();
      check(s.thinking && s.sending && s.input === "" && s.first.includes("我的提问") && s.first.includes("溥仪在这里住过吗？"),
        "提问后：输入框清空，按钮禁用，列表顶上是我的问题和「思考中」", s);
      await sleep(900);
      s = await view();
      check(!s.thinking && !s.sending && s.count === 23 && s.first.includes("答：溥仪在这里住过吗？"), "回答回来，替换掉「思考中」", s);
      await p.eval("document.getElementById('qa').scrollIntoView(), true");
      await p.shot("qa-answered");

      await type("写到一半");
      await p.click(".sheet-actions .btn-primary[data-goto]"); await sleep(600);
      s = await view();
      check((await p.state()).sheet !== "同德殿" && s.input === "" && /还没有人提问/.test(s.list), "翻到下一处：是那一处自己的（空）列表和空输入框", s);
      await p.click(".sheet-actions .btn-secondary[data-goto]"); await sleep(600);
      s = await view();
      check((await p.state()).sheet === "同德殿" && s.input === "写到一半" && s.count === 23, "翻回来：草稿和列表都还在", s);

      const posts = stub.posts;
      await type("这条会失败"); await submit(); await sleep(1200);
      s = await view();
      check(s.notice.startsWith("提交失败：导览助手暂时没有答上来") && s.input === "这条会失败" && s.count === 23 && !s.thinking && !s.sending,
        "接口失败：写明原因，问题回到输入框，列表不留残项", s);

      await type("广告：低价代订门票"); await submit(); await sleep(1200);
      s = await view();
      check(s.count === 24 && s.first.includes("只有你自己看得到"), "被判为与参观无关的提问：注明只有自己看得到", s.first);

      await type("  "); await submit(); await sleep(200);
      s = await view();
      check(s.notice === "先输入你的问题。" && stub.posts === posts + 2, "空问题不发请求", { notice: s.notice, posts: stub.posts - posts });

      stub.mode = "down";
      await openTongde();                           // 接口在但报错：要让人看得到出了什么事
      s = await view();
      check(s.shown && /载入不了/.test(s.notice) && s.count === 0, "列表接口报错：写明载入不了，给重试", s);
      stub.mode = "ok";
      await p.click("[data-qa-retry]"); await sleep(600);
      s = await view();
      check(s.count === 20 && s.notice === "", "点重试后列表回来", { count: s.count, notice: s.notice });

      stub.mode = "off";
      const flashed = await openTongde(false);
      s = await view();
      check(!flashed && !s.shown && (await p.state()).sheet === "同德殿", "接口不存在：这一块从头到尾不显示，介绍照常", { flashed, shown: s.shown });
      await p.click(".sheet-actions .btn-primary[data-goto]"); await sleep(500);
      check(!(await view()).shown && (await p.state()).sheet !== "同德殿", "翻到下一处也不再出现", await view());
    } finally {
      stub.mode = "ok"; stub.topics = {};
      // 上面故意让接口回过 404 / 500 / 502，浏览器会各记一条「资源加载失败」
      p.errors = p.errors.filter((e) => !/\/api\/tour\//.test(e));
    }
  },
};

async function main() {
  const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SCENES);
  const unknown = names.filter((n) => !SCENES[n]);
  if (unknown.length) { console.error(`没有这些场景：${unknown}。可选：${Object.keys(SCENES)}`); process.exit(2); }

  const local = BASE ? null : await startStatic();
  if (local) { BASE = local.url; LOCAL = true; }
  const profile = await mkdtemp(join(tmpdir(), "ari-tour-chrome-"));
  const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${DEBUG_PORT}`, `--user-data-dir=${profile}`,
    "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  chrome.on("error", (e) => { console.error(`起不了 Chrome（${CHROME}）：${e.message}。用 CHROME=/路径 指定`); process.exit(2); });
  try {
    for (let i = 0; ; i++) {
      try { await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/version`)).json(); break; }
      catch (e) { if (i > 50) throw new Error("Chrome 的调试端口一直没起来"); await sleep(200); }
    }
    console.log(`对着 ${BASE} 跑 ${names.length} 个场景`);
    for (const name of names) {
      const target = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/new?about:blank`, { method: "PUT" })).json();
      const ws = new WebSocket(target.webSocketDebuggerUrl);
      await new Promise((res, rej) => { ws.addEventListener("open", res); ws.addEventListener("error", rej); });
      const page = new Page(ws);
      await page.send("Page.enable"); await page.send("Runtime.enable"); await page.send("Log.enable");
      await page.send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
      await page.send("Emulation.setTouchEmulationEnabled", { enabled: true });
      console.log(`\n${name}`);
      try { await SCENES[name](page); }
      catch (e) { check(false, "场景中途出错", e.message); }
      check(page.errors.length === 0, "控制台没有报错", page.errors);
      ws.close();
    }
  } finally {
    chrome.kill();
    local?.server.close();
    const safeProfile = resolve(profile);
    if (!safeProfile.startsWith(resolve(tmpdir()) + sep + "ari-tour-chrome-")) throw new Error("临时浏览器路径越界，拒绝清理");
    await rm(safeProfile, { recursive: true, force: true }).catch(() => {});
  }
  console.log(failures ? `\n✗ ${failures} 项没过` : "\n✓ 全部通过");
  process.exit(failures ? 1 : 0);
}

main();
