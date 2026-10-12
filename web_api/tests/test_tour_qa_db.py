"""`tour_qa_store.MySqlStore` 对着真库验一遍。默认跳过，要显式打开：

    ARI_QA_TEST_DB=1 ARI_DB_DEFAULTS_FILE=~/.my.cnf ./.venv/bin/python -m pytest tests/test_tour_qa_db.py -q

test_tour_qa.py 用的是假库，验不到这里的 SQL；改了 tour_qa_store.py 或表结构之后跑这一份。

只往 `tour_topic` 里写 museum_key = 'zz_selftest' 的行，结束时把这些行删掉；
**不改 `tour_qa_setting`**（那是线上正在用的上限）。所用账号要有 DELETE 权限 ——
服务自己的账号 `ari_web` 没有，要用管理账号的配置文件。
"""

import os
import uuid
from datetime import datetime, timezone

import pytest

from app.tour_qa_llm import Answer
from app.tour_qa_store import ERROR_MAX, SETTING_NAMES, MySqlStore

pytestmark = pytest.mark.skipif(os.environ.get("ARI_QA_TEST_DB") != "1",
                                reason="要连真库：设 ARI_QA_TEST_DB=1 与 ARI_DB_DEFAULTS_FILE")

MUSEUM = "zz_selftest"


def answer(text="回答。", on_topic=True):
    return Answer(text=text, on_topic=on_topic, model="selftest-model", effort="low",
                  prompt_tokens=1234, completion_tokens=56, cached_tokens=1024, latency_ms=789)


@pytest.fixture
def store():
    s = MySqlStore()
    with s._cursor() as cur:
        cur.execute("DELETE FROM tour_topic WHERE museum_key = %s", (MUSEUM,))
    yield s
    with s._cursor() as cur:
        cur.execute("DELETE FROM tour_topic WHERE museum_key = %s", (MUSEUM,))


@pytest.fixture
def ids():
    run = uuid.uuid4().hex
    return {"me": f"me-{run}", "you": f"you-{run}", "place": f"p_{run[:8]}", "hash": run * 2}


def test_limits_are_all_present(store):
    limits = store.settings()
    assert set(limits) == set(SETTING_NAMES) and all(isinstance(v, int) for v in limits.values())


def test_question_lifecycle_and_visibility(store, ids):
    me, you, place = ids["me"], ids["you"], ids["place"]
    question = "溥仪在这里住过吗？🏯"                       # 带一个四字节字符，验 utf8mb4

    first = store.insert_pending(MUSEUM, place, me, question, ids["hash"])
    row = store.get(first)
    assert (row.status, row.is_public, row.answer, row.valid, row.reused_from) == ("pending", None, None, True, None)
    assert row.question == question and not row.public
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - row.created_at).total_seconds()
    assert abs(age) < 120, f"created_at 应是 UTC，与本机相差 {age:.0f} 秒"
    assert store.has_pending(me) and not store.has_pending(you)
    assert store.count_visitor_day(me) == 1 and store.count_visitor_day(you) == 0
    assert store.count_site_day() >= 1
    assert store.list_topics(MUSEUM, place, you, None, 10) == [], "还没答完的别人看不到"
    assert [t.id for t in store.list_topics(MUSEUM, place, me, None, 10)] == [first]

    store.finish(first, answer("住过。\n第二行 🙂"))
    row = store.get(first)
    assert (row.status, row.is_public, row.answer) == ("answered", True, "住过。\n第二行 🙂") and row.public
    assert not store.has_pending(me)
    with store._cursor() as cur:
        cur.execute("SELECT model, effort, prompt_tokens, completion_tokens, cached_tokens, latency_ms, "
                    "answered_at FROM tour_topic WHERE id = %s", (first,))
        saved = cur.fetchone()
    assert (saved["model"], saved["effort"], saved["prompt_tokens"], saved["completion_tokens"],
            saved["cached_tokens"], saved["latency_ms"]) == ("selftest-model", "low", 1234, 56, 1024, 789)
    assert saved["answered_at"] is not None

    hidden = store.insert_pending(MUSEUM, place, me, "低价代订门票", "h" * 64)
    store.finish(hidden, answer("这里只回答与参观有关的问题。", on_topic=False))
    broken = store.insert_pending(MUSEUM, place, me, "这条会失败", "f" * 64)
    store.fail(broken, "出错了" * 1000)
    with store._cursor() as cur:
        cur.execute("SELECT status, CHAR_LENGTH(error) AS n, is_public FROM tour_topic WHERE id = %s", (broken,))
        failed = cur.fetchone()
    assert (failed["status"], failed["n"], failed["is_public"]) == ("failed", ERROR_MAX, None)

    assert [t.id for t in store.list_topics(MUSEUM, place, you, None, 10)] == [first], "别人只看得到公开的"
    assert [t.id for t in store.list_topics(MUSEUM, place, None, None, 10)] == [first], "不带设备号也一样"
    assert [t.id for t in store.list_topics(MUSEUM, place, me, None, 10)] == [broken, hidden, first], "自己的全看得到，新的在前"
    assert [t.id for t in store.list_topics(MUSEUM, place, me, broken, 1)] == [hidden], "before 与 limit"
    assert store.list_topics(MUSEUM, "another_place", me, None, 10) == []


def test_reuse_and_takedown(store, ids):
    me, you, place, digest = ids["me"], ids["you"], ids["place"], ids["hash"]
    original = store.insert_pending(MUSEUM, place, me, "这是什么地方", digest)
    assert store.find_answered(digest) is None, "没答完的不算"
    store.finish(original, answer(on_topic=False))

    source = store.find_answered(digest)
    assert source.id == original and not source.public
    copy = store.insert_reused(MUSEUM, place, you, "这是什么地方", digest, source)
    row = store.get(copy)
    assert (row.status, row.is_public, row.answer, row.reused_from) == ("answered", False, "回答。", original)
    assert store.find_answered(digest).id == original, "复用出来的行不能再当源头"
    assert [t.id for t in store.list_topics(MUSEUM, place, you, None, 10)] == [copy]

    public = store.insert_pending(MUSEUM, place, me, "另一个问题", "p" * 64)
    store.finish(public, answer())
    assert [t.id for t in store.list_topics(MUSEUM, place, None, None, 10)] == [public]
    with store._cursor() as cur:
        cur.execute("UPDATE tour_topic SET valid = 0 WHERE id = %s", (public,))      # 人工下架
    assert store.list_topics(MUSEUM, place, None, None, 10) == []
    assert public not in [t.id for t in store.list_topics(MUSEUM, place, me, None, 10)], "下架后提问者自己也看不到"
    taken = store.find_answered("p" * 64)
    assert taken.id == public and not taken.public, "重问时还找得到它，但它不再算公开"
