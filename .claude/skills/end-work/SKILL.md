---
name: end-work
description: 收工时使用 —— 把本次工作归档进 AGENTS.md 与 PROGRESS.md，同步 Copilot 副本，提交并推送。用户说「收工」或调用 /end-work 时触发。
---

执行 `AGENTS.md` 中「收工流程（end-work）」一节的全部步骤。

若 `AGENTS.md` 尚未在上下文中，先完整读取它再开始。

**本环境提供持久 memory 目录**，路径见本次会话系统提示中给出的 memory 目录（不要写死路径，它含用户名与仓库路径，换台电脑就变了）。执行步骤 2 时读取其中的 memory 文件。
