import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from smeshariki_ai.auth.config import AuthConfig
from smeshariki_ai.auth.models import (
    AuthResult,
    InvalidCredentialsError,
    IssuedTokens,
    RefreshSession,
    Role,
    UnauthorizedError,
    User,
)
from smeshariki_ai.auth.passwords import Argon2PasswordHasher
from smeshariki_ai.auth.stores import RefreshSessionStore, TokenBlacklist, UserStore
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
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._blacklist = blacklist
        self._hasher = password_hasher or Argon2PasswordHasher()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._codec = TokenCodec(config)
        self._refresh_ttl = timedelta(seconds=config.refresh_ttl_seconds)

    async def register(self, login: str, password: str) -> User:
        user = await create_user(
            self._users, self._hasher, login, password, Role.USER, self._clock()
        )
        log_event(logger, logging.INFO, "auth.user.registered", user_id=str(user.id))
        return user

    async def login(self, login: str, password: str) -> AuthResult:
        record = await self._users.get_by_login(login)
        if record is None:
            await self._hasher.verify(self._hasher.dummy_hash, password)
            self._log_rejected("auth.login.rejected", None)
            raise InvalidCredentialsError
        if not await self._hasher.verify(record.password_hash, password):
            self._log_rejected("auth.login.rejected", record.user.id)
            raise InvalidCredentialsError

        now = self._clock()
        session, refresh_token = self._new_session(record.user.id, uuid4(), now)
        await self._sessions.create(session)
        log_event(
            logger, logging.INFO, "auth.login.succeeded", user_id=str(record.user.id)
        )
        return self._result(record.user, session, refresh_token, now)

    async def authenticate(self, access_token: str) -> User:
        claims = self._codec.decode_access(access_token, self._clock())
        if await self._blacklist.contains(claims.jti):
            raise UnauthorizedError
        user = await self._users.get_by_id(claims.user_id)
        if user is None:
            raise UnauthorizedError
        return user

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
        if access_token:
            try:
                claims = self._codec.decode_access(access_token, now)
            except UnauthorizedError:
                pass
            else:
                user_id = claims.user_id
                await self._blacklist.add(claims.jti, claims.expires_at)
                await self._sessions.revoke(claims.session_id, now)
        if refresh_token:
            session = await self._sessions.get_by_token_hash(
                hash_refresh_token(refresh_token)
            )
            if session is not None:
                user_id = user_id or session.user_id
                await self._sessions.revoke(session.id, now)
        log_event(
            logger,
            logging.INFO,
            "auth.logout.completed",
            user_id=None if user_id is None else str(user_id),
        )

    async def _reject_reuse(self, session: RefreshSession, now: datetime) -> None:
        await self._sessions.revoke_family(session.family_id, now)
        log_event(
            logger,
            logging.WARNING,
            "auth.refresh.reuse_detected",
            user_id=str(session.user_id),
            outcome="family_revoked",
        )
        raise UnauthorizedError

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
            user.id, user.role, session.id, now
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
