import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID, uuid4

import httpx
import pytest
from api_auth_support import AUTH_COOKIES, TEST_USER, static_auth_service

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    AgentTextDelta,
    Message,
    UserRequest,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthConfig,
    AuthService,
    AuthUnavailableError,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
)
from smeshariki_ai.dialogs import InMemoryHistoryStore
from smeshariki_ai.observability import EventFormatter


class StreamingAgent:
    async def run(
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
    app = create_app(
        service,
        heartbeat_seconds=heartbeat_seconds,
        auth_service=static_auth_service(),
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=AUTH_COOKIES,
    )


@pytest.mark.asyncio
async def test_sse_stream_returns_ready_and_ordered_message_events() -> None:
    store = InMemoryHistoryStore()
    service = AgentService(StreamingAgent(), store, InMemoryDialogEventBroker())
    dialog_id = await service.start_dialog(TEST_USER.id)
    client = make_client(service)

    async def drive_dialog() -> None:
        await asyncio.sleep(0)
        await service.submit(dialog_id, TEST_USER.id, UserRequest(content="question"))
        while len(await store.list(TEST_USER.id, 10, None)) != 1:
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
    service = AgentService(
        StreamingAgent(),
        InMemoryHistoryStore(),
        InMemoryDialogEventBroker(),
    )
    dialog_id = await service.start_dialog(TEST_USER.id)
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
    service = AgentService(
        StreamingAgent(),
        InMemoryHistoryStore(),
        InMemoryDialogEventBroker(),
    )
    client = make_client(service)

    async with client:
        response = await client.get(path)

    assert response.status_code == expected_status
    await service.shutdown()


@pytest.mark.asyncio
async def test_sse_rejects_subscription_after_shutdown() -> None:
    service = AgentService(
        StreamingAgent(),
        InMemoryHistoryStore(),
        InMemoryDialogEventBroker(),
    )
    dialog_id = await service.start_dialog(TEST_USER.id)
    await service.shutdown()
    client = make_client(service)

    async with client:
        response = await client.get(f"/api/v1/dialogs/{dialog_id}/events")

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service is unavailable."}


class Clock:
    def __init__(self) -> None:
        # Cookie lifetimes are derived from the real clock.
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


class SwitchableBlacklist(InMemoryTokenBlacklist):
    available = True

    async def contains(self, jti: str) -> bool:
        if not self.available:
            raise AuthUnavailableError
        return await super().contains(jti)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def blacklist(clock: Clock) -> SwitchableBlacklist:
    return SwitchableBlacklist(clock=clock)


@pytest.fixture
async def session(
    clock: Clock, blacklist: SwitchableBlacklist
) -> AsyncIterator[tuple[AgentService, UUID, httpx.AsyncClient]]:
    auth_service = AuthService(
        users=InMemoryUserStore(),
        sessions=InMemoryRefreshSessionStore(),
        blacklist=blacklist,
        config=AuthConfig(jwt_secret="test-secret-with-at-least-32-bytes!!"),
        password_hasher=Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1),
        clock=clock,
    )
    service = AgentService(
        StreamingAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )
    app = create_app(service, heartbeat_seconds=0.02, auth_service=auth_service)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )
    credentials = {"login": "Krosh", "password": "password123"}
    await client.post("/api/v1/users", json=credentials)
    assert (
        await client.post("/api/v1/auth/login", json=credentials)
    ).status_code == 200
    created = await client.post("/api/v1/dialogs")
    assert created.status_code == 201
    return service, UUID(created.json()["dialog_id"]), client


@pytest.mark.asyncio
async def test_sse_closes_after_logout_within_heartbeat(
    session: tuple[AgentService, UUID, httpx.AsyncClient],
) -> None:
    _, dialog_id, client = session

    async def logout() -> None:
        await asyncio.sleep(0.1)
        assert (await client.post("/api/v1/auth/logout")).status_code == 204

    logout_task = asyncio.create_task(logout())
    response = await asyncio.wait_for(
        client.get(f"/api/v1/dialogs/{dialog_id}/events"), timeout=3
    )
    await logout_task

    assert response.status_code == 200
    assert response.text.startswith("event: ready")
    assert ": keep-alive" in response.text


@pytest.mark.asyncio
async def test_sse_stays_open_after_access_token_expiry(
    clock: Clock,
    session: tuple[AgentService, UUID, httpx.AsyncClient],
) -> None:
    service, dialog_id, client = session

    async def expire_then_stop() -> None:
        await asyncio.sleep(0.05)
        clock.now += timedelta(hours=1)
        await asyncio.sleep(0.2)
        await service.shutdown()

    stopper = asyncio.create_task(expire_then_stop())
    response = await asyncio.wait_for(
        client.get(f"/api/v1/dialogs/{dialog_id}/events"), timeout=3
    )
    await stopper

    # Several heartbeats passed after exp and the stream ended only on shutdown.
    assert response.text.count(": keep-alive") >= 3


@pytest.mark.asyncio
async def test_sse_closes_when_session_storage_is_unavailable(
    blacklist: SwitchableBlacklist,
    session: tuple[AgentService, UUID, httpx.AsyncClient],
) -> None:
    _, dialog_id, client = session

    async def break_storage() -> None:
        await asyncio.sleep(0.1)
        blacklist.available = False

    breaker = asyncio.create_task(break_storage())
    response = await asyncio.wait_for(
        client.get(f"/api/v1/dialogs/{dialog_id}/events"), timeout=3
    )
    await breaker

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_sse_revocation_is_logged_without_session_details(
    session: tuple[AgentService, UUID, httpx.AsyncClient],
) -> None:
    _, dialog_id, client = session
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(EventFormatter("json"))
    app_logger = logging.getLogger("smeshariki_ai")
    original_level = app_logger.level
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)

    async def logout() -> None:
        await asyncio.sleep(0.1)
        await client.post("/api/v1/auth/logout")

    try:
        logout_task = asyncio.create_task(logout())
        await asyncio.wait_for(
            client.get(f"/api/v1/dialogs/{dialog_id}/events"), timeout=3
        )
        await logout_task
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(original_level)

    event = next(
        json.loads(line)
        for line in output.getvalue().splitlines()
        if '"dialog.subscription.revoked"' in line
    )
    assert event["outcome"] == "revoked"
    assert event["dialog_id"] == str(dialog_id)
    assert "access_token" not in output.getvalue()
