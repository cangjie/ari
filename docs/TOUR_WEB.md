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

## 游客互动（AI 问答）

2026-10-12 加入，照 MingnaCurator 小程序的「观众互动」做，这一轮只做了文字问答。
**页面已更新到线上，但接口入口还没开，游客暂时看不到这一块** —— 差数据库账号与 OpenAI key，见本节末的「部署状态」。

介绍抽屉里「介绍出处」下面多出一块：游客输入问题，导览助手（AI）结合导览页上的资料回答，
问答对所有游客公开。接口不在时这一块不显示，介绍照常。

```
页面（app.js）──→ /api/tour/…（Nginx 反代）──→ FastAPI（web_api/app/tour_qa.py）──→ MySQL：tour_topic、tour_qa_setting
                                                                              └→ OpenAI
```

| | |
|---|---|
| 接口 | `GET /api/tour/{馆}/places/{地点}/topics?before=&limit=`；`POST` 同一地址，请求体 `{"question": "…"}`，同步等回答 |
| 「我」是谁 | 没有登录。浏览器里生成一个匿名设备号存在 `localStorage`，经 `X-Visitor` 请求头带上；接口不把它返回给别人 |
| 谁看得到 | 所有人看所有人的。例外：模型判为与参观无关的、没答上来的，只有提问者自己看得到 |
| 回答依据 | 就是页面那份 `data/<馆>.json`（全馆各站的名称、评级、现状、介绍、在展藏品、出处），不另外读库 |
| 提示词 | 只写行为规则：资料之外可以用常识答，但不许挂在馆方名下；不编展厅位置、票价、是否在展；带「待复核」的不当事实讲；不超过 300 字 |
| 型号 | 环境变量 `ARI_QA_MODEL`，不写死；缺了接口回 503，不猜。实际型号记在每一行的 `model` 列 |
| 不重复花钱 | 同一地点、同一份资料、同一个问题已有公开回答就直接给，不再调模型（`prompt_hash`，与 `llm_cache` 的键同一思路） |
| 记账 | token 与耗时记在 `tour_topic` 本行，不写 `llm_call`（那张表是管线的，按展品关联） |

### 提问条数上限：改一行，立即生效

三个上限在表 `tour_qa_setting` 里，每次提问现读、不缓存。改完之后的下一条提问就按新值算，
不用重启、不用登服务器、不用部署。

| `name` | 初值 | 含义 |
|---|---:|---|
| `per_visitor_per_day` | 20 | 每个设备 24 小时内最多提问几条 |
| `per_ip_per_hour` | 120 | 每个 IP 每小时最多提问几条（只在内存里计数，不存 IP，服务重启后清零） |
| `site_per_day` | 1000 | 全站 24 小时内最多提问几条 |

```sql
UPDATE tour_qa_setting SET value = 50 WHERE name = 'per_visitor_per_day';   -- 改上限
UPDATE tour_qa_setting SET value = 0  WHERE name = 'site_per_day';          -- 关掉提问（已有问答照常显示）
SELECT name, value, updated_at FROM tour_qa_setting;                        -- 看现值
```

- **任何一项设成 0 就是关掉提问。**
- 某一行被删掉时提问接口回 503，日志里写明缺哪一项，不拿内置默认值顶替。
- 服务用的数据库账号对这张表只读，服务自己改不了自己的上限。
- 另有两条写在代码里：同一设备同时只能有一条在答；问题 2–100 字且不能只有标点。

### 下架一条问答

这一轮没有管理端，下架靠改库。`valid = 0` 之后所有人（包括提问者）都看不到；
别人再问同一个问题也不会让它重新公开。

```sql
SELECT id, place_id, question, LEFT(answer, 40), is_public, created_at
  FROM tour_topic WHERE museum_key = 'wmhg' ORDER BY id DESC LIMIT 30;      -- 先看
UPDATE tour_topic SET valid = 0 WHERE id = 123;                             -- 再下架
```

**`tour_topic` 是游客数据，重跑不出来。** 改结构只在 `web_api/sql/tour_qa.sql` 末尾追加 ALTER，不要 DROP 重建。

### 部署状态（2026-10-12）

**页面已更新到线上，但接口入口没开，游客看不到「游客互动」。** 只差 OpenAI 的 key 文件和一段 Nginx 配置。

| | 状态 |
|---|---|
| 代码、测试 | 已完成，见下文验收记录 |
| 库表 `tour_topic`、`tour_qa_setting` | **已建**（`ari` 库现为 16 张表），三行上限初值已写入 |
| 服务器上的代码与依赖 | **已做**：`git pull`；`/opt/ari/.venv` 新装 `openai 3.6.0`、`PyMySQL 1.2.0`（连带 `jiter 0.17.0`、`sniffio 1.3.1`），原有的包没有变动 |
| 服务配置 | **已做**：`/etc/ari/web-api.env`（640 root:ari，**不含密钥**）与 systemd drop-in `/etc/systemd/system/ari-web-api.service.d/tour-qa.conf`，服务已重启 |
| 数据库账号 `/etc/ari/web-api.my.cnf` | **已做**：`web_api/sql/create_ari_web.sh` 建了 `ari_web@localhost`，配置文件 640 root:ari。服务没重启就连上了库，列表接口回 200 |
| OpenAI key `/etc/ari/openai_key` | **未做**：用户定的是用同机 reqai 项目的那把 key，但权限系统不允许 AI 自己到别的项目里找密钥，要用户放过来或明确授权 |
| Nginx `location /api/` | **未做**：等 key，并先用真模型试答。入口不开，页面上这一块就不显示 |

`/etc/ari/web-api.env` 的内容（密钥不在这里，在它指向的两个文件里）：

```
ARI_QA_MODEL=gpt-5.4-nano
ARI_DB_DEFAULTS_FILE=/etc/ari/web-api.my.cnf
ARI_OPENAI_KEY_FILE=/etc/ari/openai_key
```

两个文件都是 `640 root:ari`。应用在第一次用到时才读它们，**放好之后不用重启服务**。

- `/etc/ari/openai_key`：只有一行，就是 key 本身。
- `/etc/ari/web-api.my.cnf`：MySQL 选项文件。由 `web_api/sql/create_ari_web.sh` 生成：它新建账号 `ari_web@localhost`
  （对 `ari.tour_topic` 有 SELECT / INSERT / UPDATE，对 `ari.tour_qa_setting` 只有 SELECT，别的表碰不到），
  口令随机生成、直接写进这个文件，不打印。服务走本机套接字连库。2026-10-12 已跑成（root 的配置从标准输入给，
  登上的是 `root@localhost`）。以后要换口令就重跑，跑法（会问一次 MySQL root 口令，输入不回显；这一支没有实跑过）：

  ```sh
  ssh -t ubuntu@44.207.251.65 'sh /home/ubuntu/ari/web_api/sql/create_ari_web.sh'
  ```

  `root@localhost` 与允许远程登录的 `root@%` 是两个账号，脚本会先走套接字、不行再走 TCP 各试一次。

key 文件到位后还要做三步：

1. **用真模型试答一批问题**（现有的另一把 key 所在账户余额为 0，至今一条都没答成），看提示词与型号行不行。
2. Nginx 站点 `ari-tour` 在 `location /` 之前加一段，`nginx -t` 通过后再 reload：

   ```nginx
   # 游客互动的接口，转给 ari-web-api。缓存头由应用自己发（no-store），这里不重复加
   location /api/ {
       proxy_pass http://127.0.0.1:8002;
       proxy_set_header Host              $host;
       proxy_set_header X-Real-IP         $remote_addr;
       proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_read_timeout   90s;
       client_max_body_size 8k;
   }
   ```

3. 线上验收：真问一条、查库里那一行的型号与 token、把上限临时改成 1 再改回来验证立即生效。

上线之后，改了 `web_api/app/` 要 `sudo systemctl restart ari-web-api`；只改页面和数据仍然只需 `git pull`。

### 已知的限制

- **真机上软键盘弹出时输入框会不会被挡住，没验过。** 无头浏览器模拟不了软键盘；页面做了三处防护
  （输入框挪到抽屉靠上的位置、外层 `overflow: clip`、键盘收起后把页面拨回原位），实际效果要到手机上看。
- 模型把关会误判。漏掉的不当内容靠上面的下架语句处理。
- 换手机或清了浏览器数据，「我的提问」就认不出来了，没公开的那些也看不到了。
- 没做：语音提问、回答朗读、跨地点的「我的互动」汇总页、管理端与策展人答复、流式输出、英文界面。

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

2026-10-12，游客互动（接口入口未开；除最后三行外都是本机结果）：

| 检查项 | 结果 |
|---|---|
| 本地 pytest | 63 条全绿：原有 18 条 + `/tour/` 挂载 1 条 + 问答接口 44 条（假库、假模型，不联网） |
| · 提问与列表 | 提问后拿到回答；别人看得到公开的，看不到设备号；按地点分开；新的在前、能翻页 |
| · 把关与失败 | 判为与参观无关的只有提问者看得到；模型失败回 502，该行记 failed 且不公开，内部错误原文不给游客 |
| · 上限 | 三道上限各回 429；改了上限不重启，下一条就按新值算；设成 0 一条也提不了、已有问答照常；上限表缺一行回 503 |
| · 复用 | 同一地点同一问题不再调模型；不公开的、已下架的被重问时不会重新公开 |
| · 没配置 | 缺数据库或模型配置时只有问答回 503，`/health` 照常 |
| 真库上的存取（`test_tour_qa_db.py`，默认跳过） | 3 条通过：UTC 时间、四字节字符、token 入库、错误信息截到 500 字、可见性、复用、下架。测试行已清掉，上限表未动 |
| 本机起服务连真库 | 列表 200 且 `Cache-Control: no-store`；未知地点 404；只有标点的问题 400；不带设备号 400 |
| 无头 Chrome | 63 项全过：原有 44 项 + `qa` 场景 19 项（对着脚本自带的假接口） |
| · 位置与文案 | 「游客互动」在「介绍出处」之后、「前往下一处」之前；别人的标「游客提问」，自己的标「我的提问」 |
| · 提问 | 提问后输入框清空、按钮禁用、出现「思考中」；回答回来后替换；空问题不发请求 |
| · 不被注入 | 问题与回答里的 `<img onerror>`、`<b>` 原样显示成文字，不变成元素 |
| · 翻页 | 翻到下一处是那一处自己的列表与空输入框；翻回来草稿和列表都还在 |
| · 出错 | 提问失败写明原因、问题回到输入框；列表载入失败给「点此重试」；接口不存在时整块从头到尾不显示（拿到列表之后才显示，不会先闪一下） |
| · 输入框获得焦点 | 输入框挪到屏幕上半截，外层页面不跟着滚（修掉了一个会把「消息」抽屉带出来的问题） |
| **真模型试答** | **没做成**：13 个问题全部被 OpenAI 拒绝，账户余额为 0。提示词与型号的实际效果还没有任何证据 |
| 服务器：服务重启后 | `ari-web-api` active，`/health` 200；问答接口回 503，日志写明「ARI_DB_DEFAULTS_FILE 指的文件不存在」 |
| 线上页面（新脚本已生效） | 无头 Chrome 对着 `https://tour.snowmeet.top` 跑原有 8 个场景：42 项通过；2 项「控制台没有报错」不过，报的都是 `/api/tour/…` 404，入口开通后消失 |
| 线上：互动一块 | 不显示（入口未开，符合预期）；`ai.snowmeet.top` 仍回 200 |
| 服务账号 `ari_web` 的权限（以系统用户 `ari` 用服务的配置文件连库实测） | 能读上限表与问答表；改上限表、删问答、读 `artwork`、建表都被拒（1142） |
| 服务器：账号建好之后（服务未重启） | 列表接口回 200 `{"topics":[],"more":false}`；提问回 503，日志写明「ARI_OPENAI_KEY_FILE 指的文件不存在」，库里没有多出行 |

**没验的**：真机 GPS。无头浏览器里的定位是模拟出来的，走的是浏览器真实的 `watchPosition`，
但手机在院子里的实际精度、国内浏览器给的坐标系，只有到现场才知道。

## 待办

- **游客互动的接口入口没开**：只差 `/etc/ari/openai_key`。到位后先用真模型试答，再开 Nginx 入口，见上文「部署状态」。
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
