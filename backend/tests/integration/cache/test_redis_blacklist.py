import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis

from smeshariki_ai.auth import AuthUnavailableError
from smeshariki_ai.cache import RedisConfig, RedisTokenBlacklist, create_redis

REDIS_URL = os.environ.get("TEST_REDIS_URL")
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL is not set")


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = create_redis(RedisConfig(url=REDIS_URL or "redis://unused"))
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


async def test_blacklist_entry_lives_until_token_expiry(redis: Redis) -> None:
    blacklist = RedisTokenBlacklist(redis, clock=lambda: NOW)

    await blacklist.add("jti-1", NOW + timedelta(seconds=90))

    assert await blacklist.contains("jti-1") is True
    assert await blacklist.contains("jti-2") is False
    assert 0 < await redis.ttl("auth:blacklist:jti-1") <= 90


async def test_expired_token_is_not_written(redis: Redis) -> None:
    blacklist = RedisTokenBlacklist(redis, clock=lambda: NOW)

    await blacklist.add("jti-old", NOW)

    assert await redis.exists("auth:blacklist:jti-old") == 0


async def test_unreachable_redis_is_unavailable() -> None:
    client = create_redis(RedisConfig(url="redis://127.0.0.1:1/0", timeout_seconds=0.5))
    blacklist = RedisTokenBlacklist(client)
    try:
        with pytest.raises(AuthUnavailableError):
            await blacklist.contains("jti")
        with pytest.raises(AuthUnavailableError):
            await blacklist.add("jti", datetime.now(UTC) + timedelta(minutes=1))
    finally:
        await client.aclose()
