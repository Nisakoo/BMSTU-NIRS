from datetime import UTC, datetime, timedelta

import pytest

from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthConfig,
    AuthService,
    AuthUnavailableError,
    InMemoryAttemptLimiter,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
    InvalidCredentialsError,
    RateLimitConfig,
    TooManyAttemptsError,
)

SECRET = "test-secret-with-at-least-32-bytes!!"
IP = "203.0.113.7"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


class SpyHasher(Argon2PasswordHasher):
    def __init__(self) -> None:
        super().__init__(time_cost=1, memory_cost=8, parallelism=1)
        self.verify_calls = 0

    async def verify(self, password_hash: str, password: str) -> bool:
        self.verify_calls += 1
        return await super().verify(password_hash, password)


class BrokenLimiter(InMemoryAttemptLimiter):
    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        raise AuthUnavailableError

    async def blocked(self, key: str, limit: int) -> int | None:
        raise AuthUnavailableError


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def hasher() -> SpyHasher:
    return SpyHasher()


def make_service(
    clock: Clock, hasher: SpyHasher, limiter: InMemoryAttemptLimiter | None = None
) -> AuthService:
    return AuthService(
        users=InMemoryUserStore(),
        sessions=InMemoryRefreshSessionStore(),
        blacklist=InMemoryTokenBlacklist(clock=clock),
        config=AuthConfig(jwt_secret=SECRET),
        password_hasher=hasher,
        clock=clock,
        limiter=limiter or InMemoryAttemptLimiter(clock=clock),
    )


def test_rate_limit_config_defaults() -> None:
    config = RateLimitConfig()

    assert config.login_failures == 5
    assert config.login_failure_window_seconds == 900
    assert config.login_per_ip == 30
    assert config.login_per_ip_window_seconds == 60
    assert config.register_per_ip == 10
    assert config.register_per_ip_window_seconds == 3600


async def test_hit_allows_limit_then_returns_retry_after(clock: Clock) -> None:
    limiter = InMemoryAttemptLimiter(clock=clock)

    for _ in range(3):
        assert await limiter.hit("k", 3, 60) is None
    assert await limiter.hit("k", 3, 60) == 60

    clock.advance(seconds=20.5)
    assert await limiter.hit("k", 3, 60) == 40

    clock.advance(seconds=40)
    assert await limiter.hit("k", 3, 60) is None


async def test_failures_block_until_window_ends_and_reset_clears(
    clock: Clock,
) -> None:
    limiter = InMemoryAttemptLimiter(clock=clock)
    for _ in range(2):
        await limiter.record_failure("k", 900)
    assert await limiter.blocked("k", 2) == 900
    assert await limiter.blocked("k", 3) is None
    assert await limiter.blocked("other", 2) is None

    await limiter.reset("k")
    assert await limiter.blocked("k", 2) is None

    await limiter.record_failure("k", 900)
    await limiter.record_failure("k", 900)
    clock.advance(seconds=901)
    assert await limiter.blocked("k", 2) is None


async def test_sixth_attempt_with_correct_password_is_blocked_without_verify(
    clock: Clock, hasher: SpyHasher
) -> None:
    service = make_service(clock, hasher)
    await service.register("Krosh", "password123")

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await service.login("Krosh", "wrong-password", IP)
    calls = hasher.verify_calls

    with pytest.raises(TooManyAttemptsError) as error:
        await service.login("krosh", "password123", IP)

    assert error.value.retry_after == 900
    assert error.value.limit == "login_failures"
    assert hasher.verify_calls == calls
    # Another address is not affected; the window expiry restores access.
    assert (await service.login("Krosh", "password123", "198.51.100.1")).user
    clock.advance(seconds=901)
    assert (await service.login("Krosh", "password123", IP)).user


async def test_successful_login_resets_failures(
    clock: Clock, hasher: SpyHasher
) -> None:
    service = make_service(clock, hasher)
    await service.register("Krosh", "password123")

    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            await service.login("Krosh", "wrong-password", IP)
    await service.login("Krosh", "password123", IP)

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await service.login("Krosh", "wrong-password", IP)
    with pytest.raises(TooManyAttemptsError):
        await service.login("Krosh", "password123", IP)


async def test_unknown_login_failures_are_counted(
    clock: Clock, hasher: SpyHasher
) -> None:
    service = make_service(clock, hasher)

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await service.login("Nyusha", "password123", IP)

    with pytest.raises(TooManyAttemptsError):
        await service.login("Nyusha", "password123", IP)


async def test_ip_limits_for_login_and_registration(
    clock: Clock, hasher: SpyHasher
) -> None:
    service = make_service(clock, hasher)

    for _ in range(30):
        await service.limit_login_ip(IP)
    with pytest.raises(TooManyAttemptsError) as login_error:
        await service.limit_login_ip(IP)
    assert (login_error.value.limit, login_error.value.retry_after) == (
        "login_ip",
        60,
    )
    await service.limit_login_ip("198.51.100.1")

    for _ in range(10):
        await service.limit_register_ip(IP)
    with pytest.raises(TooManyAttemptsError) as register_error:
        await service.limit_register_ip(IP)
    assert (register_error.value.limit, register_error.value.retry_after) == (
        "register_ip",
        3600,
    )


async def test_unavailable_limiter_fails_closed_before_password_check(
    clock: Clock, hasher: SpyHasher
) -> None:
    service = make_service(clock, hasher, BrokenLimiter(clock=clock))
    await service.register("Krosh", "password123")
    calls = hasher.verify_calls

    with pytest.raises(AuthUnavailableError):
        await service.login("Krosh", "password123", IP)
    with pytest.raises(AuthUnavailableError):
        await service.limit_login_ip(IP)

    assert hasher.verify_calls == calls
