#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把导览页要用的官网图片下载进仓库：web_api/tour/img/<馆>/<序号>.<扩展名>。

    python3 tour_images.py --museum wmhg --dry-run               # 只列出要下哪些
    python3 tour_images.py --museum wmhg --allow-expired-cert    # 下载还没有的
    python3 tour_images.py --museum wmhg --allow-expired-cert --refresh   # 全部重下

图片地址取库里的 artwork.image_url，只下页面上会出现的那些：路线上的各站、
站内在展的藏品、目的地卡片的封面。**下完要重跑 tour_build.py** —— 页面只显示
生成那一刻已经在仓库里的图片，没下到的站就不显示照片框。

为什么不让页面直接引用官网的图：伪满皇宫官网的证书 2026-03 过期后一直没续，
浏览器会拒绝加载；而且游客在院子里用流量，图片跟页面放在一起才稳。

证书：只对 wmhg_site_scrape.EXPIRED_CERT_HOSTS 登记过的域名、只跳过有效期、
且要显式给 --allow-expired-cert 才用（tls.ssl_ctx_allow_expired，证书链与域名照常校验）。
其余域名一律正常校验。

失败不留半截文件，逐条报告，退出码 3。官网在境外网络上连不上（AGENTS.md 第 16 条），
超时多半是这个原因，换到国内网络再跑。
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import meta_lib
import route_plan as RP
from export_excel import ZH
from tls import ssl_ctx, ssl_ctx_allow_expired
from wmhg_site_scrape import EXPIRED_CERT_HOSTS

HERE = pathlib.Path(__file__).resolve().parent
TOUR_DIR = HERE.parent.parent / "web_api" / "tour"

UA = "Mozilla/5.0 (compatible; ari-tour-images/1.0)"
TIMEOUT = 30
PAUSE_S = 2                     # 两次请求之间停一停，不给官网添负担
MAX_BYTES = 5 * 1024 * 1024
WARN_BYTES = 600 * 1024         # 超过这个数手机上加载偏慢，报出来由人决定要不要压
MAGIC = {".jpg": (b"\xff\xd8",), ".jpeg": (b"\xff\xd8",), ".png": (b"\x89PNG",),
         ".webp": (b"RIFF",)}


def wanted(mk):
    """{序号: (名称, 图片地址或 None)}：页面上会出现的全部条目。"""
    try:
        D = importlib.import_module(f"{mk}_route_data")
        T = importlib.import_module(f"{mk}_tour_data")
    except ModuleNotFoundError as e:
        sys.exit(f"缺 {e.name}.py —— 这个馆还没有路线数据或导览配置")
    conn = meta_lib.connect()
    items = RP.load_items(conn, mk)
    cur = conn.cursor()
    cur.execute("SELECT a.source_seq, a.image_url FROM artwork a JOIN museum m ON m.id = a.museum_id"
                " WHERE m.key_name = %s", (mk,))
    urls = dict(cur.fetchall())
    conn.close()
    RP.check_registry(items, D)
    seqs = [s[0] for s in D.STOPS]
    seqs += [o["seq"] for objs in RP.highlights(items, D).values() for o in objs]
    seqs.append(T.CARD["cover_seq"])
    return {s: (items[s]["name"][ZH], urls.get(s)) for s in dict.fromkeys(seqs)}


def existing(d: pathlib.Path, seq: int):
    return next((p for ext in MAGIC if (p := d / f"{seq}{ext}").is_file()), None)


def fetch(url: str, allow_expired: bool) -> bytes:
    host = urllib.parse.urlsplit(url).hostname or ""
    expired = any(host == h or host.endswith("." + h) for h in EXPIRED_CERT_HOSTS)
    if expired and not allow_expired:
        sys.exit(f"{host} 的证书已过期（登记在 EXPIRED_CERT_HOSTS）。要下它的图片须显式加 "
                 "--allow-expired-cert：只跳过有效期，证书链与域名照常校验")
    ctx = ssl_ctx_allow_expired() if expired else ssl_ctx()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        ctype = r.headers.get("Content-Type", "")
        body = r.read(MAX_BYTES + 1)
    if not ctype.startswith("image/"):
        raise ValueError(f"回的不是图片（Content-Type: {ctype or '无'}）")
    if len(body) > MAX_BYTES:
        raise ValueError(f"超过 {MAX_BYTES // 1024 // 1024} MB")
    return body


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--museum", required=True, help="museum.key_name")
    ap.add_argument("--dry-run", action="store_true", help="只列出要下哪些，不联网")
    ap.add_argument("--refresh", action="store_true", help="已有的也重新下载")
    ap.add_argument("--allow-expired-cert", action="store_true",
                    help="只对 EXPIRED_CERT_HOSTS 里登记的域名跳过证书有效期检查")
    args = ap.parse_args()

    want = wanted(args.museum)
    out = TOUR_DIR / "img" / args.museum
    no_url = [f"{s} {name}" for s, (name, url) in want.items() if not url]
    todo, have = [], 0
    for seq, (name, url) in want.items():
        if not url:
            continue
        ext = pathlib.PurePosixPath(urllib.parse.urlsplit(url).path).suffix.lower()
        if ext not in MAGIC:
            sys.exit(f"seq {seq} 的图片地址扩展名 {ext!r} 不在 {sorted(MAGIC)} 里：{url}")
        old = existing(out, seq)
        if old and not args.refresh:
            have += 1
            continue
        todo.append((seq, name, url, ext, old))

    print(f"页面上会出现 {len(want)} 个条目：库里有图片地址 {len(want) - len(no_url)} 个，"
          f"仓库里已有 {have} 张，待下载 {len(todo)} 张")
    if no_url:
        print(f"库里没有图片地址的 {len(no_url)} 个（这些站不显示照片）：" + "、".join(no_url))
    if args.dry_run:
        for seq, name, url, *_ in todo:
            print(f"   {seq:3d} {name}  {url}")
        return
    if not todo:
        return

    out.mkdir(parents=True, exist_ok=True)
    failed, big = [], []
    for i, (seq, name, url, ext, old) in enumerate(todo):
        if i:
            time.sleep(PAUSE_S)
        try:
            body = fetch(url, args.allow_expired_cert)
            if not body.startswith(MAGIC[ext]):
                raise ValueError(f"文件头不是 {ext} 图片")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            failed.append(f"{seq} {name}：{type(e).__name__} {str(e)[:100]}")
            print(f"   ✗ {seq:3d} {name}：{type(e).__name__} {str(e)[:100]}")
            if len(failed) == 3 and i == 2:
                # 头三张全失败，多半是整个站连不上，不必把剩下的挨个等到超时
                print("   头三张全部失败，停止。")
                failed += [f"{s} {n}：未尝试" for s, n, *_ in todo[3:]]
                break
            continue
        tmp = out / f".{seq}{ext}.part"
        tmp.write_bytes(body)
        if old and old.suffix != ext:
            old.unlink()                       # 同一序号换了格式，不留两张
        tmp.replace(out / f"{seq}{ext}")
        if len(body) > WARN_BYTES:
            big.append(f"{seq} {name}（{len(body) // 1024} KB）")
        print(f"   ✓ {seq:3d} {name}  {len(body) // 1024} KB")

    if big:
        print(f"偏大的 {len(big)} 张（超过 {WARN_BYTES // 1024} KB）：" + "、".join(big))
    print(f"下完了，成功 {len(todo) - len(failed)}、失败 {len(failed)}。"
          f"重跑 tour_build.py --museum {args.museum} 让页面带上照片。")
    if failed:
        print("失败的：\n   " + "\n   ".join(failed))
        sys.exit(3)


if __name__ == "__main__":
    main()
