import math
from collections.abc import Callable
from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import RedisError

from smeshariki_ai.auth import AuthUnavailableError, TokenBlacklist
from smeshariki_ai.cache.config import RedisConfig

KEY_PREFIX = "auth:blacklist:"


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
        ttl_seconds = math.ceil((expires_at - self._clock()).total_seconds())
        if ttl_seconds <= 0:
            return
        try:
            await self._redis.set(KEY_PREFIX + jti, b"1", ex=ttl_seconds)
        except (RedisError, OSError, TimeoutError) as error:
            raise AuthUnavailableError from error

    async def contains(self, jti: str) -> bool:
        try:
            return bool(await self._redis.exists(KEY_PREFIX + jti))
        except (RedisError, OSError, TimeoutError) as error:
            raise AuthUnavailableError from error
