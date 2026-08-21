# 进展时间线

最新的在最上面。格式与写入规则见 `AGENTS.md`。

---

## 2026-08-21 15:16 · claude
**做了什么** — 新建 `web_api/` FastAPI 应用（`/health` + `static/` 挂载到根路径，4 条 pytest 全绿），写了手机端 GPS 定位测试页 `static/index.html`，显式检测 `window.isSecureContext` 避免静默失败。域名 `ari.goldenma.xyz` 与 TrustAsia 证书就位后完成 HTTPS 部署：`/home/ubuntu` 放宽到 `755`、服务器 `git pull`、证书装入 `/etc/ssl/ari/`（私钥 `600`）、新增 `ari-web-api.service`（`ari` 用户跑 uvicorn `127.0.0.1:8002`）、Nginx `443` 反代加 `80` 跳转。外部验收全通：HTTPS 200/HTTP2、TLS 校验 0、80 跳 301。`ari-smoke` 保留在 8000 未动。

**下一步** — 用户在手机上实测 GPS 定位能否出坐标；确认后可考虑退役 `ari-smoke`，并把手动证书换成 Let's Encrypt + certbot 自动续期。

**未决** —
- ari 的产品定位、目标用户与客户端范围仍未确定，客户端子目录因此还不能设计。
- TLS 证书 2026-11-19 到期且无自动续期，到期前必须处理，否则站点直接不可用。
- MySQL 公网 `root@%` 且未强制 TLS 仍需在正式业务上线前重新评估。

---

## 2026-08-21 12:05 · copilot
**做了什么** — 排查服务器 `ubuntu@44.207.251.65` 无法通过 SSH 克隆 GitHub 仓库的问题；确认服务器使用 `~/.ssh/id_ed25519`，其指纹为 `SHA256:AJphJnfR+F7Id8JIonFKKchfVGeU6iWTssOZqJiJWD0`，并在 `cangjie/ari` 配置 Deploy key。最终验证 GitHub SSH 认证成功，`git ls-remote git@github.com:cangjie/ari.git HEAD` 返回提交 `0b09cb7`。
**下一步** — 继续等待产品定位、目标用户与客户端范围明确，再设计正式项目目录并替换临时 smoke 服务。
**未决** — MySQL 公网 `root@%` 且未强制 TLS 仍需在正式业务上线前重新评估。

---

## 2026-08-21 10:21 · codex
**做了什么** — 完整验证了 Codex 的 `start-work` 流程；在 AWS Ubuntu 26.04 ARM64 主机 `44.207.251.65` 上搭建服务器基础环境：MySQL 8.4.10 公网监听 `3306` 并启用 `root@%`，Python 3.14 独立虚拟环境运行 FastAPI 0.141.1 / Uvicorn 0.52.4，systemd 管理健康检查服务，Nginx 在公网 `8000` 反代到回环 `8001`，`80` 保持空闲。用红绿测试验证 `/health`，并从外部完成 HTTP 200、3306 TCP 与 `root@%` 认证验收；设计、计划和实际部署记录已写入仓库根目录。

**下一步** — 等用户给出功能需求与产品定位；定位明确后再设计正式服务端/客户端目录，用正式 FastAPI 应用替换 `/opt/ari/smoke`。

**未决** —
- ari 的产品定位、目标用户与客户端范围仍未确定，因此正式 monorepo 子目录结构仍不能设计。
- MySQL 公网 `root@%` 且未强制 TLS 是用户明确选择；正式业务上线前应重新评估安全组来源 CIDR、独立最小权限账户与 TLS。
- 本次只安装目标环境，没有执行整机升级；安装时 APT 另有 107 个可升级包。

## 2026-08-21 09:08 · claude
**做了什么** — 搭好跨 AI 工具的会话上下文持久化骨架：`AGENTS.md` 作为唯一事实源（长期事实 + 开工/收工两个流程），`.github/copilot-instructions.md` 为其逐字副本，`CLAUDE.md` 一行 import；`PROGRESS.md` 倒序时间线；三套命令入口 `.claude/skills/`、`.agents/skills/`、`.github/prompts/` 各两个。确认了 JetBrains 版 Copilot 不读 `AGENTS.md`，所以副本不能用指针代替。

**下一步** — 在 Copilot 和 Codex 里各跑一次 `start-work` / `end-work`，验证三个工具的归档结果落在同一处、格式一致。

**未决** —
- **ari 的产品定位还没定**：做什么、给谁用。这是 monorepo 子目录划分的前提，没有它无法设计服务端与各客户端的目录结构。
- 客户端具体有哪些（Web / iOS / Android / 桌面 / CLI / 小程序）尚未确定。
- 技术选型未定。
- `.idea/` 已加入 `.gitignore`；若希望跨机器同步 PyCharm 设置，需要改回来。
