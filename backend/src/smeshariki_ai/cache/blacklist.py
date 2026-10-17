import math
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from smeshariki_ai.auth import AuthUnavailableError, TokenBlacklist
from smeshariki_ai.cache.config import RedisConfig

KEY_PREFIX = "auth:blacklist:"
FAMILY_KEY_PREFIX = "auth:revoked-family:"


def create_redis(config: RedisConfig) -> Redis:
    """Create a lazy client; no connection is opened until the first command."""

    return Redis.from_url(
        config.url.get_secret_value(),
        socket_timeout=config.timeout_seconds,
        socket_connect_timeout=config.timeout_seconds,
    )


class RedisTokenBlacklist(TokenBlacklist):
    """Stores revoked access-token ids until the token would expire anyway."""

    def __init__(
        self,
        redis: Redis,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._redis = redis
        self._clock = clock or (lambda: datetime.now(UTC))

    async def add(self, jti: str, expires_at: datetime) -> None:
        await self._set(KEY_PREFIX + jti, expires_at)

    async def contains(self, jti: str) -> bool:
        return await self._exists(KEY_PREFIX + jti)

    async def revoke_family(self, family_id: UUID, until: datetime) -> None:
        await self._set(FAMILY_KEY_PREFIX + str(family_id), until)

    async def family_revoked(self, family_id: UUID) -> bool:
        return await self._exists(FAMILY_KEY_PREFIX + str(family_id))

    async def _set(self, key: str, until: datetime) -> None:
        ttl_seconds = math.ceil((until - self._clock()).total_seconds())
        if ttl_seconds <= 0:
            return
        try:
            await self._redis.set(key, b"1", ex=ttl_seconds)
        except (RedisError, OSError, TimeoutError) as error:
            raise AuthUnavailableError from error

    async def _exists(self, key: str) -> bool:
        try:
            return bool(await self._redis.exists(key))
        except (RedisError, OSError, TimeoutError) as error:
            raise AuthUnavailableError from error
