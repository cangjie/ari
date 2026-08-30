#!/usr/bin/env python3
"""metadata 读写的公共函数。所有填充脚本都应该走这里，不要自己拼 SQL。

**为什么要有这个模块**

metadata 是纯 key-value，键和值都存进 content / content_text 双语（见
schema_meta.sql）。手工写这三张表有三个坑，每个都不报错、只是静默出错：

  1. content ID 要在 2,000,000 段里自己分配，撞号或越界都不会当场发现；
  2. 两个语种必须都插，漏一个就成了缺译，要等导出时才暴露；
  3. 值必须按文本去重 —— 「清」被几百件展品共用应该只占一行。不去重的话
     content 表会迅速膨胀，且改一处译文改不全（AGENTS.md 第 1 条的初衷）。

ensure_key / ensure_value 把这三件事包掉，都是幂等的：已存在就返回既有ID，
不重复建。

**加键随时可加**：ensure_key 就是加键的全部动作，没有 DDL、不锁表。
meta_key 是普通表不是 MySQL ENUM，44 这个数字没有约束力。
"""
from __future__ import annotations

import os

import pymysql

CONTENT_ID_BASE = 2_000_000          # 本数据集的内容ID段，见 schema_meta.sql
KIND_KEY = "meta_key_name"
KIND_VALUE = "meta_value_text"

# content_text.source 是固定 ENUM：原始 / AI翻译 / 存疑 / 人工校对。
# 中文一般是源数据或人工拟定的原文，英文多为模型生成，据实标注。
SRC_ZH, SRC_EN = "原始", "AI翻译"


def connect(defaults_file: str = "~/.my.cnf", autocommit: bool = False):
    """按 AGENTS.md 硬性约定，口令走选项文件，不进命令行也不进 shell 历史。"""
    return pymysql.connect(read_default_file=os.path.expanduser(defaults_file),
                           charset="utf8mb4", autocommit=autocommit)


def _next_cid(cur) -> int:
    """本段内的下一个可用 content ID。

    只在 >= CONTENT_ID_BASE 的范围里取 MAX，避免被榜单段/展品段的 ID 带跑。
    """
    cur.execute("SELECT COALESCE(MAX(id), %s) FROM content WHERE id >= %s",
                (CONTENT_ID_BASE, CONTENT_ID_BASE))
    return cur.fetchone()[0] + 1


def _new_content(cur, kind: str, zh: str, en: str) -> int:
    cid = _next_cid(cur)
    cur.execute("INSERT INTO content (id, kind) VALUES (%s, %s)", (cid, kind))
    cur.executemany(
        "INSERT INTO content_text (content_id, lang, text, source) VALUES (%s,%s,%s,%s)",
        [(cid, "zh-CN", zh, SRC_ZH), (cid, "en", en, SRC_EN)])
    return cid


def ensure_key(cur, key_name: str, zh: str, en: str,
               note: str | None = None, sort_order: int | None = None) -> str:
    """确保键存在，返回 key_name。已存在则原样返回，不覆盖既有译名与备注。

    加新键的全部动作就是调用它一次 —— 没有 DDL，随时可加。
    """
    cur.execute("SELECT key_name FROM meta_key WHERE key_name = %s", (key_name,))
    if cur.fetchone():
        return key_name
    if sort_order is None:
        cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 FROM meta_key")
        sort_order = cur.fetchone()[0]
    cid = _new_content(cur, KIND_KEY, zh, en)
    cur.execute("INSERT INTO meta_key (key_name, name_cid, note, sort_order)"
                " VALUES (%s,%s,%s,%s)", (key_name, cid, note, sort_order))
    return key_name


def ensure_value(cur, zh: str, en: str, cache: dict | None = None) -> int:
    """确保这段值文本存在，返回 content ID。按 (中文, 英文) 整体去重。

    只比中文是不够的：同一个中文在不同语境下英文可能不同（如「金」既是
    Gold 也可能是 Jin 朝），合并会把译文改错。两边都相同才算同一段内容。

    cache 传一个 dict 可在单次批量导入内省掉重复查询；跨进程不需要，
    因为下面的 SQL 查询本身走 idx_ct_lang_text (lang, text) 索引。
    """
    if cache is not None and (zh, en) in cache:
        return cache[(zh, en)]
    cur.execute("""SELECT z.content_id FROM content_text z
                   JOIN content c ON c.id = z.content_id AND c.kind = %s
                   JOIN content_text e ON e.content_id = z.content_id AND e.lang = 'en'
                   WHERE z.lang = 'zh-CN' AND z.text = %s AND e.text = %s
                   LIMIT 1""", (KIND_VALUE, zh, en))
    row = cur.fetchone()
    cid = row[0] if row else _new_content(cur, KIND_VALUE, zh, en)
    if cache is not None:
        cache[(zh, en)] = cid
    return cid


def set_meta(cur, museum_key: str, source_seq: int, key_name: str,
             values: list[tuple[str, str]], *, source_key: str,
             value_nums: list | None = None,
             source: str | None = None, confidence: str = "medium",
             filled_by: str = "manual", cache: dict | None = None) -> int:
    """写一件展品在某个键下、**某一个来源给出**的全部取值。

    values 是 [(中文, 英文), ...]；一个键可以有多个值，如材质「木/砖/石」。
    value_nums 与 values 等长，非数字键传 None。

    **只清空同一 source_key 的旧值**，别的来源原样保留。这是有意的：
    抓取来的数据彼此矛盾是常态（源文件说 pre-contact 而 Wikidata 标 1825 年），
    冲突本身是有用信息，不该由写入方替读取方挑一个赢家。
    """
    if value_nums is not None and len(value_nums) != len(values):
        raise ValueError("value_nums 与 values 长度不一致")
    cur.execute("DELETE FROM artwork_meta WHERE museum_key=%s AND source_seq=%s"
                " AND key_name=%s AND source_key=%s",
                (museum_key, source_seq, key_name, source_key))
    rows = []
    for i, (zh, en) in enumerate(values):
        cid = ensure_value(cur, zh, en, cache)
        num = value_nums[i] if value_nums else None
        rows.append((museum_key, source_seq, key_name, source_key, i, cid, num,
                     source, confidence, filled_by))
    cur.executemany(
        "INSERT INTO artwork_meta (museum_key, source_seq, key_name, source_key,"
        " ord, value_cid, value_num, source, confidence, filled_by)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    return len(rows)
