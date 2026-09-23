#!/usr/bin/env python3
"""通过 `codex exec` 调 OpenAI 模型 —— 走 ChatGPT 订阅账号，不需要 API key。

与 `claude_cli.py` 同构：那条路用 Claude Code 的订阅跑审计，这条路用 Codex 的
ChatGPT 订阅跑评级。**打分者 OpenAI、审计者 Anthropic，正好构成跨厂商**
（AGENTS.md 第 9 条：同源审计做出来的可信度，本质是打分者给自己打分）。

本机的 `codex` 不在 PATH 上，装在 ChatGPT.app 与 VS Code 扩展里，见 `_binary()`。
认证看 `~/.codex/auth.json` 的 `auth_mode`：2026-09-22 实测为 `chatgpt`，
有订阅 tokens、**没有** OPENAI_API_KEY —— 所以不按 token 计费，但受订阅的速率限制。

**⚠ 必须把它锁死，否则评分不可复现。** `codex exec` 是个 agent：能执行命令、
读文件、上网、调插件。模型一旦跑去「补证据」，这次评分的输入就不再是我们喂进去的
那些，`llm_call` 里存的 prompt 就复现不出结果（claude_cli.py 为此禁掉了全部工具）。
所以每次调用都：

  --ignore-user-config   用户的 ~/.codex/config.toml 设着 model_reasoning_effort=xhigh、
                         默认型号 gpt-6-astra、还开着 browser/visualize 插件。不隔离的话
                         评分会跟着个人配置变，而这些**不在缓存键里** —— 改了配置就是
                         换了判据，却照样命中旧答案
  --ignore-rules         不读任何 AGENTS.md
  -C <空目录>            工作目录是个空的临时目录，没有东西可读
  --sandbox read-only    即便想写也写不了
  --ephemeral            不落会话
  -c web_search=disabled 并 --disable 掉 browser/computer_use/插件/记忆/多 agent

**光靠开关不够，还要看它实际做了什么**：解析 `--json` 事件流，出现 agent_message 与
reasoning 以外的任何 item（执行命令、改文件、搜索、调工具）就报错退出 ——
同 AGENTS.md「判断状态优先用客观量」。

2026-09-22 实测（一件，gpt-5.6-luna，effort=medium）：
    未锁死   输入 16,815 token
    锁死后   输入  7,037 / 输出 91（含 reasoning 59）/ 事件流仅 1 个 agent_message
关掉个人配置与插件，脚手架砍掉一半多。

**effort 这条路是真能控的**（不像 `claude -p` 的 `--effort` 对输出量没用），
走 `-c model_reasoning_effort=<档>`，进 llm_cache 的缓存键。

**没有 system prompt 开关**，system 与 user 拼成一段走 stdin，中间有显式分隔。
llm_cache 的键仍分别包含两者全文，复现不受影响。

stderr 里常有一条 `failed to load models cache: missing field …` —— 那是 codex
自己的型号缓存格式问题，退出码 0、结果正常。**不拿 stderr 判成败**，看退出码与事件流。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

DEFAULT_MODEL = "gpt-5.6-luna"

# 同 claude_cli：批越大耗时方差越大，定超时看最大值不看平均值。
# timeout 不进缓存键，调它不会让已跑的结果失效。
DEFAULT_TIMEOUT = 1200

# 事件流里允许出现的 item 类型。其余任何一种都说明模型动了工具 —— 输入不再只是
# 我们喂进去的那些，这次结果就不可复现。
ALLOWED_ITEMS = {"agent_message", "reasoning"}

DISABLE = ["browser_use", "computer_use", "image_generation", "memories",
           "multi_agent", "apps", "plugins"]


class Transient(RuntimeError):
    """这次失败得像是抖动（超时、速率限制、网络），值得退避重试。

    **类名必须是 Transient** —— llm_cache._TRANSIENT 按类名判断，不 import 具体 provider。
    """


def _binary() -> str | None:
    """
    找 codex 可执行文件。**找不到就返回 None，由调用方喊出来**，不猜一个路径去跑。
    顺序：环境变量 CODEX_BIN → PATH → ChatGPT.app → VS Code 扩展（取版本最新的）。
    """
    env = os.environ.get("CODEX_BIN")
    if env and os.access(env, os.X_OK):
        return env
    p = shutil.which("codex")
    if p:
        return p
    app = "/Applications/ChatGPT.app/Contents/Resources/codex"
    if os.access(app, os.X_OK):
        return app
    ext = sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/openai.chatgpt-*/bin/*/codex")))
    return ext[-1] if ext else None


def available() -> bool:
    return _binary() is not None


def version() -> str:
    b = _binary()
    if not b:
        return "（未找到 codex）"
    r = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=30)
    return (r.stdout or r.stderr).strip()


def ask(system: str, user: str, schema: dict, model: str = DEFAULT_MODEL,
        effort: str | None = None,
        timeout: int = DEFAULT_TIMEOUT) -> tuple[dict, dict]:
    """一次结构化输出调用。返回 (解析好的 dict, usage 字典)。"""
    b = _binary()
    if not b:
        raise RuntimeError("找不到 codex 可执行文件。设 CODEX_BIN，或装 ChatGPT.app / "
                           "VS Code 的 ChatGPT 扩展。")

    prompt = ("# 系统指令\n\n" + system.strip() +
              "\n\n# 任务\n\n" + user.strip() + "\n")

    with tempfile.TemporaryDirectory(prefix="codex_") as tmp:
        work = os.path.join(tmp, "empty")       # 空目录：模型想读也没东西可读
        os.mkdir(work)
        schema_path = os.path.join(tmp, "schema.json")
        out_path = os.path.join(tmp, "last.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False)

        # 一律绝对路径：-C 会改工作目录，相对路径的 schema 会找不到（09-22 踩过）
        cmd = [b, "exec", "-", "-m", model,
               "-c", "web_search=disabled",
               "--ignore-user-config", "--ignore-rules", "--ephemeral",
               "--sandbox", "read-only", "-C", work, "--skip-git-repo-check",
               "--output-schema", schema_path, "-o", out_path, "--json"]
        if effort:
            cmd[5:5] = ["-c", f"model_reasoning_effort={effort}"]
        for feat in DISABLE:
            cmd += ["--disable", feat]

        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise Transient(f"codex exec 超过 {timeout}s 未返回") from e

        events = []
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        err = next((e for e in events if e.get("type") in ("error", "turn.failed")), None)
        if r.returncode != 0 or err:
            detail = json.dumps(err, ensure_ascii=False)[:400] if err else \
                ((r.stderr or "").strip()[-400:] or "（无输出）")
            raise Transient(f"codex exec 退出码 {r.returncode}：{detail}")

        # 客观核查：模型有没有动过工具
        kinds = [(e.get("item") or {}).get("type") for e in events
                 if e.get("type", "").startswith("item.")]
        bad = sorted({k for k in kinds if k and k not in ALLOWED_ITEMS})
        if bad:
            raise RuntimeError(f"codex 在评分过程中调用了工具 {bad} —— 输入已不只是"
                               f"我们喂进去的提示词，结果不可复现，拒绝采用。")

        usage = {}
        for e in events:
            if e.get("type") == "turn.completed" and e.get("usage"):
                usage = e["usage"]

        if not os.path.exists(out_path):
            raise RuntimeError("codex 没有写出最终消息（-o 文件不存在）")
        txt = open(out_path, encoding="utf-8").read().strip()
        try:
            data = json.loads(txt)
        except json.JSONDecodeError:
            # 同 claude_cli：schema 没生效时不要从自由文本里「捞」JSON，
            # 捞出来的东西没有 schema 保证，后面每一步都会当它是合规数据
            raise RuntimeError(f"codex 最终消息不是 JSON：{txt[:300]}")
    return data, usage


class Usage:
    """把 turn.completed 的 usage 包成 llm_cache._usage_cols 认得的对象。

    codex 给的字段：input_tokens / cached_input_tokens / output_tokens /
    reasoning_output_tokens。output_tokens 已**包含** reasoning（实测 91 里 59 是推理），
    照录不拆。reasoning 放进 output_tokens_details，_usage_cols 就能取到 ——
    这条路径的计量是完整的，比 claude_cli 那条（至今记成 4/8/12）好。
    """

    def __init__(self, d: dict) -> None:
        self.input_tokens = d.get("input_tokens")
        self.output_tokens = d.get("output_tokens")
        self.cache_read_input_tokens = d.get("cached_input_tokens")
        self.output_tokens_details = SimpleNamespace(
            reasoning_tokens=d.get("reasoning_output_tokens"))


if __name__ == "__main__":
    print("codex:", _binary())
    print("版本:", version())
