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
    UnauthorizedError,
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

    async def revoke_family(self, family_id: UUID, until: datetime) -> None:
        raise AuthUnavailableError

    async def family_revoked(self, family_id: UUID) -> bool:
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

    result = await service.login("krosh", "password123", "127.0.0.1")

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
        await service.login("Krosh", "wrong-password", "127.0.0.1")
    with pytest.raises(InvalidCredentialsError) as unknown_login:
        await service.login("Nyusha", "password123", "127.0.0.1")

    assert str(wrong_password.value) == str(unknown_login.value)
    assert hasher.verify_calls == 2


async def test_authenticate_rejects_expired_foreign_and_garbage_tokens(
    service: AuthService,
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens
    other = AuthService(
        users=InMemoryUserStore(),
        sessions=sessions,
        blacklist=InMemoryTokenBlacklist(clock=clock),
        config=AuthConfig(jwt_secret="another-secret-with-at-least-32-bytes"),
        password_hasher=hasher,
        clock=clock,
    )
    await other.register("Krosh", "password123")
    foreign = (
        await other.login("Krosh", "password123", "127.0.0.1")
    ).tokens.access_token

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
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

    users.set_role(user.id, Role.ADMIN)

    assert (await service.authenticate(tokens.access_token)).role is Role.ADMIN


async def test_refresh_rotates_token_and_detects_reuse(
    service: AuthService,
    clock: Clock,
) -> None:
    user = await service.register("Krosh", "password123")
    first = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

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
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

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
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

    await service.logout(tokens.access_token, tokens.refresh_token)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(tokens.access_token)
    with pytest.raises(UnauthorizedError):
        await service.refresh(tokens.refresh_token)
    assert list(blacklist.expirations.values()) == [tokens.access_expires_at]
    assert list(blacklist.family_expirations.values()) == [tokens.access_expires_at]


async def test_logout_is_idempotent_and_accepts_missing_or_invalid_tokens(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

    await service.logout(None, None)
    await service.logout("garbage", "garbage")
    await service.logout(tokens.access_token, tokens.refresh_token)
    await service.logout(tokens.access_token, tokens.refresh_token)


async def test_logout_with_access_only_revokes_its_refresh_session(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

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
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

    with pytest.raises(AuthUnavailableError):
        await service.authenticate(tokens.access_token)
    with pytest.raises(AuthUnavailableError):
        await service.logout(tokens.access_token, None)


async def test_logout_revokes_whole_family_including_other_access_tokens(
    service: AuthService,
    clock: Clock,
) -> None:
    await service.register("Krosh", "password123")
    first = (await service.login("Krosh", "password123", "127.0.0.1")).tokens
    clock.advance(minutes=1)
    second = (await service.refresh(first.refresh_token)).tokens
    other_login = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

    await service.logout(second.access_token, None)

    for token in (first.access_token, second.access_token):
        with pytest.raises(UnauthorizedError):
            await service.authenticate(token)
    with pytest.raises(UnauthorizedError):
        await service.refresh(second.refresh_token)
    # Another login is a separate family and stays valid.
    await service.authenticate(other_login.access_token)


async def test_logout_with_refresh_only_revokes_family_access_tokens(
    service: AuthService,
) -> None:
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

    await service.logout(None, tokens.refresh_token)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(tokens.access_token)


async def test_refresh_reuse_revokes_family_access_tokens(
    service: AuthService,
    clock: Clock,
) -> None:
    await service.register("Krosh", "password123")
    first = (await service.login("Krosh", "password123", "127.0.0.1")).tokens
    clock.advance(minutes=1)
    second = (await service.refresh(first.refresh_token)).tokens

    with pytest.raises(UnauthorizedError):
        await service.refresh(first.refresh_token)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(second.access_token)


async def test_verify_session_ignores_expiry_but_not_revocation(
    service: AuthService,
    clock: Clock,
) -> None:
    user = await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens

    clock.advance(hours=2)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(tokens.access_token)
    assert await service.verify_session(tokens.access_token) == user
    with pytest.raises(UnauthorizedError):
        await service.verify_session("garbage")

    await service.logout(None, tokens.refresh_token)
    with pytest.raises(UnauthorizedError):
        await service.verify_session(tokens.access_token)


async def test_verify_session_rejects_deleted_user(
    clock: Clock,
    sessions: InMemoryRefreshSessionStore,
    hasher: CountingHasher,
) -> None:
    users = InMemoryUserStore()
    service = make_service(clock, sessions, hasher, users=users)
    await service.register("Krosh", "password123")
    tokens = (await service.login("Krosh", "password123", "127.0.0.1")).tokens
    users._users.clear()

    with pytest.raises(UnauthorizedError):
        await service.verify_session(tokens.access_token)
