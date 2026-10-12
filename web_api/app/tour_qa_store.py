"""导览站「游客互动」的存取：`tour_topic`（问答）与 `tour_qa_setting`（提问条数上限）。

建表语句在 `web_api/sql/tour_qa.sql`。几条约定：

- 关联用软键 `(museum_key, place_id)`，不建外键（AGENTS.md 第 6 条）。
- 每个操作一条短连接、自动提交。调模型的那几秒到几十秒里不占着事务 ——
  挂着的事务会锁行，进程异常退出时还会留在服务器上睡到 wait_timeout。
- 连接带读写超时：pymysql 默认不设，连接被悄悄掐断时会永远等下去。
- 上限每次提问现读、不缓存，改库之后的下一条提问就按新值算。
"""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .tour_qa_llm import Answer

SETTING_NAMES = ("per_visitor_per_day", "per_ip_per_hour", "site_per_day")
PENDING_STALE_S = 180      # 等了这么久还没答完的，当作失败：进程多半已经不在了
ERROR_MAX = 500

_COLUMNS = ("id, museum_key, place_id, visitor_id, question, answer, status, "
            "is_public, valid, reused_from, created_at")


class StoreNotConfigured(Exception):
    """缺数据库配置或缺 pymysql。接口据此回 503。"""


class SettingMissing(Exception):
    """上限表里缺一行。不拿内置默认值顶替 —— 接口回 503，日志里写明缺哪一项。"""


@dataclass
class Topic:
    id: int
    museum_key: str
    place_id: str
    visitor_id: str
    question: str
    answer: str | None
    status: str                # pending / answered / failed
    is_public: bool | None     # None = 模型还没判
    valid: bool
    reused_from: int | None
    created_at: datetime       # UTC，不带时区

    @property
    def public(self) -> bool:
        return self.valid and self.status == "answered" and bool(self.is_public)


def _topic(row: dict) -> Topic:
    return Topic(
        id=row["id"], museum_key=row["museum_key"], place_id=row["place_id"],
        visitor_id=row["visitor_id"], question=row["question"], answer=row["answer"],
        status=row["status"],
        is_public=None if row["is_public"] is None else bool(row["is_public"]),
        valid=bool(row["valid"]), reused_from=row["reused_from"], created_at=row["created_at"],
    )


class MySqlStore:
    def __init__(self) -> None:
        cnf = os.environ.get("ARI_DB_DEFAULTS_FILE", "").strip()
        if not cnf:
            raise StoreNotConfigured("没有配置 ARI_DB_DEFAULTS_FILE")
        self._cnf = str(Path(cnf).expanduser())
        if not Path(self._cnf).is_file():
            raise StoreNotConfigured(f"ARI_DB_DEFAULTS_FILE 指的文件不存在：{self._cnf}")
        self._db = os.environ.get("ARI_DB_NAME", "ari")
        try:
            import pymysql
        except ImportError as exc:
            raise StoreNotConfigured("没有安装 PyMySQL 这个包") from exc
        self._pymysql = pymysql

    @contextmanager
    def _cursor(self):
        conn = self._pymysql.connect(
            read_default_file=self._cnf, database=self._db, charset="utf8mb4", autocommit=True,
            connect_timeout=5, read_timeout=15, write_timeout=15,
            cursorclass=self._pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cur:
                yield cur
        finally:
            conn.close()

    # -------------------------------------------------------- 上限
    def settings(self) -> dict[str, int]:
        with self._cursor() as cur:
            cur.execute("SELECT name, value FROM tour_qa_setting")
            found = {row["name"]: int(row["value"]) for row in cur.fetchall()}
        missing = [name for name in SETTING_NAMES if name not in found]
        if missing:
            raise SettingMissing("tour_qa_setting 缺少：" + "、".join(missing))
        return {name: found[name] for name in SETTING_NAMES}

    def count_visitor_day(self, visitor_id: str) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM tour_topic WHERE visitor_id = %s "
                        "AND created_at > UTC_TIMESTAMP() - INTERVAL 24 HOUR", (visitor_id,))
            return int(cur.fetchone()["n"])

    def count_site_day(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM tour_topic "
                        "WHERE created_at > UTC_TIMESTAMP() - INTERVAL 24 HOUR")
            return int(cur.fetchone()["n"])

    def has_pending(self, visitor_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM tour_topic WHERE visitor_id = %s AND status = 'pending' "
                        "AND created_at > UTC_TIMESTAMP() - INTERVAL %s SECOND LIMIT 1",
                        (visitor_id, PENDING_STALE_S))
            return cur.fetchone() is not None

    # -------------------------------------------------------- 问答
    def find_answered(self, prompt_hash: str) -> Topic | None:
        """同一份提示词已经答过的那一条。只认真正调过模型的行，不认复用出来的行。"""
        with self._cursor() as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM tour_topic WHERE prompt_hash = %s "
                        "AND status = 'answered' AND reused_from IS NULL ORDER BY id DESC LIMIT 1",
                        (prompt_hash,))
            row = cur.fetchone()
        return _topic(row) if row else None

    def insert_pending(self, museum_key: str, place_id: str, visitor_id: str,
                       question: str, prompt_hash: str) -> int:
        with self._cursor() as cur:
            cur.execute("INSERT INTO tour_topic (museum_key, place_id, visitor_id, question, "
                        "status, prompt_hash, created_at) "
                        "VALUES (%s, %s, %s, %s, 'pending', %s, UTC_TIMESTAMP())",
                        (museum_key, place_id, visitor_id, question, prompt_hash))
            return int(cur.lastrowid)

    def insert_reused(self, museum_key: str, place_id: str, visitor_id: str,
                      question: str, prompt_hash: str, source: Topic) -> int:
        """沿用一条不公开的旧答案：只有提问者自己看得到，所以另存一行，不调模型。"""
        with self._cursor() as cur:
            cur.execute("INSERT INTO tour_topic (museum_key, place_id, visitor_id, question, answer, "
                        "status, is_public, prompt_hash, reused_from, created_at, answered_at) "
                        "VALUES (%s, %s, %s, %s, %s, 'answered', 0, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())",
                        (museum_key, place_id, visitor_id, question, source.answer, prompt_hash, source.id))
            return int(cur.lastrowid)

    def finish(self, topic_id: int, answer: Answer) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE tour_topic SET answer = %s, status = 'answered', is_public = %s, "
                        "model = %s, effort = %s, prompt_tokens = %s, completion_tokens = %s, "
                        "cached_tokens = %s, latency_ms = %s, answered_at = UTC_TIMESTAMP() WHERE id = %s",
                        (answer.text, int(answer.on_topic), answer.model, answer.effort,
                         answer.prompt_tokens, answer.completion_tokens, answer.cached_tokens,
                         answer.latency_ms, topic_id))

    def fail(self, topic_id: int, error: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE tour_topic SET status = 'failed', error = %s WHERE id = %s",
                        (error[:ERROR_MAX], topic_id))

    def get(self, topic_id: int) -> Topic | None:
        with self._cursor() as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM tour_topic WHERE id = %s", (topic_id,))
            row = cur.fetchone()
        return _topic(row) if row else None

    def list_topics(self, museum_key: str, place_id: str, visitor_id: str | None,
                    before: int | None, limit: int) -> list[Topic]:
        """别人看得到的是已回答且公开的；提问者另外看得到自己的全部。新的在前。"""
        sql = (f"SELECT {_COLUMNS} FROM tour_topic WHERE museum_key = %s AND place_id = %s AND valid = 1 "
               "AND ((status = 'answered' AND is_public = 1) OR visitor_id = %s)")
        args: list = [museum_key, place_id, visitor_id or ""]
        if before is not None:
            sql += " AND id < %s"
            args.append(before)
        sql += " ORDER BY id DESC LIMIT %s"
        args.append(limit)
        with self._cursor() as cur:
            cur.execute(sql, args)
            return [_topic(row) for row in cur.fetchall()]
