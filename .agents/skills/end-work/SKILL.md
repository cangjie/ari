---
name: end-work
description: 收工时使用 —— 把本次工作归档进 AGENTS.md 与 PROGRESS.md，同步 Copilot 副本，提交并推送。用户说「收工」或调用 $end-work 时触发。
---

执行 `AGENTS.md` 中「收工流程（end-work）」一节的全部步骤。

若 `AGENTS.md` 尚未在上下文中，先完整读取它再开始。

**本环境没有持久 memory 目录**，跳过步骤 2，只从本次会话提取内容。步骤 3～7 照常执行 —— 归档目标与其他工具完全相同。
