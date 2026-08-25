# 进展时间线

最新的在最上面。格式与写入规则见 `AGENTS.md`。

---

## 2026-08-26 · claude
**做了什么** — 建 `ari` 库与 `ari` 账号（`localhost` + `%`，仅 `ari`.* 全权），随后分三步把两套数据灌进去。

（1）**城市/点位榜单**：从 `500cities_tier_v2.xlsx` 导入 city 500 / cultural_site 825 / tier_change 380。

（2）**多语种改造**：源数据每个文本字段只有一种语言（点位名 575 中文 / 248 拉丁，国家名 500 行只有 115 个不同值）。按用户要求改成「一段内容一个ID + 多语种内容表」，主表另留 `*_key` 规范名撑唯一约束与索引 —— 内容ID挡不住文本重复，`uk_city_name_country` 这类约束必须落在 key 上。译名 2416 段全部补齐，其中 860 段定级理由是机器生成的模板串，写 `translate_templates.py` 按 11 个维度词 + 5 种尾注程序翻译，审 16 个词等于审完 860 条。

（3）**六馆展品**：`utils/import_data/artworks/` 下六个格式各异的 Excel 归一后导入 museum 6 / gallery 172 / artwork 8884。新增 `import_artworks.py`，六馆差异全收敛在一个 `MUSEUMS` 配置里。译名 7506 段全部补齐（故宫 976 段评级理由用 `translate_reasons.py` 按原子短语拼装，423 个翻译单位覆盖全部）。

全库最终：`content` 11117 段 / `content_text` 22234 行 = 11117×2，**零缺译**。

**关键设计** — content 表按 `kind` 划分所有权 + ID 分段（榜单 1–999999，展品 1000000 起），两个导入器各删各的。原先无条件 `DELETE FROM content` 会把另一侧文本删掉，而展品外键是 RESTRICT，后果是导入直接报错。已跑回归验证：导完展品再跑榜单导入，两侧行数不变。`museum.site_key` 做成软链而非外键，理由同上（榜单每次重灌都清空 `cultural_site`，且六馆有三家不在其中）。

**踩到的坑** — ① `load_translations` 用错了 kind 集合，把展品译名整批当未知 kind 丢弃，只留一行 warn，极易漏看；② 双语馆简介被中英各建一条 content，只引用其中一条，留下 595 条孤儿内容，已加永久守卫；③ MFA 的 `Rank` 是每个 Tier 段内各自排的，拿它当唯一键会撞。三处都已修。

**试过但放弃的** — 想给展品名也做词素槽位合成器，实测只覆盖 7%（4703 条里 343 条），未覆盖词素 2090 种长尾且语序有 bug，不划算，撤掉了改逐条手译。

**源数据问题（已如实记录不做推断）** — MFA 文件名叫「1300」实际只有 203 行有数据；首博 6159 件里 6133 件未确认在展（文件名却是「在展文物清单」）；国博的「展品简介」其实是出土/尺寸元信息，名不副实。

**下一步** — web_api 接上 `ari` 库，按 locale 出接口（回落链：请求语种 → `zh-CN` → `*_key`）；注意列表页 N+1，先批量取 cid 再一次性查文本。

**未决** — ① 展品那 7506 条译文全标了 `AI翻译`，没按把握程度分级（榜单那 2416 段是分了级的：人工校对 2266 / AI 137 / 存疑 13），要人工复核得按 kind 或按馆筛，`source` 字段帮不上忙；② 两个导入器都是清空重灌，`created_at` 只反映最后一次导入时间，追溯不了「某行文本哪天进库」，需要变更历史得另开审计表；③ 收工前从 `.claude/settings.json` 剥掉了 6 条含明文 MySQL 密码的 allow 规则 —— 权限系统会把批准过的命令原文落盘，而该文件按约定必须提交，根治办法是别把密码写进命令行。

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
