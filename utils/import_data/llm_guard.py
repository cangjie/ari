#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
长任务守护：包住一条命令运行，llm_call 里一出现**本任务**的失败记录，就结束整棵进程树。

    python3 llm_guard.py --provider openai_codex --stage "tier_stage%" --museum wmhg -- \\
        python3 tier_v3.py --museum wmhg --provider codex_cli ...

退出码：被守护命令的退出码；因发现失败而中止时为 3。

**为什么要有**（AGENTS.md 第 10 条，用户 2026-09-23 定的规矩「失败先查原因，不找到原因不许重跑」）：
脚本自带的退避重试只对网络抖动有意义，对「每次都会失败」的原因（档位、schema、额度）
重试就是照付。以前每次都是临时写守护，这里固定下来。

**只认本任务**：按 provider + stage（LIKE）+ museum 过滤，且只看启动之后新增的记录
（id 大于启动时的 MAX(id)）。09-23 的守护按「PEM 下任何失败」判，并行的 Gemini 翻译
报一次 503，就把正在跑的审计阶段三误杀了。

各流水线在 llm_call 里记的名字（2026-09-24 查库）：
    评分        provider=openai_codex   stage=tier_stage1/2/3
    审计        provider=anthropic_cli  stage=audit_stage1_slim、audit_stage3
    审计补英译  provider=openai_codex / google / anthropic_cli   stage=audit_trans
    展品翻译    provider=openai_codex   stage=trans_artwork_*（museum_key 可能为空，此时不要给 --museum）

**结束的是整棵树**：Windows 用 taskkill /T，其余系统让子进程独占一个进程组再整组发信号。
只杀父进程不够 —— `claude -p` / `codex exec` 子进程会继续跑、继续计费（AGENTS.md 第 12 条）。
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

import meta_lib as M


def kill_tree(p: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--provider", required=True, help="llm_call.provider，如 openai_codex / anthropic_cli")
    ap.add_argument("--stage", required=True, help="llm_call.stage 的 LIKE 模式，如 tier_stage%%")
    ap.add_argument("--museum", default=None, help="llm_call.museum_key；不给就不按馆过滤")
    ap.add_argument("--every", type=int, default=20, help="每隔几秒查一次")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- 之后是要守护的命令")
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        ap.error("缺要守护的命令（写在 -- 之后）")

    conn = M.connect(autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM llm_call")
    floor = cur.fetchone()[0]
    sql = ("SELECT id, stage, LEFT(error_text, 400) FROM llm_call"
           " WHERE id > %s AND status = 'error' AND provider = %s AND stage LIKE %s"
           + (" AND museum_key = %s" if a.museum else "") + " ORDER BY id LIMIT 1")
    args = (floor, a.provider, a.stage) + ((a.museum,) if a.museum else ())

    kw = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
          else {"start_new_session": True})
    p = subprocess.Popen(cmd, **kw)
    print(f"[guard] 守护 pid={p.pid}：provider={a.provider} stage LIKE {a.stage!r}"
          f"{' museum=' + a.museum if a.museum else ''}，只看 llm_call.id > {floor} 的新记录", flush=True)
    try:
        while p.poll() is None:
            time.sleep(a.every)
            try:
                cur.execute(sql, args)
                row = cur.fetchone()
            except Exception as e:                       # noqa: BLE001  跨公网，偶尔会断
                print(f"[guard] ⚠ 查 llm_call 失败（{type(e).__name__}: {e}），重连后继续守护", flush=True)
                try:
                    conn = M.connect(autocommit=True)
                    cur = conn.cursor()
                except Exception as e2:                  # noqa: BLE001
                    print(f"[guard] ⚠ 重连也失败（{e2}）—— 此刻没有守护，请人工盯着", flush=True)
                continue
            if row:
                print(f"\n[guard] 发现失败 llm_call.id={row[0]} stage={row[1]}：{row[2]}", flush=True)
                kill_tree(p)
                p.wait()
                print("[guard] 已结束整棵进程树。先查原因（error_text、CLI 会话记录），"
                      "找到原因之前不要重跑。", flush=True)
                sys.exit(3)
    except KeyboardInterrupt:
        kill_tree(p)
        raise
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
