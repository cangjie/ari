"""导览站「游客互动」接口的测试。不连数据库、不联网：库与模型都换成假的。

假的库只在内存里记行，可见性规则与 `tour_qa_store.MySqlStore` 的 SQL 写的是同一条；
真库上的那几句 SQL 由 test_tour_qa_db.py 另验（默认跳过，要显式打开）。
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import tour_qa
from app import tour_qa_llm as llm
from app.main import app
from app.tour_qa_store import PENDING_STALE_S, SettingMissing, Topic

MUSEUM, PLACE, OTHER_PLACE = "wmhg", "tongde", "south_wing"
URL = f"/api/tour/{MUSEUM}/places/{PLACE}/topics"
ME = {"X-Visitor": "11111111-aaaa-4bbb-8ccc-000000000001"}
YOU = {"X-Visitor": "22222222-aaaa-4bbb-8ccc-000000000002"}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FakeStore:
    def __init__(self):
        self.rows: dict[int, Topic] = {}
        self.hashes: dict[int, str] = {}
        self.errors: dict[int, str] = {}
        self.limits = {"per_visitor_per_day": 20, "per_ip_per_hour": 120, "site_per_day": 1000}

    def settings(self):
        missing = [k for k in ("per_visitor_per_day", "per_ip_per_hour", "site_per_day") if k not in self.limits]
        if missing:
            raise SettingMissing("tour_qa_setting 缺少：" + "、".join(missing))
        return dict(self.limits)

    def count_visitor_day(self, visitor_id):
        return sum(1 for t in self.rows.values() if t.visitor_id == visitor_id)

    def count_site_day(self):
        return len(self.rows)

    def has_pending(self, visitor_id):
        fresh = utcnow() - timedelta(seconds=PENDING_STALE_S)
        return any(t.visitor_id == visitor_id and t.status == "pending" and t.created_at > fresh
                   for t in self.rows.values())

    def find_answered(self, prompt_hash):
        hits = [t for i, t in self.rows.items()
                if self.hashes[i] == prompt_hash and t.status == "answered" and t.reused_from is None]
        return max(hits, key=lambda t: t.id) if hits else None

    def _add(self, museum_key, place_id, visitor_id, question, prompt_hash, **extra):
        topic_id = len(self.rows) + 1
        self.rows[topic_id] = Topic(
            id=topic_id, museum_key=museum_key, place_id=place_id, visitor_id=visitor_id, question=question,
            answer=None, status="pending", is_public=None, valid=True, reused_from=None, created_at=utcnow(),
        )
        self.rows[topic_id] = replace(self.rows[topic_id], **extra)
        self.hashes[topic_id] = prompt_hash
        return topic_id

    def insert_pending(self, museum_key, place_id, visitor_id, question, prompt_hash):
        return self._add(museum_key, place_id, visitor_id, question, prompt_hash)

    def insert_reused(self, museum_key, place_id, visitor_id, question, prompt_hash, source):
        return self._add(museum_key, place_id, visitor_id, question, prompt_hash, answer=source.answer,
                         status="answered", is_public=False, reused_from=source.id)

    def finish(self, topic_id, answer):
        self.rows[topic_id] = replace(self.rows[topic_id], answer=answer.text, status="answered",
                                      is_public=answer.on_topic)

    def fail(self, topic_id, error):
        self.rows[topic_id] = replace(self.rows[topic_id], status="failed")
        self.errors[topic_id] = error

    def get(self, topic_id):
        return self.rows.get(topic_id)

    def list_topics(self, museum_key, place_id, visitor_id, before, limit):
        rows = [t for t in self.rows.values()
                if t.museum_key == museum_key and t.place_id == place_id and t.valid
                and ((t.status == "answered" and t.is_public) or t.visitor_id == (visitor_id or ""))
                and (before is None or t.id < before)]
        return sorted(rows, key=lambda t: -t.id)[:limit]


class FakeAnswerer:
    model, effort = "fake-model", None

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.on_topic = True
        self.error: Exception | None = None

    def ask(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return llm.Answer(text="这是回答。", on_topic=self.on_topic, model=self.model, effort=None,
                          prompt_tokens=900, completion_tokens=40, cached_tokens=0, latency_ms=12)


@pytest.fixture
def qa():
    store, answerer = FakeStore(), FakeAnswerer()
    app.dependency_overrides[tour_qa.get_store] = lambda: store
    app.dependency_overrides[tour_qa.get_answerer] = lambda: answerer
    tour_qa.ip_limiter.clear()
    yield TestClient(app), store, answerer
    app.dependency_overrides.clear()
    tour_qa.ip_limiter.clear()


def ask(client, question="溥仪在这里住过吗？", headers=ME, url=URL):
    return client.post(url, json={"question": question}, headers=headers)


def listed(client, headers=None, url=URL, **params):
    response = client.get(url, headers=headers or {}, params=params)
    assert response.status_code == 200
    return response.json()


# ------------------------------------------------------------ 提问与列表
def test_question_is_answered_and_everyone_can_see_it(qa):
    client, store, answerer = qa
    response = ask(client)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["duplicate"] is False
    topic = body["topic"]
    assert topic["question"] == "溥仪在这里住过吗？" and topic["answer"] == "这是回答。"
    assert topic["status"] == "answered" and topic["mine"] is True and topic["public"] is True
    assert topic["created_at"].endswith("Z")
    assert len(answerer.calls) == 1

    theirs = listed(client, YOU)["topics"]
    assert [t["id"] for t in theirs] == [topic["id"]]
    assert theirs[0]["mine"] is False
    assert "visitor" not in " ".join(theirs[0].keys()), "设备号不能返回给别人"
    assert listed(client)["topics"][0]["mine"] is False, "不带设备号也能看公开的问答"


def test_prompt_carries_the_place_and_its_official_intro(qa):
    client, _, answerer = qa
    ask(client)
    system, user = answerer.calls[0]
    museum = llm.load_museum(MUSEUM)
    stop = museum["stops"][str(llm.find_place(museum, PLACE)["stops"][0])]

    assert stop["intro"][0] in system and stop["source"]["zh"] in system
    assert "同德殿" in user and "溥仪在这里住过吗？" in user
    assert "溥仪在这里住过吗？" not in system, "问题只进 user，system 要保持不变才能被缓存"


def test_non_chinese_question_is_answered_in_its_own_language(qa):
    """问题被包在几行中文里，不提醒的话模型会用中文答。"""
    client, _, answerer = qa
    ask(client, "Who lived in Jixi Building?")
    ask(client, "溥仪住在哪栋楼？")
    hint = "整段回答都用问题所用的语言"
    assert hint in answerer.calls[0][1] and hint not in answerer.calls[1][1]


def test_off_topic_question_is_visible_only_to_its_asker(qa):
    client, _, answerer = qa
    answerer.on_topic = False
    topic = ask(client, "低价代订门票加微信").json()["topic"]

    assert topic["public"] is False and topic["mine"] is True
    assert listed(client, YOU)["topics"] == []
    assert [t["id"] for t in listed(client, ME)["topics"]] == [topic["id"]]


def test_topics_belong_to_one_place(qa):
    client, _, _ = qa
    ask(client)
    other = f"/api/tour/{MUSEUM}/places/{OTHER_PLACE}/topics"
    assert listed(client, ME, url=other)["topics"] == []


def test_list_is_newest_first_and_paged(qa):
    client, _, _ = qa
    ids = [ask(client, f"第 {i} 个问题是什么").json()["topic"]["id"] for i in range(1, 6)]

    first = listed(client, YOU, limit=2)
    assert [t["id"] for t in first["topics"]] == ids[:-3:-1] and first["more"] is True
    rest = listed(client, YOU, limit=10, before=first["topics"][-1]["id"])
    assert [t["id"] for t in rest["topics"]] == ids[2::-1] and rest["more"] is False


# ------------------------------------------------------------ 校验
@pytest.mark.parametrize("url", [
    "/api/tour/nosuch/places/tongde/topics",
    "/api/tour/wmhg/places/nosuch/topics",
    "/api/tour/WMHG/places/tongde/topics",
    "/api/tour/wmhg/places/tong.de/topics",
])
def test_unknown_museum_or_place_is_404(qa, url):
    client, _, answerer = qa
    assert client.get(url).status_code == 404
    response = ask(client, url=url)
    assert response.status_code == 404 and response.json()["error_code"] == "place_not_found"
    assert answerer.calls == []


@pytest.mark.parametrize("question, code", [
    ("", "question_too_short"),
    ("   \n ", "question_too_short"),
    ("？", "question_too_short"),
    ("？？？！！！", "question_invalid"),
    ("字" * 101, "question_too_long"),
])
def test_bad_question_is_rejected_before_any_cost(qa, question, code):
    client, store, answerer = qa
    response = ask(client, question)
    assert response.status_code == 400 and response.json()["error_code"] == code
    assert store.rows == {} and answerer.calls == []


def test_question_whitespace_is_collapsed(qa):
    client, _, _ = qa
    assert ask(client, "  溥仪\n\n是谁\t？ ").json()["topic"]["question"] == "溥仪 是谁 ？"


@pytest.mark.parametrize("headers", [{}, {"X-Visitor": "short"}, {"X-Visitor": "not a valid id; drop table"}])
def test_asking_needs_a_visitor_id(qa, headers):
    client, store, _ = qa
    response = ask(client, headers=headers)
    assert response.status_code == 400 and response.json()["error_code"] == "visitor_invalid"
    assert store.rows == {}


# ------------------------------------------------------------ 条数上限
def test_per_visitor_limit(qa):
    client, store, _ = qa
    store.limits["per_visitor_per_day"] = 2
    assert ask(client, "第一个问题").status_code == 200
    assert ask(client, "第二个问题").status_code == 200
    blocked = ask(client, "第三个问题")
    assert blocked.status_code == 429 and blocked.json()["error_code"] == "limit_visitor"
    assert "2 条" in blocked.json()["message"]
    assert ask(client, "别人的问题", headers=YOU).status_code == 200, "别的设备不受影响"


def test_per_ip_limit(qa):
    client, store, _ = qa
    store.limits["per_ip_per_hour"] = 1
    assert ask(client, "第一个问题").status_code == 200
    blocked = ask(client, "换个设备再问", headers=YOU)
    assert blocked.status_code == 429 and blocked.json()["error_code"] == "limit_ip"


def test_site_limit(qa):
    client, store, _ = qa
    store.limits["site_per_day"] = 1
    assert ask(client, "第一个问题").status_code == 200
    blocked = ask(client, "换个设备再问", headers=YOU)
    assert blocked.status_code == 429 and blocked.json()["error_code"] == "limit_site"


def test_limit_change_takes_effect_on_the_next_question(qa):
    """上限每次提问现读：改了之后不用重启，下一条就按新值算。"""
    client, store, _ = qa
    assert ask(client, "第一个问题").status_code == 200
    store.limits["per_visitor_per_day"] = 1
    assert ask(client, "第二个问题").json()["error_code"] == "limit_visitor"
    store.limits["per_visitor_per_day"] = 20
    assert ask(client, "第二个问题").status_code == 200


@pytest.mark.parametrize("name", ["per_visitor_per_day", "per_ip_per_hour", "site_per_day"])
def test_zero_limit_pauses_asking_but_not_reading(qa, name):
    client, store, answerer = qa
    topic = ask(client).json()["topic"]
    store.limits[name] = 0

    blocked = ask(client, "还能问吗", headers=YOU)
    assert blocked.status_code == 429 and blocked.json()["error_code"] == "qa_paused"
    assert len(answerer.calls) == 1
    assert [t["id"] for t in listed(client, YOU)["topics"]] == [topic["id"]]


def test_missing_limit_row_is_an_error_not_a_default(qa):
    client, store, answerer = qa
    del store.limits["site_per_day"]
    response = ask(client)
    assert response.status_code == 503 and response.json()["error_code"] == "qa_setting_missing"
    assert store.rows == {} and answerer.calls == []


def test_one_question_at_a_time_per_visitor(qa):
    client, store, _ = qa
    store.insert_pending(MUSEUM, PLACE, ME["X-Visitor"], "还在答的那一条", "hash")
    blocked = ask(client, "又问一条")
    assert blocked.status_code == 429 and blocked.json()["error_code"] == "busy"
    assert ask(client, "别人不受影响", headers=YOU).status_code == 200


# ------------------------------------------------------------ 失败
def test_model_failure_is_recorded_and_never_public(qa):
    client, store, answerer = qa
    answerer.error = llm.LlmError("APITimeoutError: 超时")
    response = ask(client)

    assert response.status_code == 502 and response.json()["error_code"] == "answer_failed"
    assert "超时" not in response.json()["message"], "内部错误原文不给游客看"
    (topic_id, row), = store.rows.items()
    assert row.status == "failed" and "超时" in store.errors[topic_id]
    assert listed(client, YOU)["topics"] == []
    mine = listed(client, ME)["topics"]
    assert mine[0]["status"] == "failed" and mine[0]["answer"] is None


def test_stale_pending_question_reads_as_failed(qa):
    client, store, _ = qa
    topic_id = store.insert_pending(MUSEUM, PLACE, ME["X-Visitor"], "进程中途没了", "hash")
    store.rows[topic_id] = replace(store.rows[topic_id],
                                   created_at=utcnow() - timedelta(seconds=PENDING_STALE_S + 5))
    assert listed(client, ME)["topics"][0]["status"] == "failed"
    assert ask(client, "之后还能再问").status_code == 200


# ------------------------------------------------------------ 复用
def test_same_question_at_same_place_is_not_asked_twice(qa):
    client, store, answerer = qa
    first = ask(client).json()["topic"]
    again = ask(client, headers=YOU).json()

    assert again["duplicate"] is True and again["topic"]["id"] == first["id"]
    assert again["topic"]["mine"] is False
    assert len(answerer.calls) == 1 and len(store.rows) == 1

    other = f"/api/tour/{MUSEUM}/places/{OTHER_PLACE}/topics"
    assert ask(client, url=other).json()["duplicate"] is False, "换个地点是另一个问题"
    assert len(answerer.calls) == 2


def test_reasking_a_hidden_question_does_not_republish_it(qa):
    client, store, answerer = qa
    answerer.on_topic = False
    ask(client, "低价代订门票加微信")
    answerer.on_topic = True          # 即便模型这次会判成正常提问，也不该再去问它

    again = ask(client, "低价代订门票加微信", headers=YOU).json()
    assert again["duplicate"] is False and again["topic"]["public"] is False
    assert again["topic"]["mine"] is True and again["topic"]["answer"] == "这是回答。"
    assert len(answerer.calls) == 1


def test_reasking_a_taken_down_question_does_not_republish_it(qa):
    client, store, answerer = qa
    first = ask(client).json()["topic"]
    store.rows[first["id"]] = replace(store.rows[first["id"]], valid=False)      # 人工下架
    assert listed(client, YOU)["topics"] == []

    again = ask(client, headers=YOU).json()["topic"]
    assert again["public"] is False and len(answerer.calls) == 1
    assert listed(client)["topics"] == []


# ------------------------------------------------------------ 没配置好
def test_unconfigured_service_says_so(monkeypatch):
    """缺数据库或模型配置时只有问答回 503，站点其余部分照常。"""
    for name in ("ARI_DB_DEFAULTS_FILE", "ARI_QA_MODEL", "OPENAI_API_KEY", "ARI_OPENAI_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(tour_qa, "_store", None)
    monkeypatch.setattr(tour_qa, "_answerer", None)
    client = TestClient(app)

    for response in (client.get(URL), ask(client)):
        assert response.status_code == 503 and response.json()["error_code"] == "qa_unavailable"
    assert client.get("/health").status_code == 200


# ------------------------------------------------------------ 材料与答案的校验
def test_material_marks_review_notes_and_borrowed_positions():
    museum = {
        "name": {"zh": "某馆"}, "opening": {"zh": "全天"},
        "card": {"city": {"zh": "某市"}, "district": {"zh": "某区"}, "type": {"zh": "遗址"}, "desc": {"zh": "简介。"}},
        "places": [{"id": "a", "name": {"zh": "甲处"}, "stops": [1]}],
        "routes": [{"label": {"zh": "两小时"}, "total": 50, "stay": 45, "walk": 5, "stops": [1]}],
        "stops": {"1": {
            "name": {"zh": "甲展"}, "tier": "A", "dwell": 45, "status": {"zh": "在展"}, "intro": ["介绍正文。"],
            "source": {"zh": "官网"}, "borrowed": {"zh": "具体位置未核实。"}, "review": "直径 30 厘米疑为笔误",
            "objects": [{"name": {"zh": "某瓶"}, "tier": "B", "review": "足径与瓶形不合"}],
        }},
    }
    text = llm.museum_material(museum)
    for piece in ("待复核：直径 30 厘米疑为笔误", "位置说明：具体位置未核实。", "某瓶（导览评级 B；待复核：足径与瓶形不合）",
                  "介绍正文。", "介绍出处：官网", "建议停留约 45 分钟",
                  "两小时：1 站，约 50 分钟（停留 45 + 步行 5），依次是甲展", "都是本导览的估计"):
        assert piece in text


def test_every_published_museum_can_be_turned_into_material():
    for path in llm.TOUR_DATA_DIR.glob("*.json"):
        museum = llm.load_museum(path.stem)
        text = llm.build_system(museum)
        for stop in museum["stops"].values():
            assert stop["intro"][0] in text, f"{path.stem} seq {stop['seq']} 的介绍没进材料"
        for route in museum["routes"]:
            assert f"{route['label']['zh']}：{len(route['stops'])} 站，约 {route['total']} 分钟" in text


def test_prompt_hash_changes_with_any_part():
    base = llm.prompt_hash("m", None, "s", "u")
    assert base == llm.prompt_hash("m", None, "s", "u")
    assert len({base, llm.prompt_hash("m2", None, "s", "u"), llm.prompt_hash("m", "low", "s", "u"),
                llm.prompt_hash("m", None, "s2", "u"), llm.prompt_hash("m", None, "s", "u2")}) == 5


@pytest.mark.parametrize("content", [None, "", "不是 JSON", "[]", '{"answer": "有", "on_topic": "true"}',
                                     '{"on_topic": true}', '{"answer": "  ", "on_topic": true}'])
def test_unusable_model_output_is_a_failure(content):
    with pytest.raises(llm.LlmError):
        llm.parse_answer(content)


def test_answer_is_shown_as_plain_text():
    text, on_topic = llm.parse_answer('{"answer": "## 标题\\n**同德殿**建于 1938 年。\\n\\n\\n\\n- 一楼", "on_topic": true}')
    assert text == "标题\n同德殿建于 1938 年。\n\n• 一楼" and on_topic is True
