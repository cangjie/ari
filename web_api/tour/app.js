/* Ari Travel 导览页。原生 JS，无框架、无外部依赖。
 *
 * 数据全部来自 data/<馆>.json（utils/import_data/tour_build.py 生成）。地点的画布坐标、
 * 热区半径、景区范围、经纬度换算参数都在那份文件里，这里不写死任何坐标。
 *
 * 定位只有一条路径：onFix()。真实 GPS、?fix= 给的假定位都从这里进，
 * 所以用 ?fix= 验过的行为就是真机上的行为。
 *
 * 调试参数（界面上不露出）：
 *   ?fix=纬度,经度[,精度米]   用一个固定的定位代替 GPS
 *   ?sim=1                    不用 GPS，圆点可拖动，底栏变成「模拟游览」（原型的玩法）
 *   ?crs=gcj02                把定位从国测局坐标换回 WGS-84 再用
 *   ?debug=1                  地图右下角显示原始经纬度、精度与状态
 */
(function () {
  "use strict";

  var MUSEUMS = ["wmhg"];
  var ACC_TRIGGER_M = 30;   // 精度差于此的定位只移动圆点，不触发到站
  var STAY_FACTOR = 1.2;    // 已在某个热区里时，走出 1.2 倍半径才算离开，免得在边上反复进出
  var BANNER_MS = 6000;
  var ZOOM_MAX = 2.5;
  var FAR_ZOOM = 0.75;      // 缩到比这更小就收起地点名字，只留编号
  var SIM_SPEED = 70;       // 模拟游览的速度，画布像素/秒
  var GEO_OPTIONS = { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 };

  var $ = function (id) { return document.getElementById(id); };
  var query = new URLSearchParams(location.search);
  var OPT = {
    sim: query.get("sim") === "1",
    debug: query.get("debug") === "1",
    gcj: query.get("crs") === "gcj02",
    fix: parseFix(query.get("fix"))
  };

  var data = {};        // {馆 key: JSON}
  var M = null;         // 当前打开的馆
  var st = null;        // 当前馆的界面状态
  var spots = {};       // {地点 id: {btn, ring, num}}
  var labels = [];      // [{el, x, y}]
  var watchId = null, bannerTimer = null, raf = null;
  var gesture = { pointers: {}, pan: null, pinch: null, drag: false };

  // ------------------------------------------------------------ 小工具
  function parseFix(s) {
    if (!s) return null;
    var a = s.split(",").map(Number);
    if (a.length < 2 || isNaN(a[0]) || isNaN(a[1])) return null;
    return { lat: a[0], lon: a[1], acc: isNaN(a[2]) ? 5 : a[2] };
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function pad2(n) { return n < 10 ? "0" + n : String(n); }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function project(lat, lon) {
    var p = M.proj;
    var e = (lon - p.lon0) * p.mlon, n = (lat - p.lat0) * p.mlat;
    return [p.a * e + p.b * n + p.tx, p.c * e + p.d * n + p.ty];
  }

  function haversine(lat1, lon1, lat2, lon2) {
    var R = 6371000, rad = Math.PI / 180;
    var dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
    var h = Math.sin(dp / 2) * Math.sin(dp / 2) +
      Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) * Math.sin(dl / 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function inPoly(x, y, poly) {
    var c = false;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c;
    }
    return c;
  }

  function distPoly(x, y, poly) {
    var best = Infinity;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var x1 = poly[j][0], y1 = poly[j][1], dx = poly[i][0] - x1, dy = poly[i][1] - y1;
      var l2 = dx * dx + dy * dy;
      var t = l2 === 0 ? 0 : clamp(((x - x1) * dx + (y - y1) * dy) / l2, 0, 1);
      best = Math.min(best, Math.hypot(x - x1 - t * dx, y - y1 - t * dy));
    }
    return best;
  }

  // 景区范围 = 院区边界外扩一圈。画布是等比的，所以直接在画布坐标里算
  function inArea(xy) {
    var a = M.area;
    return inPoly(xy[0], xy[1], a.poly) || distPoly(xy[0], xy[1], a.poly) <= a.buffer;
  }

  // 国测局坐标 → WGS-84（一次近似，误差一两米）。国内部分安卓浏览器给的定位是加过偏的
  function gcjToWgs(lat, lon) {
    var a = 6378245.0, ee = 0.00669342162296594323, PI = Math.PI;
    var x = lon - 105.0, y = lat - 35.0;
    var dLat = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    dLat += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
    dLat += (20.0 * Math.sin(y * PI) + 40.0 * Math.sin(y / 3.0 * PI)) * 2.0 / 3.0;
    dLat += (160.0 * Math.sin(y / 12.0 * PI) + 320 * Math.sin(y * PI / 30.0)) * 2.0 / 3.0;
    var dLon = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    dLon += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
    dLon += (20.0 * Math.sin(x * PI) + 40.0 * Math.sin(x / 3.0 * PI)) * 2.0 / 3.0;
    dLon += (150.0 * Math.sin(x / 12.0 * PI) + 300.0 * Math.sin(x / 30.0 * PI)) * 2.0 / 3.0;
    var radLat = lat / 180.0 * PI, magic = Math.sin(radLat);
    magic = 1 - ee * magic * magic;
    var sqrtMagic = Math.sqrt(magic);
    dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * PI);
    dLon = (dLon * 180.0) / (a / sqrtMagic * Math.cos(radLat) * PI);
    return [lat - dLat, lon - dLon];
  }

  // ------------------------------------------------------------ 存取
  function storeKey() { return "ari-tour:" + M.key; }

  function save() {
    try {
      localStorage.setItem(storeKey(), JSON.stringify({ routeId: st.routeId, msgs: st.msgs }));
    } catch (e) { /* 无痕模式等存不了就算了，只是刷新后不记得 */ }
  }

  function restore() {
    try {
      var o = JSON.parse(localStorage.getItem(storeKey()) || "null");
      if (!o) return;
      if (o.routeId === "none" || M.routes.some(function (r) { return r.id === o.routeId; })) {
        st.routeId = o.routeId;
      }
      st.msgs = (o.msgs || []).filter(function (m) { return placeById(m.pid); });
    } catch (e) { /* 存的东西读不出来就当没有 */ }
  }

  // ------------------------------------------------------------ 路线
  function placeById(id) {
    for (var i = 0; i < M.places.length; i++) if (M.places[i].id === id) return M.places[i];
    return null;
  }

  function route() {
    for (var i = 0; i < M.routes.length; i++) if (M.routes[i].id === st.routeId) return M.routes[i];
    return null;
  }

  // 路线依次经过的地点（同一地点的连续几站只算一处）
  function routePlaceIds(r) {
    var out = [];
    r.stops.forEach(function (seq) {
      var pid = M.stops[seq].place;
      if (out[out.length - 1] !== pid) out.push(pid);
    });
    return out;
  }

  function routePoints(r) {
    var ent = [M.entrance.x, M.entrance.y];
    var pts = routePlaceIds(r).map(function (pid) { var p = placeById(pid); return [p.x, p.y]; });
    return [ent].concat(pts, [ent]);
  }

  // 这个地点上的几站在路线里排第几
  function placeOrdinals(r, pid) {
    var out = [];
    r.stops.forEach(function (seq, k) { if (M.stops[seq].place === pid) out.push(k + 1); });
    return out;
  }

  // 介绍抽屉里「上一处 / 下一处」走的顺序：地点在所选路线上就按路线，否则按全部地点
  function sequenceFor(pid) {
    var r = route();
    if (r) {
      var ids = routePlaceIds(r);
      if (ids.indexOf(pid) >= 0) return { ids: ids, onRoute: true };
    }
    return { ids: M.places.map(function (p) { return p.id; }), onRoute: false };
  }

  // ------------------------------------------------------------ 列表页
  var ICON_CLOCK = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>';
  var ICON_PIN = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>';
  var ICON_NEXT = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>';
  var ICON_PREV = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>';

  function renderCards() {
    var html = MUSEUMS.map(function (key) {
      var m = data[key], c = m.card;
      return '<button class="card" type="button" data-open="' + esc(key) + '">' +
        (c.cover ? '<div class="plate"><img src="' + esc(c.cover) + '" alt="' + esc(c.short.zh) + '"></div>' : "") +
        '<div class="card-body">' +
        '<div class="kicker">' + esc(c.city.zh + " · " + c.district.zh + " · " + c.type.zh) + "</div>" +
        '<div class="card-name"><strong>' + esc(c.short.zh) + "</strong><em>" + esc(c.short.en) + "</em></div>" +
        '<p class="card-desc">' + esc(c.desc.zh) + "</p>" +
        '<div class="card-foot"><div class="card-meta">' +
        "<span>" + ICON_CLOCK + esc(c.hours) + "</span>" +
        "<span>" + ICON_PIN + m.places.length + " 处热区</span>" +
        '</div><span class="card-go">导游地图' + ICON_NEXT + "</span></div>" +
        "</div></button>";
    }).join("");
    $("cards").innerHTML = html;
  }

  // ------------------------------------------------------------ 地图：搭建
  function buildMap() {
    var c = M.canvas, map = M.map;
    $("base").setAttribute("viewBox", "0 0 " + c.w + " " + c.h);
    ["roads", "woods", "walls", "water", "track", "blocks", "paths"].forEach(function (k) {
      $("ly-" + k).setAttribute("d", map[k] || "");
    });

    var overlay = $("overlay");
    overlay.innerHTML = "";
    spots = {};
    labels = [];

    M.labels.forEach(function (l) { addLabel(l.kind, l.t.zh, l.x, l.y); });
    addLabel("gate", M.entrance.name.zh, M.entrance.x, M.entrance.y + 16);

    M.places.forEach(function (p) {
      var ring = document.createElement("div");
      ring.className = "ring";
      overlay.appendChild(ring);
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "spot lp-" + p.lp;
      btn.setAttribute("aria-label", p.name.zh);
      btn.innerHTML = '<span class="spot-num"></span><span class="spot-name">' + esc(p.name.zh) + "</span>";
      btn.addEventListener("click", function () { openIntro(p.id); });
      overlay.appendChild(btn);
      spots[p.id] = { btn: btn, ring: ring, num: btn.firstChild };
    });

    $("tour-name").textContent = M.card.short.zh;
    $("tour-sub").textContent = "导游地图 · " + M.card.short.en;
    $("msgs-park").textContent = M.name.zh;
    $("credit").textContent = M.attribution.zh;
    var north = M.canvas.north * Math.PI / 180;
    $("compass-arrow").style.transform = "rotate(" + M.canvas.north + "deg)";
    $("compass-n").style.transform = "translate(" + Math.sin(north) * 22 + "px," + -Math.cos(north) * 22 + "px)";
    $("me").classList.toggle("drag", OPT.sim);

    var chips = M.routes.map(function (r) {
      return '<button class="chip" type="button" data-route="' + esc(r.id) + '">' + esc(r.label.zh) + "</button>";
    });
    chips.push('<button class="chip" type="button" data-route="none">不显示路线</button>');
    $("chips").innerHTML = chips.join("");
  }

  function addLabel(kind, text, x, y) {
    var el = document.createElement("div");
    el.className = "map-label " + kind;
    el.textContent = text;
    $("overlay").appendChild(el);
    labels.push({ el: el, x: x, y: y });
  }

  // ------------------------------------------------------------ 地图：缩放与平移
  function viewSize() {
    var el = $("map");
    return [el.clientWidth, el.clientHeight];
  }

  function topInset() { return $("routes").offsetHeight; }

  function minZoom() {
    var v = viewSize();
    return clamp(Math.min(v[0] / M.canvas.w, (v[1] - topInset()) / M.canvas.h), 0.3, 1);
  }

  function clampPan(x, y) {
    var v = viewSize(), w = M.canvas.w * st.k, h = M.canvas.h * st.k, top = topInset();
    x = w <= v[0] ? (v[0] - w) / 2 : clamp(x, v[0] - w, 0);
    y = h <= v[1] - top ? top + (v[1] - top - h) / 2 : clamp(y, v[1] - h, top);
    return [x, y];
  }

  function applyPan() {
    $("pan").style.transform = "translate(" + st.pan[0] + "px," + st.pan[1] + "px)";
  }

  function centerOn(x, y) {
    var v = viewSize(), top = topInset();
    st.pan = clampPan(v[0] / 2 - x * st.k, top + (v[1] - top) / 2 - y * st.k);
    applyPan();
  }

  // 缩放不是把整层放大：底图按比例重画，标记与名字只挪位置、大小不变，缩小了也看得清
  function layout() {
    var k = st.k, c = M.canvas, px = function (v) { return v * k + "px"; };
    $("base").setAttribute("width", c.w * k);
    $("base").setAttribute("height", c.h * k);
    $("pan").style.width = px(c.w);
    $("pan").style.height = px(c.h);
    M.places.forEach(function (p) {
      var s = spots[p.id];
      s.btn.style.left = px(p.x);
      s.btn.style.top = px(p.y);
      s.ring.style.left = px(p.x - p.r);
      s.ring.style.top = px(p.y - p.r);
      s.ring.style.width = s.ring.style.height = px(p.r * 2);
    });
    labels.forEach(function (l) { l.el.style.left = px(l.x); l.el.style.top = px(l.y); });
    $("map").classList.toggle("far", k < FAR_ZOOM);
    st.pan = clampPan(st.pan[0], st.pan[1]);
    applyPan();
    updateMe();
  }

  function zoomAt(k, cx, cy) {
    k = clamp(k, minZoom(), ZOOM_MAX);
    var ratio = k / st.k;
    st.pan = [cx - (cx - st.pan[0]) * ratio, cy - (cy - st.pan[1]) * ratio];
    st.k = k;
    layout();
  }

  // ------------------------------------------------------------ 地图：刷新
  function updateRoute() {
    var r = route();
    Array.prototype.forEach.call($("chips").children, function (b) {
      b.classList.toggle("on", b.getAttribute("data-route") === (r ? r.id : "none"));
    });
    $("route-summary").textContent = r
      ? r.stops.length + " 站 · 约 " + r.total + " 分钟（停留 " + r.stay + " + 步行 " + r.walk + "）· 入口出发并返回"
      : "显示全部热区，未选择路线";
    $("ly-route").setAttribute("d", r
      ? "M" + routePoints(r).map(function (q) { return q[0] + " " + q[1]; }).join(" L")
      : "");
    updateSpots();
  }

  function updateSpots() {
    var r = route();
    var seen = {};
    st.msgs.forEach(function (m) { seen[m.pid] = true; });
    M.places.forEach(function (p, i) {
      var s = spots[p.id], ords = r ? placeOrdinals(r, p.id) : [];
      var num = pad2(i + 1);
      if (r) num = ords.length > 2 ? ords[0] + "–" + ords[ords.length - 1] : (ords.join("·") || "·");
      s.num.textContent = num;
      s.btn.classList.toggle("on-route", ords.length > 0);
      s.btn.classList.toggle("dim", !!r && !ords.length);
      s.btn.classList.toggle("visited", !!seen[p.id]);
      s.btn.classList.toggle("inside", st.inside === p.id);
      s.ring.classList.toggle("inside", st.inside === p.id);
    });
  }

  function updateMsgs() {
    var unread = st.msgs.filter(function (m) { return !m.read; }).length;
    $("unread").hidden = !unread;
    $("unread").textContent = unread;
    $("visited").textContent = "已游览 " + st.msgs.length + " / " + M.places.length;
    $("msgs-body").innerHTML = st.msgs.length ? st.msgs.map(function (m) {
      return '<button class="msg' + (m.read ? "" : " unread") + '" type="button" data-msg="' + esc(m.pid) + '">' +
        '<span class="msg-dot"></span><span class="msg-text"><strong>已进入热区：' + esc(placeById(m.pid).name.zh) +
        "</strong><small>" + (m.read ? "已读 · 点击再次查看介绍" : "未读 · 点击查看介绍") + "</small></span>" +
        "<time>" + esc(m.time) + "</time></button>";
    }).join("") : '<p class="msgs-empty">尚未进入任何热区。<br>在地图上走近带编号的景点即可收到讲解消息。</p>';
    updateSpots();
  }

  function fmtDist(m) {
    if (m < 1000) return Math.round(m / 10) * 10 + " 米";
    if (m < 100000) return (m / 1000).toFixed(1) + " 公里";
    return Math.round(m / 1000) + " 公里";
  }

  // 当前位置的圆点、底栏文字与按钮。只有「在景区内有定位」时圆点才是亮的；
  // 其余情况一律灰着：不在景区内、还没定到位就停在入口，中途丢了信号就停在最后的位置
  function updateMe() {
    var live = st.geo === "live" || st.geo === "sim";
    var me = $("me"), k = st.k;
    me.classList.toggle("off", !live);
    me.style.left = st.pos[0] * k + "px";
    me.style.top = st.pos[1] * k + "px";
    var halo = me.firstElementChild;
    var showHalo = st.geo === "live" && st.acc > 8;
    halo.style.display = showHalo ? "" : "none";
    if (showHalo) halo.style.width = halo.style.height = 2 * st.acc * M.canvas.px_per_m * k + "px";

    var inside = st.inside && placeById(st.inside);
    var text;
    switch (st.geo) {
      case "sim":
      case "live":
        text = inside ? "位于「" + inside.name.zh + "」热区"
          : (st.geo === "live" && st.acc > ACC_TRIGGER_M ? "定位精度较低 · ±" + Math.round(st.acc) + " 米" : "未进入热区");
        break;
      case "waiting": text = "正在定位…"; break;
      case "outside": text = "不在景区范围内 · 距入口 " + fmtDist(st.dist); break;
      case "denied": text = "未获得定位授权"; break;
      case "unavailable": text = "暂时无法定位"; break;
      case "timeout": text = "定位超时，仍在尝试…"; break;
      case "insecure": text = "需 HTTPS 才能定位"; break;
      default: text = "此浏览器不支持定位";
    }
    $("status").textContent = text;
    $("status").classList.toggle("muted", !live);

    var btn = $("locate"), label;
    if (st.geo === "sim") { label = st.touring ? "暂停" : "模拟游览"; btn.disabled = false; }
    else if (st.geo === "denied") { label = "重新授权"; btn.disabled = false; }
    else { label = "回到我的位置"; btn.disabled = st.geo !== "live"; }
    $("locate-label").textContent = label;
    // 这两个图标是 SVG 元素，没有 .hidden 属性，只能直接改 hidden 特性
    $("locate-icon-go").toggleAttribute("hidden", st.touring);
    $("locate-icon-pause").toggleAttribute("hidden", !st.touring);

    if (OPT.debug) {
      var r = st.raw;
      $("debug").hidden = false;
      $("debug").textContent = "geo " + st.geo + (OPT.gcj ? " (gcj02→wgs84)" : "") +
        (r ? "\nlat " + r.lat.toFixed(6) + "\nlon " + r.lon.toFixed(6) + "\nacc " + Math.round(r.acc) + " m" : "") +
        "\ninside " + (st.inside || "-") + "  zoom " + k.toFixed(2);
    }
  }

  // ------------------------------------------------------------ 到站
  // 落在哪个热区里。热区会重叠（花园里套着防空洞），取相对距离（距离 ÷ 半径）最小的那个
  function hitPlace(x, y) {
    var best = null, bestScore = Infinity;
    M.places.forEach(function (p) {
      var d = Math.hypot(p.x - x, p.y - y), cur = p.id === st.inside;
      if (d > p.r * (cur ? STAY_FACTOR : 1)) return;
      var score = d / p.r - (cur ? 0.2 : 0);
      if (score < bestScore) { bestScore = score; best = p; }
    });
    return best;
  }

  // slackPx 是这次定位的误差半径（画布像素）。误差大到超过 ACC_TRIGGER_M 时 canTrigger 为假：
  // 不触发新的到站，只在「即使算上误差也已经不在原来那个热区里」时把所在热区清掉
  function setPos(x, y, canTrigger, slackPx) {
    st.pos = [x, y];
    var id = st.inside;
    if (canTrigger) {
      var hit = hitPlace(x, y);
      id = hit ? hit.id : null;
    } else if (id) {
      var cur = placeById(id);
      if (Math.hypot(cur.x - x, cur.y - y) > cur.r * STAY_FACTOR + (slackPx || 0)) id = null;
    }
    if (id !== st.inside) {
      st.inside = id;
      if (id && canTrigger) notify(placeById(id));
      updateSpots();
    }
    updateMe();
  }

  function notify(p) {
    var d = new Date();
    st.msgs = st.msgs.filter(function (m) { return m.pid !== p.id; });
    st.msgs.unshift({ pid: p.id, time: pad2(d.getHours()) + ":" + pad2(d.getMinutes()), read: false });
    save();
    updateMsgs();
    if (st.sheetOpen && st.sheetPid === p.id) return;      // 正看着这一处的介绍，不必再提醒
    $("banner-title").textContent = p.name.zh;
    st.bannerPid = p.id;
    $("banner").classList.add("show");
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(hideBanner, BANNER_MS);
  }

  function hideBanner() {
    clearTimeout(bannerTimer);
    $("banner").classList.remove("show");
  }

  // ------------------------------------------------------------ 定位
  function startGeo() {
    if (OPT.sim) { st.geo = "sim"; st.pos = [M.entrance.x, M.entrance.y]; updateMe(); return; }
    if (OPT.fix) {
      onFix({ coords: { latitude: OPT.fix.lat, longitude: OPT.fix.lon, accuracy: OPT.fix.acc } });
      return;
    }
    if (!("geolocation" in navigator)) { st.geo = "unsupported"; updateMe(); return; }
    if (!window.isSecureContext) { st.geo = "insecure"; updateMe(); return; }
    st.geo = "waiting";
    updateMe();
    watchId = navigator.geolocation.watchPosition(onFix, onGeoError, GEO_OPTIONS);
  }

  function stopGeo() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
  }

  function onFix(position) {
    if (!M) return;
    var c = position.coords, lat = c.latitude, lon = c.longitude;
    if (OPT.gcj) { var w = gcjToWgs(lat, lon); lat = w[0]; lon = w[1]; }
    st.raw = { lat: lat, lon: lon, acc: c.accuracy };
    var xy = project(lat, lon);
    if (inArea(xy)) {
      var first = st.geo !== "live";
      st.geo = "live";
      st.acc = c.accuracy;
      setPos(xy[0], xy[1], c.accuracy <= ACC_TRIGGER_M, c.accuracy * M.canvas.px_per_m);
      if (st.follow || first) centerOn(xy[0], xy[1]);
    } else {
      st.geo = "outside";
      st.dist = haversine(lat, lon, M.entrance.lat, M.entrance.lon);
      st.pos = [M.entrance.x, M.entrance.y];
      if (st.inside) { st.inside = null; updateSpots(); }
      updateMe();
    }
  }

  function onGeoError(err) {
    if (!M) return;
    // 超时与暂时拿不到位置时 watch 还在，不用重开；圆点先灰着停在原地。
    // 所在热区不清：信号一闪就清掉的话，恢复后会把同一处再提醒一遍
    st.geo = err.code === err.PERMISSION_DENIED ? "denied"
      : err.code === err.TIMEOUT ? "timeout" : "unavailable";
    updateMe();
  }

  // ------------------------------------------------------------ 模拟游览（仅 ?sim=1）
  function tourPoints() {
    var r = route(), ent = [M.entrance.x, M.entrance.y];
    return r ? routePoints(r) : [ent].concat(M.places.map(function (p) { return [p.x, p.y]; }));
  }

  function startTour() {
    var pts = tourPoints();
    if (st.tourIdx == null || st.tourIdx >= pts.length - 1) { st.tourIdx = 0; setPos(pts[0][0], pts[0][1], true); }
    st.touring = true;
    st.follow = true;
    updateMe();
    var last = performance.now(), pauseUntil = 0;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function step(now) {
      var dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!st.sheetOpen && !st.msgsOpen && now >= pauseUntil) {
        var target = pts[st.tourIdx + 1];
        if (!target) { stopTour(); return; }
        var dx = target[0] - st.pos[0], dy = target[1] - st.pos[1], dist = Math.hypot(dx, dy);
        var mv = SIM_SPEED * dt;
        if (dist <= mv) {
          setPos(target[0], target[1], true);
          st.tourIdx++;
          pauseUntil = now + 1400;
        } else {
          setPos(st.pos[0] + dx / dist * mv, st.pos[1] + dy / dist * mv, true);
        }
        if (st.follow) centerOn(st.pos[0], st.pos[1]);
      }
      raf = requestAnimationFrame(step);
    });
  }

  function stopTour() {
    cancelAnimationFrame(raf);
    if (st && st.touring) { st.touring = false; updateMe(); }
  }

  // ------------------------------------------------------------ 介绍抽屉
  function stopHtml(s, place, r) {
    var solo = s.name.zh === place.name.zh;       // 这一站就是地点本身，标题已经写过了
    var ord = r ? r.stops.indexOf(s.seq) + 1 : 0;
    var meta = ['<span class="tag tag-outline">' + esc(s.tier) + " 级</span>",
      "<span>建议停留约 " + s.dwell + " 分钟</span>"];
    if (r) meta.push(ord ? '<span class="tag tag-neutral">本路线第 ' + ord + " 站</span>" : "<span>不在所选路线内</span>");
    var html = '<div class="stop' + (r && !ord ? " off-route" : "") + '">' +
      (solo ? "" : "<h4>" + esc(s.name.zh) + "</h4>") +
      '<div class="stop-meta">' + meta.join("") + "</div>";
    if (s.status.zh !== "在展") html += '<div class="note">现状：' + esc(s.status.zh) + "</div>";
    if (s.borrowed) html += '<div class="note">' + esc(s.borrowed.zh) + "</div>";
    if (s.review) html += '<div class="note">馆方资料此处待复核：' + esc(s.review) + "</div>";
    html += s.intro.map(function (p) { return "<p>" + esc(p) + "</p>"; }).join("");
    if (s.objects.length) {
      html += '<div class="objects"><h5>本展在展藏品</h5><ul>' + s.objects.map(function (o) {
        return "<li><span>" + esc(o.name.zh) + (o.review ? "（待复核：" + esc(o.review) + "）" : "") +
          '</span><span class="tag tag-outline">' + esc(o.tier) + " 级</span></li>";
      }).join("") + "</ul></div>";
    }
    return html + '<div class="source">介绍出处：' + esc(s.source.zh) + "</div></div>";
  }

  function renderSheet() {
    var p = placeById(st.sheetPid), r = route();
    var seq = sequenceFor(p.id), i = seq.ids.indexOf(p.id);
    var prev = i > 0 ? placeById(seq.ids[i - 1]) : null;
    var next = i < seq.ids.length - 1 ? placeById(seq.ids[i + 1]) : null;
    var kicker = seq.onRoute
      ? "路线第 " + (i + 1) + " / " + seq.ids.length + " 处 · " + M.card.short.zh
      : "热区 " + pad2(M.places.indexOf(p) + 1) + " · " + M.card.short.zh;

    var html = (p.photo ? '<div class="plate"><img loading="lazy" src="' + esc(p.photo) + '" alt="' + esc(p.name.zh) + '"></div>' : "") +
      '<div class="kicker">' + esc(kicker) + "</div><h2>" + esc(p.name.zh) + '</h2><div class="rule"></div>' +
      p.stops.map(function (s) { return stopHtml(M.stops[s], p, seq.onRoute ? r : null); }).join("");

    if (next) {
      var meters = haversine(p.lat, p.lon, next.lat, next.lon) * M.walk.detour;
      html += '<div class="next"><div class="next-name"><span class="kicker">前往下一处</span><strong>' + esc(next.name.zh) +
        "</strong></div><small>步行约 " + Math.max(10, Math.round(meters / 10) * 10) + " 米 · " +
        Math.max(1, Math.round(meters / M.walk.m_per_min)) + " 分钟</small></div>";
    }
    html += '<div class="sheet-actions">' +
      (prev ? '<button class="btn btn-secondary" type="button" data-goto="' + esc(prev.id) + '">' + ICON_PREV + "<span>上一处 · " + esc(prev.name.zh) + "</span></button>" : "") +
      (next ? '<button class="btn btn-primary" type="button" data-goto="' + esc(next.id) + '"><span>下一处 · ' + esc(next.name.zh) + "</span>" + ICON_NEXT + "</button>" : "") +
      (!prev && !next ? '<button class="btn btn-secondary" type="button" data-close>关闭</button>' : "") +
      "</div>";
    $("sheet-body").innerHTML = html;
    $("sheet").scrollTop = 0;
  }

  function openIntro(pid) {
    st.sheetPid = pid;
    st.sheetOpen = true;
    st.msgsOpen = false;
    hideBanner();
    st.msgs.forEach(function (m) { if (m.pid === pid) m.read = true; });
    save();
    renderSheet();
    updateMsgs();
    updateSheets();
  }

  function closeSheets() {
    st.sheetOpen = st.msgsOpen = false;
    updateSheets();
  }

  function updateSheets() {
    $("sheet").classList.toggle("show", st.sheetOpen);
    $("msgs").classList.toggle("show", st.msgsOpen);
    $("backdrop").classList.toggle("show", st.sheetOpen || st.msgsOpen);
  }

  // ------------------------------------------------------------ 进出地图页
  function openMuseum(key) {
    M = data[key];
    st = {
      routeId: M.default_route, k: 1, pan: [0, 0], pos: [M.entrance.x, M.entrance.y],
      geo: "waiting", acc: 0, dist: 0, raw: null, inside: null, msgs: [],
      sheetPid: null, sheetOpen: false, msgsOpen: false, bannerPid: null,
      follow: true, touring: false, tourIdx: null
    };
    restore();
    $("list").hidden = true;
    $("tour").hidden = false;
    buildMap();
    layout();
    updateRoute();
    updateMsgs();
    updateSheets();
    centerOn(M.entrance.x, M.entrance.y);
    startGeo();
  }

  function closeMuseum() {
    stopGeo();
    stopTour();
    hideBanner();
    M = st = null;
    $("tour").hidden = true;
    $("list").hidden = false;
  }

  function onHash() {
    var key = location.hash.replace(/^#/, "");
    if (data[key]) { if (!M || M.key !== key) { if (M) closeMuseum(); openMuseum(key); } }
    else if (M) closeMuseum();
  }

  // ------------------------------------------------------------ 事件
  function mapPoint(e) {
    var r = $("map").getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function pinchState() {
    var ids = Object.keys(gesture.pointers);
    var a = gesture.pointers[ids[0]], b = gesture.pointers[ids[1]];
    return { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, cx: (a[0] + b[0]) / 2, cy: (a[1] + b[1]) / 2 };
  }

  function bindMap() {
    var map = $("map");
    map.addEventListener("pointerdown", function (e) {
      if (!M) return;
      var pt = mapPoint(e);
      gesture.pointers[e.pointerId] = pt;
      var n = Object.keys(gesture.pointers).length;
      if (OPT.sim && e.target.closest && e.target.closest("#me .grip")) {
        gesture.drag = true;
        stopTour();
        map.setPointerCapture(e.pointerId);
        return;
      }
      if (n === 2) {
        var ps = pinchState();
        gesture.pinch = { d: ps.d, k: st.k };
        gesture.pan = null;
        st.follow = false;
      } else if (n === 1) {
        gesture.pan = { x: pt[0], y: pt[1], pan: st.pan.slice(), id: e.pointerId, moved: false };
      }
    });
    map.addEventListener("pointermove", function (e) {
      if (!M || !gesture.pointers[e.pointerId]) return;
      var pt = mapPoint(e);
      gesture.pointers[e.pointerId] = pt;
      if (gesture.drag) {
        setPos(clamp((pt[0] - st.pan[0]) / st.k, 12, M.canvas.w - 12),
               clamp((pt[1] - st.pan[1]) / st.k, 12, M.canvas.h - 12), true);
        return;
      }
      if (gesture.pinch) {
        var ps = pinchState();
        zoomAt(gesture.pinch.k * ps.d / gesture.pinch.d, ps.cx, ps.cy);
        return;
      }
      var pn = gesture.pan;
      if (!pn) return;
      var dx = pt[0] - pn.x, dy = pt[1] - pn.y;
      if (!pn.moved && Math.hypot(dx, dy) < 5) return;      // 小于 5 像素当作点按，让给标记的 click
      if (!pn.moved) { pn.moved = true; st.follow = false; stopTour(); map.setPointerCapture(pn.id); }
      st.pan = clampPan(pn.pan[0] + dx, pn.pan[1] + dy);
      applyPan();
    });
    var end = function (e) {
      delete gesture.pointers[e.pointerId];
      gesture.drag = false;
      gesture.pinch = null;
      gesture.pan = null;
    };
    map.addEventListener("pointerup", end);
    map.addEventListener("pointercancel", end);
    map.addEventListener("wheel", function (e) {
      if (!M) return;
      e.preventDefault();
      var pt = mapPoint(e);
      st.follow = false;
      zoomAt(st.k * Math.exp(-e.deltaY / 400), pt[0], pt[1]);
    }, { passive: false });
    window.addEventListener("resize", function () { if (M) layout(); });
  }

  function bindUi() {
    $("cards").addEventListener("click", function (e) {
      var b = e.target.closest("[data-open]");
      if (b) location.hash = b.getAttribute("data-open");
    });
    $("back").addEventListener("click", function () { location.hash = ""; });
    $("bell").addEventListener("click", function () {
      st.msgsOpen = true;
      st.sheetOpen = false;
      updateSheets();
    });
    $("chips").addEventListener("click", function (e) {
      var b = e.target.closest("[data-route]");
      if (!b) return;
      stopTour();
      st.tourIdx = null;
      st.routeId = b.getAttribute("data-route");
      save();
      updateRoute();
    });
    $("locate").addEventListener("click", function () {
      if (st.geo === "sim") { if (st.touring) stopTour(); else startTour(); return; }
      if (st.geo === "denied") { stopGeo(); startGeo(); return; }
      st.follow = true;
      centerOn(st.pos[0], st.pos[1]);
    });
    $("banner").addEventListener("click", function () { if (st.bannerPid) openIntro(st.bannerPid); });
    $("backdrop").addEventListener("click", closeSheets);
    $("sheet").addEventListener("click", function (e) {
      var go = e.target.closest("[data-goto]");
      if (go) { openIntro(go.getAttribute("data-goto")); return; }
      if (e.target.closest("[data-close]")) closeSheets();
    });
    $("msgs-body").addEventListener("click", function (e) {
      var b = e.target.closest("[data-msg]");
      if (b) openIntro(b.getAttribute("data-msg"));
    });
    window.addEventListener("hashchange", onHash);
  }

  // ------------------------------------------------------------ 启动
  function loadAll() {
    return Promise.all(MUSEUMS.map(function (key) {
      return fetch("data/" + key + ".json", { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error(key + ".json HTTP " + r.status);
        return r.json();
      }).then(function (j) { data[key] = j; });
    }));
  }

  bindUi();
  bindMap();
  loadAll().then(function () {
    renderCards();
    onHash();
  }).catch(function (e) {
    $("cards").innerHTML = '<p class="load-note">数据没有载入成功，请刷新重试。<br>' + esc(e.message) + "</p>";
  });
})();
