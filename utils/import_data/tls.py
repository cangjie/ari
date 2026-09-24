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


# OpenSSL 的 X509_V_FLAG_NO_CHECK_TIME（1.1.0 起有）。Python 的 ssl 模块没导出这个常量，
# 但 verify_flags 的 setter 会把整数原样交给 X509_VERIFY_PARAM_set_flags。
_NO_CHECK_TIME = 0x200000


def ssl_ctx_allow_expired() -> ssl.SSLContext:
    """只跳过证书**有效期**检查的上下文，证书链与域名照常校验。

    用途只有一种：对方网站的证书过期了没续（2026-09-24 伪满皇宫官网）。
    这不是关掉校验 —— 换一张不是受信根签发的、或签给别的域名的证书，照样报错。
    本机 OpenSSL 若不认这个标志位，结果是继续报「已过期」，失败方向是安全的。

    只能由调用方按域名显式选用，**不要拿它当默认上下文**。
    """
    ctx = ssl_ctx()
    ctx.verify_flags |= _NO_CHECK_TIME
    return ctx


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
