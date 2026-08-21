# web_api

ari 的服务端 Web 应用。FastAPI + Uvicorn，静态页面与接口都由这一个应用提供。

## 目录

```
web_api/
├── app/main.py        应用入口。接口路由在前，静态挂载在最后一行
├── static/            静态页面根目录，直接映射到站点根路径
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

本地是 Python 3.12，服务器是 3.14；当前依赖在两个版本上行为一致。
`.venv/` 已被 `.gitignore` 忽略，不进仓库。

## 静态页面与 HTTPS

`static/index.html` 是 GPS 定位测试页，使用浏览器的 Geolocation API。

**该 API 只在安全上下文中可用**——HTTPS，或 `localhost`。因此：

- 本机 <http://127.0.0.1:8099/> 能正常定位（localhost 视为安全上下文）
- 手机访问 `http://<裸 IP>/` **拿不到定位**，浏览器不会弹权限窗

页面会检测 `window.isSecureContext`，在不满足时直接显示提示并禁用按钮，
而不是让用户面对一个按了没反应的按钮。

## 部署

见仓库根目录 `WEB_API.md`。
