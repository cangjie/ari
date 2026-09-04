#!/usr/bin/env python3
"""通过 `claude` CLI 的 headless 模式调 Anthropic 模型 —— 走订阅账号，不需要 API key。

**为什么需要这条路**

`audit_meta.py` 的设计前提是**打分者与审计者不同源**：V3.0 那批分由 claude-opus-5
打，审计换 OpenAI，以切断「你自己打的分证据够不够」这个问题里的自评偏差。
2026-09-02 起本机没有 Anthropic 凭据，打分被迫也换成 gpt-5.6-sol，
于是变成同一个模型先打分再审自己 —— 交叉验证形同虚设（AGENTS.md 已记）。

本机有 Claude Code 的订阅登录，`claude -p` 的 headless 模式恰好提供了所需的一切：
  --system-prompt / stdin  长提示词从管道进，不撞 ARG_MAX
  --json-schema            结构化输出，与 OpenAI 的 strict 模式等价
  --model                  claude-opus-5 可用，正是当初打分的那个型号
  --output-format json     返回体里带 structured_output 与完整 usage

**⚠ 三个必须知道的代价**

1. **每次调用附带约 5.4k token 的 Claude Code 自身脚手架**（系统提示词、工具定义），
   走 prompt cache 但仍计入用量。相比直连 SDK 是纯额外开销。
2. **慢**：单次 4–10 秒，含进程启动。4464 件 × 3 阶段是以小时计的。
3. **没有 effort 旋钮**。CLI 不暴露 reasoning_effort，档位无法按阶段调，
   只能靠选型号（opus / sonnet）。故本 provider 的 effort 一律记 NULL。

**不要加 `--bare`**：它明说「Anthropic auth is strictly ANTHROPIC_API_KEY or
apiKeyHelper，OAuth and keychain are never read」—— 加了就用不了订阅账号。
"""
from __future__ import annotations

import json
import shutil
import subprocess

# 打分是纯文本判断，不需要任何工具。全部禁掉：
#   · 省掉工具调用的往返与 token
#   · 更要紧的是防止模型跑去读文件/上网「补证据」—— 那会让这次评分的输入
#     不再是我们喂进去的那些，llm_call 里存的 prompt 就不能复现结果了
NO_TOOLS = ["Bash", "Edit", "Write", "Read", "Glob", "Grep",
            "WebFetch", "WebSearch", "Task", "NotebookEdit", "TodoWrite"]

DEFAULT_MODEL = "claude-opus-5"


def available() -> bool:
    return shutil.which("claude") is not None


def ask(system: str, user: str, schema: dict, model: str = DEFAULT_MODEL,
        timeout: int = 600) -> tuple[dict, dict]:
    """一次结构化输出调用。返回 (解析好的 dict, usage 字典)。

    user 走 stdin —— 评分提示词动辄几千字符，塞进 argv 会撞 ARG_MAX，
    而且会整段出现在 ps 输出里。
    """
    cmd = [
        "claude", "-p",
        "--system-prompt", system,
        "--model", model,
        "--json-schema", json.dumps(schema, ensure_ascii=False),
        "--output-format", "json",
        "--disallowedTools", *NO_TOOLS,
    ]
    r = subprocess.run(cmd, input=user, capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI 退出码 {r.returncode}：{r.stderr[:400]}")
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude CLI 返回的不是 JSON：{r.stdout[:400]}")
    if out.get("is_error"):
        raise RuntimeError(f"claude CLI 报错：{str(out.get('result'))[:400]}")
    data = out.get("structured_output")
    if data is None:
        # schema 没生效时 result 里是自由文本 —— 不要试图从中「捞」JSON，
        # 捞出来的东西没有 schema 保证，后面每一步都会当它是合规数据。
        raise RuntimeError(f"没有 structured_output，stop_reason="
                           f"{out.get('stop_reason')}；result={str(out.get('result'))[:200]}")
    return data, out.get("usage") or {}


class Usage:
    """把 CLI 的 usage 字典包成 llm_cache._usage_cols 认得的对象。

    字段名与 Anthropic SDK 一致（input_tokens / output_tokens /
    cache_read_input_tokens），所以 _usage_cols 里那套 getattr 探测原样适用。
    reasoning token 这条路径拿不到，留空 —— 少记一列，不编。
    """

    def __init__(self, d: dict) -> None:
        self.input_tokens = d.get("input_tokens")
        self.output_tokens = d.get("output_tokens")
        self.cache_read_input_tokens = d.get("cache_read_input_tokens")
        self.cache_creation_input_tokens = d.get("cache_creation_input_tokens")
