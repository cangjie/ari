# Server Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install and verify MySQL, Python FastAPI, Uvicorn, systemd, and Nginx on `44.207.251.65`.

**Architecture:** Ubuntu manages MySQL and Nginx as native services. A dedicated `ari` account runs a Python 3.14 virtual environment under `/opt/ari`; systemd keeps a minimal FastAPI health service on loopback port 8001, and Nginx exposes it on public port 8000.

**Tech Stack:** Ubuntu 26.04 ARM64, MySQL 8.4.10, Python 3.14, FastAPI, Uvicorn, pytest, httpx2, systemd, Nginx 1.28.

**Spec:** `SERVER_ENVIRONMENT.md`

## Global Constraints

- Execute remote commands only as `ubuntu@44.207.251.65`; use passwordless `sudo` for privileged operations.
- Do not store the MySQL root password in this repository, shell command arguments, remote option files, or service configuration.
- MySQL classic protocol must listen on `0.0.0.0:3306`; `root@localhost` and `root@%` use `caching_sha2_password`.
- Uvicorn must listen only on `127.0.0.1:8001`.
- Nginx must listen on public port `8000`, proxy to Uvicorn, and leave port `80` unused.
- Do not create a server-side source directory in this repository; `/opt/ari/smoke` is temporary deployment-only validation code.
- Record the executed installation process, final versions, effective configuration, and acceptance evidence in root-level `SERVER_ENVIRONMENT_REPORT.md`; never include the MySQL password.
- Stop immediately if package installation, syntax validation, service startup, or a required acceptance check fails.

---

### Task 1: Install operating-system packages

**Files:**
- Modify remotely: APT package metadata and package database
- Create remotely via packages: MySQL and Nginx distribution files
- Test: package versions and systemd unit availability

**Interfaces:**
- Consumes: SSH access and passwordless `sudo`
- Produces: `mysql`, `mysqld`, `nginx`, `python3`, pip, and venv commands

- [x] **Step 1: Refresh package metadata**

```bash
ssh ubuntu@44.207.251.65 'sudo apt-get update'
```

Expected: exit 0 and package indexes for `resolute`, `resolute-updates`, and `resolute-security`.

- [x] **Step 2: Confirm exact package candidates**

```bash
ssh ubuntu@44.207.251.65 \
  'apt-cache policy mysql-server nginx python3-pip python3-venv'
```

Expected: install candidates exist; MySQL candidate is `8.4.10-0ubuntu0.26.04.1`.

- [x] **Step 3: Install packages non-interactively**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server nginx python3-pip python3-venv'
```

Expected: exit 0 with no packages left unconfigured.

- [x] **Step 4: Verify installed tools and initial services**

```bash
ssh ubuntu@44.207.251.65 \
  'mysql --version; nginx -v; python3 --version; python3 -m pip --version; systemctl is-active mysql; systemctl is-active nginx'
```

Expected: MySQL 8.4.10, Nginx 1.28.x, Python 3.14.x, pip available, and both services active.

### Task 2: Configure MySQL networking and root accounts

**Files:**
- Create remotely: `/etc/mysql/mysql.conf.d/zz-ari.cnf`
- Modify remotely: MySQL grant tables through account-management SQL
- Test: MySQL configuration, account metadata, authentication, and listeners

**Interfaces:**
- Consumes: working MySQL service from Task 1 and the root password supplied in this conversation
- Produces: public `3306` listener plus `root@localhost` and `root@%`

- [x] **Step 1: Write the isolated MySQL network configuration**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo tee /etc/mysql/mysql.conf.d/zz-ari.cnf >/dev/null && sudo chown root:root /etc/mysql/mysql.conf.d/zz-ari.cnf && sudo chmod 0644 /etc/mysql/mysql.conf.d/zz-ari.cnf' <<'EOF'
[mysqld]
bind-address = 0.0.0.0
mysqlx-bind-address = 127.0.0.1
EOF
```

- [x] **Step 2: Validate configuration before restart**

```bash
ssh ubuntu@44.207.251.65 'sudo mysqld --validate-config'
```

Expected: exit 0 with no configuration error.

- [x] **Step 3: Configure both root accounts without persisting the password**

Open `sudo mysql` through an interactive SSH session:

```bash
ssh -tt ubuntu@44.207.251.65 'sudo mysql'
```

Send these statements over standard input. Replace the password tokens only in the interactive input with the conversation-supplied value; do not save the resulting SQL:

```sql
ALTER USER 'root'@'localhost'
  IDENTIFIED WITH caching_sha2_password BY '<conversation-supplied-secret>';
CREATE USER IF NOT EXISTS 'root'@'%'
  IDENTIFIED WITH caching_sha2_password BY '<conversation-supplied-secret>';
ALTER USER 'root'@'%'
  IDENTIFIED WITH caching_sha2_password BY '<conversation-supplied-secret>';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
```

Expected: all statements succeed. The token is an external secret input, not a value to commit.

- [x] **Step 4: Restart and enable MySQL**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo systemctl restart mysql && sudo systemctl enable mysql'
```

Expected: exit 0.

- [x] **Step 5: Verify accounts and network binding**

Run account inspection through `sudo mysql` and inspect listeners:

```sql
SELECT user, host, plugin
FROM mysql.user
WHERE user = 'root'
ORDER BY host;
```

```bash
ssh ubuntu@44.207.251.65 \
  "systemctl is-active mysql; systemctl is-enabled mysql; sudo ss -lntp | grep -E '(:3306|:33060)'"
```

Expected: `root@localhost` and `root@%` use `caching_sha2_password`; MySQL is active/enabled; 3306 listens on `0.0.0.0`, while 33060 is not public.

### Task 3: Build the isolated FastAPI smoke application with a test

**Files:**
- Create remotely: `/opt/ari/.venv`
- Create remotely: `/opt/ari/smoke/test_app.py`
- Create remotely: `/opt/ari/smoke/app.py`
- Create remotely: `/opt/ari/smoke/requirements.lock`
- Test: `/opt/ari/smoke/test_app.py`

**Interfaces:**
- Consumes: Python 3.14, pip, and venv from Task 1
- Produces: ASGI object `app:app` and `GET /health -> {"status":"ok"}`

- [x] **Step 1: Create the service account and directories**

```bash
ssh ubuntu@44.207.251.65 \
  'id -u ari >/dev/null 2>&1 || sudo useradd --system --home-dir /opt/ari --create-home --shell /usr/sbin/nologin ari; sudo install -d -o ari -g ari -m 0755 /opt/ari/smoke'
```

Expected: `id ari` succeeds and `/opt/ari/smoke` belongs to `ari:ari`.

- [x] **Step 2: Create the virtual environment and install test/runtime dependencies**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo -u ari python3 -m venv /opt/ari/.venv && sudo -u ari /opt/ari/.venv/bin/python -m pip install --upgrade pip && sudo -u ari /opt/ari/.venv/bin/python -m pip install "fastapi[standard]" pytest httpx2'
```

Expected: exit 0; FastAPI, Uvicorn, and pytest import under `/opt/ari/.venv/bin/python`.

- [x] **Step 3: Write the health test before the application**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo -u ari tee /opt/ari/smoke/test_app.py >/dev/null && sudo chmod 0644 /opt/ari/smoke/test_app.py' <<'EOF'
from fastapi.testclient import TestClient

from app import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
EOF
```

- [x] **Step 4: Run the test and verify the expected failure**

```bash
ssh ubuntu@44.207.251.65 \
  "sudo -u ari sh -c 'cd /opt/ari/smoke && /opt/ari/.venv/bin/python -m pytest -q'"
```

Expected: FAIL during collection because module `app` does not exist.

- [x] **Step 5: Write the minimal FastAPI application**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo -u ari tee /opt/ari/smoke/app.py >/dev/null && sudo chmod 0644 /opt/ari/smoke/app.py' <<'EOF'
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
EOF
```

- [x] **Step 6: Run the test and lock resolved versions**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo -u ari sh -c "cd /opt/ari/smoke && /opt/ari/.venv/bin/python -W error -m pytest -q" && sudo -u ari /opt/ari/.venv/bin/python -m pip freeze --all | sudo -u ari tee /opt/ari/smoke/requirements.lock >/dev/null'
```

Expected: `1 passed`; the lock file contains exact FastAPI and Uvicorn versions.

### Task 4: Run Uvicorn under systemd

**Files:**
- Create remotely: `/etc/systemd/system/ari-smoke.service`
- Test: systemd unit validation, status, listener, and direct health response

**Interfaces:**
- Consumes: `/opt/ari/smoke/app.py` and `/opt/ari/.venv`
- Produces: loopback HTTP service at `127.0.0.1:8001`

- [x] **Step 1: Write the systemd unit**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo tee /etc/systemd/system/ari-smoke.service >/dev/null && sudo chown root:root /etc/systemd/system/ari-smoke.service && sudo chmod 0644 /etc/systemd/system/ari-smoke.service' <<'EOF'
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
EOF
```

- [x] **Step 2: Validate the unit before enabling it**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo systemd-analyze verify /etc/systemd/system/ari-smoke.service'
```

Expected: exit 0 with no unit error.

- [x] **Step 3: Enable and start the service**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo systemctl daemon-reload && sudo systemctl enable --now ari-smoke'
```

Expected: exit 0.

- [x] **Step 4: Verify systemd, loopback binding, and direct response**

```bash
ssh ubuntu@44.207.251.65 \
  'systemctl is-active ari-smoke; systemctl is-enabled ari-smoke; sudo ss -lntp | grep "127.0.0.1:8001"; curl --fail --silent --show-error http://127.0.0.1:8001/health'
```

Expected: active, enabled, loopback-only listener, and `{"status":"ok"}`.

### Task 5: Configure Nginx on port 8000

**Files:**
- Create remotely: `/etc/nginx/sites-available/ari-smoke`
- Create remotely: `/etc/nginx/sites-enabled/ari-smoke` symlink
- Remove remotely: `/etc/nginx/sites-enabled/default` symlink only
- Test: Nginx syntax, listeners, and proxied health response

**Interfaces:**
- Consumes: loopback FastAPI service at `127.0.0.1:8001`
- Produces: public HTTP health endpoint at `0.0.0.0:8000/health`

- [x] **Step 1: Write the Nginx site**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo tee /etc/nginx/sites-available/ari-smoke >/dev/null && sudo chown root:root /etc/nginx/sites-available/ari-smoke && sudo chmod 0644 /etc/nginx/sites-available/ari-smoke' <<'EOF'
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
EOF
```

- [x] **Step 2: Enable the smoke site and release port 80**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo ln -sfn /etc/nginx/sites-available/ari-smoke /etc/nginx/sites-enabled/ari-smoke; if [ -L /etc/nginx/sites-enabled/default ]; then sudo unlink /etc/nginx/sites-enabled/default; fi'
```

Expected: the distribution file remains under `sites-available`; only its enabled symlink is removed.

- [x] **Step 3: Validate and restart Nginx**

```bash
ssh ubuntu@44.207.251.65 \
  'sudo nginx -t && sudo systemctl restart nginx && sudo systemctl enable nginx'
```

Expected: syntax successful and exit 0.

- [x] **Step 4: Verify listeners and local proxy response**

```bash
ssh ubuntu@44.207.251.65 \
  'systemctl is-active nginx; systemctl is-enabled nginx; sudo ss -lntp | grep ":8000"; if sudo ss -lntH | grep -qE "(:|])80 "; then echo "unexpected port 80 listener" >&2; exit 1; fi; curl --fail --silent --show-error http://127.0.0.1:8000/health'
```

Expected: Nginx active/enabled, port 8000 listening, no port 80 listener, and `{"status":"ok"}`.

### Task 6: Run end-to-end acceptance checks

**Files:**
- Read only: remote service state, listeners, account metadata, and dependency lock
- Test externally: public FastAPI endpoint and MySQL TCP/authentication
- Create locally: `SERVER_ENVIRONMENT_REPORT.md`

**Interfaces:**
- Consumes: all services configured in Tasks 1–5 and AWS security-group rules managed by the user
- Produces: evidence for every acceptance criterion in `SERVER_ENVIRONMENT.md`

- [x] **Step 1: Verify all remote services and listeners in one fresh check**

```bash
ssh ubuntu@44.207.251.65 \
  'set -eu; for service in mysql nginx ari-smoke; do systemctl is-active "$service"; systemctl is-enabled "$service"; done; mysql --version; nginx -v; sudo -u ari /opt/ari/.venv/bin/python -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"; sudo ss -lntp; curl --fail --silent --show-error http://127.0.0.1:8000/health'
```

Expected: all services active/enabled, versions printed, required listeners present, and health JSON returned.

- [x] **Step 2: Verify the health endpoint from the local workstation**

```bash
curl --fail --silent --show-error http://44.207.251.65:8000/health
```

Expected: `{"status":"ok"}`. If it times out while the server-local request passes, report that AWS security group port 8000 is not yet reachable.

- [x] **Step 3: Verify public MySQL TCP reachability**

```bash
nc -vz -w 5 44.207.251.65 3306
```

Expected: TCP connection succeeds. If it times out while 3306 is listening remotely, report that AWS security group port 3306 is not yet reachable.

- [x] **Step 4: Verify `root@%` authentication from outside the server**

Use an installed local MySQL 8 client if available. Otherwise create a temporary local virtual environment outside the repository, install PyMySQL, prompt for the conversation-supplied password with `getpass`, connect to `44.207.251.65:3306` as root, and run:

```sql
SELECT CURRENT_USER(), VERSION();
```

Expected: `CURRENT_USER()` is `root@%` and the version begins with `8.4`.

- [x] **Step 5: Record the executed installation and final configuration**

Create root-level `SERVER_ENVIRONMENT_REPORT.md` containing:

- deployment timestamp and target host;
- every package and Python dependency version actually installed;
- the commands and file paths used for installation and configuration;
- final MySQL, systemd, and Nginx configuration with the password omitted;
- service states, listeners, internal/external health checks, and MySQL authentication evidence;
- any AWS security-group check that remains an external dependency.

Run `git diff --check`, confirm the password is absent, then commit the report and the checked-off plan with:

```bash
git add SERVER_ENVIRONMENT_REPORT.md SERVER_ENVIRONMENT_PLAN.md
git commit -m "ops: record server environment deployment"
```

- [x] **Step 6: Review requirements against the spec**

Re-read `SERVER_ENVIRONMENT.md` and compare all seven acceptance criteria with fresh output from Steps 1–4. Report any unmet criterion explicitly; do not claim completion if an AWS security-group dependency remains.
