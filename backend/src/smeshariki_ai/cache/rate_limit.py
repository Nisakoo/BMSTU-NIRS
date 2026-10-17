from redis.asyncio import Redis
from redis.exceptions import RedisError

from smeshariki_ai.auth import AttemptLimiter, AuthUnavailableError

KEY_PREFIX = "auth:ratelimit:"


class RedisAttemptLimiter(AttemptLimiter):
    """Fixed-window counters; the window starts at the first counted event."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        count, ttl = await self._increment(key, window_seconds)
        return max(1, ttl) if count > limit else None

    async def blocked(self, key: str, limit: int) -> int | None:
        try:
            async with self._redis.pipeline(transaction=True) as pipeline:
                pipeline.get(KEY_PREFIX + key)
                pipeline.ttl(KEY_PREFIX + key)
                value, ttl = await pipeline.execute()
        except (RedisError, OSError, TimeoutError) as error:
            raise AuthUnavailableError from error
        if value is None or int(value) < limit:
            return None
        return max(1, ttl)

    async def record_failure(self, key: str, window_seconds: int) -> None:
        await self._increment(key, window_seconds)

    async def reset(self, key: str) -> None:
        try:
            await self._redis.delete(KEY_PREFIX + key)
        except (RedisError, OSError, TimeoutError) as error:
            raise AuthUnavailableError from error

    async def _increment(self, key: str, window_seconds: int) -> tuple[int, int]:
        try:
            async with self._redis.pipeline(transaction=True) as pipeline:
                pipeline.incr(KEY_PREFIX + key)
                pipeline.expire(KEY_PREFIX + key, window_seconds, nx=True)
                pipeline.ttl(KEY_PREFIX + key)
                count, _, ttl = await pipeline.execute()
        except (RedisError, OSError, TimeoutError) as error:
            raise AuthUnavailableError from error
        return int(count), int(ttl)
