#!/usr/bin/env python3
"""通过 Google AI Studio（Gemini API）做结构化输出调用。

**为什么加这条路（2026-09-09）**

审计原本走 `claude_cli`（订阅账号）。实测下来额度撑不住：4667 件里跑完 264 件
（5.4%）就把 5 小时窗口吃掉一大半，外推还需约 3.9M 输出 token、跨 4–5 个窗口，
且全程与用户自己用 Claude Code 抢同一份额度。换 Google 后：

  · 跨厂商仍然成立 —— 打分是 OpenAI，审计是 Google，两端不同源；
  · 限速 12 次/分钟，368 次调用最少 31 分钟，比 claude CLI 的 17 小时快两个量级。

**⚠ 三处与别的 provider 不一样，改代码前必须知道**

1. **key 从 `~/.gemini_key`（权限 600）读，绝不进命令行。** 同 MySQL 口令、
   OpenAI key 的规矩：命令行里的密钥会进 shell 历史，也会被权限系统写进
   `.claude/settings.json`，而那个文件必须提交进仓库。
   鉴权用 `x-goog-api-key` 请求头，**不用 `?key=` 查询参数** —— 后者会把密钥
   写进 URL，代理日志、异常堆栈里都可能留下副本。

2. **`responseSchema` 只吃 OpenAPI 3.0 子集，不是完整 JSON Schema。**
   `additionalProperties` 这类关键字它不认，必须先剥掉（见 `_to_gemini_schema`）。
   剥掉之后约束比 OpenAI 的 `strict:true` 松 —— 兜底靠 `llm_cache.call(validate=)`，
   返回不合格会重试，这层不能省。

3. **限速由本模块自己扛。** 免费层 12 次/分钟，超了返回 429。这里做进程内
   节流（至少间隔 60/RPM 秒），并把 429/5xx 归为 `Transient` 让 llm_cache 退避重试。
   多进程并行跑会各算各的节流，**所以并发只能是 1**。
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.request

# 型号进缓存键：换型号 = 整批重跑，且新旧结果不可直接比较。
#
# **⚠ 必须用 pro 档，flash 实测不能用来做审计。** 2026-09-09 拿同一批 12 件做过对比：
#   · `gemini-3.8-flash`：12 件**全部返回空 missing**、事实错误全 false —— 直接摆烂，
#     和 99.9% 饱和是同一类失效（一列常量不携带信息），只是方向相反；
#   · `gemini-3.5-flash`：每件不多不少正好 1 条，配额式凑数，内容还多是
#     「缺学术代表性定位」这种空话，恰好撞上判据里明令排除的学术项；
#   · 两个 flash 都漏掉了 claude 抓到的真实错误（简介称 Martin Brimmer 为 MFA
#     首任馆长，实为首任董事会主席）—— 而 found_factual_error 是不许降标准的一项。
#
# 根因是档次不是厂商：判据（游客口径、B/C 规则、学术项排除清单）是在
# **claude-opus-5 这个旗舰型号上验证收敛的**。判据里「资料足够时给空列表」和
# 「B/C 段不给 tier_sensitive」这两条，强模型能拿捏分寸，**弱模型直接走捷径**。
# 判据本身没错，但它对模型能力有依赖 —— 换型号一律要重新做同批对比再整批开跑。
#
# 免费层给 pro 的输入 token 上限是 0（一发就 429），所以这条路要求账号已开通付费。
DEFAULT_MODEL = "gemini-3.1-pro-preview"

ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent")

# 免费层是 12 次/分钟；2026-09-09 开通付费后放宽。取环境变量便于分片时
# 各分一份配额（N 个分片就各给 总RPM/N，避免它们各算各的一起超速）。
# 超了会 429，而 429 已归入 Transient 由 llm_cache 退避重试，所以这里
# 设得略激进也不会丢数据，只是会多几次重试。
RPM = int(os.environ.get("GEMINI_RPM", "20"))
_MIN_GAP = 60.0 / RPM         # 两次请求之间至少隔这么久
_last_call = 0.0
_lock = threading.Lock()


class Transient(RuntimeError):
    """这次失败像抖动或限流，值得重试。

    类名必须是 `Transient` —— `llm_cache._TRANSIENT` 按**类名**匹配，
    这样它不必 import 任何具体 provider。
    """


def _key(path: str = "~/.gemini_key") -> str:
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise RuntimeError(f"找不到 {p}。去 AI Studio 建 key 后写入该文件并 chmod 600")
    mode = p.stat().st_mode & 0o777
    if mode & 0o077:
        raise RuntimeError(f"{p} 权限是 {mode:o}，必须是 600（其他人可读的密钥等于泄露）")
    k = p.read_text().strip()
    if not k:
        raise RuntimeError(f"{p} 是空的")
    return k


def available() -> bool:
    try:
        _key()
        return True
    except RuntimeError:
        return False


def _to_gemini_schema(s):
    """把 JSON Schema 转成 Gemini 的 responseSchema 能吃的形状。

    它用的是 OpenAPI 3.0 子集：不认 `additionalProperties`、`$ref`、`oneOf` 等。
    带着这些字段发过去会 400，而**错误信息只说「Invalid JSON payload」，
    不会指出是哪个关键字** —— 所以这里显式白名单，宁可少传也不传它不认的。

    `propertyOrdering` 是 Gemini 特有的，给上能让输出字段顺序稳定，
    对逐条比对新旧结果有好处。
    """
    if not isinstance(s, dict):
        return s
    out = {}
    for k in ("description", "enum", "format", "nullable"):
        if k in s:
            out[k] = s[k]
    # 可空字段的两种写法要对齐：
    #   JSON Schema 用联合类型  {"type": ["string", "null"]}
    #   Gemini 的 proto 要标量  {"type": "string", "nullable": true}
    # 直接把列表发过去会 400，而报错只说
    # 「Unknown name "type" ... Proto field is not repeating, cannot start list」，
    # 完全看不出是「可空」这件事 —— 2026-09-09 第一次接就栽在这儿。
    ty = s.get("type")
    if isinstance(ty, list):
        non_null = [x for x in ty if x != "null"]
        if len(non_null) != 1:
            raise ValueError(f"无法转换的联合类型 {ty}：Gemini 只支持单一类型 + nullable")
        out["type"] = non_null[0]
        if "null" in ty:
            out["nullable"] = True
    elif ty is not None:
        out["type"] = ty
    if "properties" in s:
        out["properties"] = {k: _to_gemini_schema(v) for k, v in s["properties"].items()}
        out["propertyOrdering"] = list(s["properties"])
    if "items" in s:
        out["items"] = _to_gemini_schema(s["items"])
    if "required" in s:
        out["required"] = list(s["required"])
    return out


def _throttle() -> None:
    """进程内节流。**只在单进程下有效** —— 并行跑要各自算，会一起超速。"""
    global _last_call
    with _lock:
        gap = time.monotonic() - _last_call
        if gap < _MIN_GAP:
            time.sleep(_MIN_GAP - gap)
        _last_call = time.monotonic()


class Usage:
    """把 Gemini 的 usageMetadata 包成 llm_cache._usage_cols 认得的对象。

    字段名对齐 OpenAI 那套（prompt_tokens / completion_tokens），
    _usage_cols 里的 getattr 探测就能直接取到。
    thoughtsTokenCount 是推理 token，单独记 —— 这条路径能拿到，就别浪费。
    """

    def __init__(self, d: dict) -> None:
        self.prompt_tokens = d.get("promptTokenCount")
        self.completion_tokens = d.get("candidatesTokenCount")
        self.cache_read_input_tokens = d.get("cachedContentTokenCount")
        self.reasoning_tokens = d.get("thoughtsTokenCount")

    # _usage_cols 从 completion_tokens_details 里取 reasoning_tokens，
    # 给它一个同名属性指回自己即可，不必造第二个类。
    @property
    def completion_tokens_details(self):
        return self


def ask(system: str, user: str, schema: dict, model: str = DEFAULT_MODEL,
        timeout: int = 300, key_file: str = "~/.gemini_key") -> tuple[dict, Usage]:
    """一次结构化输出调用。返回 (解析好的 dict, Usage)。

    刻意不传 temperature / topK：不同代际的默认值不同，全部走服务端默认，
    换型号时不必改代码 —— 与 audit_meta.ask 对 OpenAI 的处理一致。
    """
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _to_gemini_schema(schema),
        },
    }
    req = urllib.request.Request(
        ENDPOINT.format(model=model),
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": _key(key_file)},
        method="POST")

    _throttle()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        # 429=限流、5xx=服务端抖动，都该重试；4xx 其余是我们自己发错了，不该重试。
        if e.code == 429 or e.code >= 500:
            raise Transient(f"Gemini HTTP {e.code}：{detail}") from e
        raise RuntimeError(f"Gemini HTTP {e.code}：{detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise Transient(f"Gemini 网络错误：{type(e).__name__} {e}") from e

    cands = resp.get("candidates") or []
    if not cands:
        # 没有候选多半是被安全策略拦了。把原因带出来，别只说「空返回」。
        raise RuntimeError(f"Gemini 没有返回候选：{json.dumps(resp, ensure_ascii=False)[:400]}")
    cand = cands[0]
    reason = cand.get("finishReason")
    if reason and reason not in ("STOP", "MAX_TOKENS"):
        raise RuntimeError(f"Gemini 异常结束 finishReason={reason}")
    if reason == "MAX_TOKENS":
        # 截断的 JSON 解析出来也是残的，**绝不能当成功**：那会把半批结果写进缓存。
        raise Transient("Gemini 输出被 MAX_TOKENS 截断，需减小批大小")

    parts = cand.get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise RuntimeError("Gemini 返回了空文本")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini 返回的不是合法 JSON：{text[:400]}") from e
    return data, Usage(resp.get("usageMetadata") or {})
