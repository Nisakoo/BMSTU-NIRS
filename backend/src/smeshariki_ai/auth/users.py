from datetime import datetime
from uuid import uuid4

from smeshariki_ai.auth.models import Role, User
from smeshariki_ai.auth.passwords import Argon2PasswordHasher
from smeshariki_ai.auth.stores import UserStore


async def create_user(
    users: UserStore,
    hasher: Argon2PasswordHasher,
    login: str,
    password: str,
    role: Role,
    created_at: datetime,
) -> User:
    """Hash the password and persist a user; shared by registration and CLI."""

    password_hash = await hasher.hash(password)
    return await users.create(uuid4(), login, password_hash, role, created_at)
