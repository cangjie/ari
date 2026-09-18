#!/usr/bin/env python3
"""HTTPS 的 TLS 上下文。所有走网络的脚本共用。

⚠ **python.org 版 Python 装在 macOS 上时不带根证书** —— 它指向
`…/etc/openssl/cert.pem`，而那个文件要跑一次 `Install Certificates.command`
才会建出来。没建的机器上，任何 HTTPS 请求都报
`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`。

2026-09-16 本机就是这样。更麻烦的是**失败信息长得像网络问题** ——
`gemini_api` 把它归进「Transient 网络错误」并重试，6 次调用全挂，
看起来像限流，实际一个字节都没发出去。

这里显式兜住：默认信任库不可用就用 certifi，certifi 也没装就退出并说清怎么修。
**绝不静默降级成不校验证书** —— 关掉校验等于把中间人攻击的门打开，比报错严重得多。
"""
from __future__ import annotations

import pathlib
import ssl
import sys


def ssl_ctx() -> ssl.SSLContext:
    if pathlib.Path(ssl.get_default_verify_paths().openssl_cafile or "").exists():
        return ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        sys.exit("本机 Python 没有可用的根证书，且未装 certifi。\n"
                 "修法二选一：\n"
                 "  · pip install certifi\n"
                 "  · 跑一次 /Applications/Python 3.x/Install Certificates.command")
    return ssl.create_default_context(cafile=certifi.where())
