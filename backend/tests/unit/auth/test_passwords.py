import asyncio
import threading
import time

import pytest

from smeshariki_ai.auth import Argon2PasswordHasher


class TrackedHasher:
    """Stands in for ``argon2.PasswordHasher`` and records parallel calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def _work(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.05)
        with self._lock:
            self.active -= 1

    def hash(self, password: str) -> str:
        self._work()
        return "hash"

    def verify(self, password_hash: str, password: str) -> bool:
        self._work()
        return True


@pytest.fixture
def hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


async def test_hash_and_verify_share_the_concurrency_limit(
    hasher: Argon2PasswordHasher,
) -> None:
    tracked = TrackedHasher()
    hasher._hasher = tracked  # type: ignore[assignment]

    await asyncio.gather(
        *(hasher.hash("password123") for _ in range(8)),
        *(hasher.verify("hash", "password123") for _ in range(8)),
    )

    assert tracked.peak == 4


async def test_concurrency_limit_is_configurable() -> None:
    hasher = Argon2PasswordHasher(
        time_cost=1, memory_cost=8, parallelism=1, max_concurrency=2
    )
    tracked = TrackedHasher()
    hasher._hasher = tracked  # type: ignore[assignment]

    await asyncio.gather(*(hasher.hash("password123") for _ in range(6)))

    assert tracked.peak == 2


async def test_hash_still_verifies(hasher: Argon2PasswordHasher) -> None:
    password_hash = await hasher.hash("password123")

    assert await hasher.verify(password_hash, "password123") is True
    assert await hasher.verify(password_hash, "wrong-password") is False
