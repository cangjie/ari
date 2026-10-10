// 导览站的浏览器验收：用无头 Chrome 模拟手机视口与 GPS，把页面真跑一遍。
//
//   node web_api/tests/tour_browser_check.mjs                  # 全部场景
//   node web_api/tests/tour_browser_check.mjs live outside     # 只跑点名的
//   SHOTS=/某个目录 node web_api/tests/tour_browser_check.mjs   # 另存每个场景的截图
//   BASE=https://tour.snowmeet.top node …                      # 对着线上跑（默认自己起一个本地静态服务）
//
// pytest 那边（test_tour.py）只管数据对不对得上；页面的定位、到站、手势在这里验。
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
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const TOUR_DIR = fileURLToPath(new URL("../tour/", import.meta.url));
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const SHOTS = process.env.SHOTS || "";
const DEBUG_PORT = 9333;
const MIME = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".woff2": "font/woff2", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp" };

// 几个有出处的位置（WGS-84）。同德殿等取自 wmhg_route_data.POINTS
const TONGDE = [43.90398, 125.34323], QINMIN = [43.90412, 125.34226], SHRINE = [43.90323, 125.34420];
const JIXI = [43.90359, 125.34239], BEIJING = [39.9163, 116.3972], NEARBY = [43.9010, 125.3440];
const GCJ_TONGDE = [43.906420, 125.349804];     // 同德殿加偏成国测局坐标后的值

let BASE = process.env.BASE || "";
let failures = 0;

function check(ok, what, got) {
  if (!ok) failures++;
  console.log(`  ${ok ? "✓" : "✗"} ${what}${ok ? "" : `  —— 实际：${JSON.stringify(got)}`}`);
}

async function startStatic() {
  const server = createServer(async (req, res) => {
    const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^([/\\])+/, "");
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
      ? "!document.getElementById('tour').hidden && !['', '正在定位…'].includes(document.getElementById('status').textContent)"
      : "!!document.querySelector('#cards .card')";
    for (let i = 0; i < 80; i++) {
      if (await this.eval(want).catch(() => false)) break;
      await sleep(250);
    }
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
};

async function main() {
  const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SCENES);
  const unknown = names.filter((n) => !SCENES[n]);
  if (unknown.length) { console.error(`没有这些场景：${unknown}。可选：${Object.keys(SCENES)}`); process.exit(2); }

  const local = BASE ? null : await startStatic();
  if (local) BASE = local.url;
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
    await rm(profile, { recursive: true, force: true }).catch(() => {});
  }
  console.log(failures ? `\n✗ ${failures} 项没过` : "\n✓ 全部通过");
  process.exit(failures ? 1 : 0);
}

main();
