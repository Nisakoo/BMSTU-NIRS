import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

import httpx
import pytest

from smeshariki_ai.admin import (
    AdminStatsService,
    AdminStatsStore,
    AdminStatsUnavailableError,
    FeedbackStats,
    RecentUser,
    UserStatsSnapshot,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthConfig,
    AuthService,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
    Role,
)
from smeshariki_ai.dialogs import InMemoryHistoryStore
from smeshariki_ai.observability import EventFormatter

SECRET = "test-secret-with-at-least-32-bytes!!"
PASSWORD = "password123"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


class NoAgent:
    async def run(self, history, request):  # type: ignore[no-untyped-def]
        raise AssertionError("Agent must not run in admin tests")
        yield


class FakeStatsStore(AdminStatsStore):
    def __init__(self) -> None:
        self.available = True
        self.calls: list[datetime] = []

    async def user_stats(self, since: datetime, limit: int) -> UserStatsSnapshot:
        self.calls.append(since)
        if not self.available:
            raise AdminStatsUnavailableError
        return UserStatsSnapshot(
            users_total=3,
            new_users=1,
            active_users=2,
            feedback=FeedbackStats(
                answers_total=10, rated_answers=5, counts=(1, 0, 0, 1, 3)
            ),
            recent_users=(
                RecentUser(
                    id=UUID(int=1),
                    login="Krosh",
                    role=Role.USER,
                    registered_at=NOW - timedelta(days=1),
                    last_active_at=NOW - timedelta(hours=2),
                ),
                RecentUser(
                    id=UUID(int=2),
                    login="Sovunya",
                    role=Role.ADMIN,
                    registered_at=NOW - timedelta(days=60),
                    last_active_at=None,
                ),
            ),
        )


@pytest.fixture
def users() -> InMemoryUserStore:
    return InMemoryUserStore()


@pytest.fixture
def stats_store() -> FakeStatsStore:
    return FakeStatsStore()


def make_app(users: InMemoryUserStore, stats: AdminStatsService | None):  # type: ignore[no-untyped-def]
    auth_service = AuthService(
        users=users,
        sessions=InMemoryRefreshSessionStore(),
        blacklist=InMemoryTokenBlacklist(),
        config=AuthConfig(jwt_secret=SECRET),
        password_hasher=Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1),
    )
    service = AgentService(
        NoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )
    return create_app(service, auth_service=auth_service, admin_stats=stats)


@pytest.fixture
async def client(
    users: InMemoryUserStore, stats_store: FakeStatsStore
) -> AsyncIterator[httpx.AsyncClient]:
    app = make_app(users, AdminStatsService(stats_store, clock=lambda: NOW))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as value:
        yield value


@pytest.fixture
def log_output() -> Iterator[StringIO]:
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(EventFormatter("json"))
    app_logger = logging.getLogger("smeshariki_ai")
    original_level = app_logger.level
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.DEBUG)
    try:
        yield output
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(original_level)


async def login_as(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    role: Role,
    login: str = "Sovunya",
) -> None:
    registered = await client.post(
        "/api/v1/users", json={"login": login, "password": PASSWORD}
    )
    assert registered.status_code == 201
    users.set_role(UUID(registered.json()["id"]), role)
    response = await client.post(
        "/api/v1/auth/login", json={"login": login, "password": PASSWORD}
    )
    assert response.status_code == 200


async def test_admin_receives_user_statistics(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    stats_store: FakeStatsStore,
) -> None:
    await login_as(client, users, Role.ADMIN)

    response = await client.get("/api/v1/admin/stats", params={"period": "30"})

    assert response.status_code == 200
    assert stats_store.calls == [NOW - timedelta(days=30)]
    assert response.json() == {
        "period": "30",
        "users_total": 3,
        "active_users": 2,
        "new_users": 1,
        "recent_users": [
            {
                "id": str(UUID(int=1)),
                "login": "Krosh",
                "role": "user",
                "registered_at": "2026-10-15T12:00:00Z",
                "last_active_at": "2026-10-16T10:00:00Z",
                "status": "new",
            },
            {
                "id": str(UUID(int=2)),
                "login": "Sovunya",
                "role": "admin",
                "registered_at": "2026-08-17T12:00:00Z",
                "last_active_at": None,
                "status": "inactive",
            },
        ],
        "feedback": {
            "answers_total": 10,
            "rated_answers": 5,
            "counts": [1, 0, 0, 1, 3],
        },
    }


@pytest.mark.parametrize("query", ["", "?period=30", "?period=bad"])
async def test_guest_is_rejected_before_validation(
    client: httpx.AsyncClient, stats_store: FakeStatsStore, query: str
) -> None:
    response = await client.get(f"/api/v1/admin/stats{query}")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert stats_store.calls == []


@pytest.mark.parametrize("query", ["?period=30", "?period=bad"])
async def test_regular_user_is_forbidden(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    stats_store: FakeStatsStore,
    query: str,
) -> None:
    await login_as(client, users, Role.USER, "Krosh")

    response = await client.get(f"/api/v1/admin/stats{query}")

    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}
    assert stats_store.calls == []


@pytest.mark.parametrize("query", ["", "?period=1", "?period=thirty"])
async def test_admin_with_invalid_period_gets_422(
    client: httpx.AsyncClient, users: InMemoryUserStore, query: str
) -> None:
    await login_as(client, users, Role.ADMIN)

    response = await client.get(f"/api/v1/admin/stats{query}")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_unavailable_storage_returns_503(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    stats_store: FakeStatsStore,
) -> None:
    await login_as(client, users, Role.ADMIN)
    stats_store.available = False

    response = await client.get("/api/v1/admin/stats", params={"period": "7"})

    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}


async def test_missing_stats_service_returns_503(users: InMemoryUserStore) -> None:
    app = make_app(users, None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await login_as(client, users, Role.ADMIN)
        response = await client.get("/api/v1/admin/stats", params={"period": "7"})

    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}


async def test_logs_do_not_contain_returned_logins(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    log_output: StringIO,
) -> None:
    await login_as(client, users, Role.ADMIN, "Pin")

    response = await client.get("/api/v1/admin/stats", params={"period": "7"})

    assert response.status_code == 200
    logs = log_output.getvalue()
    assert "Krosh" not in logs
    assert "Sovunya" not in logs
