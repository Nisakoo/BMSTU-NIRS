import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from io import StringIO
from uuid import UUID

import httpx
import pytest

from smeshariki_ai.admin import (
    AdminReportsService,
    AdminStatsUnavailableError,
    MessageReport,
    ReportNotFoundError,
    ReportStatus,
    ReportStore,
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
from smeshariki_ai.dialogs import InMemoryHistoryStore, ReportReason
from smeshariki_ai.observability import EventFormatter

SECRET = "test-secret-with-at-least-32-bytes!!"
PASSWORD = "password123"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class NoAgent:
    async def run(self, history, request):  # type: ignore[no-untyped-def]
        raise AssertionError("Agent must not run in admin tests")
        yield


def report(number: int, status: ReportStatus, **changes: object) -> MessageReport:
    values: dict[str, object] = {
        "id": number,
        "reason": ReportReason.RUDE,
        "comment": None,
        "request_text": "Расскажи про Нюшу",
        "answer_text": "Грубый ответ",
        "status": status,
        "created_at": NOW,
        "resolved_at": None,
        "dialog_deleted": False,
    }
    values.update(changes)
    return MessageReport(**values)  # type: ignore[arg-type]


class FakeReportStore(ReportStore):
    def __init__(self) -> None:
        self.available = True
        self.reports = {
            1: report(1, ReportStatus.NEW, comment="Обидно", dialog_deleted=True),
            2: report(
                2,
                ReportStatus.RESOLVED,
                reason=ReportReason.SCARY,
                request_text=None,
                resolved_at=NOW,
            ),
        }
        self.listed: list[ReportStatus | None] = []
        self.changed: list[tuple[int, ReportStatus, UUID]] = []

    async def list_reports(
        self, status: ReportStatus | None, limit: int
    ) -> tuple[MessageReport, ...]:
        if not self.available:
            raise AdminStatsUnavailableError
        self.listed.append(status)
        return tuple(
            item
            for item in self.reports.values()
            if status is None or item.status is status
        )

    async def set_status(
        self, report_id: int, status: ReportStatus, admin_id: UUID
    ) -> None:
        if not self.available:
            raise AdminStatsUnavailableError
        if report_id not in self.reports:
            raise ReportNotFoundError(report_id)
        self.changed.append((report_id, status, admin_id))


@pytest.fixture
def users() -> InMemoryUserStore:
    return InMemoryUserStore()


@pytest.fixture
def store() -> FakeReportStore:
    return FakeReportStore()


def make_app(users: InMemoryUserStore, reports: AdminReportsService | None):  # type: ignore[no-untyped-def]
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
    return create_app(service, auth_service=auth_service, admin_reports=reports)


@pytest.fixture
async def client(
    users: InMemoryUserStore, store: FakeReportStore
) -> AsyncIterator[httpx.AsyncClient]:
    app = make_app(users, AdminReportsService(store))
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
) -> UUID:
    registered = await client.post(
        "/api/v1/users", json={"login": login, "password": PASSWORD}
    )
    assert registered.status_code == 201
    user_id = UUID(registered.json()["id"])
    users.set_role(user_id, role)
    response = await client.post(
        "/api/v1/auth/login", json={"login": login, "password": PASSWORD}
    )
    assert response.status_code == 200
    return user_id


async def test_admin_lists_new_reports_with_texts_but_no_author(
    client: httpx.AsyncClient, users: InMemoryUserStore, store: FakeReportStore
) -> None:
    await login_as(client, users, Role.ADMIN)

    response = await client.get("/api/v1/admin/reports")

    assert response.status_code == 200
    assert store.listed == [ReportStatus.NEW]
    assert response.json() == {
        "reports": [
            {
                "id": 1,
                "reason": "rude",
                "comment": "Обидно",
                "request_text": "Расскажи про Нюшу",
                "answer_text": "Грубый ответ",
                "status": "new",
                "created_at": "2026-10-18T12:00:00Z",
                "resolved_at": None,
                "dialog_deleted": True,
            }
        ]
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("?status=resolved", [ReportStatus.RESOLVED]),
        ("?status=dismissed", [ReportStatus.DISMISSED]),
        ("?status=all", [None]),
    ],
)
async def test_reports_are_filtered_by_status(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    store: FakeReportStore,
    query: str,
    expected: list[ReportStatus | None],
) -> None:
    await login_as(client, users, Role.ADMIN)

    response = await client.get(f"/api/v1/admin/reports{query}")

    assert response.status_code == 200
    assert store.listed == expected


async def test_admin_changes_the_status(
    client: httpx.AsyncClient, users: InMemoryUserStore, store: FakeReportStore
) -> None:
    admin_id = await login_as(client, users, Role.ADMIN)

    responses = [
        await client.patch("/api/v1/admin/reports/1", json={"status": status})
        for status in ("resolved", "dismissed", "new")
    ]

    assert [response.status_code for response in responses] == [204, 204, 204]
    assert store.changed == [
        (1, ReportStatus.RESOLVED, admin_id),
        (1, ReportStatus.DISMISSED, admin_id),
        (1, ReportStatus.NEW, admin_id),
    ]


async def test_unknown_report_is_404(
    client: httpx.AsyncClient, users: InMemoryUserStore
) -> None:
    await login_as(client, users, Role.ADMIN)

    response = await client.patch(
        "/api/v1/admin/reports/99", json={"status": "resolved"}
    )

    assert (response.status_code, response.json()) == (404, {"error": "not_found"})


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/admin/reports?status=open", None),
        ("PATCH", "/api/v1/admin/reports/abc", {"status": "resolved"}),
        ("PATCH", "/api/v1/admin/reports/0", {"status": "resolved"}),
        ("PATCH", f"/api/v1/admin/reports/{2**63}", {"status": "resolved"}),
        ("PATCH", "/api/v1/admin/reports/1", {"status": "closed"}),
        ("PATCH", "/api/v1/admin/reports/1", {}),
        ("PATCH", "/api/v1/admin/reports/1", {"status": "new", "extra": 1}),
    ],
)
async def test_admin_with_invalid_input_gets_422(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    store: FakeReportStore,
    method: str,
    path: str,
    body: object,
) -> None:
    await login_as(client, users, Role.ADMIN)

    response = await client.request(method, path, json=body)

    assert response.status_code == 422
    assert store.changed == []


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/v1/admin/reports?status=bad"), ("PATCH", "/api/v1/admin/reports/x")],
)
async def test_guest_and_user_are_rejected_before_validation(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    store: FakeReportStore,
    method: str,
    path: str,
) -> None:
    guest = await client.request(method, path, json={"status": "bad"})
    await login_as(client, users, Role.USER, "Krosh")
    user = await client.request(method, path, json={"status": "bad"})

    assert (guest.status_code, guest.json()) == (401, {"error": "unauthorized"})
    assert (user.status_code, user.json()) == (403, {"error": "forbidden"})
    assert (store.listed, store.changed) == ([], [])


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/v1/admin/reports"), ("PATCH", "/api/v1/admin/reports/1")],
)
async def test_unavailable_storage_returns_503(
    client: httpx.AsyncClient,
    users: InMemoryUserStore,
    store: FakeReportStore,
    method: str,
    path: str,
) -> None:
    await login_as(client, users, Role.ADMIN)
    store.available = False

    response = await client.request(method, path, json={"status": "resolved"})

    assert (response.status_code, response.json()) == (503, {"error": "unavailable"})


async def test_missing_reports_service_returns_503(users: InMemoryUserStore) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app(users, None)),
        base_url="http://testserver",
    ) as client:
        await login_as(client, users, Role.ADMIN)
        response = await client.get("/api/v1/admin/reports")

    assert (response.status_code, response.json()) == (503, {"error": "unavailable"})


async def test_logs_do_not_contain_report_texts(
    client: httpx.AsyncClient, users: InMemoryUserStore, log_output: StringIO
) -> None:
    await login_as(client, users, Role.ADMIN)

    await client.get("/api/v1/admin/reports?status=all")
    await client.patch("/api/v1/admin/reports/1", json={"status": "resolved"})

    logs = log_output.getvalue()
    assert "admin.report.status_changed" in logs
    for text in ("Обидно", "Нюшу", "Грубый ответ"):
        assert text not in logs
