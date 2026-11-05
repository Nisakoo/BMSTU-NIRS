import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthConfig,
    AuthService,
    AuthUnavailableError,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
    InvalidCredentialsError,
    LoginTakenError,
    Role,
    SamePasswordError,
    UnauthorizedError,
    WrongPasswordError,
)

SECRET = "test-secret-with-at-least-32-bytes!!"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


class FailingBlacklist(InMemoryTokenBlacklist):
    async def contains(self, jti: str) -> bool:
        raise AuthUnavailableError

    async def add(self, jti: str, expires_at: datetime) -> None:
        raise AuthUnavailableError


class CountingHasher(Argon2PasswordHasher):
    def __init__(self) -> None:
        super().__init__(time_cost=1, memory_cost=8, parallelism=1)
        self.verify_calls = 0

    async def verify(self, password_hash: str, password: str) -> bool:
        self.verify_calls += 1
        return await super().verify(password_hash, password)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def sessions() -> InMemoryRefreshSessionStore:
    return InMemoryRefreshSessionStore()


@pytest.fixture
def hasher() -> CountingHasher:
    return CountingHasher()


def make_service(
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
    *,
    users: InMemoryUserStore | None = None,
    blacklist: InMemoryTokenBlacklist | None = None,
) -> AuthService:
    return AuthService(
        users=users or InMemoryUserStore(),
        sessions=sessions,
        blacklist=blacklist or InMemoryTokenBlacklist(clock=clock),
        config=AuthConfig(jwt_secret=SECRET),
        password_hasher=hasher,
        clock=clock,
    )


@pytest.fixture
def service(
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> AuthService:
    return make_service(clock, sessions, hasher)


async def test_register_creates_user_role_and_hashes_password() -> None:
    users = InMemoryUserStore()
    clock = Clock()
    service = make_service(
        clock, InMemoryRefreshSessionStore(), CountingHasher(), users=users
    )

    user = await service.register("Krosh", "password123")

    assert isinstance(user.id, UUID)
    assert user.login == "Krosh"
    assert user.role is Role.USER
    stored = await users.get_by_login("krosh")
    assert stored is not None
    assert stored.password_hash.startswith("$argon2id$")
    assert "password123" not in stored.password_hash


async def test_register_rejects_login_that_differs_only_by_case(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")

    with pytest.raises(LoginTakenError):
        await service.register("kROSH", "other-password")


async def test_login_is_case_insensitive_and_issues_tokens(
    service: AuthService,
    clock: Clock,
) -> None:
    registered = await service.register("Krosh", "password123")

    result = await service.login("krosh", "password123")

    assert result.user == registered
    assert result.tokens.access_expires_at == clock.now + timedelta(seconds=900)
    assert result.tokens.refresh_expires_at == clock.now + timedelta(days=30)
    assert await service.authenticate(result.tokens.access_token) == registered


async def test_login_failures_are_indistinguishable_and_always_verify_hash(
    service: AuthService,
    hasher: CountingHasher,
) -> None:
    await service.register("Krosh", "password123")

    with pytest.raises(InvalidCredentialsError) as wrong_password:
        await service.login("Krosh", "wrong-password")
    with pytest.raises(InvalidCredentialsError) as unknown_login:
        await service.login("Nyusha", "password123")

    assert str(wrong_password.value) == str(unknown_login.value)
    assert hasher.verify_calls == 2


async def test_authenticate_rejects_expired_foreign_and_garbage_tokens(
    service: AuthService,
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens
    other = AuthService(
        users=InMemoryUserStore(),
        sessions=sessions,
        blacklist=InMemoryTokenBlacklist(clock=clock),
        config=AuthConfig(jwt_secret="another-secret-with-at-least-32-bytes"),
        password_hasher=hasher,
        clock=clock,
    )
    await other.register("Krosh", "password123")
    foreign = (await other.login("Krosh", "password123")).tokens.access_token

    for token in (foreign, "not-a-jwt", ""):
        with pytest.raises(UnauthorizedError):
            await service.authenticate(token)

    clock.advance(seconds=900)
    with pytest.raises(UnauthorizedError):
        await service.authenticate(tokens.access_token)


async def test_authenticate_returns_current_role_from_store(
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> None:
    users = InMemoryUserStore()
    service = make_service(clock, sessions, hasher, users=users)
    user = await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    users.set_role(user.id, Role.ADMIN)

    assert (await service.authenticate(tokens.access_token)).role is Role.ADMIN


async def test_refresh_rotates_token_and_detects_reuse(
    service: AuthService,
    clock: Clock,
) -> None:
    user = await service.register("Krosh", "password123")
    first = (await service.login("Krosh", "password123")).tokens

    clock.advance(minutes=1)
    second = await service.refresh(first.refresh_token)

    assert second.user == user
    assert second.tokens.refresh_token != first.refresh_token
    assert second.tokens.access_token != first.access_token
    assert await service.authenticate(second.tokens.access_token) == user

    with pytest.raises(UnauthorizedError):
        await service.refresh(first.refresh_token)
    with pytest.raises(UnauthorizedError):
        await service.refresh(second.tokens.refresh_token)


async def test_refresh_rejects_unknown_and_expired_tokens(
    service: AuthService,
    clock: Clock,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    with pytest.raises(UnauthorizedError):
        await service.refresh("unknown-refresh-token")

    clock.advance(days=30)
    with pytest.raises(UnauthorizedError):
        await service.refresh(tokens.refresh_token)


async def test_logout_blacklists_access_until_expiry_and_revokes_refresh(
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> None:
    blacklist = InMemoryTokenBlacklist(clock=clock)
    service = make_service(clock, sessions, hasher, blacklist=blacklist)
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    await service.logout(tokens.access_token, tokens.refresh_token)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(tokens.access_token)
    with pytest.raises(UnauthorizedError):
        await service.refresh(tokens.refresh_token)
    assert list(blacklist.expirations.values()) == [tokens.access_expires_at]


async def test_logout_is_idempotent_and_accepts_missing_or_invalid_tokens(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    await service.logout(None, None)
    await service.logout("garbage", "garbage")
    await service.logout(tokens.access_token, tokens.refresh_token)
    await service.logout(tokens.access_token, tokens.refresh_token)


async def test_logout_with_access_only_revokes_its_refresh_session(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    await service.logout(tokens.access_token, None)

    with pytest.raises(UnauthorizedError):
        await service.refresh(tokens.refresh_token)


async def test_unavailable_blacklist_fails_closed(
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> None:
    service = make_service(
        clock, sessions, hasher, blacklist=FailingBlacklist(clock=clock)
    )
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    with pytest.raises(AuthUnavailableError):
        await service.authenticate(tokens.access_token)
    with pytest.raises(AuthUnavailableError):
        await service.logout(tokens.access_token, None)


async def test_change_password_replaces_hash_for_later_logins(
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> None:
    users = InMemoryUserStore()
    service = make_service(clock, sessions, hasher, users=users)
    user = await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    await service.change_password(tokens.access_token, "password123", "carrot-456")

    with pytest.raises(InvalidCredentialsError):
        await service.login("Krosh", "password123")
    assert (await service.login("Krosh", "carrot-456")).user == user
    stored = await users.get_by_login("Krosh")
    assert stored is not None
    assert stored.password_hash.startswith("$argon2id$")
    assert "carrot-456" not in stored.password_hash


async def test_change_password_keeps_current_session_and_revokes_others(
    service: AuthService,
    clock: Clock,
) -> None:
    await service.register("Krosh", "password123")
    await service.register("Nyusha", "password123")
    current = (await service.login("Krosh", "password123")).tokens
    other = (await service.login("Krosh", "password123")).tokens
    stranger = (await service.login("Nyusha", "password123")).tokens

    await service.change_password(current.access_token, "password123", "carrot-456")

    clock.advance(minutes=1)
    assert (await service.refresh(current.refresh_token)).user.login == "Krosh"
    with pytest.raises(UnauthorizedError):
        await service.refresh(other.refresh_token)
    assert (await service.refresh(stranger.refresh_token)).user.login == "Nyusha"


async def test_change_password_rejects_wrong_current_password(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    current = (await service.login("Krosh", "password123")).tokens
    other = (await service.login("Krosh", "password123")).tokens

    with pytest.raises(WrongPasswordError):
        await service.change_password(current.access_token, "wrong-pass", "carrot-456")

    assert (await service.login("Krosh", "password123")).user.login == "Krosh"
    assert (await service.refresh(other.refresh_token)).user.login == "Krosh"


async def test_change_password_rejects_the_same_password_after_checking_it(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    with pytest.raises(WrongPasswordError):
        await service.change_password(tokens.access_token, "wrong-pass", "wrong-pass")
    with pytest.raises(SamePasswordError):
        await service.change_password(tokens.access_token, "password123", "password123")


async def test_change_password_requires_a_valid_access_token(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens
    await service.logout(tokens.access_token, None)

    for token in (tokens.access_token, "garbage"):
        with pytest.raises(UnauthorizedError):
            await service.change_password(token, "password123", "carrot-456")


async def test_change_password_logs_events_without_passwords(
    service: AuthService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123")).tokens

    with caplog.at_level(logging.INFO, logger="smeshariki_ai"):
        with pytest.raises(WrongPasswordError):
            await service.change_password(tokens.access_token, "wrong-pass", "x" * 8)
        await service.change_password(tokens.access_token, "password123", "carrot-456")

    events = {getattr(record, "event", None): record for record in caplog.records}
    assert "auth.password.rejected" in events
    assert "auth.password.changed" in events
    for record in caplog.records:
        rendered = f"{record.getMessage()} {record.__dict__}"
        for secret in ("password123", "wrong-pass", "carrot-456", "$argon2id$"):
            assert secret not in rendered
    assert events["auth.password.changed"].log_fields["user_id"] == str(user.id)
    rejected = events["auth.password.rejected"].log_fields
    assert rejected["user_id"] == str(user.id)
    assert rejected["outcome"] == "rejected"
