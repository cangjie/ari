# web_api

ari 的服务端 Web 应用。FastAPI + Uvicorn，静态页面与接口都由这一个应用提供。

## 目录

```
web_api/
├── app/main.py        应用入口。接口路由在前，静态挂载在最后一行
├── app/tour_qa*.py    导览站的游客互动（AI 问答）：接口、提示词与调模型、存库
├── sql/tour_qa.sql    游客互动的两张表
├── static/            静态页面根目录，直接映射到站点根路径
├── prototype/         在线原型，挂在 /prototype/
├── tour/              手机导览站，独立站点 tour.snowmeet.top，页面由 Nginx 直接出静态（见下）
├── tests/             pytest 验收测试
├── requirements.txt   运行依赖，版本与服务器 /opt/ari/.venv 对齐
└── requirements-dev.txt  额外的测试依赖
```

## 路由约定

`StaticFiles` 挂在 `/` 上并开启 `html=True`，会吞掉所有未匹配的路径，
因此它必须是 `app/main.py` 的最后一行。**新增接口一律走 `/api/` 前缀**，
并写在静态挂载之前，否则会被静态目录吃掉。

| 路径 | 内容 |
|---|---|
| `/` | `static/index.html` |
| `/<name>.html` | `static/` 下的对应文件，缺失返回 404 |
| `/health` | `{"status":"ok"}`，供 systemd、Nginx 与外部探活 |
| `/api/tour/{馆}/places/{地点}/topics` | 导览站的游客互动：`GET` 取问答列表，`POST` 提问。线上由 `tour.snowmeet.top` 的 Nginx 把 `/api/` 反代过来 |
| `/tour/` | 导览站页面。**只给本地联调用**，线上页面由 Nginx 直接提供 |

## 本地运行

```sh
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/uvicorn app.main:app --reload --port 8099
```

打开 <http://127.0.0.1:8099/>。

测试：

```sh
./.venv/bin/python -m pytest tests/ -q
```

本地 `.venv` 与服务器都是 Python 3.14。
`.venv/` 已被 `.gitignore` 忽略，不进仓库。

## 静态页面与 HTTPS

`static/index.html` 是 GPS 定位测试页，使用浏览器的 Geolocation API。

**该 API 只在安全上下文中可用**——HTTPS，或 `localhost`。因此：

- 本机 <http://127.0.0.1:8099/> 能正常定位（localhost 视为安全上下文）
- 手机访问 `http://<裸 IP>/` **拿不到定位**，浏览器不会弹权限窗

页面会检测 `window.isSecureContext`，在不满足时直接显示提示并禁用按钮，
而不是让用户面对一个按了没反应的按钮。

## 导览站 `tour/`

`tour/` 是一个手机网站：目的地列表 → 导游地图，走进景点热区时推送讲解。
页面是纯静态的，线上由 Nginx 以 `tour.snowmeet.top` 直接提供这个目录。
唯一要服务端的是介绍抽屉里的「游客互动」（AI 问答），接口在本应用的 `/api/tour/` 下，
见下一节。部署记录见 `docs/TOUR_WEB.md`。

```
tour/
├── index.html  app.css  app.js    页面。原生 JS，无框架；字体、脚本都不引用站外地址
├── fonts/                         Cormorant Garamond、Lora 的拉丁子集（取自原型）
├── data/<馆>.json                 生成文件，勿手改 —— utils/import_data/tour_build.py
└── img/<馆>/<序号>.jpg            官网图片 —— utils/import_data/tour_images.py
```

本地看：

```sh
python3 -m http.server 8098 --bind 127.0.0.1 --directory tour
```

打开 <http://127.0.0.1:8098/>。`localhost` 是安全上下文，浏览器会给定位；
人不在景区时用调试参数（界面上不露出）：

| 参数 | 作用 |
|---|---|
| `?fix=43.90398,125.34323` | 用一个固定的定位代替 GPS（可加第三项：精度，米）。与真实定位走同一段代码 |
| `?sim=1` | 不用 GPS，圆点可拖动，底栏变成「模拟游览」 |
| `?crs=gcj02` | 把定位从国测局坐标换回 WGS-84 再用。国内部分安卓浏览器给的是加过偏的坐标，会偏约 500 米 |
| `?debug=1` | 地图右下角显示原始经纬度、精度与状态 |

参数写在 `#` 前面，例如 `/?fix=43.90398,125.34323#wmhg`。

改了页面之后跑两层验收（`tests/` 下）：

```sh
./.venv/bin/python -m pytest tests/ -q        # 数据自己对不对得上，不连库
node tests/tour_browser_check.mjs             # 无头 Chrome 模拟手机视口与 GPS，把页面真跑一遍
```

后者只要 Node 22 以上与本机 Chrome，没有别的依赖；自己起一个本地静态服务，
`BASE=https://tour.snowmeet.top` 可改成对着线上跑，`SHOTS=<目录>` 另存截图。

数据变了（重新评分、改了路线数据）之后重新生成并提交：

```sh
cd utils/import_data
python3 tour_build.py --museum wmhg          # 读库只读；--check 只比对不写
```

## 游客互动（AI 问答）

游客在介绍抽屉里提问，AI 结合导览页上的资料回答，问答对所有游客公开。
设计、上限怎么改、怎么下架一条问答，都在 `docs/TOUR_WEB.md` 的「游客互动」一节。

```
app/tour_qa.py         接口：校验、三道条数上限、流程
app/tour_qa_llm.py     回答依据的资料（tour/data/<馆>.json）、提示词、调 OpenAI
app/tour_qa_store.py   MySQL 存取：tour_topic（问答）、tour_qa_setting（上限，每次提问现读）
sql/tour_qa.sql        建表语句
```

配置全走环境变量，缺了只有问答回 503，站点其余部分照常：

| 变量 | 作用 |
|---|---|
| `ARI_DB_DEFAULTS_FILE` | MySQL 选项文件（`[client]` 段），口令不进命令行 |
| `ARI_QA_MODEL` | 回答用的型号，不写死 |
| `ARI_QA_EFFORT` | 可选，推理档位；不设就不传 |
| `OPENAI_API_KEY` 或 `ARI_OPENAI_KEY_FILE` | key 本身，或存着 key 的文件 |

本地联调：一个端口同时出页面和接口，打开 <http://127.0.0.1:8099/tour/>。

```sh
ARI_DB_DEFAULTS_FILE=~/.my.cnf ARI_QA_MODEL=gpt-5.4-mini ARI_OPENAI_KEY_FILE=~/.openai_key \
  ./.venv/bin/uvicorn app.main:app --reload --port 8099
```

**⚠ 本机的 `~/.my.cnf` 连的就是线上那个库。** 这样起服务后在页面上提的问题是真的写进 `tour_topic`，
公开的那些线上游客也看得到。只想看页面交互就用下面的浏览器验收，它自带一个假接口。

三层验收：

```sh
./.venv/bin/python -m pytest tests/ -q                 # 接口逻辑，假库假模型，不联网
node tests/tour_browser_check.mjs qa                   # 页面交互，对着脚本自带的假接口
ARI_QA_TEST_DB=1 ARI_DB_DEFAULTS_FILE=~/.my.cnf \
  ./.venv/bin/python -m pytest tests/test_tour_qa_db.py -q   # 真库上的 SQL；改了存取或表结构后跑
```

## 部署

FastAPI 应用见 `docs/WEB_API.md`，导览站见 `docs/TOUR_WEB.md`。
