import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from smeshariki_ai.auth.config import AuthConfig
from smeshariki_ai.auth.memory import InMemoryAttemptLimiter
from smeshariki_ai.auth.models import (
    AccessClaims,
    AuthResult,
    InvalidCredentialsError,
    IssuedTokens,
    RefreshSession,
    Role,
    TooManyAttemptsError,
    UnauthorizedError,
    User,
)
from smeshariki_ai.auth.passwords import Argon2PasswordHasher
from smeshariki_ai.auth.stores import (
    AttemptLimiter,
    RefreshSessionStore,
    TokenBlacklist,
    UserStore,
)
from smeshariki_ai.auth.tokens import TokenCodec, hash_refresh_token, new_refresh_token
from smeshariki_ai.auth.users import create_user
from smeshariki_ai.observability import log_event

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class AuthService:
    """Registration, login, access validation, refresh rotation and logout.

    The service is transport independent: it does not know about cookies or
    HTTP and receives already validated credentials.
    """

    def __init__(
        self,
        *,
        users: UserStore,
        sessions: RefreshSessionStore,
        blacklist: TokenBlacklist,
        config: AuthConfig,
        password_hasher: Argon2PasswordHasher | None = None,
        clock: Clock | None = None,
        limiter: AttemptLimiter | None = None,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._blacklist = blacklist
        self._hasher = password_hasher or Argon2PasswordHasher()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._limiter = limiter or InMemoryAttemptLimiter(clock=self._clock)
        self._limits = config.rate_limit
        self._codec = TokenCodec(config)
        self._access_ttl = timedelta(seconds=config.access_ttl_seconds)
        self._refresh_ttl = timedelta(seconds=config.refresh_ttl_seconds)

    async def register(self, login: str, password: str) -> User:
        user = await create_user(
            self._users, self._hasher, login, password, Role.USER, self._clock()
        )
        log_event(logger, logging.INFO, "auth.user.registered", user_id=str(user.id))
        return user

    async def limit_register_ip(self, client_ip: str) -> None:
        """Count a registration request of ``client_ip`` before its body is read."""

        await self._hit(
            "register_ip",
            f"register-ip:{client_ip}",
            self._limits.register_per_ip,
            self._limits.register_per_ip_window_seconds,
        )

    async def limit_login_ip(self, client_ip: str) -> None:
        """Count a login request of ``client_ip`` before its body is read."""

        await self._hit(
            "login_ip",
            f"login-ip:{client_ip}",
            self._limits.login_per_ip,
            self._limits.login_per_ip_window_seconds,
        )

    async def login(self, login: str, password: str, client_ip: str) -> AuthResult:
        # The login is hashed so the limiter storage never holds it in clear.
        digest = hashlib.sha256(login.lower().encode()).hexdigest()
        failure_key = f"login-fail:{digest}:{client_ip}"
        retry_after = await self._limiter.blocked(
            failure_key, self._limits.login_failures
        )
        if retry_after is not None:
            self._log_rate_limited("login_failures")
            raise TooManyAttemptsError("login_failures", retry_after)

        record = await self._users.get_by_login(login)
        if record is None:
            await self._hasher.verify(self._hasher.dummy_hash, password)
            await self._limiter.record_failure(
                failure_key, self._limits.login_failure_window_seconds
            )
            self._log_rejected("auth.login.rejected", None)
            raise InvalidCredentialsError
        if not await self._hasher.verify(record.password_hash, password):
            await self._limiter.record_failure(
                failure_key, self._limits.login_failure_window_seconds
            )
            self._log_rejected("auth.login.rejected", record.user.id)
            raise InvalidCredentialsError
        await self._limiter.reset(failure_key)

        now = self._clock()
        session, refresh_token = self._new_session(record.user.id, uuid4(), now)
        await self._sessions.create(session)
        log_event(
            logger, logging.INFO, "auth.login.succeeded", user_id=str(record.user.id)
        )
        return self._result(record.user, session, refresh_token, now)

    async def authenticate(self, access_token: str) -> User:
        claims = self._codec.decode_access(access_token, self._clock())
        return await self._resolve(claims)

    async def verify_session(self, access_token: str) -> User:
        """Re-check a token for a long-lived stream: ``exp`` is not enforced."""

        claims = self._codec.decode_access(
            access_token, self._clock(), verify_expiry=False
        )
        return await self._resolve(claims)

    async def refresh(self, refresh_token: str) -> AuthResult:
        now = self._clock()
        current = await self._sessions.get_by_token_hash(
            hash_refresh_token(refresh_token)
        )
        if current is None:
            self._log_rejected("auth.refresh.rejected", None)
            raise UnauthorizedError
        if current.revoked_at is not None:
            await self._reject_reuse(current, now)
        if current.expires_at <= now:
            self._log_rejected("auth.refresh.rejected", current.user_id)
            raise UnauthorizedError
        user = await self._users.get_by_id(current.user_id)
        if user is None:
            self._log_rejected("auth.refresh.rejected", current.user_id)
            raise UnauthorizedError

        replacement, new_token = self._new_session(user.id, current.family_id, now)
        if not await self._sessions.rotate(current.id, replacement, now):
            # Another request rotated the same token first: treat it as reuse.
            await self._reject_reuse(current, now)
        log_event(logger, logging.INFO, "auth.refresh.succeeded", user_id=str(user.id))
        return self._result(user, replacement, new_token, now)

    async def logout(
        self,
        access_token: str | None,
        refresh_token: str | None,
    ) -> None:
        now = self._clock()
        user_id: UUID | None = None
        families: set[UUID] = set()
        if access_token:
            try:
                claims = self._codec.decode_access(access_token, now)
            except UnauthorizedError:
                pass
            else:
                user_id = claims.user_id
                families.add(claims.family_id)
                await self._blacklist.add(claims.jti, claims.expires_at)
        if refresh_token:
            session = await self._sessions.get_by_token_hash(
                hash_refresh_token(refresh_token)
            )
            if session is not None:
                user_id = user_id or session.user_id
                families.add(session.family_id)
        for family_id in families:
            await self._revoke_family(family_id, now)
        log_event(
            logger,
            logging.INFO,
            "auth.logout.completed",
            user_id=None if user_id is None else str(user_id),
        )

    async def _hit(self, limit: str, key: str, maximum: int, window: int) -> None:
        retry_after = await self._limiter.hit(key, maximum, window)
        if retry_after is not None:
            self._log_rate_limited(limit)
            raise TooManyAttemptsError(limit, retry_after)

    @staticmethod
    def _log_rate_limited(limit: str) -> None:
        log_event(
            logger,
            logging.INFO,
            "auth.rate_limit.rejected",
            limit=limit,
            outcome="rejected",
        )

    async def _reject_reuse(self, session: RefreshSession, now: datetime) -> None:
        await self._revoke_family(session.family_id, now)
        log_event(
            logger,
            logging.WARNING,
            "auth.refresh.reuse_detected",
            user_id=str(session.user_id),
            outcome="family_revoked",
        )
        raise UnauthorizedError

    async def _revoke_family(self, family_id: UUID, now: datetime) -> None:
        await self._sessions.revoke_family(family_id, now)
        await self._blacklist.revoke_family(family_id, now + self._access_ttl)

    async def _resolve(self, claims: AccessClaims) -> User:
        if await self._blacklist.contains(claims.jti):
            raise UnauthorizedError
        if await self._blacklist.family_revoked(claims.family_id):
            raise UnauthorizedError
        user = await self._users.get_by_id(claims.user_id)
        if user is None:
            raise UnauthorizedError
        return user

    def _new_session(
        self,
        user_id: UUID,
        family_id: UUID,
        now: datetime,
    ) -> tuple[RefreshSession, str]:
        token = new_refresh_token()
        session = RefreshSession(
            id=uuid4(),
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh_token(token),
            created_at=now,
            expires_at=now + self._refresh_ttl,
        )
        return session, token

    def _result(
        self,
        user: User,
        session: RefreshSession,
        refresh_token: str,
        now: datetime,
    ) -> AuthResult:
        access_token, claims = self._codec.encode_access(
            user.id, user.role, session.id, session.family_id, now
        )
        return AuthResult(
            user=user,
            tokens=IssuedTokens(
                access_token=access_token,
                access_expires_at=claims.expires_at,
                refresh_token=refresh_token,
                refresh_expires_at=session.expires_at,
            ),
        )

    @staticmethod
    def _log_rejected(event: str, user_id: UUID | None) -> None:
        log_event(
            logger,
            logging.INFO,
            event,
            user_id=None if user_id is None else str(user_id),
            outcome="rejected",
        )
