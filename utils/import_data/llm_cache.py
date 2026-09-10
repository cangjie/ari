#!/usr/bin/env python3
"""LLM 调用的缓存与计量。tier_v3.py 与 audit_meta.py 的 ask() 都从这里过。

**为什么要有这个模块**

2026-09-03 复盘：两天约 100 美元，其中约一半是判据改动后作废重跑的。
原来的 JSONL 断点续跑只按 seq 记「这件做过了」，于是：

  · 换 --out-dir 就等于全额重新付费（tier_v3_out → tier_v3_out_ev → run2/…）；
  · 改了判据沿用旧 JSONL 会**静默返回旧提示词下的答案**，为安全只能整轮删掉重跑。

本模块把键换成 sha256(provider|model|effort|system|user|schema)：
提示词一个字符没变就必然命中（不花钱），变了就必然不命中（不会拿到旧答案）。
两个性质是同一个哈希带来的，不需要额外的失效逻辑。

另外把 resp.usage 落库 —— 原来的 ask() 拿到响应只取 content，用量直接丢弃，
以致「100 美元花在哪」事后只能靠数 JSONL 行数倒推。

**用法**

    import llm_cache
    data = llm_cache.call(
        lambda: 真正发请求并返回 (dict, usage对象或None),
        provider="openai", model=model, effort=effort,
        stage="tier_stage1", museum_key="pem", scope="seq 1-12",
        system=system, user=user, schema=schema)

`fn` 只在未命中时被调用，返回 `(解析好的 dict, usage)`；usage 给 None 也可以，
只是该行的 token 列为空。

**缓存不可用时不阻塞调用。** 连不上库、表不存在，都只打一行 warn 然后照常发请求
—— 缓存是省钱手段，不该成为跑不动的理由。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

# 每百万 token 的美元单价 (input, cached_input, output)。
#
# **默认留空是有意的：本项目只记 token 数，不折算金额**（2026-09-03 决定）。
# token 是客观事实，单价会变、会有折扣、会随账户不同 —— 把两者混在一列里，
# 日后没人分得清某个数字是当时的真实支出还是某次估算的残留。
# 要临时看金额就把实际单价填进来；不填时 cost_usd 恒为 NULL，
# **绝不按「差不多的型号」套一个数字**：猜出来的价会被当成账目读，比没有更糟。
PRICES: dict[str, tuple[float, float, float]] = {
    # 例：'gpt-5.6-sol': (1.25, 0.125, 10.00),
}

_conn = None
_available = None          # None=还没试过；True/False=试过的结果
_stats = {"hit": 0, "miss": 0, "error": 0, "legacy_skip": 0}


def _connect():
    """惰性连库。失败只警告不抛 —— 缓存不该成为跑不动的理由。"""
    global _conn, _available
    if _available is not None:
        return _conn
    try:
        import meta_lib
        _conn = meta_lib.connect(autocommit=True)
        cur = _conn.cursor()
        cur.execute("SELECT 1 FROM llm_call LIMIT 1")
        cur.fetchall()
        _available = True
    except Exception as e:                       # noqa: BLE001 —— 任何原因都降级
        print(f"  [warn] LLM 缓存不可用（{type(e).__name__}: {e}），本轮全部实调",
              file=sys.stderr)
        _conn, _available = None, False
    return _conn


def cache_key(provider: str, model: str, effort: str | None,
              system: str, user: str, schema: dict) -> str:
    """键含提示词与 schema 全文。

    用 \\x00 分隔而不是普通字符：分隔符若可能出现在字段里，
    ("a|b", "c") 与 ("a", "b|c") 会撞成同一个键。
    """
    schema_txt = json.dumps(schema, sort_keys=True, ensure_ascii=False)
    raw = "\x00".join([provider, model, effort or "", system, user, schema_txt])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _usage_cols(usage) -> dict:
    """从 OpenAI / Anthropic 的 usage 对象里取数，取不到就留空。

    两家的字段名不同，且同一家不同版本也在变，所以逐个 getattr 试，
    **绝不假设某个字段一定存在** —— 少记一列比整轮崩掉好。
    """
    if usage is None:
        return {}
    g = lambda o, *names: next(                                   # noqa: E731
        (v for n in names if (v := getattr(o, n, None)) is not None), None)
    det_in = getattr(usage, "prompt_tokens_details", None) or \
             getattr(usage, "input_tokens_details", None)
    det_out = getattr(usage, "completion_tokens_details", None) or \
              getattr(usage, "output_tokens_details", None)
    return {
        "prompt_tokens": g(usage, "prompt_tokens", "input_tokens"),
        "completion_tokens": g(usage, "completion_tokens", "output_tokens"),
        "cached_tokens": (g(det_in, "cached_tokens") if det_in else
                          g(usage, "cache_read_input_tokens")),
        "reasoning_tokens": g(det_out, "reasoning_tokens") if det_out else None,
    }


def estimate_cost(model: str, cols: dict) -> float | None:
    """按 PRICES 估价。型号未登记返回 None，不猜。"""
    p = PRICES.get(model)
    if not p or cols.get("prompt_tokens") is None:
        return None
    p_in, p_cached, p_out = p
    cached = cols.get("cached_tokens") or 0
    fresh = max(0, (cols.get("prompt_tokens") or 0) - cached)
    out = cols.get("completion_tokens") or 0          # reasoning 已含在 completion 里
    return (fresh * p_in + cached * p_cached + out * p_out) / 1_000_000


def _link_items(conn, call_id: int, museum_key: str | None, seqs) -> None:
    """写 llm_call_item：这次调用覆盖了哪几件展品。

    用 INSERT IGNORE 而非普通 INSERT —— 命中缓存时也会走这里补齐关联，
    重复插入是常态不是异常。

    artwork_id / museum_id 是便利列，这里顺手按软键解析一次填上。
    **它们会在下次 import_artworks.py 之后失效**（那边清空三表并重置
    AUTO_INCREMENT），届时要跑 `llm_cache.py --refresh-ids`。
    权威键始终是 (museum_key, source_seq)，那两列只是省一次 JOIN。
    """
    if not (call_id and museum_key and seqs):
        return
    rows = [(call_id, museum_key, int(s)) for s in sorted(set(seqs))]
    try:
        cur = conn.cursor()
        cur.executemany(
            "INSERT IGNORE INTO llm_call_item (call_id, museum_key, source_seq) "
            "VALUES (%s,%s,%s)", rows)
        # 便利列：解析不到就留 NULL，不报错 —— 展品可能还没导入
        cur.execute(
            """UPDATE llm_call_item i
                 JOIN museum m  ON m.key_name = i.museum_key
                 LEFT JOIN artwork a ON a.museum_id = m.id AND a.source_seq = i.source_seq
                  SET i.museum_id = m.id, i.artwork_id = a.id,
                      i.ids_synced_at = NOW(3)
                WHERE i.call_id = %s""", (call_id,))
        cur.execute(
            """UPDATE llm_call c JOIN museum m ON m.key_name = c.museum_key
                  SET c.museum_id = m.id, c.ids_synced_at = NOW(3)
                WHERE c.id = %s""", (call_id,))
    except Exception as e:                       # noqa: BLE001
        print(f"  [warn] 关联写入失败（{type(e).__name__}: {e}）", file=sys.stderr)


def refresh_ids() -> tuple[int, int, int]:
    """按软键重新解析 artwork_id / museum_id。**每次 import_artworks.py 之后必跑。**

    返回 (llm_call 更新行数, llm_call_item 更新行数, 解析不到 artwork 的行数)。

    为什么需要它：import_artworks.py 对 museum/gallery/artwork 三表
    DELETE + ALTER AUTO_INCREMENT = 1，所以这两列每次导入后都指向错误的行。
    实测 2026-09-03 加入 mfa_boston_ext 后，PEM 的 museum.id 由 2 变 3、
    首件 artwork.id 由 204 变 4668 —— 而 PEM 本身一个字都没改。
    """
    conn = _connect()
    if not conn:
        raise SystemExit("连不上库")
    cur = conn.cursor()
    cur.execute("""UPDATE llm_call c
                     LEFT JOIN museum m ON m.key_name = c.museum_key
                      SET c.museum_id = m.id, c.ids_synced_at = NOW(3)""")
    n_call = cur.rowcount
    cur.execute("""UPDATE llm_call_item i
                     LEFT JOIN museum m ON m.key_name = i.museum_key
                     LEFT JOIN artwork a ON a.museum_id = m.id
                                        AND a.source_seq = i.source_seq
                      SET i.museum_id = m.id, i.artwork_id = a.id,
                          i.ids_synced_at = NOW(3)""")
    n_item = cur.rowcount
    cur.execute("SELECT COUNT(*) FROM llm_call_item WHERE artwork_id IS NULL")
    n_orphan = cur.fetchone()[0]
    return n_call, n_item, n_orphan


class Invalid(Exception):
    """validate 判定这次返回不可用。调用方可据此重试。"""


# 值得重试的瞬时故障。**按类名匹配而不是 import 具体异常类** —— 这里不该
# 依赖 openai/anthropic 任一 SDK 的内部类型，换供应商时也不必改这份名单。
# 认不出的异常一律原样抛出：宁可停下来让人看，也不要对着一个真 bug 空转三次。
# Transient 是 claude_cli 自己的类 —— 按类名匹配就不必 import 它，
# 也就不会让本模块依赖某个具体 provider。
_TRANSIENT = ("Transient",
              "APIConnectionError", "APITimeoutError", "RateLimitError",
              "InternalServerError", "APIStatusError", "ConnectionError",
              "ReadTimeout", "ConnectTimeout", "RemoteProtocolError")


def _transient(e: Exception) -> bool:
    return type(e).__name__ in _TRANSIENT


def call(fn, *, provider: str, model: str, effort: str | None,
         stage: str, system: str, user: str, schema: dict,
         museum_key: str | None = None, scope: str | None = None,
         seqs=None, prompt_version: str | None = None,
         refresh: bool = False, validate=None, retries: int = 2) -> dict:
    """查缓存 -> 命中直接返回；未命中调 fn 并落库。

    fn() 须返回 (dict, usage)；usage 可为 None。
    seqs 是本次调用覆盖的 source_seq 列表，写进 llm_call_item
    （**不是 artwork.id** —— 那个每次重灌都重新分配，见 schema_llm_cache.sql）。
    refresh=True 时跳过读缓存但照常写（用于确认「不是缓存的锅」）。

    【validate：为什么校验必须在缓存内部】
    2026-09-05 实测：一批 12 件的阶段一调用，模型只返回了 11 件（漏了 seq 3412）。
    API 层面完全成功、JSON 合法、schema 也过，于是被当成好答案存进缓存；
    而校验写在调用方（stage1 的漏评检查），发现时已经晚了 ——
    **重跑必然命中这条缓存、拿回同一个残缺答案、在同一处再崩**，
    一个跑了 5 小时的进程就这么卡死在第 285 次调用上。

    所以校验要在写缓存**之前**做。`validate(data)` 返回 falsy 或抛异常都算不通过：
    不通过就重试（换不到新答案时按 error 落库，`cache_key=NULL` 不污染缓存），
    重试用尽才抛 Invalid。给 error 行留痕是有意的 —— 那次调用的 token 已经花了。
    """
    key = cache_key(provider, model, effort, system, user, schema)
    conn = _connect()

    if conn and not refresh:
        cur = conn.cursor()
        cur.execute("SELECT id, response_json FROM llm_call WHERE cache_key = %s", (key,))
        row = cur.fetchone()
        if row:
            data = json.loads(row[1])
            # 缓存里的老答案也要过校验 —— 本次改造之前存进去的坏答案就靠这一步挡住
            if validate is not None:
                try:
                    ok = validate(data)
                except Exception:                    # noqa: BLE001
                    ok = False
                if not ok:
                    print(f"  [warn] 缓存里的答案未通过校验（{stage} {scope}），"
                          f"删除后重新请求", file=sys.stderr)
                    conn.cursor().execute("DELETE FROM llm_call WHERE id = %s", (row[0],))
                    row = None
            if row:
                _stats["hit"] += 1
                # 命中也补一次关联：首次写入若失败过，这里能自愈
                _link_items(conn, row[0], museum_key, seqs)
                return data

    _stats["miss"] += 1
    for attempt in range(retries + 1):
        # 瞬时故障（网络断、限流、网关 5xx）退避重试，不要让一次抖动打死整轮。
        # 2026-09-05 实测：一次 APIConnectionError 让跑了 20 次调用的审计整个退出，
        # 而 3 小时的活重启后要从断点重来。校验不过与请求失败走同一个重试计数。
        try:
            data, usage, latency = _once(fn, conn, provider, model, effort, stage,
                                         museum_key, scope, prompt_version,
                                         system, user, schema)
        except Exception as e:                   # noqa: BLE001
            if attempt >= retries or not _transient(e):
                raise
            wait = 5 * 2 ** attempt
            print(f"  [warn] {stage} {scope} 请求失败（{type(e).__name__}），"
                  f"{wait}s 后重试 {attempt + 1}/{retries}", file=sys.stderr)
            time.sleep(wait)
            continue
        if validate is None:
            break
        try:
            ok = validate(data)
        except Exception:                        # noqa: BLE001
            ok = False
        if ok:
            break
        # 校验没过：按 error 落库（cache_key=NULL，不污染缓存），换个种子再要一次。
        # token 已经花了，留痕才查得出「这一批为什么反复要」。
        _stats["error"] += 1
        _log_error(conn, provider, model, effort, stage, museum_key, scope,
                   prompt_version, system, user, schema, latency,
                   f"validate failed (attempt {attempt + 1}/{retries + 1})")
        print(f"  [warn] {stage} {scope} 返回未通过校验，"
              f"第 {attempt + 1}/{retries + 1} 次，重试中", file=sys.stderr)
    else:
        raise Invalid(f"{stage} {scope}：连试 {retries + 1} 次都没通过校验")

    if conn:
        cols = _usage_cols(usage)
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO llm_call
                   (cache_key, provider, model, effort, stage, museum_key, scope,
                    prompt_version, system_text, user_text, schema_sha, response_json,
                    prompt_tokens, cached_tokens, completion_tokens, reasoning_tokens,
                    cost_usd, latency_ms)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE id = id""",
                (key, provider, model, effort, stage, museum_key, scope,
                 prompt_version, system, user,
                 _sha(json.dumps(schema, sort_keys=True, ensure_ascii=False)),
                 json.dumps(data, ensure_ascii=False),
                 cols.get("prompt_tokens"), cols.get("cached_tokens"),
                 cols.get("completion_tokens"), cols.get("reasoning_tokens"),
                 estimate_cost(model, cols), latency))
            call_id = cur.lastrowid
            if not call_id:
                cur.execute("SELECT id FROM llm_call WHERE cache_key = %s", (key,))
                r = cur.fetchone()
                call_id = r[0] if r else None
            _link_items(conn, call_id, museum_key, seqs)
        except Exception as e:                   # noqa: BLE001
            print(f"  [warn] 缓存写入失败（{type(e).__name__}: {e}），本次结果未入库",
                  file=sys.stderr)
    return data


def _log_error(conn, provider, model, effort, stage, museum_key, scope,
               prompt_version, system, user, schema, latency, msg) -> None:
    """把一次不可用的调用记成 error 行。**cache_key 恒为 NULL**，不参与命中。"""
    if not conn:
        return
    try:
        conn.cursor().execute(
            """INSERT INTO llm_call
               (cache_key, provider, model, effort, stage, museum_key, scope,
                prompt_version, system_text, user_text, schema_sha, response_json,
                latency_ms, status, error_text)
               VALUES (NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'',%s,'error',%s)""",
            (provider, model, effort, stage, museum_key, scope, prompt_version,
             system, user,
             _sha(json.dumps(schema, sort_keys=True, ensure_ascii=False)),
             latency, msg[:60000]))
    except Exception as e:                       # noqa: BLE001
        print(f"  [warn] 失败记录写入也失败了（{type(e).__name__}: {e}）", file=sys.stderr)


def _once(fn, conn, provider, model, effort, stage, museum_key, scope,
          prompt_version, system, user, schema):
    """发一次请求，返回 (data, usage, latency_ms)。**只发不写缓存** ——
    写缓存归 call()，因为要等 validate 过了才能写。抛异常时先留痕再原样抛出。
    """
    t0 = time.time()
    try:
        data, usage = fn()
    except Exception as e:                       # noqa: BLE001
        # 失败也要留痕：token 可能已经烧掉了，整批 429 这类事故只有靠它才看得见。
        _stats["error"] += 1
        _log_error(conn, provider, model, effort, stage, museum_key, scope,
                   prompt_version, system, user, schema,
                   int((time.time() - t0) * 1000), f"{type(e).__name__}: {e}")
        raise
    return data, usage, int((time.time() - t0) * 1000)


def stats() -> dict:
    return dict(_stats)


def report() -> str:
    s = _stats
    n = s["hit"] + s["miss"]
    if not n:
        return "LLM 调用：0 次"
    return (f"LLM 调用：命中缓存 {s['hit']} / 实发 {s['miss']}"
            f"（命中率 {s['hit'] / n * 100:.0f}%）"
            + (f"，失败 {s['error']}" if s["error"] else ""))


def main() -> None:
    """`python3 llm_cache.py` 出一张成本表。"""
    import argparse
    ap = argparse.ArgumentParser(description="LLM 调用账目")
    ap.add_argument("--museum", default="")
    ap.add_argument("--since", default="", help="YYYY-MM-DD")
    ap.add_argument("--refresh-ids", action="store_true",
                    help="按 (museum_key, source_seq) 重新解析 artwork_id / museum_id。"
                         "**每次跑完 import_artworks.py 都要跑一次** —— 那边重置了 "
                         "AUTO_INCREMENT，这两列会全部指向错误的行，且不报错")
    args = ap.parse_args()

    if args.refresh_ids:
        n_call, n_item, n_orphan = refresh_ids()
        print(f"已刷新：llm_call {n_call} 行、llm_call_item {n_item} 行")
        if n_orphan:
            print(f"  [info] {n_orphan} 行解析不到 artwork（该馆尚未导入，或源表序号已变），"
                  f"artwork_id 置 NULL —— 软键仍然有效，不影响账目")
        return

    conn = _connect()
    if not conn:
        sys.exit("连不上库")
    where, params = ["1=1"], []
    if args.museum:
        where.append("museum_key = %s"); params.append(args.museum)
    if args.since:
        where.append("created_at >= %s"); params.append(args.since)
    cur = conn.cursor()
    cur.execute(f"""SELECT museum_key, stage, model, COUNT(*),
                           SUM(prompt_tokens), SUM(completion_tokens),
                           SUM(reasoning_tokens), SUM(cost_usd), SUM(is_legacy),
                           SUM(status = 'error')
                    FROM llm_call WHERE {' AND '.join(where)}
                    GROUP BY museum_key, stage, model
                    ORDER BY museum_key, stage""", params)
    rows = cur.fetchall()
    if not rows:
        print("（无记录）")
        return
    # token 是本表的主产出，所以给出「每次调用平均多少」与「推理占输出多少」——
    # 前者定位哪个阶段单次最贵，后者说明贵在推理还是贵在正文。
    # effort 调档只影响推理那一半，看不见占比就不知道该不该调。
    print(f"{'馆':14s} {'阶段':14s} {'型号':16s} {'次数':>6s} "
          f"{'输入tok':>10s} {'输出tok':>10s} {'推理tok':>10s} "
          f"{'推理占比':>7s} {'均输出/次':>9s} {'美元':>8s} {'回填':>5s} {'失败':>5s}")
    tc = td = te = 0
    tpi = tpo = tpr = 0
    for mk, st, md, n, pi, po, pr, cost, lg, er in rows:
        pi, po, pr = int(pi or 0), int(po or 0), int(pr or 0)
        tc += float(cost or 0); td += n; te += int(er or 0)
        tpi += pi; tpo += po; tpr += pr
        share = f"{pr / po * 100:.0f}%" if po else "—"
        per = f"{po / n:.0f}" if n else "—"
        # SUM() 回来的是 Decimal，:d 格式化不了 —— 必须显式转 int
        print(f"{mk or '—':14s} {st:14s} {md:16s} {n:6d} "
              f"{pi:10d} {po:10d} {pr:10d} {share:>7s} {per:>9s} "
              f"{('%.4f' % cost) if cost is not None else '—':>8s} "
              f"{int(lg or 0):5d} {int(er or 0):5d}")
    print(f"{'合计':14s} {'':14s} {'':16s} {int(td):6d} "
          f"{tpi:10d} {tpo:10d} {tpr:10d} "
          f"{(f'{tpr / tpo * 100:.0f}%' if tpo else '—'):>7s} "
          f"{(f'{tpo / td:.0f}' if td else '—'):>9s} "
          f"{(('%.4f' % tc) if tc else '—'):>8s} {'':5s} {te:5d}")
    if tc == 0:
        print("\n[note] 本项目只记 token，不折算金额（cost_usd 恒为 NULL）。"
              "临时要看美元就把单价填进 llm_cache.PRICES，token 数已存，可随时回算。")


if __name__ == "__main__":
    main()
