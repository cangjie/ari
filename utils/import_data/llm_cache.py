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


def call(fn, *, provider: str, model: str, effort: str | None,
         stage: str, system: str, user: str, schema: dict,
         museum_key: str | None = None, scope: str | None = None,
         seqs=None, prompt_version: str | None = None,
         refresh: bool = False) -> dict:
    """查缓存 -> 命中直接返回；未命中调 fn 并落库。

    fn() 须返回 (dict, usage)；usage 可为 None。
    seqs 是本次调用覆盖的 source_seq 列表，写进 llm_call_item
    （**不是 artwork.id** —— 那个每次重灌都重新分配，见 schema_llm_cache.sql）。
    refresh=True 时跳过读缓存但照常写（用于确认「不是缓存的锅」）。
    """
    key = cache_key(provider, model, effort, system, user, schema)
    conn = _connect()

    if conn and not refresh:
        cur = conn.cursor()
        cur.execute("SELECT id, response_json FROM llm_call WHERE cache_key = %s", (key,))
        row = cur.fetchone()
        if row:
            _stats["hit"] += 1
            # 命中也补一次关联：首次写入若失败过，这里能自愈
            _link_items(conn, row[0], museum_key, seqs)
            return json.loads(row[1])

    _stats["miss"] += 1
    t0 = time.time()
    try:
        data, usage = fn()
    except Exception as e:                       # noqa: BLE001
        # 失败也要留痕：token 可能已经烧掉了，而且整批 429 这类事故只有靠它才看得见。
        # **cache_key 写 NULL** —— 否则下次同样的提示词会命中这条失败记录，
        # 把一次报错永久固化成「答案」。
        _stats["error"] += 1
        if conn:
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
                     int((time.time() - t0) * 1000),
                     f"{type(e).__name__}: {e}"[:60000]))
            except Exception as e2:              # noqa: BLE001
                print(f"  [warn] 失败记录写入也失败了（{type(e2).__name__}: {e2}）",
                      file=sys.stderr)
        raise
    latency = int((time.time() - t0) * 1000)

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
            # lastrowid 为 0 说明撞上了 ON DUPLICATE（并发下另一个进程先写了），
            # 回查一次拿真正的 id，否则关联会挂到 0 上
            call_id = cur.lastrowid
            if not call_id:
                cur.execute("SELECT id FROM llm_call WHERE cache_key = %s", (key,))
                r = cur.fetchone()
                call_id = r[0] if r else None
            _link_items(conn, call_id, museum_key, seqs)
        except Exception as e:                   # noqa: BLE001
            # 写缓存失败不能让整轮白跑 —— 答案已经拿到了，钱也已经花了
            print(f"  [warn] 缓存写入失败（{type(e).__name__}: {e}），本次结果未入库",
                  file=sys.stderr)
    return data


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
