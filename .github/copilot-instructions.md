# ari — AI 协作约定

> **本文件与 `.github/copilot-instructions.md` 是同一份内容的两个副本，逐字相同。**
> 事实源是 `AGENTS.md`；`.github/copilot-instructions.md` 由收工流程自动复制生成。
> 要修改规则，请改 `AGENTS.md`，**不要**改 `.github/copilot-instructions.md`。

本文件是本仓库所有 AI 编码工具的唯一事实源。Claude Code、GitHub Copilot、OpenAI Codex 共用这一套规则，行为必须一致。

---

## 项目

**ari** —— 产品定位尚未确定，见 `PROGRESS.md` 的未决项。

本仓库是 monorepo 根目录，将包含一个服务端子项目和多个客户端子项目。

- 仓库：`git@github.com:cangjie/ari.git`
- 主分支：`master`

### 子目录

- `web_api/` —— 服务端 Web 应用，FastAPI，静态页面与接口同进程提供。已上线，见 `WEB_API.md`
- 客户端子目录尚未创建，待产品定位与客户端范围明确后再定

**子目录由用户创建，AI 不要擅自新建。** 用户创建后会明确告知，届时再往里写代码。

## 技术选型

服务端基础栈已确定：

- Python 3.14 + FastAPI，Uvicorn 作为 ASGI 服务
- MySQL 8.4
- Nginx 反向代理
- systemd 管理服务进程

客户端技术选型仍待产品定位与客户端范围确定后再决定。

### 服务器环境

- AWS 主机：`44.207.251.65`
- 系统：Ubuntu 26.04，ARM64（aarch64）
- SSH：`ubuntu@44.207.251.65`
- 域名：`ari.goldenma.xyz`，A 记录指向 `44.207.251.65`
- 公网入口：HTTPS `443`（web_api 正式入口）、HTTP `80`（301 跳转到 443）、MySQL `3306`、Nginx 环境验证 `8000`
- 本机入口：Uvicorn `127.0.0.1:8002`（web_api）、`127.0.0.1:8001`（smoke）、MySQL X Protocol `127.0.0.1:33060`
- 服务：`mysql`、`nginx`、`ari-web-api`、`ari-smoke` 均由 systemd 管理并开机启动
- 代码：仓库 clone 在 `/home/ubuntu/ari`，属主 `ubuntu`；服务以 `ari` 用户运行，对代码**只读**
- `/home/ubuntu` 权限为 `755`，否则 `ari` 用户穿不进去读不到代码
- 部署方式：`cd /home/ubuntu/ari && git pull --ff-only` + `sudo systemctl restart ari-web-api`
- Python 虚拟环境：`/opt/ari/.venv`（Python 3.14），web_api 与 smoke 共用
- TLS 证书：`/etc/ssl/ari/`，TrustAsia 手动签发，**2026-11-19 到期且无自动续期**
- 临时健康检查：`/opt/ari/smoke`，仍在 8000 上跑，作为环境自检对照；web_api 稳定后可退役
- MySQL 已按用户明确要求允许 `root@%` 公网登录，未强制 TLS；密码不进入仓库
- GitHub Deploy key：服务器 `ubuntu` 使用 `~/.ssh/id_ed25519`，指纹为 `SHA256:AJphJnfR+F7Id8JIonFKKchfVGeU6iWTssOZqJiJWD0`，已验证可访问 `cangjie/ari`
- 基础环境的设计、实施计划与部署记录见 `SERVER_ENVIRONMENT.md`、`SERVER_ENVIRONMENT_PLAN.md`、`SERVER_ENVIRONMENT_REPORT.md`；web_api 的部署记录见 `WEB_API.md`

---

## 工作流程

两个流程。三个工具的行为必须完全一致。

### 开工流程（start-work）

调用：Claude Code `/start-work`，Copilot `/start-work`，Codex `$start-work`，或直接说「开工」。

1. `git pull --ff-only`。失败就**停下来报告**，不要自动 merge 或 rebase —— 拉不动说明有未推送的本地提交或远端分歧，需要人看一眼。
2. 读 `AGENTS.md` 全文（若尚未在上下文中）。
3. 读 `PROGRESS.md` 顶部最近 3 条。
4. 跑 `git log --oneline -10` 和 `git status`，与 PROGRESS 的记载对照，看有没有未被记录的改动。
5. 校验 `.github/copilot-instructions.md` 与 `AGENTS.md` 是否逐字一致（`cmp -s AGENTS.md .github/copilot-instructions.md`）。不一致就报告 —— 说明上次收工没走完。
6. 向用户汇报三句话：项目现状 → 上次做到哪、是哪个工具做的 → 建议的下一步。**然后等用户决定做什么，不要自行开工。**

### 收工流程（end-work）

调用：Claude Code `/end-work`，Copilot `/end-work`，Codex `$end-work`，或直接说「收工」。

> **归档目标不随执行者变化。** 无论由哪个工具执行，写入目标恒定为下列四项。
> 唯一允许的差异在**输入**侧：若当前环境提供持久 memory 目录（目前只有 Claude Code 有），额外把其中的长期事实并入 `AGENTS.md`；没有就只从本次会话提取。**输出恒定不变。**

1. 从本次会话提取：做了什么、下一步、未决问题。
2. 若当前环境有持久 memory 目录，读取其中的 memory 文件，把属于长期事实的内容并入 `AGENTS.md`。没有则跳过。
3. 更新 `AGENTS.md` —— **就地修订，不是追加**。长期事实会被推翻（选型换了、决策改了），必须改写原处，不要越堆越多。
4. 在 `PROGRESS.md` **顶部**插入本次条目，格式见下。
5. 把 `AGENTS.md` 逐字复制到 `.github/copilot-instructions.md`：`cp AGENTS.md .github/copilot-instructions.md`。
6. `git add -A`，按下方格式提交，`git push`。
7. 汇报提交了什么。

若本次会话没有任何实质改动，只汇报，不产生空提交。

### PROGRESS.md 条目格式

新条目插在**文件顶部**（倒序）。这样开工只需读文件头部固定几条，攒到几百条也不会拖慢。

```markdown
## YYYY-MM-DD HH:MM · <工具名>
**做了什么** — …
**下一步** — …
**未决** — …
```

`<工具名>` 取 `claude` / `copilot` / `codex`。

这一栏在接力时能解释痕迹：比如上一棒是 `copilot`，它没有 memory 目录，那么某些判断只会落在 `PROGRESS.md` 里而不在 `AGENTS.md` 里 —— 知道执行者是谁，就知道该去哪找。

### 提交信息格式

```
end-work(<工具名>): <一句话概括本次工作>
```

让工具接力在 `git log` 里直接可见。

---

## 硬性约定

- **`.claude/`、`.agents/`、`.github/` 必须提交进仓库，绝不能加进 `.gitignore`。** 这三个目录装着两个流程在各工具下的入口。一旦被忽略，换台电脑 clone 下来命令就消失了，而且**不会报错**，只是静默地不存在。
- **不要手工编辑 `.github/copilot-instructions.md`。** 改 `AGENTS.md`，由收工流程同步过去。
- **memory 是单向的**：memory 目录 → 仓库。开工流程**不**反向写 memory 目录。仓库是权威源，memory 只是本地缓存；双向同步只会制造重复和冲突。
- **上下文必须随仓库走。** 任何项目上下文都不要只留在会话里，也不要写到仓库外的位置。
- **证书、私钥、密码绝不进仓库。** `.gitignore` 已挡掉 `*.key` `*.pem` `*.crt` `*.zip` 等后缀，但提交前仍要查一遍暂存区。私钥传服务器用管道直写并原子设权限，不在 `/tmp` 留副本。
- **浏览器的定位、剪贴板等 API 只在安全上下文可用**（HTTPS 或 `localhost`）。公网入口必须是 HTTPS，裸 IP 的 HTTP 一律拿不到定位。

---

## 文件地图

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | 事实源。Codex、Claude Code、VS Code Copilot 自动读取 |
| `.github/copilot-instructions.md` | 上者的逐字副本。**全部** Copilot 界面都自动读取（JetBrains / Visual Studio / Xcode 不读 `AGENTS.md`） |
| `CLAUDE.md` | 一行 import，指向 `AGENTS.md` |
| `PROGRESS.md` | 进展时间线，倒序追加 |
| `SERVER_ENVIRONMENT.md` | 服务器基础环境设计与验收标准 |
| `SERVER_ENVIRONMENT_PLAN.md` | 已执行的服务器环境实施计划 |
| `SERVER_ENVIRONMENT_REPORT.md` | 服务器实际版本、配置、安装过程与验收记录 |
| `WEB_API.md` | web_api 的部署记录：服务、Nginx、证书与验收证据 |
| `web_api/README.md` | web_api 的开发说明：本地怎么跑、路由约定 |
| `.claude/skills/*/SKILL.md` | Claude Code 的两个命令入口 |
| `.agents/skills/*/SKILL.md` | Codex 的两个命令入口 |
| `.github/prompts/*.prompt.md` | Copilot 的两个命令入口 |
