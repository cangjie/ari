# 服务器端基础环境设计

## 目标

在 AWS 主机 `44.207.251.65` 上建立 ari 的服务器端基础运行环境：MySQL、Python FastAPI、Uvicorn、systemd 与 Nginx。当前阶段只验证运行链路，不确定业务目录结构，不引入正式业务代码。

## 主机基线

- 操作系统：Ubuntu 26.04，ARM64（aarch64）
- 系统 Python：3.14
- 资源：约 2 GB 内存、61 GB 根磁盘
- 登录用户：`ubuntu`，可免密使用 `sudo`
- 当前状态：仅 SSH 端口监听；MySQL、Nginx、pip、FastAPI 与 Uvicorn 均未安装

## 部署结构

采用 Ubuntu 原生服务与 Python 虚拟环境，不使用 Docker，也不向系统 Python 全局安装应用依赖。

### MySQL

- 使用 Ubuntu 官方仓库提供的 MySQL 8.4.10。
- 通过独立配置文件 `/etc/mysql/mysql.conf.d/ari.cnf` 设置 `bind-address = 0.0.0.0`，让经典协议监听公网 IPv4 的 `3306` 端口。
- 保持 MySQL X Protocol 不向公网开放。
- `root@localhost` 与 `root@%` 使用用户指定的同一密码。
- `root@%` 具有完整管理权限及授权权限，使用 MySQL 8.4 默认的 `caching_sha2_password` 认证插件。
- 不为 `root@%` 额外设置 `REQUIRE SSL`；客户端仍可使用 MySQL 默认提供的 TLS 能力。
- 密码只通过 MySQL 标准输入设置，不放入命令行参数、服务器配置文件或本仓库。
- 公网访问边界由 AWS 安全组控制。

### Python 与 FastAPI

- 创建不可交互登录的系统用户 `ari`，工作目录为 `/opt/ari`。
- 在 `/opt/ari/.venv` 创建 Python 3.14 虚拟环境；依赖仅安装到该环境。
- 安装与 Python 3.14 兼容的当前稳定版 FastAPI 和 Uvicorn，并将最终解析版本写入 `/opt/ari/smoke/requirements.lock`。
- 在 `/opt/ari/smoke/app.py` 放置临时健康检查应用，仅提供 `GET /health`，响应为 `{"status":"ok"}`。
- 临时健康检查不是正式服务端目录设计；后续业务项目建立后应由正式应用替换。

### systemd

- 创建 `/etc/systemd/system/ari-smoke.service`。
- 服务以 `ari` 用户运行，工作目录为 `/opt/ari/smoke`。
- Uvicorn 监听 `127.0.0.1:8001`，不直接暴露到公网。
- 服务异常退出后自动重启，并随系统启动。

### Nginx

- 使用 Ubuntu 官方仓库提供的 Nginx。
- 禁用安装包自带的默认站点，确保公网 `80` 端口保持空闲。
- 创建 `/etc/nginx/sites-available/ari-smoke`，并启用对应链接。
- Nginx 监听 `0.0.0.0:8000`，将请求反向代理到 `127.0.0.1:8001`。
- 转发 `Host`、真实客户端地址及代理链请求头。

## 数据流

环境验证请求按以下路径流动：

`公网客户端 -> 44.207.251.65:8000 (Nginx) -> 127.0.0.1:8001 (Uvicorn) -> FastAPI /health`

数据库连接路径为：

`获 AWS 安全组放行的客户端 -> 44.207.251.65:3306 -> MySQL root@%`

## 失败处理与回滚

- 安装前刷新 APT 元数据；任一包安装失败即停止，不继续写服务配置。
- 写入配置前保留被替换文件的副本；优先新增独立配置文件，避免修改发行版原文件。
- 每次重启服务前先运行语法检查：Nginx 使用 `nginx -t`，systemd 使用 `systemd-analyze verify`。
- 若 MySQL 公网配置导致启动失败，移除 `ari.cnf` 后恢复原监听设置并重新启动。
- 若健康检查服务失败，保留 MySQL 与 Nginx 安装，只停用 `ari-smoke.service` 和对应 Nginx 站点以便诊断。

## 验收标准

以下检查必须全部通过：

1. `mysql`、`nginx`、`ari-smoke` 均处于 `active` 且已设为开机启动。
2. MySQL 版本为 Ubuntu 仓库的 8.4.10，监听 `0.0.0.0:3306`。
3. `root@localhost` 与 `root@%` 均存在，使用 `caching_sha2_password`，且指定密码可认证。
4. Uvicorn 仅监听 `127.0.0.1:8001`。
5. Nginx 监听 `0.0.0.0:8000`，不占用 `80` 端口。
6. 服务器本机及外部客户端访问 `http://44.207.251.65:8000/health` 均返回 HTTP 200 和 `{"status":"ok"}`。
7. 外部可建立到 `44.207.251.65:3306` 的 TCP 连接；AWS 安全组未放行时，明确记录为外部依赖而不是服务器配置失败。

## 参考

- [Ubuntu：安装和配置 MySQL](https://ubuntu.com/server/docs/install-and-configure-a-mysql-server)
- [MySQL 8.4：Caching SHA-2 认证](https://dev.mysql.com/doc/refman/8.4/en/caching-sha2-pluggable-authentication.html)
- [Python 3.14：venv](https://docs.python.org/3.14/library/venv.html)
- [Nginx：HTTP 代理模块](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
