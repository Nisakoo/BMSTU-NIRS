import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    """Argon2id hashing executed outside the event loop thread."""

    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 64 * 1024,
        parallelism: int = 4,
        max_concurrency: int = 4,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
        )
        # Each operation needs memory_cost KiB, so concurrent ones are bounded.
        self._semaphore = asyncio.Semaphore(max_concurrency)
        # Verified for unknown logins so their timing matches existing ones.
        self.dummy_hash = self._hasher.hash("dummy-password-for-timing")

    async def hash(self, password: str) -> str:
        async with self._semaphore:
            return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        def verify() -> bool:
            try:
                return self._hasher.verify(password_hash, password)
            except (VerificationError, InvalidHashError):
                return False

        async with self._semaphore:
            return await asyncio.to_thread(verify)
