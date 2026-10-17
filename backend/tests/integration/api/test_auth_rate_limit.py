import logging
from collections.abc import AsyncIterator, Iterator
from io import StringIO

import httpx
import pytest

from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthConfig,
    AuthService,
    AuthUnavailableError,
    InMemoryAttemptLimiter,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
    RateLimitConfig,
)
from smeshariki_ai.dialogs import InMemoryHistoryStore
from smeshariki_ai.observability import EventFormatter

SECRET = "test-secret-with-at-least-32-bytes!!"
PASSWORD = "password123"
CLIENT_IP = "203.0.113.7"
OTHER_IP = "198.51.100.1"


class NoAgent:
    async def run(self, history, request):  # type: ignore[no-untyped-def]
        raise AssertionError("Agent must not run in rate limit tests")
        yield


class SpyHasher(Argon2PasswordHasher):
    def __init__(self) -> None:
        super().__init__(time_cost=1, memory_cost=8, parallelism=1)
        self.hash_calls = 0
        self.verify_calls = 0

    async def hash(self, password: str) -> str:
        self.hash_calls += 1
        return await super().hash(password)

    async def verify(self, password_hash: str, password: str) -> bool:
        self.verify_calls += 1
        return await super().verify(password_hash, password)


class SwitchableLimiter(InMemoryAttemptLimiter):
    def __init__(self) -> None:
        super().__init__()
        self.available = True

    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        if not self.available:
            raise AuthUnavailableError
        return await super().hit(key, limit, window_seconds)

    async def blocked(self, key: str, limit: int) -> int | None:
        if not self.available:
            raise AuthUnavailableError
        return await super().blocked(key, limit)


@pytest.fixture
def hasher() -> SpyHasher:
    return SpyHasher()


@pytest.fixture
def limiter() -> SwitchableLimiter:
    return SwitchableLimiter()


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


def make_client(
    hasher: SpyHasher,
    limiter: SwitchableLimiter,
    rate_limit: RateLimitConfig,
    *,
    ip: str = CLIENT_IP,
) -> httpx.AsyncClient:
    auth_service = AuthService(
        users=InMemoryUserStore(),
        sessions=InMemoryRefreshSessionStore(),
        blacklist=InMemoryTokenBlacklist(),
        config=AuthConfig(jwt_secret=SECRET, rate_limit=rate_limit),
        password_hasher=hasher,
        limiter=limiter,
    )
    service = AgentService(
        NoAgent(), InMemoryHistoryStore(), InMemoryDialogEventBroker()
    )
    app = create_app(service, auth_service=auth_service)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 5000)),
        base_url="http://testserver",
    )


@pytest.fixture
async def client(
    hasher: SpyHasher, limiter: SwitchableLimiter
) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(hasher, limiter, RateLimitConfig()) as value:
        yield value


def credentials(password: str = PASSWORD) -> dict[str, str]:
    return {"login": "Krosh", "password": password}


async def test_sixth_login_attempt_is_limited_without_password_check(
    client: httpx.AsyncClient, hasher: SpyHasher
) -> None:
    await client.post("/api/v1/users", json=credentials())
    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login", json=credentials("wrong-password")
        )
        assert response.status_code == 401
    calls = hasher.verify_calls

    response = await client.post("/api/v1/auth/login", json=credentials())

    assert response.status_code == 429
    assert response.json() == {"error": "too_many_attempts"}
    assert 0 < int(response.headers["retry-after"]) <= 900
    assert hasher.verify_calls == calls


async def test_other_ip_and_successful_login_are_not_limited(
    hasher: SpyHasher, limiter: SwitchableLimiter
) -> None:
    async with (
        make_client(hasher, limiter, RateLimitConfig()) as first,
        make_client(hasher, limiter, RateLimitConfig(), ip=OTHER_IP) as second,
    ):
        for _ in range(5):
            await first.post("/api/v1/auth/login", json=credentials("wrong-password"))
        blocked = await first.post("/api/v1/auth/login", json=credentials())
        ok = await second.post("/api/v1/auth/login", json=credentials())

    assert blocked.status_code == 429
    assert ok.status_code == 401


async def test_login_ip_limit_applies_before_body_validation(
    hasher: SpyHasher, limiter: SwitchableLimiter
) -> None:
    config = RateLimitConfig(login_per_ip=2)
    async with make_client(hasher, limiter, config) as client:
        invalid = [
            await client.post("/api/v1/auth/login", json={"login": "x"})
            for _ in range(2)
        ]
        limited = await client.post("/api/v1/auth/login", json={"login": "x"})

    assert [response.status_code for response in invalid] == [422, 422]
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert hasher.verify_calls == 0


async def test_register_ip_limit_skips_hashing(
    hasher: SpyHasher, limiter: SwitchableLimiter
) -> None:
    config = RateLimitConfig(register_per_ip=1)
    async with make_client(hasher, limiter, config) as client:
        first = await client.post("/api/v1/users", json=credentials())
        calls = hasher.hash_calls
        limited = await client.post(
            "/api/v1/users", json={"login": "Losyash", **{"password": PASSWORD}}
        )

    assert first.status_code == 201
    assert limited.status_code == 429
    assert limited.json() == {"error": "too_many_attempts"}
    assert limited.headers["retry-after"] == "3600"
    assert hasher.hash_calls == calls


@pytest.mark.parametrize("path", ["/api/v1/users", "/api/v1/auth/login"])
async def test_check_order_is_403_415_429_422(
    hasher: SpyHasher, limiter: SwitchableLimiter, path: str
) -> None:
    config = RateLimitConfig(login_per_ip=1, register_per_ip=1)
    async with make_client(hasher, limiter, config) as client:
        await client.post(path, json=credentials())  # consumes the IP budget

        cross_site = await client.post(
            path, json=credentials(), headers={"Sec-Fetch-Site": "cross-site"}
        )
        wrong_type = await client.post(
            path, content=b"{}", headers={"Content-Type": "text/plain"}
        )
        limited = await client.post(path, json={"login": "x"})

    assert cross_site.status_code == 403
    assert wrong_type.status_code == 415
    assert limited.status_code == 429


async def test_invalid_body_spends_only_the_ip_budget(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/v1/users", json=credentials())
    for _ in range(6):
        response = await client.post("/api/v1/auth/login", json={"login": "Krosh"})
        assert response.status_code == 422

    response = await client.post("/api/v1/auth/login", json=credentials())

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/users", "/api/v1/auth/login"])
async def test_unavailable_limiter_returns_503_without_password_check(
    client: httpx.AsyncClient,
    hasher: SpyHasher,
    limiter: SwitchableLimiter,
    path: str,
) -> None:
    limiter.available = False

    response = await client.post(path, json=credentials())

    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}
    assert hasher.hash_calls == 0
    assert hasher.verify_calls == 0


async def test_rejection_is_logged_without_login_password_or_ip(
    client: httpx.AsyncClient, log_output: StringIO
) -> None:
    for _ in range(6):
        await client.post("/api/v1/auth/login", json=credentials("secret-marker-1"))

    text = log_output.getvalue()
    assert '"event":"auth.rate_limit.rejected"' in text
    assert '"limit":"login_failures"' in text
    for marker in ("Krosh", "krosh", "secret-marker-1", CLIENT_IP):
        assert marker not in text
