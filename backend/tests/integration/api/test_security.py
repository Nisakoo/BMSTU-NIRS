import logging
from collections.abc import AsyncIterator, Iterator
from io import StringIO

import httpx
import pytest
from api_auth_support import AUTH_COOKIES, TEST_USER, static_auth_service

from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthConfig,
    AuthService,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
)
from smeshariki_ai.dialogs import InMemoryHistoryStore
from smeshariki_ai.observability import EventFormatter

SECRET = "test-secret-with-at-least-32-bytes!!"
PASSWORD = "password123"
CREDENTIALS = '{"login":"Krosh","password":"password123"}'


class NoAgent:
    async def run(self, history, request):  # type: ignore[no-untyped-def]
        raise AssertionError("Agent must not run in security tests")
        yield


def make_app(*, real_auth: bool):  # type: ignore[no-untyped-def]
    service = AgentService(
        NoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )
    auth_service = (
        AuthService(
            users=InMemoryUserStore(),
            sessions=InMemoryRefreshSessionStore(),
            blacklist=InMemoryTokenBlacklist(),
            config=AuthConfig(jwt_secret=SECRET),
            password_hasher=Argon2PasswordHasher(
                time_cost=1, memory_cost=8, parallelism=1
            ),
        )
        if real_auth
        else static_auth_service()
    )
    return service, create_app(service, auth_service=auth_service)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    _, app = make_app(real_auth=True)
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


async def login_status(client: httpx.AsyncClient, **kwargs: object) -> httpx.Response:
    return await client.post("/api/v1/auth/login", **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["cross-site", "same-site", "Cross-Site"])
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_cross_site_unsafe_requests_are_forbidden(
    client: httpx.AsyncClient, method: str, value: str
) -> None:
    response = await client.request(
        method,
        "/api/v1/auth/login",
        content=CREDENTIALS,
        headers={"Sec-Fetch-Site": value, "Content-Type": "application/json"},
    )

    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_origin"}
    assert "set-cookie" not in response.headers
    assert "x-request-id" in response.headers


@pytest.mark.parametrize("value", ["same-origin", "none", None])
async def test_same_origin_none_and_missing_header_pass(
    client: httpx.AsyncClient, value: str | None
) -> None:
    await client.post("/api/v1/users", json={"login": "Krosh", "password": PASSWORD})
    headers = {} if value is None else {"Sec-Fetch-Site": value}

    response = await login_status(
        client, json={"login": "Krosh", "password": PASSWORD}, headers=headers
    )

    assert response.status_code == 200


async def test_cross_site_get_is_not_affected(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/users/me", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 401


async def test_forbidden_origin_precedes_authentication_and_validation(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/dialogs",
        headers={"Sec-Fetch-Site": "same-site"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/plain"},
        {"Content-Type": "application/x-www-form-urlencoded"},
        {"Content-Type": "multipart/form-data; boundary=x"},
        {"Content-Type": "application/jsonx"},
        {},
    ],
)
@pytest.mark.parametrize("path", ["/api/v1/users", "/api/v1/auth/login"])
async def test_credentials_require_json_media_type(
    client: httpx.AsyncClient, path: str, headers: dict[str, str]
) -> None:
    # The body is valid JSON, so only the media type can cause the rejection.
    response = await client.post(path, content=CREDENTIALS, headers=headers)

    assert response.status_code == 415
    assert response.json() == {"error": "unsupported_media_type"}
    assert "set-cookie" not in response.headers
    login = await login_status(
        client, content=CREDENTIALS, headers={"Content-Type": "application/json"}
    )
    assert login.status_code == 401  # no user was created


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=utf-8", "Application/JSON"],
)
async def test_json_media_type_variants_are_accepted(
    client: httpx.AsyncClient, content_type: str
) -> None:
    response = await client.post(
        "/api/v1/users",
        content=CREDENTIALS,
        headers={"Content-Type": content_type},
    )

    assert response.status_code == 201


async def test_checks_run_in_order_403_415_422(client: httpx.AsyncClient) -> None:
    both = await client.post(
        "/api/v1/users",
        content="not json",
        headers={"Sec-Fetch-Site": "cross-site", "Content-Type": "text/plain"},
    )
    media = await client.post(
        "/api/v1/users", content="not json", headers={"Content-Type": "text/plain"}
    )
    invalid = await client.post(
        "/api/v1/users",
        content="not json",
        headers={"Content-Type": "application/json"},
    )

    assert (both.status_code, media.status_code, invalid.status_code) == (
        403,
        415,
        422,
    )


async def test_messages_require_json_after_authentication() -> None:
    service, app = make_app(real_auth=False)
    dialog_id = await service.start_dialog(TEST_USER.id)
    path = f"/api/v1/dialogs/{dialog_id}/messages"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as guest:
        guest_response = await guest.post(
            path, content='{"request":"hi"}', headers={"Content-Type": "text/plain"}
        )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", cookies=AUTH_COOKIES
    ) as user:
        rejected = await user.post(
            path, content='{"request":"hi"}', headers={"Content-Type": "text/plain"}
        )
        missing = await user.post(path, content='{"request":"hi"}')
        accepted = await user.post(
            path,
            content='{"request":"hi"}',
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    assert guest_response.status_code == 401
    assert rejected.status_code == missing.status_code == 415
    assert rejected.json() == {"detail": "Unsupported media type."}
    assert accepted.status_code == 202
    await service.shutdown()


async def test_rejections_are_logged_without_request_details(
    client: httpx.AsyncClient, log_output: StringIO
) -> None:
    await client.post(
        "/api/v1/auth/login",
        content='{"login":"secret-login","password":"secret-password"}',
        headers={"Content-Type": "text/secret-type"},
    )
    await client.post(
        "/api/v1/auth/login",
        content="secret-body",
        headers={"Sec-Fetch-Site": "cross-site", "Cookie": "access_token=secret-token"},
    )

    logs = log_output.getvalue()
    assert "http.request.unsupported_media_type" in logs
    assert "http.request.forbidden_origin" in logs
    for secret in (
        "secret-login",
        "secret-password",
        "secret-type",
        "secret-body",
        "secret-token",
    ):
        assert secret not in logs
