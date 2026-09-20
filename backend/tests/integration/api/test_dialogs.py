import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID, uuid4

import httpx
import pytest

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    AgentTextDelta,
    Message,
    UserRequest,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import (
    AgentService,
    AgentServiceUnavailableError,
    InMemoryDialogEventBroker,
)
from smeshariki_ai.dialogs import InMemoryHistoryStore


class BlockingAgent:
    def __init__(self, response: str = "") -> None:
        self.response = response
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[tuple[tuple[Message, ...], UserRequest]] = []

    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.calls.append((tuple(history), request))
        self.started.set()
        await self.release.wait()
        if self.response:
            yield AgentTextDelta(content=self.response)
        yield AgentResponse(content=self.response)


def make_service(
    agent: BlockingAgent,
    history_store: InMemoryHistoryStore,
) -> AgentService:
    return AgentService(agent, history_store, InMemoryDialogEventBroker())


def make_client(
    service: AgentService,
    *,
    cookies: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    app = create_app(service)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies=cookies,
    )


async def wait_for_history_size(
    store: InMemoryHistoryStore,
    dialog_id: UUID,
    expected_size: int,
) -> tuple[Message, ...]:
    async def wait() -> tuple[Message, ...]:
        while True:
            history = await store.get(dialog_id)
            if len(history) == expected_size:
                return history
            await asyncio.sleep(0)

    return await asyncio.wait_for(wait(), timeout=1)


@pytest.mark.asyncio
async def test_create_dialog_returns_201_uuid4_and_location() -> None:
    agent = BlockingAgent()
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    client = make_client(service)

    async with client:
        response = await client.post("/api/v1/dialogs")

    assert response.status_code == 201
    dialog_id = UUID(response.json()["dialog_id"])
    assert dialog_id.version == 4
    assert response.headers["location"] == f"/api/v1/dialogs/{dialog_id}"
    assert "set-cookie" not in response.headers
    assert "access-control-allow-origin" not in response.headers
    assert await store.get(dialog_id) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_message_returns_empty_202_before_agent_finishes() -> None:
    agent = BlockingAgent(response="")
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    dialog_id = await service.start_dialog()
    client = make_client(service)

    async with client:
        response = await asyncio.wait_for(
            client.post(
                f"/api/v1/dialogs/{dialog_id}/messages",
                json={"request": "question"},
            ),
            timeout=0.1,
        )
        await asyncio.wait_for(agent.started.wait(), timeout=0.1)

    assert response.status_code == 202
    assert response.content == b""
    assert "content-type" not in response.headers
    assert not agent.release.is_set()
    assert await store.get(dialog_id) == ()

    agent.release.set()
    history = await wait_for_history_size(store, dialog_id, 2)
    assert history[-1].content == ""
    await service.shutdown()


@pytest.mark.asyncio
async def test_unknown_dialog_returns_404_without_starting_agent() -> None:
    agent = BlockingAgent()
    service = make_service(agent, InMemoryHistoryStore())
    client = make_client(service)

    async with client:
        response = await client.post(
            f"/api/v1/dialogs/{uuid4()}/messages",
            json={"request": "question"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Dialog not found."}
    assert agent.calls == []
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/dialogs/not-a-uuid/messages", {"request": "question"}),
        (f"/api/v1/dialogs/{uuid4()}/messages", {"request": "   "}),
        (f"/api/v1/dialogs/{uuid4()}/messages", {}),
    ],
    ids=["invalid-uuid", "blank-request", "missing-request"],
)
async def test_invalid_path_or_body_returns_422(path: str, body: object) -> None:
    agent = BlockingAgent()
    service = make_service(agent, InMemoryHistoryStore())
    client = make_client(service)

    async with client:
        response = await client.post(path, json=body)

    assert response.status_code == 422
    assert agent.calls == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_closed_service_returns_safe_503() -> None:
    agent = BlockingAgent()
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    dialog_id = await service.start_dialog()
    await service.shutdown()
    client = make_client(service)

    async with client:
        response = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages",
            json={"request": "question"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service is unavailable."}
    assert agent.calls == []


@pytest.mark.asyncio
async def test_cookie_does_not_select_or_modify_dialog() -> None:
    agent = BlockingAgent()
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    dialog_id = await service.start_dialog()
    client = make_client(
        service,
        cookies={"dialog_id": str(uuid4())},
    )

    async with client:
        response = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages",
            json={"request": "question"},
        )

    assert response.status_code == 202
    assert "set-cookie" not in response.headers
    await asyncio.wait_for(agent.started.wait(), timeout=0.1)
    agent.release.set()
    await wait_for_history_size(store, dialog_id, 2)
    await service.shutdown()


@pytest.mark.asyncio
async def test_application_lifespan_shuts_service_down() -> None:
    agent = BlockingAgent()
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    dialog_id = await service.start_dialog()
    app = create_app(service)

    async with app.router.lifespan_context(app):
        pass

    with pytest.raises(AgentServiceUnavailableError):
        await service.submit(dialog_id, UserRequest(content="question"))
