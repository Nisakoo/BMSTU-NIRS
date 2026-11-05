"""Authentication stand-in for API tests that exercise protected dialog routes."""

from typing import cast
from uuid import UUID

from smeshariki_ai.auth import AuthService, Role, UnauthorizedError, User

ACCESS_TOKEN = "test-access-token"
AUTH_COOKIES = {"access_token": ACCESS_TOKEN}
OTHER_ACCESS_TOKEN = "other-access-token"
ADMIN_ACCESS_TOKEN = "admin-access-token"
OTHER_COOKIES = {"access_token": OTHER_ACCESS_TOKEN}
ADMIN_COOKIES = {"access_token": ADMIN_ACCESS_TOKEN}
TEST_USER = User(id=UUID(int=1), login="krosh", role=Role.USER)
OTHER_USER = User(id=UUID(int=2), login="losyash", role=Role.USER)
ADMIN_USER = User(id=UUID(int=3), login="sovunya", role=Role.ADMIN)
USERS = {
    ACCESS_TOKEN: TEST_USER,
    OTHER_ACCESS_TOKEN: OTHER_USER,
    ADMIN_ACCESS_TOKEN: ADMIN_USER,
}


class StaticAuthService:
    """Accepts the tokens in ``USERS``; the real service is covered by test_auth."""

    async def authenticate(self, access_token: str) -> User:
        try:
            return USERS[access_token]
        except KeyError:
            raise UnauthorizedError from None

    async def verify_session(self, access_token: str) -> User:
        return await self.authenticate(access_token)


def static_auth_service() -> AuthService:
    return cast(AuthService, StaticAuthService())
