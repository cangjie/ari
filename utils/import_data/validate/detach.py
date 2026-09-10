#!/usr/bin/env python3
"""把 go.sh 放到一个独立的会话里跑，脱离 Claude Code 的进程组。

**为什么 nohup 不够。** 2026-09-08 夜里用 `nohup ./go.sh &` 启动，
看守本身工作正常（额度耗尽被正确判为外部条件、进入 5 分钟轮询等待），
但 Claude Code 会话退出时整个进程组被收走，看守跟着一起没了 ——
`nohup` 只挡 SIGHUP，挡不住进程组被杀。
os.setsid() 让子进程成为新会话的首进程，父进程死了也不受影响。
"""
import os, subprocess, sys, pathlib

here = pathlib.Path(__file__).resolve().parent
log = (here / "detach.out").open("ab")
p = subprocess.Popen(
    ["/bin/zsh", str(here / "go.sh")],
    cwd=str(here.parent),
    stdout=log, stderr=log, stdin=subprocess.DEVNULL,
    start_new_session=True,          # = os.setsid()，关键就是这一行
)
print(f"已脱离会话启动，PID {p.pid}（新会话首进程）")
