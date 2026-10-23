# 导览站部署记录

Ari Travel 手机导览站，部署在 `tour.snowmeet.top`。本文记录它是怎么来的、线上实况与待办；
本地怎么跑、调试参数见 `web_api/README.md`。

首次部署：2026-10-10，由 claude 执行。2026-10-15接入宛平城及周边（`wanping`），与伪满皇宫博物院（`wmhg`）共用服务器景区清单。

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
**2026-10-12 已上线。** 服务器上的配置见本节的「部署实况」。

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
| 回答依据 | 就是页面那份 `data/<馆>.json`（全馆各站的名称、评级、建议停留时间、现状、介绍、在展藏品、出处，以及五条参观路线），不另外读库 |
| 提示词 | 只写行为规则：历史与人物可以用一般知识答，但不许挂在馆方名下；现场实况（展厅位置、票价、今天是否开放、设施）资料没写就说不知道；带「待复核」的不当事实讲；不超过 300 字 |
| 型号 | 环境变量 `ARI_QA_MODEL`，不写死；缺了接口回 503，不猜。线上是 `gpt-5.4-mini`，实际型号记在每一行的 `model` 列 |
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

### 部署实况（2026-10-12 上线）

| | |
|---|---|
| 库表 | `tour_topic`、`tour_qa_setting`（`ari` 库现为 16 张表），三行上限初值 20 / 120 / 1000 |
| 依赖 | `/opt/ari/.venv` 新装 `openai 3.6.0`、`PyMySQL 1.2.0`（连带 `jiter 0.17.0`、`sniffio 1.3.1`），原有的包没有变动 |
| 服务配置 | `/etc/ari/web-api.env` 与 systemd drop-in `/etc/systemd/system/ari-web-api.service.d/tour-qa.conf`（`EnvironmentFile=`） |
| 数据库账号 | `ari_web@localhost`，配置在 `/etc/ari/web-api.my.cnf`，走本机套接字。由 `web_api/sql/create_ari_web.sh` 生成 |
| OpenAI key | `/etc/ari/openai_key`，只有一行。用户 2026-10-12 提供 |
| Nginx | 站点 `ari-tour` 加了 `location ^~ /api/`，见下文「Nginx」。改之前的备份是同目录的 `ari-tour.bak-20261012` |

`/etc/ari/` 是 `750 root:ari`，里面三个文件都是 `640 root:ari`。`web-api.env` 不含密钥：

```
ARI_QA_MODEL=gpt-5.4-mini
ARI_DB_DEFAULTS_FILE=/etc/ari/web-api.my.cnf
ARI_OPENAI_KEY_FILE=/etc/ari/openai_key
```

- **换 key**：把新 key 写进 `/etc/ari/openai_key`（只留一行），然后 `sudo systemctl restart ari-web-api`。
  写的时候用 `sudo sh -c 'cat > /etc/ari/openai_key.new && chown root:ari … && chmod 640 … && mv …'` 这种读标准输入的写法；
  `sudo install … /dev/stdin …` 在 SSH 管道下不稳（2026-10-12 第二次用时报 `No such file or directory`，文件没换成，
  接下来的试答用的还是旧 key —— **换完要比对内容或看修改时间，再下结论**）。
- **换型号**：改 `web-api.env` 里的 `ARI_QA_MODEL`，重启服务。每一行问答都记着当时用的型号。
- **换数据库口令**：重跑 `create_ari_web.sh`（会问一次 MySQL root 口令，输入不回显；交互这一支没有实跑过，
  上线那次是把 root 的客户端配置从标准输入给它的），然后重启服务：

  ```sh
  ssh -t ubuntu@44.207.251.65 'sh /home/ubuntu/ari/web_api/sql/create_ari_web.sh'
  ```

  `ari_web` 对 `ari.tour_topic` 有 SELECT / INSERT / UPDATE，对 `ari.tour_qa_setting` 只有 SELECT，别的表碰不到。
- 改了 `web_api/app/` 要 `sudo systemctl restart ari-web-api`；只改页面和数据仍然只需 `git pull`。

### 型号是怎么定的：`gpt-5.4-mini`

原定照 MingnaCurator 用 `gpt-5.4-nano`。2026-10-12 用真模型试答了 71 次（nano 42 次、mini 29 次），nano 跟不住三条细则，改用 mini。
对比用的是同一份提示词、同一批 17 个问题（多数是改完提示词之后才写的，没用来调过）：

| | `gpt-5.4-nano` | `gpt-5.4-mini` |
|---|---|---|
| 把关（与预期一致的条数） | 13 / 17：「让它改规则」的输入 5 条漏了 4 条 | 17 / 17 |
| 历史与人物（资料没写的） | 4 条里 3 条只答「资料未说明」 | 都用一般知识作答，并说明不是馆方资料 |
| 现场实况（票价、厕所、今天开不开） | 都老实说不知道 | 同左 |
| 模型自身耗时 | 0.9–2.5 秒 | 0.6–1.5 秒 |
| 每问 token | 输入约 6,400（其中约 5,900 命中缓存），输出 30–150 | 同左 |

两个型号都把英文提问答成了中文，这一条改由代码补一句提示来保证（`build_user`）。本项目不折算金额，只记 token。

**一般历史知识会出错，这是放开它的代价。** mini 答「婉容后来怎么样了」，一次答的是「被带走，1946 年去世」，
另一次多出一句「被苏方拘押」—— 后一句不对。页面上每条回答都标着「AI 生成」，提问框上方写着「可能有误」。
要更稳有两条路：把规则 2 甲改回「资料没写就说不知道」（稳，但常常答不上），或换更大的型号（贵）。

### 已知的限制

- **真机上软键盘弹出时输入框会不会被挡住，没验过。** 无头浏览器模拟不了软键盘；页面做了三处防护
  （输入框挪到抽屉靠上的位置、外层 `overflow: clip`、键盘收起后把页面拨回原位），实际效果要到手机上看。
- 模型把关会误判。漏掉的不当内容靠上面的下架语句处理。
- 换手机或清了浏览器数据，「我的提问」就认不出来了，没公开的那些也看不到了。
- 没做：语音提问、回答朗读、跨地点的「我的互动」汇总页、管理端与策展人答复、流式输出、英文界面。

## 服务器部署实况

- 域名 `tour.snowmeet.top`，A 记录指向 `44.207.251.65`
- 站点根目录就是仓库里的 `web_api/tour`：`/home/ubuntu/ari/web_api/tour`，Nginx（`www-data`）可读
- 页面**不经过 FastAPI**，由 Nginx 直接出静态；只有 `/api/`（游客互动）反代到 `ari-web-api`（`127.0.0.1:8002`）
- 更新 = `cd /home/ubuntu/ari && git pull --ff-only`。只改页面和数据不用重启任何服务；改了 `web_api/app/` 要 `sudo systemctl restart ari-web-api`

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

    # 游客互动的接口，转给 ari-web-api（web_api/app/tour_qa.py）。缓存头由应用自己发（no-store），这里不重复加。
    # ^~：这个前缀下不再去匹配后面按扩展名的那条规则
    location ^~ /api/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout   90s;
        client_max_body_size 8k;
    }

    # Android APK download, published independently of the web application.
    location = /android/app {
        alias /home/ubuntu/ari-downloads/android/app.apk;
        default_type application/vnd.android.package-archive;
        add_header Content-Disposition 'attachment; filename="ari-travel-0.1.0.apk"';
        add_header Cache-Control "no-store";
    }

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

同一台机器上的其它站点（`ari-web-api`、`ari-smoke`、`reqai`）没有改动；2026-10-12 加 `/api/` 入口时也只动了 `ari-tour` 这一个文件。

### Android APK 下载（2026-10-15）

用户指定的下载入口：[下载 Android APK](https://tour.snowmeet.top/android/app)。该地址直接返回安装包，
由 `ari-tour` 的精确 `location = /android/app` 提供；文件放在仓库外的
`/home/ubuntu/ari-downloads/android/app.apk`，APK 不提交 Git，网页 `git pull` 不更新这个文件。

当日首次发布本机已有的 `android/app/build/outputs/apk/debug/app-debug.apk`（以下为历史记录）：

- 应用 `Ari Travel`，包名 `top.snowmeet.tour`，版本 `0.1.0` / versionCode `1`，Debug 签名，minSdk `26`、targetSdk `35`。
- 大小 `8279219` 字节，SHA-256 `1efdb270c7c17e06e428b4fe886ffee4e8d66d6d6a4e7d705a9849de2db21b81`。
- 本次没有重新构建。包内景区数据只有 `wmhg.json`，不含工作区尚在修改的宛平城资料与较新的网页改动。
- `apksigner verify` 通过（v2 签名）；公网完整下载返回 HTTP 200、上述字节数与 SHA-256 一致。
  响应为 `application/vnd.android.package-archive`，下载文件名 `ari-travel-0.1.0.apk`，`Cache-Control: no-store`。
- Nginx 配置备份 `/etc/nginx/sites-available/ari-tour.bak-apk-20261015T081441Z`；`nginx -t` 通过后 reload，首页复查 HTTP 200。
  下载与签名检查不代表安装或真机功能验收。

后续更新：先检查新包的版本、签名和内置资料，上传到临时文件并核对 SHA-256，再以 `644` 权限写入同目录的
`app.apk.new`，原子替换 `app.apk`，最后从公网完整下载校验；只替换 APK 不需要 reload 或重启服务。
版本名改变时同步修改上方 `Content-Disposition` 的文件名，经 `nginx -t` 检查后 reload。
保留相同签名才能覆盖安装，已安装更高 versionCode 的设备需要另行处理版本号。

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

2026-10-12，游客互动：

| 检查项 | 结果 |
|---|---|
| 本地 pytest | 64 条全绿：原有 18 条 + `/tour/` 挂载 1 条 + 问答接口 45 条（假库、假模型，不联网） |
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
| 真模型试答（在服务器上，以服务的身份与配置） | 71 次：见上文「型号是怎么定的」。前两把 key（本机 `~/.openai_key`、reqai 项目那把）都因账户余额为 0 被拒，第三把调通 |
| 服务账号 `ari_web` 的权限（以系统用户 `ari` 用服务的配置文件连库实测） | 能读上限表与问答表；改上限表、删问答、读 `artwork`、建表都被拒（1142） |
| 线上列表接口 | `https://tour.snowmeet.top/api/tour/wmhg/places/tongde/topics` 200，`Cache-Control: no-store`；未知地点 404 |
| 线上真问一条 | 「同德殿是哪年建成的？当年是做什么用的？」3.1 秒拿到回答（从本机算，含往返美国）；换一个设备号能在列表里看到，`mine` 为假 |
| 库里那一行 | `model = gpt-5.4-mini`，输入 6376 token（缓存命中 5888）、输出 54、模型耗时 1451 毫秒，`is_public = 1` |
| **改上限立即生效** | 把 `per_visitor_per_day` 改成 1，没有重启，同一设备的下一条提问回 429「达到上限」；改回 20 后重问第一条回 200（直接给已有回答，库里没有多出行） |
| 线上页面，无头 Chrome（`BASE=https://tour.snowmeet.top`） | 46 项全过：原有 44 项 + 互动一块显示且列表能载入（线上不发帖）+ 控制台无报错 |
| 收尾 | 验收用的那一行已删，上限表是初值 20 / 120 / 1000；`ai.snowmeet.top` 仍回 200；服务日志自重启后无告警 |

**没验的**：真机 GPS。无头浏览器里的定位是模拟出来的，走的是浏览器真实的 `watchPosition`，
但手机在院子里的实际精度、国内浏览器给的坐标系，只有到现场才知道。

## 待办

- **游客互动：一般历史知识会出错**（见「型号是怎么定的」末尾的例子）。是维持现状、收紧到只答资料里有的、还是换更大的型号，待定。
- **游客互动：真机上软键盘弹出时输入框会不会被挡住**，没验过。
- **OpenAI 账户余额**：前两把 key 都是余额为 0。现在这把一旦用完，每个提问都会回「导览助手暂时没有答上来」；到时把 `site_per_day` 设成 0 可以先把提问关掉。
- **线上的 OpenAI key 与 MySQL root 口令在 2026-10-12 的会话里出现过明文**，建议各换一次（换法见「部署实况」）。
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

## 宛平城与动态景区清单（2026-10-15）

`web_api/tour/catalog.json` 的 `museums` 数组决定Web与App共同的上架清单及顺序，当前为 `wmhg`、`wanping`。编辑清单及 `data/<key>.json` 后通过Git部署，App回到前台会重新打开线上首页，不需更换安装包。新增景区生成时首次追加；重生成保留清单中的排序和下架选择。

App本次从内置网页改为直接打开 `https://tour.snowmeet.top/index.html`，需要安装新包一次。网页将成功加载的同一份资料交给原生定位、通知和悬浮导览；原生只缓存最后有效快照，删除、清空与顺序变化一起同步。APK不再包含导览网页或景区数据。

新包为0.1.0 / versionCode1，大小8312316字节，SHA-256 `0a91add6947d004153f44c618c4f7f4513e76a50df11d3e768ddd4095d3ba201`，沿用旧包Debug签名。下载入口仍为 `/android/app`，更新时保留旧包备份，核对暂存包哈希后原子替换；未做真机安装验收。

宛平城39条资料由已审计本地包生成，无需重灌现有业务库。7个有坐标依据的到达点承接整体、分展区与实物资料。免费线约3小时45分，排除收费桥面和城墙顶部；全面线约5小时10分，包含卢沟桥及登城，官方旧文成人参考票价合计50元，现场售票为准。来源、开放限制、路线依据、审计处理与验收见 `docs/WANPING_DATA.md`。游客互动提示词同时读入费用、预约和整体停留说明，因此部署时需要重启 `ari-web-api`。

### 宛平城图片（2026-10-16）

已收录12张可对应到具体条目的官方资料图，放在 `web_api/tour/img/wanping/`。包括宛平城和顺治门、城墙与弹痕、县衙外观、卢沟桥与石狮及卢沟晓月碑、抗战馆外观、雕塑园和纪念碑、卢沟桥历史博物馆外观。地点封面与条目照片分别显示，介绍页列出图片出处；馆外观没有借给室内新展。

发布JPEG合计1457885字节，完整原件和来源HTML在本机忽略导出目录留存。用户指定的2222映射服务器仅用于纯管道下载，未写图片、脚本或临时文件。来源、完整性检查、固定模型文本复核和处理记录见 `docs/WANPING_DATA.md` 及 `utils/import_data/wanping_photo_publish_report.json`。

本轮仅部署静态网页、JSON及图片，未重启服务、重打APK或改业务资料。App重新回到前台即可从同一Web读取照片。

### 南锣鼓巷及什刹海清单（2026-10-23）

新增100条已审资料：84条文化参观点、16家特色商铺，S8/A32/B35/C25。郭沫若故居（郭沫若纪念馆）为第48条A级；第76条锡晋斋保留《平复帖》原件现藏故宫的复核提示。来源包、既定评分及审计直接生成`data/nanluo_shichahai.json`，不导入或重灌业务资料表。

该资料包没有核实过的地图坐标和路线，使用共用页面的`mode=collection`清单模式，支持搜索、类别/区域/评级筛选和详情。门店地址、特色、平台快照与实时状态边界分别列示；没有停留数据不显示0分钟，也不把前后翻阅当作步行导航。生成及比对使用`tour_build.py --museum nanluo_shichahai [--check]`，详见`docs/NANLUO_SHICHAHAI_DATA.md`。

App继续打开线上Web，原APK不变；首页显示完整服务器清单，原生定位缓存只同步有几何依据的目的地。进入纯清单会退出当前原生景区，不给100条资料编造热区。浏览器桥接模拟可以针对本地及公开页面运行，未做Android真机验收。

游客互动同样读取这份JSON；新清单的Core分数、地址、特色及平台提示都进入回答材料。Core分数和资料说明文案按显式模式区分，原有两馆的问答材料已与改动前逐字比对一致。部署需要`git pull --ff-only`后重启`ari-web-api`，不改Nginx或APK。发布复核用原Sonnet 5 medium，实际公开文件哈希与只读GET验收记录在`nanluo_shichahai_release_report.json`。

内容版本`6ac44bd`已推送并部署，服务active；7个公开页面/脚本/资料文件逐字节核对通过，三处景区问答GET正常，公网清单、桥接模拟及旧景区回归通过。首次冷启动超过原验收脚本20秒等待，改为明确等到载入完成、60秒超时即报错后复查通过；历史失败保留。85项pytest通过、3项真库写入测试未启用。Android真机未测，APK未替换。


### 南锣鼓巷及什刹海地图/照片补充（2026-10-23）

完整100条清单新增37处OSM来源参考位置与10张独立资料图；清单和景点地图可切换，详情可以聚焦地图。`collection`中的`map_mode=browse`只用于位置浏览，不送原生定位缓存、不启动GPS或自动到站。未知位置、缺图条目仍可浏览；未生成路线和停留时间。地图、图片均随仓库静态提供，无站外资源请求；App继续打开同一网页，无需更新APK。问答材料同步增加页面可见的位置口径、来源和图注，只提供文字不让模型冒充识图。因同时修改`web_api/app/tour_qa_llm.py`，部署后重启`ari-web-api`；不改Nginx。数据口径、来源与验收见`docs/NANLUO_SHICHAHAI_DATA.md`及`nanluo_shichahai_media_release_report.json`。
