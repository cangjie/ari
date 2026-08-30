# 服务器端基础环境部署记录

## 部署结果

- 部署时间：2026-08-21 10:14 CST（服务器 2026-08-21 02:14 UTC）
- 目标：`ubuntu@44.207.251.65`
- 主机名：`ip-172-31-30-54`
- 系统：Ubuntu 26.04，ARM64（aarch64）
- 结果：MySQL、Nginx、FastAPI/Uvicorn 与三个 systemd 服务均通过内部和外部验收
- 密码：已按用户指定值设置，但不记录在本文件、仓库或服务器配置中

## 安装过程

### 1. 系统包

执行：

```bash
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  mysql-server nginx python3-pip python3-venv
```

APT 首次刷新下载约 33.5 MB 索引；安装下载约 36.6 MB，新增 17 个包并升级 6 个 Python 3.14 组件，占用约 196 MB。没有执行整机升级，安装结束时另有 107 个不属于本任务的可升级包。

最终直接依赖版本：

```text
mysql-server  8.4.10-0ubuntu0.26.04.1
nginx         1.28.3-2ubuntu1.10
python3-pip   25.1.1+dfsg-1ubuntu2
python3-venv  3.14.3-0ubuntu2
Python        3.14.4
```

初次盘点时 MySQL 候选为 8.4.9；刷新 APT 后官方安全更新候选变为 8.4.10，因此部署并记录 8.4.10。

安装中公网 SSH 新握手曾两次在到达 sshd 之前超时；22 端口、主机负载与 sshd 日志均未显示服务器故障或主动拒绝。建立带 keepalive 的 SSH 控制连接并复用同一加密通道后，后续操作稳定完成；没有因此修改服务器 SSH 配置。

### 2. MySQL

安装后新增独立覆盖文件 `/etc/mysql/mysql.conf.d/zz-ari.cnf`：

```ini
[mysqld]
bind-address = 0.0.0.0
mysqlx-bind-address = 127.0.0.1
```

文件名最初为 `ari.cnf`。验证发现 Ubuntu 的 `mysqld.cnf` 按字典序在其后加载，把 3306 重新覆盖为 `127.0.0.1`；`my_print_defaults mysqld` 的最后有效值证实了原因。将文件改为后加载的 `zz-ari.cnf` 后，最后有效值变为 `0.0.0.0`，随后通过 `mysqld --validate-config` 并重启。

账户配置通过 MySQL 客户端标准输入完成：

- `root@localhost`：`caching_sha2_password`
- `root@%`：`caching_sha2_password`
- `root@%`：`ALL PRIVILEGES ON *.*`，包含 `GRANT OPTION`
- 两个账户使用用户指定的同一密码
- `root@%` 未设置 `REQUIRE SSL`

密码未出现在 shell 命令参数、MySQL 选项文件或仓库文件中。

### 3. Python 与 FastAPI

创建专用系统账户与目录：

```text
user: ari
shell: /usr/sbin/nologin
home: /opt/ari
virtualenv: /opt/ari/.venv
smoke app: /opt/ari/smoke/app.py
test: /opt/ari/smoke/test_app.py
lock: /opt/ari/smoke/requirements.lock
```

安装命令：

```bash
python3 -m venv /opt/ari/.venv
/opt/ari/.venv/bin/python -m pip install --upgrade pip
/opt/ari/.venv/bin/python -m pip install "fastapi[standard]" pytest httpx2
```

健康检查使用测试先行：

1. 测试先因 `app` 模块不存在而无法收集。
2. 创建仅含 FastAPI 对象、没有路由的最小应用后，测试以 `404 != 200` 失败。
3. 添加 `GET /health` 后测试通过。
4. Starlette 1.6 在缺少 `httpx2` 时发出弃用警告；按其提示安装 `httpx2` 后，以 `-W error` 重跑得到 `1 passed`、零警告。

健康检查实现：

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

完整 Python 锁定版本：

```text
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.14.2
certifi==2026.7.22
click==8.4.2
detect-installer==0.1.0
dnspython==2.8.0
email-validator==2.3.0
fastapi==0.141.1
fastapi-cli==0.0.32
fastapi-cloud-cli==0.23.0
fastar==0.12.0
h11==0.16.0
httpcore==1.0.9
httpcore2==2.12.0
httptools==0.8.0
httpx==0.28.1
httpx2==2.12.0
idna==3.19
iniconfig==2.3.0
Jinja2==3.1.6
markdown-it-py==4.2.0
MarkupSafe==3.0.3
mdurl==0.1.2
packaging==26.3
pip==26.2.1
pluggy==1.6.0
pydantic==2.13.4
pydantic-extra-types==2.11.1
pydantic-settings==2.15.0
pydantic_core==2.46.4
Pygments==2.21.0
pytest==9.1.1
python-dotenv==1.2.3
python-multipart==0.0.32
PyYAML==6.0.3
rich==15.0.0
rich-toolkit==0.20.3
rignore==0.8.1
sentry-sdk==2.68.0
shellingham==1.5.4
starlette==1.6.0
truststore==0.10.4
typer==0.27.1
typing-inspection==0.4.4
typing_extensions==4.16.0
urllib3==2.7.0
uvicorn==0.52.4
uvloop==0.22.1
watchfiles==1.2.0
websockets==17.0.1
```

### 4. systemd

`/etc/systemd/system/ari-smoke.service`：

```ini
[Unit]
Description=ari FastAPI environment smoke test
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ari
Group=ari
WorkingDirectory=/opt/ari/smoke
ExecStart=/opt/ari/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`systemd-analyze verify` 未发现本单元错误；它同时报告 Ubuntu 自带的两个 XFS 单元仍包含已移除的 `CPUAccounting` 选项，该警告与 ari 服务无关。

首次启动检查出现约 1 秒的就绪竞态：systemd 已标记 active，Uvicorn 尚未绑定端口。日志显示应用随后正常启动，最终验收改为轮询实际健康端点。

### 5. Nginx

`/etc/nginx/sites-available/ari-smoke`：

```nginx
server {
    listen 8000 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用链接为：

```text
/etc/nginx/sites-enabled/ari-smoke
  -> /etc/nginx/sites-available/ari-smoke
```

安装包默认站点文件仍保留在 `sites-available`，仅移除了 `sites-enabled/default` 链接，因此 80 端口保持空闲。`nginx -t` 验证成功。

## 最终监听端口

| 地址 | 进程 | 用途 |
|---|---|---|
| `0.0.0.0:22`、`[::]:22` | sshd | SSH |
| `0.0.0.0:3306` | mysqld | 公网 MySQL 经典协议 |
| `127.0.0.1:33060` | mysqld | 仅本机 MySQL X Protocol |
| `127.0.0.1:8001` | uvicorn | 仅本机 FastAPI 上游 |
| `0.0.0.0:8000` | nginx | 公网环境验证入口 |

80 端口没有监听。

## 验收证据

| 检查 | 结果 |
|---|---|
| `mysql` systemd | active / enabled |
| `nginx` systemd | active / enabled |
| `ari-smoke` systemd | active / enabled |
| MySQL 版本 | `8.4.10-0ubuntu0.26.04.1` |
| Nginx 版本 | `1.28.3` |
| Python 版本 | `3.14.4` |
| FastAPI / Uvicorn | `0.141.1` / `0.52.4` |
| 测试 | `1 passed`，warning-as-error 模式 |
| 服务器本机经 Nginx 访问 | `{"status":"ok"}` |
| 外部访问 `http://44.207.251.65:8000/health` | HTTP 200，`{"status":"ok"}` |
| 外部 TCP 连接 `44.207.251.65:3306` | 成功 |
| 外部 MySQL root 认证 | 成功，`CURRENT_USER() = root@%` |

AWS 安全组的 8000 与 3306 规则在部署时均已通过真实外部连接验证，没有遗留的外部依赖。

## 运维与回滚

- 查看服务：`systemctl status mysql nginx ari-smoke`
- 查看应用日志：`journalctl -u ari-smoke`
- 验证 Nginx：`nginx -t`
- 验证 MySQL 配置：`mysqld --validate-config`
- 停用环境验证：禁用 `ari-smoke.service` 与 Nginx 的 `ari-smoke` 启用链接
- 恢复 MySQL 本机监听：移除 `/etc/mysql/mysql.conf.d/zz-ari.cnf` 后验证配置并重启 MySQL
- 恢复 Nginx 默认站点：重新建立 `/etc/nginx/sites-enabled/default` 指向 `/etc/nginx/sites-available/default` 的链接

公网 root 权限及未强制 TLS 是用户明确选择；后续正式业务上线时，应重新评估数据库账户、来源 CIDR 与 TLS 策略。
