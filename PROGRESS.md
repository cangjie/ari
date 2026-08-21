# 进展时间线

最新的在最上面。格式与写入规则见 `AGENTS.md`。

---

## 2026-08-21 09:08 · claude
**做了什么** — 搭好跨 AI 工具的会话上下文持久化骨架：`AGENTS.md` 作为唯一事实源（长期事实 + 开工/收工两个流程），`.github/copilot-instructions.md` 为其逐字副本，`CLAUDE.md` 一行 import；`PROGRESS.md` 倒序时间线；三套命令入口 `.claude/skills/`、`.agents/skills/`、`.github/prompts/` 各两个。确认了 JetBrains 版 Copilot 不读 `AGENTS.md`，所以副本不能用指针代替。

**下一步** — 在 Copilot 和 Codex 里各跑一次 `start-work` / `end-work`，验证三个工具的归档结果落在同一处、格式一致。

**未决** —
- **ari 的产品定位还没定**：做什么、给谁用。这是 monorepo 子目录划分的前提，没有它无法设计服务端与各客户端的目录结构。
- 客户端具体有哪些（Web / iOS / Android / 桌面 / CLI / 小程序）尚未确定。
- 技术选型未定。
- `.idea/` 已加入 `.gitignore`；若希望跨机器同步 PyCharm 设置，需要改回来。
