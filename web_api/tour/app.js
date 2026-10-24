/* Ari Travel 导览页。原生 JS，无框架、无外部依赖。
 *
 * 数据全部来自 data/<馆>.json（utils/import_data/tour_build.py 生成）。地点的画布坐标、
 * 热区半径、景区范围、经纬度换算参数都在那份文件里，这里不写死任何坐标。
 *
 * 介绍抽屉里的「游客互动」是唯一要服务端的部分：同域名 /api/tour/ 下的问答接口
 * （web_api/app/tour_qa.py）。接口不在时那一块不显示，其余照常。
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

  var HOST = window.AriHost || null;
  var MUSEUMS = []; // Server catalog controls membership and order on both Web and App.
  var ACC_TRIGGER_M = 30;   // 精度差于此的定位只移动圆点，不触发到站
  var STAY_FACTOR = 1.2;    // 已在某个热区里时，走出 1.2 倍半径才算离开，免得在边上反复进出
  var BANNER_MS = 6000;
  var ZOOM_MAX = 2.5;
  var FAR_ZOOM = 0.75;      // 缩到比这更小就收起地点名字，只留编号
  var SIM_SPEED = 70;       // 模拟游览的速度，画布像素/秒
  var GEO_OPTIONS = { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 };
  var QA_PAGE = 20;         // 游客互动每次取几条
  var QA_MAX = 100;         // 一个问题最多几个字，与服务端一致
  var QA_TIMEOUT_MS = 70000;

  var $ = function (id) { return document.getElementById(id); };
  var query = new URLSearchParams(location.search);
  var OPT = {
    sim: !HOST && query.get("sim") === "1",
    debug: query.get("debug") === "1",
    gcj: !HOST && query.get("crs") === "gcj02",
    fix: HOST ? null : parseFix(query.get("fix"))
  };

  var data = {};        // {馆 key: JSON}
  var M = null;         // 当前打开的馆
  var st = null;        // 当前馆的界面状态
  var spots = {};       // {地点 id: {btn, ring, num}}
  var labels = [];      // [{el, x, y}]
  var watchId = null, bannerTimer = null, raf = null;
  var gesture = { pointers: {}, pan: null, pinch: null, drag: false };
  var qa = {};          // {馆:地点 → 这一处的问答状态}，见「游客互动」一节
  var qaLive = null;    // 问答接口在不在：null 还不知道 / true 在 / false 不在（整块不显示）
  var visitor = null;   // 匿名设备号

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
    var a = gpsData(M).area;
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

  function isCollection(m) { return (m || M).mode === "collection"; }
  function hasBrowseMap() { return isCollection() && M.map_mode === "browse"; }
  function mapVisible() { return M && !$("mapwrap").hidden; }
  function mapPlaces() { return M.places.filter(function (p) { return Number.isFinite(p.x) && Number.isFinite(p.y); }); }
  function gpsData(m) { return isCollection(m) ? m.navigation : m; }
  function gpsActive() { return M && (!isCollection() || !!(M.navigation && st.themeId && mapVisible())); }
  function gpsPlace(id) { return gpsData(M).places.filter(function (p) { return p.id === id; })[0]; }
  function nativeTour(m) {
    if (!isCollection(m)) return m;
    return Object.assign({}, m, {area:m.navigation.area, entrance:m.navigation.entrance, places:m.navigation.places});
  }

  function collectionView(showMap, pid) {
    if (!hasBrowseMap()) return;
    stopGeo(); stopTour(); hideBanner();
    if (HOST) HOST.leave();
    $("collection").hidden = showMap;
    $("collection-themes").hidden = true;
    $("view-themes").classList.remove("on");
    $("view-themes").setAttribute("aria-pressed", "false");
    $("mapwrap").hidden = !showMap;
    $("tour").scrollTop = 0;
    window.scrollTo(0, 0);
    var guided = gpsActive();
    $("me").hidden = !guided;
    $("bell").hidden = !guided;
    document.querySelector('.bottombar').hidden = !guided;
    ["list", "map"].forEach(function (name) {
      var active = showMap === (name === "map"), button = $("view-" + name);
      button.classList.toggle("on", active); button.setAttribute("aria-pressed", String(active));
    });
    if (showMap) {
      buildMap();
      st.k = minZoom();
      if (pid) st.k = Math.max(1, st.k);
      layout(); updateRoute();
      var place = pid && placeById(pid);
      var selected = themeSelection();
      if (selected && !place) {
        var xs = selected.variant.path.map(function (q) { return q[0]; }), ys = selected.variant.path.map(function (q) { return q[1]; });
        var left = Math.min.apply(null, xs), right = Math.max.apply(null, xs), top = Math.min.apply(null, ys), bottom = Math.max.apply(null, ys), view = viewSize();
        st.k = clamp(Math.min((view[0] - 60) / (right - left + 40), (view[1] - topInset() - 60) / (bottom - top + 40)), minZoom(), 1.4);
        layout(); centerOn((left + right) / 2, (top + bottom) / 2);
      } else centerOn(place ? place.x : M.canvas.w / 2, place ? place.y : M.canvas.h / 2);
      if (guided) { updateMsgs(); startGeo(); }
    } else {
      $("tour-sub").textContent = "景点与特色商铺 · " + M.places.length + "条";
    }
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
    if (r.path && r.path.length) return r.path;
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
    if (isCollection()) return { ids: collectionPlaces().map(function (p) { return p.id; }), onRoute: false };
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
        "<span>" + ICON_PIN + m.places.length + (isCollection(m) ? " 条资料" : " 处热区") + "</span>" +
        '</div><span class="card-go">' + (isCollection(m) ? '景点与商铺' : '导游地图') + ICON_NEXT + "</span></div>" +
        "</div></button>";
    }).join("");
    $("cards").innerHTML = html || '<p class="load-note">暂无可用景区，请稍后刷新。</p>';
  }

  // 已有介绍但尚无定位依据的目的地也可阅读；筛选只影响浏览顺序，不构造步行路线。
  function collectionPlaces() {
    var word = $("collection-search").value.trim().toLowerCase();
    var kind = $("collection-kind").value, area = $("collection-area").value, tier = $("collection-tier").value;
    var category = $("collection-shop-category").value, tag = $("collection-shop-tag").value;
    return M.places.filter(function (p) {
      var s = M.stops[p.stops[0]];
      var text = [s.name.zh, s.name.en, (s.aliases || []).join(" "), s.intro.join(" "),
        s.address.zh, s.specialty.zh, s.area.zh, s.related ? s.related.zh : "", s.review || "",
        s.platform.zh, s.borrowed ? s.borrowed.zh : "", s.shop_kind ? s.shop_kind.zh : "",
        s.shop_category || "", (s.shop_tags || []).join(" ")].join(" ").toLowerCase();
      return (kind === "all" || s.kind === kind) && (area === "all" || s.area.zh === area) &&
        (tier === "all" || s.tier === tier) && (category === "all" || s.shop_category === category) &&
        (tag === "all" || (s.shop_tags || []).indexOf(tag) >= 0) && (!word || text.indexOf(word) >= 0);
    });
  }

  function renderCollection() {
    var places = collectionPlaces();
    $("collection-count").textContent = "显示 " + places.length + " / " + M.places.length + " 条";
    $("collection-items").innerHTML = places.map(function (p) {
      var s = M.stops[p.stops[0]], intro = s.intro.join(" ");
      return '<button class="card collection-item" type="button" data-place="' + esc(p.id) + '">' +
        (p.photo ? '<img class="collection-thumb" loading="lazy" src="' + esc(p.photo) + '" alt="' + esc(p.photo_info.caption.zh) + '">' : '') +
        '<div class="stop-meta"><span class="tag tag-outline">' + esc(s.tier) + ' 级</span><span>' +
        esc(s.area.zh + " · " + (s.kind === "shop" ? "特色商铺" : "文化参观点")) + '</span></div>' +
        '<strong>' + esc(s.seq + ". " + s.name.zh) + '</strong><span class="collection-alias">' + esc(s.name.en) + '</span>' +
        shopTags(s) +
        '<p>' + esc(intro.length > 90 ? intro.slice(0, 90) + "…" : intro) + '</p></button>';
    }).join("") || '<p class="load-note">没有符合条件的条目，请调整搜索或筛选。</p>';
  }

  function buildCollection() {
    $("tour-name").textContent = M.card.short.zh;
    $("tour-sub").textContent = "景点与特色商铺 · " + M.places.length + "条";
    $("collection-desc").textContent = M.card.desc.zh;
    $("collection-note").textContent = M.planning.zh;
    $("collection-themes").hidden = true;
    $("view-themes").hidden = !(M.itineraries && M.itineraries.length);
    ["collection-search", "collection-kind", "collection-tier"].forEach(function (id) {
      $(id).value = id === "collection-search" ? "" : "all";
    });
    var areas = [];
    M.places.forEach(function (p) { var area = M.stops[p.stops[0]].area.zh; if (areas.indexOf(area) < 0) areas.push(area); });
    $("collection-area").innerHTML = '<option value="all">全部区域</option>' + areas.map(function (a) {
      return '<option value="' + esc(a) + '">' + esc(a) + '</option>';
    }).join("");
    ["category", "tag"].forEach(function (name) {
      var values = [];
      Object.keys(M.stops).forEach(function (key) {
        var s = M.stops[key], entries = name === "category" ? (s.shop_category ? [s.shop_category] : []) : (s.shop_tags || []);
        entries.forEach(function (value) { if (values.indexOf(value) < 0) values.push(value); });
      });
      $("collection-shop-" + name).innerHTML = '<option value="all">全部' + (name === "category" ? "商铺分类" : "特色标签") + '</option>' + values.map(function (value) {
        return '<option value="' + esc(value) + '">' + esc(value) + '</option>';
      }).join("");
    });
    $("shop-filters").hidden = !M.shop_label_policy;
    $("collection").scrollTop = 0;
    renderCollection();
  }

  function shopTags(s) {
    if (!s.shop_category) return "";
    return '<div class="shop-tags"><span class="tag tag-outline">' + esc(s.shop_category) + '</span>' + (s.shop_tags || []).map(function (tag) {
      return '<span class="tag tag-neutral">' + esc(tag) + '</span>';
    }).join("") + '</div>';
  }

  function themeSelection() {
    if (!M.itineraries || !st.themeId) return null;
    var theme = M.itineraries.filter(function (t) { return t.id === st.themeId; })[0];
    if (!theme) return null;
    var start = st.themeStarts[theme.id] || theme.default_start;
    return { theme: theme, variant: theme.variants.filter(function (v) { return v.start_station === start; })[0] };
  }

  function renderThemes() {
    function station(id) { return M.itinerary_stations.filter(function (s) { return s.id === id; })[0]; }
    $("collection-themes").innerHTML = '<h2>选一种方式，慢慢逛</h2><p class="note">用时未计用餐和排队；地图参考点并非检票入口。</p><details class="theme-policy"><summary>路线依据与使用说明</summary><p>' + esc(M.itinerary_policy) + '</p></details>' +
      '<nav class="theme-shortcuts" aria-label="选择主题">' + M.itineraries.map(function (t) { return '<button class="chip" type="button" data-theme-jump="' + esc(t.id) + '">' + esc(t.name) + '</button>'; }).join('') + '</nav>' + M.itineraries.map(function (theme) {
      var start = st.themeStarts[theme.id] || theme.default_start;
      var v = theme.variants.filter(function (r) { return r.start_station === start; })[0];
      return '<article class="theme-card" data-theme="' + esc(theme.id) + '"><h3>' + esc(theme.name) + '</h3><p>' + esc(theme.description) + '</p>' +
        '<label>地铁起点<select data-theme-start="' + esc(theme.id) + '">' + M.itinerary_stations.map(function (s) {
          return '<option value="' + esc(s.id) + '"' + (s.id === start ? ' selected' : '') + '>' + esc(s.name + ' · ' + s.lines.join('/') + '号线') + '</option>';
        }).join("") + '</select></label><p class="theme-summary">步行约 ' + (v.meters / 1000).toFixed(1) + ' 公里 · 约 ' + Math.floor(v.total_minutes / 60) + '小时' + (v.total_minutes % 60) + '分（停留 ' + v.stay_minutes + ' + 步行 ' + v.walk_minutes + ' 分钟，均为估计）</p>' +
        '<p>终点：' + esc(station(v.end_station).name) + (v.start_station === v.end_station ? '（同站往返）' : '') + '</p>' +
        '<button class="btn btn-primary" type="button" data-theme-map="' + esc(theme.id) + '">' + (M.navigation ? '开始GPS导览' : '在互动地图查看线路') + '</button>' +
        (v.map_assets ? '<figure class="theme-map-preview"><a href="' + esc(v.map_assets.svg) + '" target="_blank" rel="noopener"><img src="' + esc(v.map_assets.svg) + '" width="1200" height="1600" loading="lazy" alt="' + esc(theme.name + '线路图，' + station(start).name + '出发；数字表示游览顺序') + '"></a><figcaption>点击线路图可放大查看 · S起点 / E终点 · 数字为游览顺序</figcaption></figure><div class="theme-map-actions"><a href="' + esc(v.map_assets.svg) + '" target="_blank" rel="noopener">打开完整线路图</a><a href="' + esc(v.map_assets.png) + '" download>保存PNG图片</a></div>' : '') +
        '<ol>' + theme.steps.map(function (step) {
          return '<li><button class="theme-stop" type="button" data-place="' + esc(M.stops[step.seq].place) + '">' + esc(step.name.zh) + '</button> · 约' + step.minutes + '分钟<p>' + esc(step.note) + '</p>' +
            (step.related.length ? '<p>沿途可选：' + step.related.map(function (seq) { return '<button class="theme-stop" type="button" data-place="' + esc(M.stops[seq].place) + '">' + esc(M.stops[seq].name.zh) + '</button>'; }).join('、') + '</p>' : '') + '</li>';
        }).join("") + '</ol><p><strong>费用：</strong>' + esc(theme.fee) + '</p><p class="note">' + esc(theme.access) + '</p>' +
        '<p>餐饮或小店可选（用餐、购物时间另加）：' + theme.optional_shops.map(function (seq) { return '<button class="theme-stop" type="button" data-place="' + esc(M.stops[seq].place) + '">' + esc(M.stops[seq].name.zh) + '</button>'; }).join('、') + '</p>' + sourceLinks(theme.sources) + sourceLinks([station(start).source, station(start).position_source, station(v.end_station).source, station(v.end_station).position_source]) + '</article>';
    }).join("");
  }

  function showThemes() {
    if (!isCollection() || !M.itineraries) return;
    collectionView(false);
    $("collection").hidden = true; $("collection-themes").hidden = false;
    $("view-list").classList.remove("on"); $("view-list").setAttribute("aria-pressed", "false");
    $("view-themes").classList.add("on"); $("view-themes").setAttribute("aria-pressed", "true");
    $("tour-sub").textContent = "四条主题线路 · 地铁起步";
    renderThemes();
  }

  // ------------------------------------------------------------ 地图：搭建
  function buildMap() {
    var c = M.canvas, map = M.map;
    $("base").classList.toggle("themed", !!themeSelection());
    $("base").setAttribute("viewBox", "0 0 " + c.w + " " + c.h);
    ["roads", "woods", "walls", "water", "track", "blocks", "paths"].forEach(function (k) {
      $("ly-" + k).setAttribute("d", map[k] || "");
    });

    var overlay = $("overlay");
    overlay.innerHTML = "";
    spots = {};
    labels = [];

    M.labels.forEach(function (l) { addLabel(l.kind, l.t.zh, l.x, l.y); });
    var themed = themeSelection();
    if (themed) {
      var path = themed.variant.path;
      var loop = themed.variant.start_station === themed.variant.end_station;
      addLabel("route", loop ? "S/E" : "S", path[0][0], path[0][1]);
      if (!loop) addLabel("route", "E", path[path.length - 1][0], path[path.length - 1][1]);
    }
    if (!isCollection()) addLabel("gate", M.entrance.name.zh, M.entrance.x, M.entrance.y + 16);

    mapPlaces().forEach(function (p) {
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
    $("tour-sub").textContent = (hasBrowseMap() ? "景点地图 · " : "导游地图 · ") + M.card.short.en;
    $("msgs-park").textContent = M.name.zh;
    $("credit").textContent = M.attribution.zh;
    var north = M.canvas.north * Math.PI / 180;
    $("compass-arrow").style.transform = "rotate(" + M.canvas.north + "deg)";
    $("compass-n").style.transform = "translate(" + Math.sin(north) * 22 + "px," + -Math.cos(north) * 22 + "px)";
    $("me").classList.toggle("drag", OPT.sim);

    var chips = M.routes.map(function (r) {
      return '<button class="chip" type="button" data-route="' + esc(r.id) + '">' + esc(r.label.zh) + "</button>";
    });
    if (M.itineraries) {
      chips.push('<button class="chip" type="button" data-map-theme="">全部景点</button>');
      M.itineraries.forEach(function (t) { chips.push('<button class="chip" type="button" data-map-theme="' + esc(t.id) + '">' + esc(t.name) + '</button>'); });
    }
    if (!hasBrowseMap()) chips.push('<button class="chip" type="button" data-route="none">不显示路线</button>');
    $("chips").innerHTML = chips.join("");
    $("chips").hidden = !chips.length;
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
    return clamp(Math.min(v[0] / M.canvas.w, (v[1] - topInset()) / M.canvas.h), hasBrowseMap() ? .1 : .3, 1);
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
    var themed = themeSelection();
    mapPlaces().forEach(function (p) {
      var s = spots[p.id];
      var step = themed && themed.theme.steps.filter(function (v) { return M.stops[v.seq].place === p.id; })[0];
      var point = step ? project(step.point[0], step.point[1]) : [p.x, p.y];
      s.btn.style.left = px(point[0]);
      s.btn.style.top = px(point[1]);
      s.btn.hidden = themed ? !step : k < (p.min_zoom || 0);
      var geo = themed && M.navigation ? gpsPlace(p.id) : null, radius = geo ? geo.r : p.r;
      s.ring.hidden = !Number.isFinite(radius) || !!(themed && !step);
      s.ring.style.left = px(point[0] - (radius || 0));
      s.ring.style.top = px(point[1] - (radius || 0));
      s.ring.style.width = s.ring.style.height = px((radius || 0) * 2);
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
    var themed = themeSelection();
    Array.prototype.forEach.call($("chips").children, function (b) {
      b.classList.toggle("on", b.hasAttribute("data-map-theme") ? b.getAttribute("data-map-theme") === (st.themeId || "") : b.getAttribute("data-route") === (r ? r.id : "none"));
    });
    $("route-summary").textContent = r
      ? r.stops.length + " 站 · 约 " + r.total + " 分钟（停留 " + r.stay + " + 步行 " + r.walk + "）· 入口出发并返回" + (r.fee ? " · " + r.fee.zh : "")
      : (hasBrowseMap() ? mapPlaces().length + " 处参考位置 · 数字对应清单序号，点选查看；放大显示街巷。无路线及到站提醒" : "显示全部热区，未选择路线");
    $("route-details").hidden = !(r && r.note);
    if (r && r.note) {
      $("route-detail-body").innerHTML = '<p>' + esc(r.note.zh) + '</p><ol>' + r.stops.map(function (seq) {
        var s = M.stops[seq];
        return '<li>' + esc(s.name.zh) + ' · 约 ' + s.dwell + ' 分钟</li>';
      }).join('') + '</ol><p>' + esc(M.opening.zh) + '</p>' +
        (M.planning ? '<p>' + esc(M.planning.zh) + '</p>' : '') + sourceLinks(r.sources);
    }
    $("ly-route").setAttribute("d", r
      ? "M" + routePoints(r).map(function (q) { return q[0] + " " + q[1]; }).join(" L")
      : "");
    if (themed) {
      var t = themed.theme, v = themed.variant;
      $("route-summary").textContent = t.name + " · 约" + (v.meters / 1000).toFixed(1) + "公里 · 估计" + v.total_minutes + "分钟（停留" + v.stay_minutes + "+步行" + v.walk_minutes + "）· 数字为游览顺序 · " + (M.navigation ? "GPS导览 · 到附近提醒" : "无到站提醒");
      $("ly-route").setAttribute("d", "M" + v.path.map(function (q) { return q[0] + " " + q[1]; }).join(" L"));
      $("route-details").hidden = false;
      var stations = M.itinerary_stations.filter(function (s) { return s.id === v.start_station || s.id === v.end_station; });
      function stationName(id) { return stations.filter(function (s) { return s.id === id; })[0].name; }
      $("route-detail-body").innerHTML = '<p>S起点：' + esc(stationName(v.start_station)) + '；E终点：' + esc(stationName(v.end_station)) + '</p><ol>' + t.steps.map(function (s) { return '<li>' + esc(s.name.zh) + '</li>'; }).join('') + '</ol>' +
        (v.map_assets ? '<p><a href="' + esc(v.map_assets.svg) + '" target="_blank" rel="noopener">打开完整线路图</a> · <a href="' + esc(v.map_assets.png) + '" download>保存PNG图片</a></p>' : '') +
        '<p>' + esc(t.fee) + '</p><p>' + esc(t.access) + '</p><p>' + esc(M.itinerary_policy) + '</p>' +
        (M.navigation ? '<p>' + esc(M.navigation.policy) + '</p>' : '') + sourceLinks(t.sources);
    }
    updateSpots();
  }

  function updateSpots() {
    var r = route();
    var themed = themeSelection();
    var seen = {};
    st.msgs.forEach(function (m) { seen[m.pid] = true; });
    mapPlaces().forEach(function (p, i) {
      var s = spots[p.id], ords = r ? placeOrdinals(r, p.id) : [];
      if (themed) themed.theme.steps.forEach(function (step, order) { if (M.stops[step.seq].place === p.id) ords.push(order + 1); });
      var num = isCollection() ? String(p.stops[0]) : pad2(i + 1);
      if (r || themed) num = ords.length > 2 ? ords[0] + "–" + ords[ords.length - 1] : (ords.join("·") || "·");
      s.num.textContent = num;
      s.btn.classList.toggle("on-route", ords.length > 0);
      s.btn.classList.toggle("dim", !!r && !ords.length);
      s.btn.classList.toggle("visited", !!seen[p.id]);
      s.btn.classList.toggle("inside", st.inside === p.id);
      s.ring.classList.toggle("inside", st.inside === p.id);
    });
  }

  function updateMsgs() {
    if (isCollection() && !gpsActive()) return;
    var unread = st.msgs.filter(function (m) { return !m.read; }).length;
    $("unread").hidden = !unread;
    $("unread").textContent = unread;
    $("visited").textContent = (isCollection() ? "已到附近 " : "已游览 ") + st.msgs.length + " / " + gpsData(M).places.length;
    $("msgs-body").innerHTML = st.msgs.length ? st.msgs.map(function (m) {
      return '<button class="msg' + (m.read ? "" : " unread") + '" type="button" data-msg="' + esc(m.pid) + '">' +
        '<span class="msg-dot"></span><span class="msg-text"><strong>' + (isCollection() ? '已到附近：' : '已进入热区：') + esc(placeById(m.pid).name.zh) +
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
    me.hidden = !gpsActive();
    if (!gpsActive()) return;
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
        text = inside ? (isCollection() ? "已到「" + inside.name.zh + "」附近" : "位于「" + inside.name.zh + "」热区")
          : (st.geo === "live" && st.acc > ACC_TRIGGER_M ? "定位精度较低 · ±" + Math.round(st.acc) + " 米" : "未进入热区");
        break;
      case "waiting": text = "正在定位…"; break;
      case "outside": text = (isCollection() ? "导览覆盖范围外 · 距" + gpsData(M).entrance.name.zh + " " : "不在景区范围内 · 距入口 ") + fmtDist(st.dist); break;
      case "denied": text = "未获得定位授权"; break;
      case "unavailable": text = "暂时无法定位"; break;
      case "timeout": text = "定位超时，仍在尝试…"; break;
      case "approximate": text = "网络位置仅供参考 · 等待卫星定位"; break;
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
    gpsData(M).places.forEach(function (p) {
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
      var cur = gpsPlace(id);
      if (Math.hypot(cur.x - x, cur.y - y) > cur.r * STAY_FACTOR + (slackPx || 0)) id = null;
    }
    if (id !== st.inside) {
      st.inside = id;
      if (id && canTrigger) notify(placeById(id));
      updateSpots();
    }
    updateMe();
  }

  function notify(p, at) {
    var d = at ? new Date(at) : new Date();
    st.msgs = st.msgs.filter(function (m) { return m.pid !== p.id; });
    st.msgs.unshift({ pid: p.id, time: pad2(d.getHours()) + ":" + pad2(d.getMinutes()), at: d.getTime(), read: false });
    save();
    updateMsgs();
    if (st.sheetOpen && st.sheetPid === p.id) return;      // 正看着这一处的介绍，不必再提醒
    $("banner-title").textContent = p.name.zh + (isCollection() ? "附近" : "");
    $("banner").querySelector('.banner-top > span').textContent = isCollection() ? "Ari Travel · 已到附近" : "Ari Travel · 已进入热区";
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
    if (!gpsActive()) return;
    if (HOST) {
      st.geo = "waiting";
      updateMe();
      HOST.ready(M.key);
      return;
    }
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
    if (!gpsActive()) return;
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
      var entrance = gpsData(M).entrance;
      st.dist = haversine(lat, lon, entrance.lat, entrance.lon);
      st.pos = [entrance.x, entrance.y];
      if (st.inside) { st.inside = null; updateSpots(); }
      updateMe();
    }
  }

  function onGeoError(err) {
    if (!gpsActive()) return;
    // 超时与暂时拿不到位置时 watch 还在，不用重开；圆点先灰着停在原地。
    // 所在热区不清：信号一闪就清掉的话，恢复后会把同一处再提醒一遍
    st.geo = err.code === err.PERMISSION_DENIED ? "denied"
      : err.code === err.TIMEOUT ? "timeout" : "unavailable";
    updateMe();
  }

  // ------------------------------------------------------------ 模拟游览（仅 ?sim=1）
  function tourPoints() {
    var themed = themeSelection();
    if (themed) return themed.variant.path;
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
  function photoHtml(path, info, name) {
    if (!path) return '';
    var caption = info && info.caption ? info.caption.zh : name;
    var plate = '<div class="plate"' + (info && Number.isFinite(info.width) ? ' style="max-width:' + info.width + 'px"' : '') + '><img loading="lazy" src="' + esc(path) + '" alt="' + esc(caption) + '"></div>';
    if (!info) return plate;
    var source = info.source, credit = source && source.title ? '图片出处：' + esc(source.title) : '';
    try {
      if (new URL(source.url).protocol === 'https:') {
        credit = '<a href="' + esc(source.url) + '" target="_blank" rel="noopener noreferrer">图片出处：' + esc(source.title) + '</a>';
      }
    } catch (e) { /* No clickable credit for an invalid source URL. */ }
    return '<figure class="tour-photo">' + plate + '<figcaption>' + esc(caption) +
      ' · 资料图' + (credit ? '<br>' + credit : '') + '</figcaption></figure>';
  }

  function stopHtml(s, place, r) {
    var solo = s.name.zh === place.name.zh;       // 这一站就是地点本身，标题已经写过了
    var ord = r ? r.stops.indexOf(s.seq) + 1 : 0;
    var meta = ['<span class="tag tag-outline">' + esc(s.tier) + " 级</span>"];
    if (isCollection() && Number.isFinite(s.core)) meta.push('<span>Core ' + s.core.toFixed(4) + '</span>');
    if (s.included_in) meta.push('<span>随「' + esc(M.stops[s.included_in].name.zh) + '」参观，时间已计入整体</span>');
    else if (Number.isFinite(s.dwell)) meta.push("<span>建议停留约 " + s.dwell + " 分钟</span>");
    if (r) meta.push(ord ? '<span class="tag tag-neutral">本路线第 ' + ord + " 站</span>" : "<span>不在所选路线内</span>");
    var html = '<div class="stop' + (r && !ord ? " off-route" : "") + '">' +
      (solo ? "" : "<h4>" + esc(s.name.zh) + "</h4>") +
      '<div class="stop-meta">' + meta.join("") + "</div>";
    // 地点封面已展示的同一张图不重复；组成部分只展示它自己收录的照片。
    if (s.photo && s.photo !== place.photo) html += photoHtml(s.photo, s.photo_info, s.name.zh);
    (s.supplementary_photos || []).forEach(function (p) { html += photoHtml(p.path, p.info, s.name.zh); });
    if (s.status.zh !== "在展") html += '<div class="note">现状：' + esc(s.status.zh) + "</div>";
    if (s.borrowed) html += '<div class="note">' + esc(s.borrowed.zh) + "</div>";
    if (s.review) html += '<div class="note">' + (isCollection() ? '资料此处待复核：' : '馆方资料此处待复核：') + esc(s.review) + "</div>";
    if (s.related) html += '<div class="note">关联整体：' + esc(s.related.zh) + '</div>';
    if (s.shop_category) html += shopTags(s) + '<p class="note">标签依据：' + esc(s.shop_label_note) + '</p>' + '<p class="note">' + esc(M.shop_label_policy) + '</p>';
    if (s.specialty && s.specialty.zh) html += '<p><strong>特色：</strong>' + esc(s.specialty.zh) + '</p>';
    if (s.address && s.address.zh) html += '<p><strong>地址（来源记载）：</strong>' + esc(s.address.zh) + '</p>';
    if (s.platform && s.platform.zh) html += '<p><strong>平台参考：</strong>' + esc(s.platform.zh) + '</p>';
    html += s.intro.map(function (p) { return "<p>" + esc(p) + "</p>"; }).join("");
    if (s.objects.length) {
      html += '<div class="objects"><h5>本展在展藏品</h5><ul>' + s.objects.map(function (o) {
        return "<li><span>" + esc(o.name.zh) + (o.review ? "（待复核：" + esc(o.review) + "）" : "") +
          '</span><span class="tag tag-outline">' + esc(o.tier) + " 级</span></li>";
      }).join("") + "</ul></div>";
    }
    return html + '<div class="source">介绍出处：' + esc(s.source.zh) + "</div>" + sourceLinks(s.sources) + "</div>";
  }

  function sourceLinks(sources) {
    if (!sources) return '';
    return '<div class="source">' + sources.filter(function (s) {
      try { return new URL(s.url).protocol === 'https:'; } catch (e) { return false; }
    }).map(function (s) {
      return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(s.title) + '</a>';
    }).join(' · ') + '</div>';
  }

  function renderSheet() {
    var p = placeById(st.sheetPid), r = route();
    var seq = sequenceFor(p.id), i = seq.ids.indexOf(p.id);
    var prev = i > 0 ? placeById(seq.ids[i - 1]) : null;
    var next = i < seq.ids.length - 1 ? placeById(seq.ids[i + 1]) : null;
    var kicker = seq.onRoute
      ? "路线第 " + (i + 1) + " / " + seq.ids.length + " 处 · " + M.card.short.zh
      : (isCollection() ? "清单第 " + M.stops[p.stops[0]].seq + " 条" : "热区 " + pad2(M.places.indexOf(p) + 1)) + " · " + M.card.short.zh;

    var html = photoHtml(p.photo, p.photo_info, p.name.zh) +
      (isCollection() && p.position ? '<p class="note">地图：' + esc(p.position.note) + '</p>' +
        sourceLinks([p.position.source]) + '<button class="btn" type="button" data-show-map="' + esc(p.id) + '">在地图查看</button>' : '') +
      '<div class="kicker">' + esc(kicker) + "</div><h2>" + esc(p.name.zh) + '</h2><div class="rule"></div>' +
      p.stops.map(function (s) { return stopHtml(M.stops[s], p, seq.onRoute ? r : null); }).join("") +
      (qaLive === false ? "" : QA_HTML);

    if (next && !isCollection()) {
      var meters = haversine(p.lat, p.lon, next.lat, next.lon) * M.walk.detour;
      var leg = r && seq.onRoute && r.legs ? r.legs.filter(function (l) {
        return l.start === p.id && l.end === next.id;
      })[0] : null;
      var walking;
      if (leg) {
        walking = "步行约 " + Math.max(10, Math.round(leg.meters / 10) * 10) + " 米 · " +
          Math.max(1, Math.round(leg.minutes)) + " 分钟";
      } else if (M.walk.method === "osm-walking-graph") {
        walking = "两地直线约 " + Math.max(10, Math.round(meters / 10) * 10) + " 米，步行请按现场道路通行";
      } else {
        walking = "步行约 " + Math.max(10, Math.round(meters / 10) * 10) + " 米 · " +
          Math.max(1, Math.round(meters / M.walk.m_per_min)) + " 分钟";
      }
      html += '<div class="next"><div class="next-name"><span class="kicker">前往下一处</span><strong>' + esc(next.name.zh) +
        "</strong></div><small>" + esc(walking) + "</small></div>";
    }
    html += '<div class="sheet-actions">' +
      (prev ? '<button class="btn btn-secondary" type="button" data-goto="' + esc(prev.id) + '">' + ICON_PREV + "<span>上一处 · " + esc(prev.name.zh) + "</span></button>" : "") +
      (next ? '<button class="btn btn-primary" type="button" data-goto="' + esc(next.id) + '"><span>下一处 · ' + esc(next.name.zh) + "</span>" + ICON_NEXT + "</button>" : "") +
      (!prev && !next ? '<button class="btn btn-secondary" type="button" data-close>关闭</button>' : "") +
      "</div>";
    $("sheet-body").innerHTML = html;
    $("sheet").scrollTop = 0;
    qaMount(p.id);
  }

  // ------------------------------------------------------------ 游客互动
  // 介绍下面的一块：游客提问，导览助手（AI）结合这一页的资料回答，问答对所有游客公开。
  // 接口在同一个域名的 /api/tour/ 下（web_api/app/tour_qa.py）。没有登录，「我」是存在浏览器里的匿名设备号。
  // 抽屉每次翻页都整块重画，所以问答的状态按地点存在 qa 里，这里只重画列表，不碰输入框。
  var QA_HTML = '<section class="qa" id="qa">' +
    '<div class="kicker">向导览助手提问</div><h4>游客互动</h4>' +
    '<p class="qa-lede">提问与回答对所有游客公开，请勿填写个人信息。回答由 AI 生成，可能有误。</p>' +
    '<form class="qa-form" id="qa-form" autocomplete="off">' +
    '<input id="qa-input" type="text" maxlength="' + QA_MAX + '" enterkeyhint="send" placeholder="例如：这里当年是做什么用的？" aria-label="向导览助手提问">' +
    '<button class="btn btn-primary" id="qa-send" type="submit">提问</button></form>' +
    '<div class="qa-notice" id="qa-notice" role="status"></div>' +
    '<div class="qa-list" id="qa-list"></div></section>';

  function visitorId() {
    if (HOST) return HOST.visitorId();
    if (visitor) return visitor;
    try { visitor = localStorage.getItem("ari-tour:visitor"); } catch (e) { /* 读不了就现生成一个，只在这次打开期间有效 */ }
    if (!visitor || !/^[A-Za-z0-9-]{16,64}$/.test(visitor)) {
      if (window.crypto && crypto.randomUUID) visitor = crypto.randomUUID();
      else {
        visitor = "";
        while (visitor.length < 32) visitor += Math.floor(Math.random() * 16).toString(16);
      }
      try { localStorage.setItem("ari-tour:visitor", visitor); } catch (e) { /* 同上 */ }
    }
    return visitor;
  }

  function qaState(key, pid) {
    var k = key + ":" + pid;
    return qa[k] || (qa[k] = { topics: [], more: false, state: "new", loading: false, asking: false, draft: "", notice: "" });
  }

  function qaUrl(key, pid) {
    return "/api/tour/" + encodeURIComponent(key) + "/places/" + encodeURIComponent(pid) + "/topics";
  }

  function qaViewing(key, pid) {
    return !!M && M.key === key && st.sheetOpen && st.sheetPid === pid && !!$("qa");
  }

  // 发请求并把响应读成 {ok, status, body}。出错的响应体不一定是 JSON（比如网关报的 502），读不出来就当空对象
  function qaFetch(url, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    opts.headers["X-Visitor"] = visitorId();
    var ctl = window.AbortController ? new AbortController() : null, timer = null;
    if (ctl) {
      opts.signal = ctl.signal;
      timer = setTimeout(function () { ctl.abort(); }, QA_TIMEOUT_MS);
    }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        clearTimeout(timer);
        return { ok: r.ok, status: r.status, body: body || {} };
      });
    }, function (err) {
      clearTimeout(timer);
      throw err;
    });
  }

  function qaTime(iso) {
    var t = new Date(iso), mins = Math.floor((Date.now() - t.getTime()) / 60000);
    if (isNaN(mins)) return "";
    if (mins < 1) return "刚刚";
    if (mins < 60) return mins + " 分钟前";
    if (mins < 1440) return Math.floor(mins / 60) + " 小时前";
    return (t.getMonth() + 1) + " 月 " + t.getDate() + " 日";
  }

  function qaItemHtml(t) {
    var html = '<div class="qa-item' + (t.mine ? " mine" : "") + '">' +
      '<div class="qa-q"><div class="qa-meta"><span class="qa-role">' + (t.mine ? "我的提问" : "游客提问") + "</span><span>" +
      esc(qaTime(t.created_at)) + "</span></div><p>" + esc(t.question) + "</p></div>";
    if (t.status === "pending") {
      html += '<div class="qa-a"><div class="qa-meta"><span class="qa-role">导览助手</span></div><p class="qa-thinking">思考中…</p></div>';
    } else if (t.status === "answered") {
      html += '<div class="qa-a"><div class="qa-meta"><span class="qa-role">导览助手</span><span>AI 生成</span></div><p>' + esc(t.answer || "") + "</p></div>";
      if (t.mine && !t.public) html += '<div class="qa-private">这条提问没有公开，只有你自己看得到。</div>';
    } else {
      html += '<div class="qa-private">这条提问没有得到回答。</div>';
    }
    return html + "</div>";
  }

  function qaRender(key, pid) {
    if (!qaViewing(key, pid)) return;
    var q = qaState(key, pid);
    // 第一次拿到列表之前不显示：接口没部署时，这一块不该先闪出来再消失
    $("qa").hidden = qaLive === false || (qaLive === null && q.state !== "error");
    if (qaLive === false) return;
    $("qa-send").disabled = q.asking;
    $("qa-notice").innerHTML = q.state === "error"
      ? '暂时载入不了大家的提问。<button type="button" class="qa-link" data-qa-retry>点此重试</button>'
      : esc(q.notice);
    var html = q.topics.map(qaItemHtml).join("");
    if (!q.topics.length) {
      if (q.state === "ready") html = '<p class="qa-empty">还没有人提问。可以从历史背景、建筑、人物或参观方式切入。</p>';
      else if (q.state !== "error") html = '<p class="qa-empty">正在载入…</p>';
    }
    if (q.more) html += '<button type="button" class="btn btn-secondary qa-more" data-qa-more>更早的提问</button>';
    $("qa-list").innerHTML = html;
  }

  function qaMount(pid) {
    if (qaLive === false) return;
    var q = qaState(M.key, pid);
    $("qa-input").value = q.draft;
    qaRender(M.key, pid);
    if (q.state === "new") qaLoad(M.key, pid, false);
  }

  // older：接着往前翻一页；否则取最新的一页
  function qaLoad(key, pid, older) {
    var q = qaState(key, pid);
    if (q.loading) return;
    q.loading = true;
    if (q.state !== "ready") q.state = "loading";
    var url = qaUrl(key, pid) + "?limit=" + QA_PAGE;
    if (older && q.topics.length) url += "&before=" + encodeURIComponent(q.topics[q.topics.length - 1].id);
    qaFetch(url).then(function (res) {
      q.loading = false;
      if (res.status === 404 || res.status === 503) {
        qaLive = false;                            // 接口没部署：整块不显示，介绍照常
      } else if (!res.ok || !res.body.topics) {
        q.state = "error";
      } else {
        qaLive = true;
        // 正在等回答的那一条只存在于本机，重取列表时留着它
        var waiting = q.topics.filter(function (t) { return t.local; });
        q.topics = older ? q.topics.concat(res.body.topics) : waiting.concat(res.body.topics);
        q.more = !!res.body.more;
        q.state = "ready";
      }
      qaRender(key, pid);
    }, function () {
      q.loading = false;
      if (q.state !== "ready") q.state = "error";
      qaRender(key, pid);
    });
  }

  function qaAsk(pid) {
    var key = M.key, q = qaState(key, pid), input = $("qa-input");
    var text = input.value.replace(/\s+/g, " ").trim();
    if (q.asking) return;
    if (text.length < 2) {
      q.notice = "先输入你的问题。";
      qaRender(key, pid);
      return;
    }
    var mine = { id: "local-" + Date.now(), local: true, question: text, answer: null, status: "pending",
                 mine: true, public: false, created_at: new Date().toISOString() };
    q.topics.unshift(mine);
    q.asking = true;
    q.notice = q.draft = input.value = "";
    input.blur();                                  // 收起键盘，让出地方看回答
    qaRender(key, pid);

    // 回答（或失败）回来时人可能已经翻到别处：状态照记，画不画由 qaRender 自己判断
    function settle(topic, notice) {
      q.asking = false;
      q.topics = q.topics.filter(function (t) { return t !== mine && !(topic && t.id === topic.id); });
      if (topic) q.topics.unshift(topic);
      q.notice = notice;
      qaRender(key, pid);
    }
    function failed(message) {
      settle(null, "提交失败：" + message);
      if (q.draft) return;                         // 等的时候已经在写下一个问题了，不去覆盖
      q.draft = text;
      if (qaViewing(key, pid)) $("qa-input").value = text;
    }
    qaFetch(qaUrl(key, pid), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: text })
    }).then(function (res) {
      if (res.ok && res.body.topic) settle(res.body.topic, res.body.duplicate ? "这个问题已经有人问过，回答在下面。" : "");
      else failed(res.body.message || "服务器没有答上来（" + res.status + "）");
    }, function () {
      failed("网络不通或等待超时，请重试。");
      qaLoad(key, pid, false);                     // 请求也许其实到了服务器：把列表重新取一遍
    });
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
    var entrance = M.entrance || {x: 0, y: 0};
    st = {
      routeId: M.default_route, k: 1, pan: [0, 0], pos: [entrance.x, entrance.y],
      geo: "waiting", acc: 0, dist: 0, raw: null, inside: null, msgs: [],
      sheetPid: null, sheetOpen: false, msgsOpen: false, bannerPid: null,
      follow: true, touring: false, tourIdx: null, themeId: null, themeStarts: {}
    };
    restore();
    $("list").hidden = true;
    $("tour").hidden = false;
    var collection = isCollection();
    $("collection-views").hidden = !hasBrowseMap();
    $("collection").hidden = !collection;
    $("collection-themes").hidden = true;
    $("mapwrap").hidden = collection;
    $("bell").hidden = collection;
    document.querySelector('.bottombar').hidden = collection;
    if (collection) {
      if (HOST) HOST.leave();
      buildCollection();
      if (hasBrowseMap()) collectionView(false);
      updateSheets();
      return;
    }
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
    if (HOST) HOST.leave();
  }

  // Android 的到站判定在原生引擎中完成。网页接收画布位置、所在热区与消息，
  // 不再启动浏览器 GPS，也不把原生坐标送回 setPos() 重判一次。
  var hostSeen = {};
  if (OPT.debug) window.AriTourDebug = {
    snapshot: function () { return M && st ? { status: st.geo, inside: st.inside, x: st.pos[0], y: st.pos[1], raw: st.raw } : null; },
    error: function (status) { onGeoError({ code: status === "timeout" ? 3 : 2, TIMEOUT: 3, PERMISSION_DENIED: 1 }); }
  };
  if (HOST) window.AriTour = {
    state: function (s) {
      if (!M || !st || !gpsActive() || s.museum !== M.key) return;
      var first = st.geo !== "live";
      st.geo = s.status;
      st.pos = [s.x, s.y];
      st.acc = s.acc || 0;
      st.dist = s.dist || 0;
      st.raw = s.raw || null;
      st.inside = s.inside || null;
      (s.history || []).slice().reverse().forEach(function (m) {
        if (!placeById(m.pid)) return;
        var seenKey = s.museum + ":" + m.pid;
        if ((hostSeen[seenKey] || 0) >= m.at) return;
        hostSeen[seenKey] = m.at;
        var d = new Date(m.at);
        if (m.at >= s.connectedAt) notify(placeById(m.pid), m.at);
        else {
          // 从后台返回时补齐消息。时间更近的本地原生记录优先，已读状态保留。
          var old = st.msgs.filter(function (item) { return item.pid === m.pid; })[0];
          st.msgs = st.msgs.filter(function (item) { return item.pid !== m.pid; });
          st.msgs.unshift({ pid: m.pid, time: pad2(d.getHours()) + ":" + pad2(d.getMinutes()), at: m.at, read: !!(old && old.at >= m.at && old.read) });
        }
      });
      save();
      updateMsgs();
      updateMe();
      if (s.status === "live" && (st.follow || first)) centerOn(s.x, s.y);
    },
    open: function (pid) { if (M && placeById(pid)) openIntro(pid); },
    back: function () {
      if (M && (st.sheetOpen || st.msgsOpen)) { closeSheets(); return true; }
      if (M) { location.hash = ""; return true; }
      return false;
    }
  };

  function onHash() {
    var key = location.hash.replace(/^#/, "");
    if (data[key]) { if (!M || M.key !== key) { if (M) closeMuseum(); openMuseum(key); } }
    else if (M) { closeMuseum(); refreshHome(); }
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
    window.addEventListener("resize", function () { if (mapVisible()) layout(); });
  }

  function bindUi() {
    $("view-list").addEventListener("click", function () { collectionView(false); });
    $("view-map").addEventListener("click", function () { st.themeId = null; collectionView(true); });
    $("view-themes").addEventListener("click", showThemes);
    $("collection-themes").addEventListener("change", function (e) {
      var id = e.target.getAttribute("data-theme-start");
      if (id) { st.themeStarts[id] = e.target.value; renderThemes(); }
    });
    $("collection-themes").addEventListener("click", function (e) {
      var map = e.target.closest("[data-theme-map]"), place = e.target.closest("[data-place]"), jump = e.target.closest("[data-theme-jump]");
      if (map) { st.routeId = "none"; st.themeId = map.getAttribute("data-theme-map"); collectionView(true); }
      else if (place) openIntro(place.getAttribute("data-place"));
      else if (jump) {
        var pane = $("collection-themes"), target = pane.querySelector('[data-theme="' + jump.getAttribute("data-theme-jump") + '"]');
        if (target) pane.scrollTop += target.getBoundingClientRect().top - pane.getBoundingClientRect().top - 8;
      }
    });
    $("collection-search").addEventListener("input", function () { if (M && isCollection()) renderCollection(); });
    ["collection-kind", "collection-area", "collection-tier", "collection-shop-category", "collection-shop-tag"].forEach(function (id) {
      $(id).addEventListener("change", function () { if (M && isCollection()) renderCollection(); });
    });
    $("collection-items").addEventListener("click", function (e) {
      var b = e.target.closest("[data-place]");
      if (b) openIntro(b.getAttribute("data-place"));
    });
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
      var theme = e.target.closest("[data-map-theme]");
      if (theme) { st.routeId = "none"; st.themeId = theme.getAttribute("data-map-theme") || null; collectionView(true); return; }
      var b = e.target.closest("[data-route]");
      if (!b) return;
      stopTour();
      st.tourIdx = null;
      if (st.themeId) { st.themeId = null; buildMap(); layout(); }
      st.routeId = b.getAttribute("data-route");
      save();
      updateRoute();
    });
    $("locate").addEventListener("click", function () {
      if (HOST && st.geo === "denied") { HOST.requestLocation(); return; }
      if (st.geo === "sim") { if (st.touring) stopTour(); else startTour(); return; }
      if (st.geo === "denied") { stopGeo(); startGeo(); return; }
      st.follow = true;
      centerOn(st.pos[0], st.pos[1]);
    });
    $("banner").addEventListener("click", function () { if (st.bannerPid) openIntro(st.bannerPid); });
    $("backdrop").addEventListener("click", closeSheets);
    $("sheet").addEventListener("click", function (e) {
      var showMap = e.target.closest("[data-show-map]");
      if (showMap) { closeSheets(); collectionView(true, showMap.getAttribute("data-show-map")); return; }
      var go = e.target.closest("[data-goto]");
      if (go) { openIntro(go.getAttribute("data-goto")); return; }
      if (e.target.closest("[data-qa-more]")) { qaLoad(M.key, st.sheetPid, true); return; }
      if (e.target.closest("[data-qa-retry]")) { qaLoad(M.key, st.sheetPid, false); qaRender(M.key, st.sheetPid); return; }
      if (e.target.closest("[data-close]")) closeSheets();
    });
    $("sheet").addEventListener("submit", function (e) {
      if (e.target.id !== "qa-form") return;
      e.preventDefault();
      qaAsk(st.sheetPid);
    });
    $("sheet").addEventListener("input", function (e) {
      if (e.target.id === "qa-input") qaState(M.key, st.sheetPid).draft = e.target.value;
    });
    $("sheet").addEventListener("focusin", function (e) {
      // 软键盘会盖住屏幕下半截：把输入框挪到抽屉靠上的位置。只滚抽屉自己 ——
      // scrollIntoView 会连外层一起滚，把收在屏幕下面的另一个抽屉带出来
      if (e.target.id !== "qa-input") return;
      setTimeout(function () {
        var sheet = $("sheet");
        sheet.scrollTop += e.target.getBoundingClientRect().top - sheet.getBoundingClientRect().top - 90;
      }, 350);
    });
    $("sheet").addEventListener("focusout", function (e) {
      // 部分手机浏览器在键盘收起后不把页面放回原位
      if (e.target.id === "qa-input") window.scrollTo(0, 0);
    });
    // 外层不该滚动（见 app.css 里 #app 的说明）。不认 overflow: clip 的浏览器上，被带着滚了就拨回去
    $("tour").addEventListener("scroll", function () { this.scrollTop = this.scrollLeft = 0; });
    $("app").addEventListener("scroll", function () {
      if (this.scrollTop || this.scrollLeft) this.scrollTop = this.scrollLeft = 0;
    });
    $("msgs-body").addEventListener("click", function (e) {
      var b = e.target.closest("[data-msg]");
      if (b) openIntro(b.getAttribute("data-msg"));
    });
    window.addEventListener("hashchange", onHash);
  }

  // ------------------------------------------------------------ 启动
  function loadAll() {
    return fetch('catalog.json', {cache: 'no-cache'}).then(function (r) {
      if (!r.ok) throw new Error('景区清单 HTTP ' + r.status);
      return r.json();
    }).then(function (catalog) {
      if (!Array.isArray(catalog.museums) || catalog.museums.some(function (key) {
        return typeof key !== 'string' || !/^[a-z0-9_]{1,32}$/.test(key);
      }) || new Set(catalog.museums).size !== catalog.museums.length) throw new Error('景区清单格式错误');
      var nextData = {};
      return Promise.all(catalog.museums.map(function (key) {
      // 不带额外参数：这样才能直接用上 index.html 里预先下载的那一份。
      // 要不要重新向服务器确认由响应头决定（Nginx 对 JSON 发的是 Cache-Control: no-cache）
      return fetch("data/" + key + ".json", {cache: 'no-cache'}).then(function (r) {
        if (!r.ok) throw new Error(key + ".json HTTP " + r.status);
        return r.json();
      }).then(function (j) {
        if (j.key !== key) throw new Error('景区资料标识不一致');
        nextData[key] = j;
      });
      })).then(function () {
        // 原生缓存只接收有真实几何的目的地；清单仍由同一网页显示，无需旧APK理解新数据类型。
        var mapped = catalog.museums.map(function (key) { return nextData[key]; }).filter(function (m) { return !isCollection(m) || !!m.navigation; }).map(nativeTour);
        if (HOST && !HOST.catalog(JSON.stringify(mapped))) {
          throw new Error('景区资料未能同步至定位服务，请重试');
        }
        MUSEUMS = catalog.museums; data = nextData;
      });
    });
  }

  function refreshHome() {
    loadAll().then(renderCards).catch(function () {
      $("cards").innerHTML = '<p class="load-note">景区清单更新失败，请联网后刷新。</p>';
    });
  }

  bindUi();
  bindMap();
  document.addEventListener('visibilitychange', function () { if (!document.hidden && !M) refreshHome(); });
  loadAll().then(function () {
    renderCards();
    onHash();
  }).catch(function (e) {
    $("cards").innerHTML = '<p class="load-note">数据没有载入成功，请刷新重试。<br>' + esc(e.message) + "</p>";
  });
})();
