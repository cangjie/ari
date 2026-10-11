# 导览站部署记录

Ari Travel 手机导览站，部署在 `tour.snowmeet.top`。本文记录它是怎么来的、线上实况与待办；
本地怎么跑、调试参数见 `web_api/README.md`。

首次部署：2026-10-10，由 claude 执行。目前只上线了伪满皇宫博物院（`wmhg`）一处。

## 这是什么

照原型 AriTour 做的手机网页：目的地列表 → 导游地图。地图上方选参观路线，
走进景点热区时推送讲解，点开看介绍，可以「上一处 / 下一处」顺着路线走。

和原型的三处不同，都是因为原型是演示、这里要接真实定位：

| | 原型 | 线上 |
|---|---|---|
| 地图 | 手绘示意图 | 按 OpenStreetMap 的建筑、围墙、道路轮廓重画，样式照原型 |
| 当前位置 | 拖动圆点 / 模拟游览 | 手机实时 GPS（`watchPosition`） |
| 热区 | 22 个，含几个画在示意位置上的 | 18 个，全部有实测坐标 |

原型的手绘图与实测坐标对不齐（18 个点均方根差 13.5 米，书画楼差 32 米），
而热区半径只有十几米 —— 拿它接 GPS，人站在楼前圆点会落在隔壁。

## 数据从哪来

页面只读一个文件 `web_api/tour/data/wmhg.json`，由 `utils/import_data/tour_build.py` 生成：

```
库（评级、名称、介绍、在展状态、复核标记）──┐
wmhg_route_data.py（参观顺序、坐标、停留时间）─┼─ tour_build.py ─→ web_api/tour/data/wmhg.json
wmhg_osm_data.json（OSM 几何）+ wmhg_tour_data.py ┘
```

```sh
cd utils/import_data
python3 tour_osm_fetch.py --museum wmhg            # 体检现有的 OSM 数据；--refresh 重新取
python3 tour_build.py --museum wmhg                # 生成；--check 只比对不写
python3 tour_images.py --museum wmhg --allow-expired-cert   # 下载官网图片（要能连上官网）
```

路线不是另算的：`tour_build.py` 直接调用 `route_plan.py` 的 `Planner`，
五条路线的分钟数（119 / 120 / 233 / 235 / 418）与导出的 Excel 是同一段代码算出来的。

### 几条生成规则

**热区是「地点」，不是「站」。** 路线上的一站是库里的一个节点，地图上的一个热区是一个
实际能走到的位置。25 站落在 18 个地点上：怀远楼含楼上的御纹章展，东北沦陷史陈列馆含三个陈列，
嘉乐殿含《从皇帝到公民》。

**坐标是借用的站不单独成点。** 路线数据里游泳池、卤簿车库、百年机车馆、薰南楼四站在 OSM 上
没找到，坐标借的是东御花园或跑马场。页面把它们列在所借地点的介绍里，并写明「具体位置未核实」。
在一个没有出处的位置上画标记、并在那里触发到站提醒，等于告诉游客一件我们不知道的事。

**热区半径**取 OSM 轮廓的等效半径加 10 米，限制在 15–45 米。热区会重叠（花园里套着防空洞），
落在几个热区里时取相对距离（距离 ÷ 半径）最小的那个。

**景区范围** = OSM 上「伪满皇宫博物院」的院区边界（`way/227373465`）外扩 30 米。
售票处在边界外 3 米，所以要外扩；生成时断言入口与全部地点都在范围内。

**介绍**用库里的官网中文原文，出处按 `artwork.official_url` 标注。
带复核标记的条目会附上复核原因（AGENTS.md 第 9 条）；目前页面上会出现的 30 个条目里 0 件。

## 定位

| 情形 | 圆点 | 底栏 |
|---|---|---|
| 在景区范围内 | 黑色、有脉冲，随 GPS 移动 | 「位于「同德殿」热区」或「未进入热区」 |
| 不在景区范围内 | 灰色、停在入口 | 「不在景区范围内 · 距入口 2.3 公里」 |
| 未授权 | 灰色 | 「未获得定位授权」，按钮变成「重新授权」 |
| 中途丢了信号 | 灰色、停在最后的位置 | 「暂时无法定位」/「定位超时，仍在尝试…」 |
| 不是 HTTPS | 灰色 | 「需 HTTPS 才能定位」 |

- 精度差于 30 米的定位只移动圆点、不触发到站；圆点外有一圈表示误差范围。
- 已在某个热区里时，走出 1.2 倍半径才算离开，免得在边上反复进出。
- 信号一闪不清「所在热区」，否则恢复后会把同一处再提醒一遍。
- 国内部分安卓浏览器给的是国测局坐标（GCJ-02），在长春偏约 590 米（北 270、东 527），
  会被判成不在景区。现场若遇到，在网址上加 `?crs=gcj02` 验证。**页面目前不会自动判断坐标系。**
- 室内 GPS 很差，到站提醒主要在走近建筑时触发。

## 服务器部署实况

- 域名 `tour.snowmeet.top`，A 记录指向 `44.207.251.65`
- 站点根目录就是仓库里的 `web_api/tour`：`/home/ubuntu/ari/web_api/tour`，Nginx（`www-data`）可读
- **不经过 FastAPI**，与 `ari-web-api` 服务无关
- 更新 = `cd /home/ubuntu/ari && git pull --ff-only`，不用重启任何服务

### 证书

- 签发机构：TrustAsia LiteSSL RSA CA 2025，RSA，只签给 `tour.snowmeet.top` 一个域名
- 证书链（3 张，叶子在前）：`/etc/ssl/tour/tour.snowmeet.top.crt`，`644 root:root`
- 私钥：`/etc/ssl/tour/tour.snowmeet.top.key`，`600 root:root`，目录 `700`
- **有效期 2026-10-10 至 2027-01-07，只有 90 天**

证书由用户手动申请，**没有自动续期**。到期前需重新下载并替换，或改用 Let's Encrypt + certbot。

2026-10-10 的经过：用户先给的 `~/Desktop/tour-snowmeet-top-nginx-1010093039.zip` 是 0 字节的空文件，
站点先只开了 80 上线；同名文件在 `~/Downloads/` 里是完整的（5728 字节），当天下午装上并切到 HTTPS。
**同名文件在两个目录里可能不是同一份，装之前先看大小。**

### Nginx

`/etc/nginx/sites-available/ari-tour`，已在 `sites-enabled` 建链接：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name tour.snowmeet.top;

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name tour.snowmeet.top;

    # TrustAsia 手动签发，2027-01-07 到期，没有自动续期
    ssl_certificate     /etc/ssl/tour/tour.snowmeet.top.crt;
    ssl_certificate_key /etc/ssl/tour/tour.snowmeet.top.key;

    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    root  /home/ubuntu/ari/web_api/tour;
    index index.html;

    # 明确告诉浏览器是 UTF-8，不靠它从 <meta> 里猜（text/html 恒被包含）
    charset       utf-8;
    charset_types text/css application/javascript application/json;

    gzip            on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types      text/plain text/css application/javascript application/json image/svg+xml;
    gzip_vary       on;

    # 页面与数据随 git pull 更新：每次都向服务器确认，不让手机拿着旧版本
    location / {
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";
    }

    # 字体与图片不会变，放心缓存 30 天
    location ~* \.(woff2|jpg|jpeg|png|webp)$ {
        try_files $uri =404;
        add_header Cache-Control "public, max-age=2592000";
    }
}
```

同一台机器上的其它站点（`ari-web-api`、`ari-smoke`、`reqai`）没有改动。

### 换证书的步骤

1. **本机核对，不解压进仓库、不输出私钥内容**：

   ```sh
   Z=~/Downloads/<证书包>.zip
   ls -la "$Z"                      # 先看大小，正常约 5.7 KB
   unzip -l "$Z"
   unzip -p "$Z" tour.snowmeet.top_cert_chain.pem | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
   unzip -p "$Z" tour.snowmeet.top_cert_chain.pem | grep -c 'BEGIN CERTIFICATE'     # 链的张数，叶子在前
   unzip -p "$Z" tour.snowmeet.top_cert_chain.pem | openssl x509 -pubkey -noout | openssl sha256
   unzip -p "$Z" tour.snowmeet.top_key.key | openssl pkey -pubout | openssl sha256   # 两个摘要必须相同
   ```

   主体或 SAN 不含 `tour.snowmeet.top`、已过期、摘要不同，任一项不过就停下。

2. **管道直写到服务器**，不在 `/tmp` 留副本，私钥从创建那一刻起就是 600：

   ```sh
   unzip -p "$Z" tour.snowmeet.top_cert_chain.pem | ssh ubuntu@44.207.251.65 \
     'sudo sh -c "umask 022 && cat > /etc/ssl/tour/tour.snowmeet.top.crt"'
   unzip -p "$Z" tour.snowmeet.top_key.key | ssh ubuntu@44.207.251.65 \
     'sudo sh -c "umask 077 && cat > /etc/ssl/tour/tour.snowmeet.top.key"'
   ```

   服务器上再验一次配对与证书链（`openssl verify -untrusted`，中间证书取同一文件的第 2、3 张）。

3. `sudo nginx -t` 通过后再 `sudo systemctl reload nginx`，两条分开执行。

4. 把新的到期日改进本文和 `AGENTS.md`。

**这台服务器的 22 端口偶尔连不上**（新连接超时，80/443 同时是通的，过一两分钟自己恢复；
2026-08-21 装环境时也遇到过）。一次部署要连好几回时，用 `ControlMaster` 复用同一条连接：
`ssh -o ControlMaster=auto -o ControlPath=~/.ssh/cm-%C -o ControlPersist=900 …`。

## 验收记录

2026-10-10：

| 检查项 | 结果 |
|---|---|
| `tour_osm_fetch.py` | 132 个 OSM 要素；路线数据里手抄的 23 个坐标与 OSM 现值相差均不超过 5 米 |
| `tour_build.py` | 18 个地点、25 站；路线合计 119 / 120 / 233 / 235 / 418 分钟，与 Excel 一致；`--check` 一致 |
| 本地 pytest | 18 条全绿（原有 9 条 + 导览站 9 条） |
| 无头 Chrome，390×844，经浏览器真实的 `watchPosition`（脚本：`web_api/tests/tour_browser_check.mjs`） | 见下 |
| · 定位在同德殿 | 黑点落在同德殿，横幅弹出，底栏「位于「同德殿」热区」 |
| · 依次到勤民楼、建国神庙 | 各提醒一次，消息列表三条，已游览 3 / 18 |
| · 精度 80 米 | 圆点移动、不触发，底栏「定位精度较低 · ±80 米」 |
| · 定位在北京 / 院外 200 米 | 圆点灰、停在入口，「不在景区范围内 · 距入口 862 公里 / 200 米」，按钮禁用 |
| · 拒绝授权 | 圆点灰，「未获得定位授权」，按钮「重新授权」 |
| · 国测局坐标 | 不换算判在院外 750 米；加 `?crs=gcj02` 回到同德殿 |
| · 触摸 | 单指拖动、双指缩放、点按标记开介绍、路线条横滑不带动地图 |
| 证书与私钥配对 | 公钥 sha256 一致，本机与服务器各验一次 |
| 证书链校验 | `openssl verify` → OK |
| 服务器 `nginx -t` | 通过 |
| 外部 `https://tour.snowmeet.top/` | 200，HTTP/2，`text/html; charset=utf-8` |
| 客户端 TLS 校验 | `Verify return code: 0 (ok)` |
| 外部 HTTP 80 | `301` → `https://tour.snowmeet.top/` |
| 外部 `/data/wmhg.json` | 200，gzip 后 13 KB（原 43 KB），`Cache-Control: no-cache` |
| 外部字体 | 200，`font/woff2`，缓存 30 天 |
| 线上页面，无头 Chrome 模拟定位 | `isSecureContext = true`；同德殿 → 黑点与横幅；北京 → 灰点、「不在景区范围内 · 距入口 862 公里」；拒绝授权 → 「未获得定位授权」 |
| 线上首次打开（本机到美国，无缓存） | 约 3 秒出地图，其中建连接与首字节占 2 秒；数据文件改成预先下载之前是约 5 秒 |
| `ai.snowmeet.top`、`ari.goldenma.xyz`（直连服务器） | 200，证书校验通过 —— 未受影响 |

只开 HTTP 的那几个小时里也验过：`isSecureContext = false` 时底栏写「需 HTTPS 才能定位」，圆点灰。

**没验的**：真机 GPS。无头浏览器里的定位是模拟出来的，走的是浏览器真实的 `watchPosition`，
但手机在院子里的实际精度、国内浏览器给的坐标系，只有到现场才知道。

## 待办

- **证书 2027-01-07 到期**，没有自动续期。
- **真机 GPS 验收**还没做。
- **照片**：2026-10-11 已下载 17 张官网图片并部署到导览站，16/25 个站点有图，目的地卡片封面有图；线上 JSON 和 17 个图片 URL 均返回 HTTP 200。
  其中 5 张超过 600 KB。另有 13 个条目库里没有图片地址（52–61 号节点与 4 件在展藏品），需先补来源才能配图。
- **游泳池与卤簿车库可能有实测位置**：OSM 上院内有一个无名的 `leisure=swimming_pool`
  （`way/227329948`，在御用防空洞入口北侧约 29 米）和一栋名为「停车间」的 `building=garage`
  （`way/227338690`）。路线数据写的是「OSM 无此点」，是按名字没搜到。核实后可以改
  `wmhg_route_data.POINTS`，这两站就能单独成点 —— 但步行分钟数会跟着变，路线 Excel 要重导。
- **坐标系不会自动判断**，见上文「定位」。
- **`goldenma.xyz` 整个域名解析不出来**（2026-10-10，8.8.8.8 与 1.1.1.1 都查不到 NS 与 A 记录）。
  服务器上的 `ari.goldenma.xyz` 站点本身正常，只是从外面按域名访问不到。与本次部署无关。
- 「已游览」存在手机浏览器里，隔天再来还在，目前没有清除入口。
