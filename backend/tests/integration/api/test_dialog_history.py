import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta
from uuid import UUID, uuid4

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
    UserRequest,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.dialogs import (
    DialogStoreUnavailableError,
    DialogSummary,
    DialogTranscript,
    InMemoryHistoryStore,
)

UNAVAILABLE = {"detail": "Agent service is unavailable."}


class EchoAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Message, ...], UserRequest]] = []

    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.calls.append((tuple(history), request))
        yield AgentResponse(content=f"ответ: {request.content}")


class UnavailableHistoryStore(InMemoryHistoryStore):
    async def create(self, owner_id: UUID) -> UUID:
        raise DialogStoreUnavailableError

    async def get(self, owner_id: UUID, dialog_id: UUID) -> tuple[Message, ...]:
        raise DialogStoreUnavailableError

    async def list_dialogs(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[DialogSummary, ...]:
        raise DialogStoreUnavailableError

    async def transcript(self, owner_id: UUID, dialog_id: UUID) -> DialogTranscript:
        raise DialogStoreUnavailableError


def make_client(
    service: AgentService, cookies: dict[str, str] | None = None
) -> httpx.AsyncClient:
    app = create_app(service, auth_service=static_auth_service())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=AUTH_COOKIES if cookies is None else cookies,
    )


async def wait_for_history(
    store: InMemoryHistoryStore, dialog_id: UUID, size: int
) -> None:
    async def wait() -> None:
        while len(await store.get(TEST_USER.id, dialog_id)) != size:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait(), timeout=1)


def assert_utc(value: str) -> None:
    assert datetime.fromisoformat(value).utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_list_is_empty_for_a_new_user() -> None:
    service = AgentService(
        EchoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )

    async with make_client(service) as client:
        response = await client.get("/api/v1/dialogs")

    assert response.status_code == 200
    assert response.json() == {"dialogs": []}
    await service.shutdown()


@pytest.mark.asyncio
async def test_answered_dialog_is_listed_and_its_messages_are_returned() -> None:
    store = InMemoryHistoryStore()
    service = AgentService(EchoAgent(), store, InMemoryDialogEventBroker())

    async with make_client(service) as client:
        dialog_id = (await client.post("/api/v1/dialogs")).json()["dialog_id"]
        await client.post("/api/v1/dialogs")
        await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages",
            json={"request": "Крош и Ёжик строят ракету"},
        )
        await wait_for_history(store, UUID(dialog_id), 2)
        listed = await client.get("/api/v1/dialogs")
        history = await client.get(f"/api/v1/dialogs/{dialog_id}/messages")

    assert listed.status_code == 200
    [summary] = listed.json()["dialogs"]
    assert summary["dialog_id"] == dialog_id
    assert summary["title"] == "Крош и Ёжик строят ракету"
    assert set(summary) == {"dialog_id", "title", "created_at", "updated_at"}
    assert_utc(summary["created_at"])
    assert_utc(summary["updated_at"])

    assert history.status_code == 200
    body = history.json()
    assert body["dialog_id"] == dialog_id
    assert body["title"] == "Крош и Ёжик строят ракету"
    assert [(item["role"], item["content"]) for item in body["messages"]] == [
        ("user", "Крош и Ёжик строят ракету"),
        ("assistant", "ответ: Крош и Ёжик строят ракету"),
    ]
    for item in body["messages"]:
        assert set(item) == {"id", "role", "content", "created_at", "feedback"}
        assert isinstance(item["id"], int)
        assert item["feedback"] is None
        assert_utc(item["created_at"])
    await service.shutdown()


@pytest.mark.asyncio
async def test_new_dialog_has_no_title_and_no_messages() -> None:
    service = AgentService(
        EchoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )

    async with make_client(service) as client:
        dialog_id = (await client.post("/api/v1/dialogs")).json()["dialog_id"]
        response = await client.get(f"/api/v1/dialogs/{dialog_id}/messages")

    assert response.status_code == 200
    assert response.json() == {"dialog_id": dialog_id, "title": None, "messages": []}
    await service.shutdown()


@pytest.mark.asyncio
async def test_foreign_dialog_is_not_found_on_every_dialog_route() -> None:
    agent = EchoAgent()
    store = InMemoryHistoryStore()
    service = AgentService(agent, store, InMemoryDialogEventBroker())

    async with make_client(service) as owner:
        dialog_id = (await owner.post("/api/v1/dialogs")).json()["dialog_id"]
    async with make_client(service, OTHER_COOKIES) as stranger:
        history = await stranger.get(f"/api/v1/dialogs/{dialog_id}/messages")
        submitted = await stranger.post(
            f"/api/v1/dialogs/{dialog_id}/messages", json={"request": "hi"}
        )
        events = await stranger.get(f"/api/v1/dialogs/{dialog_id}/events")
        listed = await stranger.get("/api/v1/dialogs")
        missing = await stranger.get(f"/api/v1/dialogs/{uuid4()}/messages")

    for response in (history, submitted, events, missing):
        assert response.status_code == 404
        assert response.json() == {"detail": "Dialog not found."}
    assert listed.json() == {"dialogs": []}
    assert agent.calls == []
    assert await store.get(TEST_USER.id, UUID(dialog_id)) == ()
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/v1/dialogs", "/api/v1/dialogs/not-a-uuid/messages"],
)
async def test_guest_gets_401_before_validation(path: str) -> None:
    service = AgentService(
        EchoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )

    async with make_client(service, {}) as client:
        response = await client.get(path)

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/dialogs"),
        ("POST", "/api/v1/dialogs"),
        ("GET", f"/api/v1/dialogs/{uuid4()}/messages"),
        ("GET", f"/api/v1/dialogs/{uuid4()}/events"),
    ],
)
async def test_unavailable_store_returns_safe_503(method: str, path: str) -> None:
    service = AgentService(
        EchoAgent(), UnavailableHistoryStore(), InMemoryDialogEventBroker()
    )

    async with make_client(service) as client:
        response = await client.request(method, path)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    await service.shutdown()


@pytest.mark.asyncio
async def test_unavailable_store_on_submit_returns_safe_503() -> None:
    service = AgentService(
        EchoAgent(), UnavailableHistoryStore(), InMemoryDialogEventBroker()
    )

    async with make_client(service) as client:
        response = await client.post(
            f"/api/v1/dialogs/{uuid4()}/messages", json={"request": "hi"}
        )

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    await service.shutdown()
