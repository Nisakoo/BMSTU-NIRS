"""Authentication stand-in for API tests that exercise protected dialog routes."""

from typing import cast
from uuid import UUID

from smeshariki_ai.auth import AuthService, Role, UnauthorizedError, User

ACCESS_TOKEN = "test-access-token"
AUTH_COOKIES = {"access_token": ACCESS_TOKEN}
TEST_USER = User(id=UUID(int=1), login="krosh", role=Role.USER)


class StaticAuthService:
    """Accepts only ``ACCESS_TOKEN``; the real service is covered by test_auth."""

    async def authenticate(self, access_token: str) -> User:
        if access_token != ACCESS_TOKEN:
            raise UnauthorizedError
        return TEST_USER


def static_auth_service() -> AuthService:
    return cast(AuthService, StaticAuthService())
