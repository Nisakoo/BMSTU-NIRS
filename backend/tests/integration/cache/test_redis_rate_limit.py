import os
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from smeshariki_ai.auth import AuthUnavailableError
from smeshariki_ai.cache import RedisAttemptLimiter, RedisConfig, create_redis

REDIS_URL = os.environ.get("TEST_REDIS_URL")

needs_redis = pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL is not set")


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = create_redis(RedisConfig(url=REDIS_URL or "redis://unused"))
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


@needs_redis
async def test_hit_counts_in_fixed_window_with_ttl(redis: Redis) -> None:
    limiter = RedisAttemptLimiter(redis)

    assert await limiter.hit("login-ip:1", 2, 60) is None
    assert await limiter.hit("login-ip:1", 2, 60) is None
    retry_after = await limiter.hit("login-ip:1", 2, 60)

    assert retry_after is not None and 0 < retry_after <= 60
    assert 0 < await redis.ttl("auth:ratelimit:login-ip:1") <= 60
    assert await limiter.hit("login-ip:2", 2, 60) is None


@needs_redis
async def test_hit_does_not_extend_window(redis: Redis) -> None:
    limiter = RedisAttemptLimiter(redis)
    await limiter.hit("k", 5, 100)
    await redis.expire("auth:ratelimit:k", 10)

    await limiter.hit("k", 5, 100)

    assert await redis.ttl("auth:ratelimit:k") <= 10


@needs_redis
async def test_failures_block_and_reset(redis: Redis) -> None:
    limiter = RedisAttemptLimiter(redis)

    for _ in range(2):
        assert await limiter.blocked("login-fail:a", 2) is None
        await limiter.record_failure("login-fail:a", 900)
    retry_after = await limiter.blocked("login-fail:a", 2)

    assert retry_after is not None and 0 < retry_after <= 900
    assert await limiter.blocked("login-fail:b", 2) is None
    await limiter.reset("login-fail:a")
    assert await limiter.blocked("login-fail:a", 2) is None
    assert await redis.exists("auth:ratelimit:login-fail:a") == 0


async def test_unreachable_redis_is_unavailable() -> None:
    client = create_redis(RedisConfig(url="redis://127.0.0.1:1/0", timeout_seconds=0.5))
    limiter = RedisAttemptLimiter(client)
    try:
        with pytest.raises(AuthUnavailableError):
            await limiter.hit("k", 1, 60)
        with pytest.raises(AuthUnavailableError):
            await limiter.blocked("k", 1)
        with pytest.raises(AuthUnavailableError):
            await limiter.record_failure("k", 60)
        with pytest.raises(AuthUnavailableError):
            await limiter.reset("k")
    finally:
        await client.aclose()
