"""导览站「游客互动」的接口：游客在景点介绍页上提问，AI 结合导览资料回答。

接口形状照 MingnaCurator 的 `PostTopic/{id}` 与 `{id}/topics`。不同在于这里没有登录：
「我」是浏览器里生成的匿名设备号（请求头 `X-Visitor`），问答对所有游客公开。

    GET  /api/tour/{museum}/places/{place}/topics?before=<id>&limit=20
    POST /api/tour/{museum}/places/{place}/topics      {"question": "…"}

公开入口、匿名、每次提问都花钱，所以有三道条数上限，存在库里的 `tour_qa_setting`，
每次提问现读 —— 改库即生效，设成 0 就是关掉（见 web_api/sql/tour_qa.sql）。
"""

import logging
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import tour_qa_llm as llm
from .tour_qa_store import PENDING_STALE_S, MySqlStore, SettingMissing, StoreNotConfigured, Topic

log = logging.getLogger("ari.tour_qa")

VISITOR_RE = re.compile(r"^[A-Za-z0-9-]{16,64}$")
QUESTION_MIN, QUESTION_MAX = 2, 100
PAGE_DEFAULT, PAGE_MAX = 20, 50
IP_WINDOW_S = 3600


class QaError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def qa_error_handler(request: Request, exc: QaError) -> JSONResponse:
    return JSONResponse({"error_code": exc.code, "message": exc.message},
                        status_code=exc.status, headers={"Cache-Control": "no-store"})


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/tour", dependencies=[Depends(_no_store)])


# ------------------------------------------------------------ 依赖
_store: MySqlStore | None = None
_answerer: llm.OpenAiAnswerer | None = None


def get_store() -> MySqlStore:
    global _store
    if _store is None:
        try:
            _store = MySqlStore()
        except StoreNotConfigured as exc:
            log.error("游客互动不可用（数据库）：%s", exc)
            raise QaError(503, "qa_unavailable", "互动功能暂不可用。") from exc
    return _store


def get_answerer() -> llm.OpenAiAnswerer:
    global _answerer
    if _answerer is None:
        try:
            _answerer = llm.OpenAiAnswerer()
        except llm.LlmNotConfigured as exc:
            log.error("游客互动不可用（模型）：%s", exc)
            raise QaError(503, "qa_unavailable", "互动功能暂不可用。") from exc
    return _answerer


# ------------------------------------------------------------ 每 IP 的计数
class IpLimiter:
    """每个 IP 最近一小时提了几条。只在内存里：不往库里存 IP，服务重启后清零。"""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def count(self, ip: str) -> int:
        cutoff = time.monotonic() - IP_WINDOW_S
        with self._lock:
            hits = self._hits.get(ip)
            if not hits:
                return 0
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[ip]
            return len(hits)

    def add(self, ip: str) -> None:
        with self._lock:
            self._hits.setdefault(ip, deque()).append(time.monotonic())

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


ip_limiter = IpLimiter()


# ------------------------------------------------------------ 校验
def _require_place(museum_key: str, place_id: str) -> tuple[dict, dict]:
    museum = llm.load_museum(museum_key)
    place = llm.find_place(museum, place_id) if museum else None
    if place is None:
        raise QaError(404, "place_not_found", "没有这个地点。")
    return museum, place


def _visitor(header: str | None) -> str | None:
    return header if header and VISITOR_RE.match(header) else None


def clean_question(raw: str) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", raw or "")).strip()
    if len(text) < QUESTION_MIN:
        raise QaError(400, "question_too_short", "先输入你的问题。")
    if len(text) > QUESTION_MAX:
        raise QaError(400, "question_too_long", f"问题请控制在 {QUESTION_MAX} 字以内。")
    if sum(ch.isalnum() for ch in text) < QUESTION_MIN:
        raise QaError(400, "question_invalid", "问题过短或只有标点，请重新输入。")
    return text


def _check_limits(store: MySqlStore, visitor: str, ip: str) -> None:
    try:
        limits = store.settings()
    except SettingMissing as exc:
        log.error("游客互动不可用（上限表）：%s", exc)
        raise QaError(503, "qa_setting_missing", "互动功能暂不可用。") from exc

    site, per_visitor, per_ip = limits["site_per_day"], limits["per_visitor_per_day"], limits["per_ip_per_hour"]
    if site == 0 or per_visitor == 0 or per_ip == 0:
        raise QaError(429, "qa_paused", "提问功能已暂停，已有的问答仍可查看。")
    if store.has_pending(visitor):
        raise QaError(429, "busy", "上一条提问还在回答中，请稍等。")
    if store.count_visitor_day(visitor) >= per_visitor:
        raise QaError(429, "limit_visitor", f"你在 24 小时内已提问 {per_visitor} 条，达到上限，请明天再来。")
    if ip_limiter.count(ip) >= per_ip:
        raise QaError(429, "limit_ip", f"当前网络下的提问太多了（每小时上限 {per_ip} 条），请稍后再试。")
    if store.count_site_day() >= site:
        raise QaError(429, "limit_site", f"全站 24 小时内的提问已达上限（{site} 条），请明天再来。")


def _client_ip(request: Request) -> str:
    # 服务只监听 127.0.0.1，进来的请求都经过 Nginx，X-Real-IP 由它用 $remote_addr 覆盖
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _topic_json(topic: Topic, visitor: str | None) -> dict:
    created = topic.created_at.replace(tzinfo=timezone.utc)
    status = topic.status
    if status == "pending" and (datetime.now(timezone.utc) - created).total_seconds() > PENDING_STALE_S:
        status = "failed"
    return {
        "id": topic.id,
        "question": topic.question,
        "answer": topic.answer if status == "answered" else None,
        "status": status,
        "mine": visitor is not None and topic.visitor_id == visitor,
        "public": topic.public,
        "created_at": created.isoformat().replace("+00:00", "Z"),
    }


# ------------------------------------------------------------ 接口
class Ask(BaseModel):
    question: str = ""


@router.get("/{museum_key}/places/{place_id}/topics")
def list_topics(museum_key: str, place_id: str, before: int | None = None, limit: int = PAGE_DEFAULT,
                x_visitor: str | None = Header(default=None),
                store: MySqlStore = Depends(get_store)) -> dict:
    _require_place(museum_key, place_id)
    visitor = _visitor(x_visitor)
    limit = max(1, min(limit, PAGE_MAX))
    rows = store.list_topics(museum_key, place_id, visitor, before, limit + 1)
    return {"topics": [_topic_json(row, visitor) for row in rows[:limit]], "more": len(rows) > limit}


@router.post("/{museum_key}/places/{place_id}/topics")
def ask(museum_key: str, place_id: str, body: Ask, request: Request,
        x_visitor: str | None = Header(default=None),
        store: MySqlStore = Depends(get_store),
        answerer: llm.OpenAiAnswerer = Depends(get_answerer)) -> dict:
    museum, place = _require_place(museum_key, place_id)
    visitor = _visitor(x_visitor)
    if visitor is None:
        raise QaError(400, "visitor_invalid", "缺少设备标识，请刷新页面后重试。")
    question = clean_question(body.question)
    ip = _client_ip(request)
    _check_limits(store, visitor, ip)

    system = llm.build_system(museum)
    user = llm.build_user(museum, place, question)
    digest = llm.prompt_hash(answerer.model, answerer.effort, system, user)

    # 同一地点、同一份资料、同一个问题已经答过：不再调模型
    known = store.find_answered(digest)
    if known and known.public:
        return {"topic": _topic_json(known, visitor), "duplicate": True}
    if known:
        # 旧答案不公开（模型判为与参观无关，或已被下架）：重问一遍不该让它重新公开
        topic_id = store.insert_reused(museum_key, place_id, visitor, question, digest, known)
    else:
        topic_id = store.insert_pending(museum_key, place_id, visitor, question, digest)
        try:
            answer = answerer.ask(system, user)
        except llm.LlmError as exc:
            log.warning("提问 %s 没有答上来：%s", topic_id, exc)
            store.fail(topic_id, str(exc))
            raise QaError(502, "answer_failed", "导览助手暂时没有答上来，请稍后再试。") from exc
        store.finish(topic_id, answer)
    ip_limiter.add(ip)
    return {"topic": _topic_json(store.get(topic_id), visitor), "duplicate": False}
