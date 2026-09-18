#!/usr/bin/env python3
"""去重用的模型调用：统一走 haiku-4.5，并带**本地文件缓存**。

**为什么要本地缓存（2026-09-16 的教训）**

所有调用本该走 `llm_cache.call()`（缓存键含提示词全文，改一字就重跑、不改就必中）。
但它的存储在 MySQL 里，而这台机器连不上库 —— `llm_cache` 只打一行 warn 就退化成
「全部实调、一条不留」。那一轮用 claude-opus-5 跑了半小时去重确认，被叫停时
**已付费的答案一条都没落下**，重跑就得再付一遍。

所以这里在 `llm_cache` 外面再包一层 JSONL：键与 `llm_cache` 同构
（model + system + user + schema 全文的 sha256），**校验通过才写**
（同 llm_cache：坏答案进了缓存会让每次重启都崩在同一个地方）。
库能连上时两层都会写，互不冲突。

缓存文件 `dedupe_llm_cache.jsonl` 入仓库 —— 已付费的答案就是资产。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import audit_meta as A

HERE = pathlib.Path(__file__).parent
CACHE = HERE / "dedupe_llm_cache.jsonl"

# 去重用的模型，**全仓库只在这一处定义**（用户 2026-09-17 定：haiku-4.5）。
MODEL = "claude-haiku-4-5"

_mem: dict[str, dict] | None = None


def _load() -> dict[str, dict]:
    global _mem
    if _mem is None:
        _mem = {}
        if CACHE.exists():
            for line in CACHE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    _mem[r["key"]] = r["resp"]
    return _mem


def _key(model: str, system: str, user: str, schema: dict) -> str:
    h = hashlib.sha256()
    for part in (model, system, user, json.dumps(schema, sort_keys=True, ensure_ascii=False)):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def ask(system: str, user: str, schema: dict, *, stage: str, scope: str,
        validate=None, model: str = MODEL) -> tuple[dict, bool]:
    """返回 (结果, 是否命中本地缓存)。"""
    mem = _load()
    k = _key(model, system, user, schema)
    if k in mem:
        r = mem[k]
        if validate is None or validate(r):
            return r, True
        del mem[k]                      # 旧答案过不了新校验，丢掉重问
    A.CLAUDE_CLI = model
    r = A.ask(None, model, system, user, stage, schema, None,
              museum_key="mfa_boston", scope=scope, validate=validate)
    if validate is not None and not validate(r):
        raise RuntimeError(f"{stage} {scope}：模型输出过不了校验，不写缓存")
    mem[k] = r
    with CACHE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"key": k, "model": model, "stage": stage, "scope": scope,
                            "resp": r}, ensure_ascii=False) + "\n")
    return r, False
