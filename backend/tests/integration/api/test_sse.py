import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import uuid4

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
from smeshariki_ai.application import AgentService
from smeshariki_ai.dialogs import InMemoryHistoryStore


class StreamingAgent:
    async def stream(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        yield AgentTextDelta(content="Привет")
        await asyncio.sleep(0)
        yield AgentTextDelta(content=", Крош!")
        yield AgentResponse(content="Привет, Крош!")


def make_client(
    service: AgentService,
    *,
    heartbeat_seconds: float = 15.0,
) -> httpx.AsyncClient:
    app = create_app(service, heartbeat_seconds=heartbeat_seconds)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_sse_stream_returns_ready_and_ordered_message_events() -> None:
    store = InMemoryHistoryStore()
    service = AgentService(StreamingAgent(), store)
    dialog_id = await service.start_dialog()
    client = make_client(service)

    async def drive_dialog() -> None:
        await asyncio.sleep(0)
        await service.submit(dialog_id, UserRequest(content="question"))
        while len(await store.get(dialog_id)) != 2:
            await asyncio.sleep(0)
        await service.shutdown()

    driver = asyncio.create_task(drive_dialog())
    async with client:
        response = await client.get(f"/api/v1/dialogs/{dialog_id}/events")
    await driver

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.text.split("\n\n")[:-1] == [
        f'event: ready\ndata: {{"dialog_id":"{dialog_id}"}}',
        "event: message_start\ndata: {}",
        'event: message_delta\ndata: {"delta":"Привет"}',
        'event: message_delta\ndata: {"delta":", Крош!"}',
        "event: message_end\ndata: {}",
    ]


@pytest.mark.asyncio
async def test_sse_sends_heartbeat_while_dialog_is_idle() -> None:
    service = AgentService(StreamingAgent(), InMemoryHistoryStore())
    dialog_id = await service.start_dialog()
    client = make_client(service, heartbeat_seconds=0.001)

    async def stop_service() -> None:
        await asyncio.sleep(0.01)
        await service.shutdown()

    stopper = asyncio.create_task(stop_service())
    async with client:
        response = await client.get(f"/api/v1/dialogs/{dialog_id}/events")
    await stopper

    assert ": keep-alive\n\n" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/api/v1/dialogs/not-a-uuid/events", 422),
        (f"/api/v1/dialogs/{uuid4()}/events", 404),
    ],
)
async def test_sse_rejects_invalid_or_unknown_dialog(
    path: str,
    expected_status: int,
) -> None:
    service = AgentService(StreamingAgent(), InMemoryHistoryStore())
    client = make_client(service)

    async with client:
        response = await client.get(path)

    assert response.status_code == expected_status
    await service.shutdown()


@pytest.mark.asyncio
async def test_sse_rejects_subscription_after_shutdown() -> None:
    service = AgentService(StreamingAgent(), InMemoryHistoryStore())
    dialog_id = await service.start_dialog()
    await service.shutdown()
    client = make_client(service)

    async with client:
        response = await client.get(f"/api/v1/dialogs/{dialog_id}/events")

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service is unavailable."}
