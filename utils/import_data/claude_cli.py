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
3. **有 `--effort low|medium|high|max` 开关，但对压输出量没用 —— 别指望它。**
   （早先这里写的是「CLI 不暴露 reasoning_effort」，那是错的，已更正。
   因为这个错误认知，llm_call.effort 一路记成 NULL，实际跑的是默认档。）

   2026-09-09 在 haiku-4.5 同一批 12 件上实测：

       档位        输出 token   耗时    missing 总数   进队列
       默认          14,137      —          —           —
       --effort low  18,519     218s        0           0     ← 更贵且判断垮掉
       --effort med  14,521     163s        9           6

   **low 档不但不省，反而多吐 31%，而且 12 件全返回空 missing**（与 gemini-flash
   同一种摆烂形态）。medium 与默认持平。三档下 num_turns 恒为 2。

4. **`num_turns` 恒为 2，这是输出量的结构性来源。** 配 `--json-schema` 时 CLI
   要跑两轮（极可能是先作答、再按 schema 重排），同一份内容生成两次都计费。
   实测一次调用 output_tokens=14,137，而可见内容合计只有 3,780 字符
   （structured_output 3,063 + result 717）—— 约七成 token 看不见。

   **压输出这件事，三条路都试过了，全部无效**（详见 audit_meta.py 的
   STAGE1_SLIM_SCHEMA 注释）：砍可见文本（token 反升）、限量限长（判断垮掉）、
   调 effort（同上）。要省只能换模型：同一任务 gemini-3.1-pro 均 1,667 token/次，
   opus-5 均 10,721，haiku-4.5 均 17,719 —— **haiku 是三个里最费的**。

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


class Transient(RuntimeError):
    """这次调用失败得像是抖动，值得重试。

    llm_cache._TRANSIENT 按**类名**判断该不该退避重试，而它原先只列了 OpenAI 的
    异常类名。claude_cli 一直抛普通 RuntimeError，于是 2026-09-05 给 OpenAI 那条
    路径加的重试保护，在 Claude 这条路径上**从来没生效过** —— 2026-09-08 七个分片
    并发跑 MFA，第 2 次调用后全部被并发限打回，一个都没重试，24/4667 件就全灭了。
    """


def available() -> bool:
    return shutil.which("claude") is not None


# 单次调用的超时。**1200 而不是 600**：2026-09-10 跑 MFA 的 S/A 700 件时，
# sonnet-5 + batch 48 的实测耗时是 214–402 秒，但分布有长尾 —— 16 次调用里至少
# 4 批撞上 600 秒被砍（seq 1-60 第 3 次才成、seq 71-211 与 seq 2694-3251 都用满
# 4 次重试）。每次超时白烧 600 秒的生成量且照付，有效产出被严重稀释。
#
# ⚠ 教训：**批越大，耗时的方差越大**。当初只用 2 次调用就判定 batch 48 安全，
# 样本量看不出分布的尾巴。以后定批大小要看多次调用的最大值，不是平均值。
#
# timeout 不进 llm_cache 的缓存键（键是 provider|model|effort|system|user|schema），
# 所以调它不会让已跑的结果失效。
DEFAULT_TIMEOUT = 1200


def ask(system: str, user: str, schema: dict, model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT) -> tuple[dict, dict]:
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
    try:
        r = subprocess.run(cmd, input=user, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise Transient(f"claude CLI 超过 {timeout}s 未返回") from e
    if r.returncode != 0:
        # stdout 也要带上 —— `--output-format json` 下 CLI 把错误写在 stdout，
        # 只报 stderr 会得到一句空的「退出码 1」，查不出任何东西。
        detail = (r.stderr or "").strip() or (r.stdout or "").strip() or "（无输出）"
        raise Transient(f"claude CLI 退出码 {r.returncode}：{detail[:400]}")
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
