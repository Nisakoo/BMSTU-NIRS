import logging
from collections.abc import AsyncIterator, Iterator
from io import StringIO

import httpx
import pytest
from fastapi import Depends

from smeshariki_ai.api import create_app
from smeshariki_ai.api.auth import current_user
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthConfig,
    AuthService,
    AuthUnavailableError,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
    User,
)
from smeshariki_ai.dialogs import InMemoryHistoryStore
from smeshariki_ai.observability import EventFormatter

SECRET = "test-secret-with-at-least-32-bytes!!"
PASSWORD = "password123"


class NoAgent:
    async def run(self, history, request):  # type: ignore[no-untyped-def]
        raise AssertionError("Agent must not run in auth tests")
        yield


class SwitchableBlacklist(InMemoryTokenBlacklist):
    def __init__(self) -> None:
        super().__init__()
        self.available = True

    async def contains(self, jti: str) -> bool:
        if not self.available:
            raise AuthUnavailableError
        return await super().contains(jti)


def make_auth_service(blacklist: InMemoryTokenBlacklist) -> AuthService:
    return AuthService(
        users=InMemoryUserStore(),
        sessions=InMemoryRefreshSessionStore(),
        blacklist=blacklist,
        config=AuthConfig(jwt_secret=SECRET),
        password_hasher=Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1),
    )


@pytest.fixture
def blacklist() -> SwitchableBlacklist:
    return SwitchableBlacklist()


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


@pytest.fixture
async def client(blacklist: SwitchableBlacklist) -> AsyncIterator[httpx.AsyncClient]:
    service = AgentService(
        NoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )
    app = create_app(service, auth_service=make_auth_service(blacklist))

    @app.get("/api/v1/protected-test")
    async def protected(user: User = Depends(current_user)) -> dict[str, str]:
        return {"id": str(user.id)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as value:
        yield value


async def register_and_login(
    client: httpx.AsyncClient,
    login: str = "Krosh",
) -> httpx.Response:
    registered = await client.post(
        "/api/v1/users", json={"login": login, "password": PASSWORD}
    )
    assert registered.status_code == 201
    response = await client.post(
        "/api/v1/auth/login", json={"login": login.lower(), "password": PASSWORD}
    )
    assert response.status_code == 200
    return response


def set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    headers = response.headers.get_list("set-cookie")
    return {header.split("=", 1)[0]: header for header in headers}


async def test_register_returns_user_without_cookies(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users", json={"login": "Krosh", "password": PASSWORD}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "login", "role"}
    assert body["login"] == "Krosh"
    assert body["role"] == "user"
    assert "set-cookie" not in response.headers


async def test_register_conflict_is_case_insensitive(client: httpx.AsyncClient) -> None:
    await client.post("/api/v1/users", json={"login": "Krosh", "password": PASSWORD})

    response = await client.post(
        "/api/v1/users", json={"login": "KROSH", "password": PASSWORD}
    )

    assert response.status_code == 409
    assert response.json() == {"error": "login_taken"}


@pytest.mark.parametrize(
    "content",
    [
        b'{"login":"Krosh","password":"password123","role":"admin"}',
        b'{"login":"Kr","password":"password123"}',
        b'{"login":"\xd0\x9a\xd1\x80\xd0\xbe\xd1\x88","password":"password123"}',
        b'{"login":"Krosh","password":"short"}',
        b'{"login":"Krosh","password":"' + b"x" * 129 + b'"}',
        b'{"login":"Krosh"}',
        b'{"login":123,"password":"password123"}',
        b"not json",
        b"",
    ],
)
async def test_invalid_fields_return_422_without_echo(
    client: httpx.AsyncClient,
    content: bytes,
) -> None:
    for path in ("/api/v1/users", "/api/v1/auth/login"):
        response = await client.post(
            path, content=content, headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422
        assert response.json() == {"error": "invalid_fields"}
    assert (
        await client.post(
            "/api/v1/auth/login", json={"login": "Krosh", "password": PASSWORD}
        )
    ).status_code == 401


async def test_login_sets_http_only_cookies(client: httpx.AsyncClient) -> None:
    response = await register_and_login(client)

    assert response.json()["login"] == "Krosh"
    cookies = set_cookie_headers(response)
    access = cookies["access_token"].lower()
    refresh = cookies["refresh_token"].lower()
    assert "httponly" in access and "httponly" in refresh
    assert "samesite=lax" in access and "samesite=lax" in refresh
    assert "path=/;" in access or access.endswith("path=/")
    assert "path=/api/v1/auth" in refresh
    assert "max-age=900" in access
    assert "max-age=2592000" in refresh
    assert "secure" not in access
    assert response.json() == (await client.get("/api/v1/users/me")).json()


async def test_login_errors_are_identical(client: httpx.AsyncClient) -> None:
    await client.post("/api/v1/users", json={"login": "Krosh", "password": PASSWORD})

    wrong = await client.post(
        "/api/v1/auth/login", json={"login": "Krosh", "password": "wrong-password"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"login": "Nyusha", "password": PASSWORD}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.content == unknown.content == b'{"error":"invalid_credentials"}'
    assert "set-cookie" not in wrong.headers


async def test_me_requires_access_cookie(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    client.cookies.set("access_token", "garbage")
    garbage = await client.get("/api/v1/users/me")

    assert response.status_code == garbage.status_code == 401
    assert response.json() == {"error": "unauthorized"}


async def test_logout_blacklists_copied_access_token(client: httpx.AsyncClient) -> None:
    login = await register_and_login(client)
    access = login.cookies["access_token"]

    logout = await client.post("/api/v1/auth/logout")
    client.cookies.set("access_token", access)
    me = await client.get("/api/v1/users/me")

    assert logout.status_code == 204
    assert logout.content == b""
    cleared = set_cookie_headers(logout)
    assert 'access_token=""' in cleared["access_token"]
    assert "max-age=0" in cleared["refresh_token"].lower()
    assert "path=/api/v1/auth" in cleared["refresh_token"].lower()
    assert me.status_code == 401


async def test_logout_without_session_returns_204(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204


async def test_refresh_rotates_cookies_and_detects_reuse(
    client: httpx.AsyncClient,
) -> None:
    login = await register_and_login(client)
    first_refresh = login.cookies["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh")
    second_refresh = refreshed.cookies["refresh_token"]
    client.cookies.clear()
    client.cookies.set("refresh_token", first_refresh, path="/api/v1/auth")
    reused = await client.post("/api/v1/auth/refresh")
    client.cookies.clear()
    client.cookies.set("refresh_token", second_refresh, path="/api/v1/auth")
    after_reuse = await client.post("/api/v1/auth/refresh")

    assert refreshed.status_code == 200
    assert refreshed.json() == login.json()
    assert second_refresh != first_refresh
    assert reused.status_code == after_reuse.status_code == 401
    assert reused.json() == {"error": "unauthorized"}
    assert "max-age=0" in set_cookie_headers(reused)["refresh_token"].lower()


async def test_unavailable_storage_returns_503(
    client: httpx.AsyncClient,
    blacklist: SwitchableBlacklist,
) -> None:
    await register_and_login(client)
    blacklist.available = False

    response = await client.get("/api/v1/users/me")
    protected = await client.get("/api/v1/protected-test")

    assert response.status_code == protected.status_code == 503
    assert response.json() == protected.json() == {"error": "unavailable"}


async def test_current_user_dependency_protects_routes(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/v1/protected-test")).status_code == 401

    await register_and_login(client)
    response = await client.get("/api/v1/protected-test")

    assert response.status_code == 200


async def test_dialog_routes_keep_their_error_format(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/dialogs/not-a-uuid/messages", json={})

    assert response.status_code == 422
    assert "detail" in response.json()


async def test_logs_do_not_contain_credentials_or_tokens(
    client: httpx.AsyncClient,
    log_output: StringIO,
) -> None:
    login = await register_and_login(client, "SecretLogin")
    await client.post("/api/v1/auth/refresh")
    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/login", json={"login": "SecretLogin", "password": "wrong-pass"}
    )

    logs = log_output.getvalue()
    assert "auth.login.succeeded" in logs
    assert "auth.logout.completed" in logs
    for secret in (
        "SecretLogin",
        "secretlogin",
        PASSWORD,
        "wrong-pass",
        login.cookies["access_token"],
        login.cookies["refresh_token"],
        SECRET,
    ):
        assert secret not in logs


async def test_cookie_secure_flag_follows_config(
    blacklist: SwitchableBlacklist,
) -> None:
    service = AgentService(
        NoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )
    app = create_app(
        service,
        auth_service=make_auth_service(blacklist),
        auth_cookie_secure=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://testserver",
    ) as secure_client:
        response = await register_and_login(secure_client)
        logout = await secure_client.post("/api/v1/auth/logout")

    for headers in (set_cookie_headers(response), set_cookie_headers(logout)):
        assert "; secure" in headers["access_token"].lower()
        assert "; secure" in headers["refresh_token"].lower()
