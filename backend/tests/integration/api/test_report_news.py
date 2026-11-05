from collections.abc import AsyncIterator, Collection, Sequence
from uuid import UUID

import httpx
import pytest
from api_auth_support import (
    AUTH_COOKIES,
    OTHER_COOKIES,
    TEST_USER,
    static_auth_service,
)

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.dialogs import (
    DialogStoreUnavailableError,
    InMemoryHistoryStore,
    ReportNews,
    ReportReason,
)

NEWS = "/api/v1/reports/news"
SEEN = "/api/v1/reports/news/seen"


class SilentAgent:
    async def run(
        self, history: Sequence[Message], request: UserRequest
    ) -> AsyncIterator[AgentStreamEvent]:
        yield AgentResponse(content="")


class UnavailableNewsStore(InMemoryHistoryStore):
    async def report_news(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[ReportNews, ...]:
        raise DialogStoreUnavailableError

    async def mark_report_news_seen(
        self, owner_id: UUID, report_ids: Collection[int]
    ) -> int:
        raise DialogStoreUnavailableError


async def reviewed(
    store: InMemoryHistoryStore, service: AgentService, title: str, status: str
) -> tuple[UUID, int]:
    dialog_id = await service.start_dialog(TEST_USER.id)
    _, answer_id = await store.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content=title),
            Message(role=MessageRole.ASSISTANT, content="Ответ"),
        ),
    )
    report_id = await store.report(
        TEST_USER.id, dialog_id, answer_id, ReportReason.RUDE, None
    )
    store.set_report_status(report_id, status)  # type: ignore[arg-type]
    return dialog_id, report_id


def client(
    service: AgentService, cookies: dict[str, str] | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(service, auth_service=static_auth_service())
        ),
        base_url="http://test",
        cookies=AUTH_COOKIES if cookies is None else cookies,
    )


def make(store: InMemoryHistoryStore) -> AgentService:
    return AgentService(SilentAgent(), store, InMemoryDialogEventBroker())


@pytest.mark.asyncio
async def test_news_name_the_story_and_hide_the_outcome() -> None:
    store = InMemoryHistoryStore()
    service = make(store)
    rocket, resolved = await reviewed(store, service, "Ракета", "resolved")
    tea, dismissed = await reviewed(store, service, "Чай", "dismissed")
    await reviewed(store, service, "Ждёт", "new")

    async with client(service) as http:
        response = await http.get(NEWS)
        history = await http.get(f"/api/v1/dialogs/{tea}/messages")

    assert response.status_code == 200
    assert response.json() == {
        "news": [
            {"report_id": dismissed, "dialog_id": str(tea), "dialog_title": "Чай"},
            {"report_id": resolved, "dialog_id": str(rocket), "dialog_title": "Ракета"},
        ]
    }
    messages = history.json()["messages"]
    assert [(item["report"], item["reported"]) for item in messages] == [
        (None, False),
        ("reviewed", True),
    ]
    for body in (response.text, history.text):
        assert "dismissed" not in body
        assert "resolved" not in body
    await service.shutdown()


@pytest.mark.asyncio
async def test_seen_news_do_not_come_back_and_others_are_skipped() -> None:
    store = InMemoryHistoryStore()
    service = make(store)
    _, first = await reviewed(store, service, "Ракета", "resolved")
    _, second = await reviewed(store, service, "Чай", "resolved")

    async with client(service, OTHER_COOKIES) as stranger:
        foreign = await stranger.post(SEEN, json={"report_ids": [first]})
    async with client(service) as http:
        seen = await http.post(SEEN, json={"report_ids": [first, 999]})
        news = (await http.get(NEWS)).json()["news"]

    assert foreign.status_code == 204
    assert (seen.status_code, seen.content) == (204, b"")
    assert [item["report_id"] for item in news] == [second]
    await service.shutdown()


@pytest.mark.asyncio
async def test_news_of_a_deleted_story_have_no_dialog() -> None:
    store = InMemoryHistoryStore()
    service = make(store)
    dialog_id, report_id = await reviewed(store, service, "Ракета", "resolved")

    async with client(service) as http:
        await http.delete(f"/api/v1/dialogs/{dialog_id}")
        response = await http.get(NEWS)

    assert response.json() == {
        "news": [{"report_id": report_id, "dialog_id": None, "dialog_title": None}]
    }
    await service.shutdown()


@pytest.mark.asyncio
async def test_new_story_has_no_report_and_no_news() -> None:
    store = InMemoryHistoryStore()
    service = make(store)
    dialog_id = await service.start_dialog(TEST_USER.id)
    await store.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="q"),
            Message(role=MessageRole.ASSISTANT, content="a"),
        ),
    )

    async with client(service) as http:
        news = await http.get(NEWS)
        history = await http.get(f"/api/v1/dialogs/{dialog_id}/messages")

    assert news.json() == {"news": []}
    assert [item["report"] for item in history.json()["messages"]] == [None, None]
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"report_ids": []},
        {"report_ids": list(range(1, 22))},
        {"report_ids": ["1"]},
        {"report_ids": [1.5]},
        {"report_ids": [True]},
        {"report_ids": [1], "extra": 1},
    ],
)
async def test_invalid_seen_body_returns_422(body: object) -> None:
    service = make(InMemoryHistoryStore())

    async with client(service) as http:
        response = await http.post(SEEN, json=body)

    assert response.status_code == 422
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), [("GET", NEWS), ("POST", SEEN)])
async def test_guest_gets_401_before_validation(method: str, path: str) -> None:
    service = make(InMemoryHistoryStore())

    async with client(service, {}) as http:
        response = await http.request(method, path, json={"report_ids": "bad"})

    assert (response.status_code, response.json()) == (401, {"error": "unauthorized"})
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), [("GET", NEWS), ("POST", SEEN)])
async def test_unavailable_store_returns_503(method: str, path: str) -> None:
    service = make(UnavailableNewsStore())

    async with client(service) as http:
        response = await http.request(method, path, json={"report_ids": [1]})

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service is unavailable."}
    await service.shutdown()
