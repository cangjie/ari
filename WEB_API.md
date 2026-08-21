# web_api 部署记录

ari 的服务端 Web 应用，部署在 `ari.goldenma.xyz`。本文记录实际部署结果与验收证据；
应用本身的开发说明见 `web_api/README.md`。

首次部署：2026-08-21，由 claude 执行。

## 应用

`web_api/` 是完整的 FastAPI 应用，静态页面与接口由同一个进程提供。

| 路径 | 内容 |
|---|---|
| `/` | `web_api/static/index.html` |
| `/<name>.html` | `static/` 下的对应文件，缺失返回 404 |
| `/health` | `{"status":"ok"}`，供 systemd、Nginx 与外部探活 |

`StaticFiles` 挂在 `/` 上并开启 `html=True`，会吞掉所有未匹配路径，
因此它必须是 `app/main.py` 的最后一行。**新增接口一律走 `/api/` 前缀**
并写在静态挂载之前，否则会被静态目录吃掉。

静态目录用 `Path(__file__)` 解析，不依赖进程工作目录，
保证 systemd、pytest、本地 uvicorn 三种启动方式指向同一处。

## 为什么必须是 HTTPS

首个静态页 `static/index.html` 是 GPS 定位测试页，使用浏览器 Geolocation API。
**该 API 只在安全上下文中可用**——HTTPS，或 `localhost`。
手机访问纯 HTTP 的裸 IP 时权限弹窗根本不会出现，表现为「按钮按了没反应」。

页面因此显式检测 `window.isSecureContext`，不满足时直接提示并禁用按钮，
而不是让用户面对一个静默失败的界面。这也是本项目公网入口必须上 HTTPS 的原因。

## 服务器部署实况

### 代码

- 仓库 clone 在 `/home/ubuntu/ari`，属主 `ubuntu`（持有 GitHub Deploy key）
- 服务以 `ari` 用户运行，对代码目录**只读**——服务用户改不了自己的代码
- 为让 `ari` 能穿过家目录，`/home/ubuntu` 权限从 `750` 放宽为 `755`（用户明确选择此方案，
  另两个备选是 ACL 与「服务改用 ubuntu 跑」）
- 部署 = `cd /home/ubuntu/ari && git pull --ff-only` + `sudo systemctl restart ari-web-api`

### Python 依赖

复用既有的 `/opt/ari/.venv`（Python 3.14）。当前只有一个 Python 子项目，
不额外建虚拟环境；出现第二个子项目时再拆。版本锁在 `web_api/requirements.txt`，
与服务器实际安装一致：FastAPI 0.141.1、Uvicorn 0.52.4。

### systemd

`/etc/systemd/system/ari-web-api.service`：

- `User=ari`，`WorkingDirectory=/home/ubuntu/ari/web_api`
- `Environment=PYTHONPATH=/home/ubuntu/ari/web_api`
- `ExecStart=/opt/ari/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002`
- `Restart=on-failure`，已 `enable` 开机启动
- **不能启用 `ProtectHome`**——代码在 `/home/ubuntu` 下，启用后服务读不到自己的代码

### Nginx

`/etc/nginx/sites-available/ari-web-api`，已在 `sites-enabled` 建链接：

- `80` → `301` 跳转到 `https://ari.goldenma.xyz`
- `443` 加载证书，`http2 on`，反代到 `127.0.0.1:8002`
- `ssl_protocols TLSv1.2 TLSv1.3`
- 转发 `Host`、真实客户端地址及代理链请求头

8000 端口上的 `ari-smoke` 原样保留，作为环境自检对照，本次未改动。

### 证书

- 域名 `ari.goldenma.xyz`，A 记录指向 `44.207.251.65`
- 签发机构：TrustAsia LiteSSL RSA CA 2025，RSA 2048
- 证书链（3 张，叶子在前）：`/etc/ssl/ari/ari.goldenma.xyz.crt`，`644 root:root`
- 私钥：`/etc/ssl/ari/ari.goldenma.xyz.key`，`600 root:root`，目录 `700`
- **有效期至 2026-11-19**

证书由用户手动申请，**没有自动续期**。到期前需重新下载并替换，
或改用 Let's Encrypt + certbot 做成自动续期。安装时用管道直接写入并原子设权限，
不在 `/tmp` 留副本。

## 验收记录

2026-08-21 全部通过：

| 检查项 | 结果 |
|---|---|
| 本地 pytest | 4 条全绿 |
| DNS 解析 | `ari.goldenma.xyz` → `44.207.251.65` |
| 证书与私钥配对 | 公钥 md5 一致，本地与服务器各验一次 |
| 证书链校验 | `openssl verify` → OK |
| `nginx -t` | 通过 |
| `systemd-analyze verify` | 通过 |
| `ari-web-api` | `active` + `enabled` |
| 服务器本机 `127.0.0.1:8002` | `/health` 200、`/` 200 |
| 外部 HTTPS | `/` 200（HTTP/2）、`/health` 200 |
| 外部 HTTP 80 | `301` → `https://ari.goldenma.xyz/` |
| 客户端 TLS 校验 | `Verify return code: 0 (ok)` |
| 返回内容 | `<title>ari · GPS 定位测试</title>`，含定位按钮 |

AWS 安全组已放行 `80` 与 `443`。

## 待办

- 证书 2026-11-19 到期，无自动续期。建议换 Let's Encrypt + certbot。
- `ari-smoke` 在 8000 上仍在跑。web_api 稳定后可以退役它。
