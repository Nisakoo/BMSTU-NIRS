"""Create an administrator: ``python -m smeshariki_ai.create_admin --login <login>``.

The password is read interactively and never accepted as an argument or from
the environment, so it does not end up in shell history or process listings.
"""

import argparse
import asyncio
import getpass
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TextIO

from pydantic import TypeAdapter, ValidationError

from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthUnavailableError,
    Credentials,
    LoginTakenError,
    Role,
    UserStore,
)
from smeshariki_ai.auth.models import Login
from smeshariki_ai.auth.users import create_user
from smeshariki_ai.observability import log_event

logger = logging.getLogger(__name__)

LOGIN_RULES = "Логин: от 3 до 32 символов, латинские буквы, цифры, «_», «.» или «-»."
PASSWORD_RULES = "Пароль: от 8 до 128 символов."


class _CreateAdminError(Exception):
    """Carries a message that is safe to show: it never contains the password."""


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m smeshariki_ai.create_admin",
        description="Создать пользователя с ролью admin.",
    )
    parser.add_argument("--login", required=True)
    return parser.parse_args(argv)


async def run(
    argv: Sequence[str],
    *,
    users: UserStore,
    hasher: Argon2PasswordHasher,
    read_password: Callable[[str], str] = getpass.getpass,
    output: TextIO = sys.stdout,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    login = _parse_args(argv).login
    try:
        try:
            TypeAdapter(Login).validate_python(login)
        except ValidationError as error:
            raise _CreateAdminError(LOGIN_RULES) from error

        password = read_password("Пароль: ")
        if read_password("Повторите пароль: ") != password:
            raise _CreateAdminError("Пароли не совпадают.")
        try:
            credentials = Credentials(login=login, password=password)
        except ValidationError as error:
            raise _CreateAdminError(PASSWORD_RULES) from error

        try:
            user = await create_user(
                users,
                hasher,
                credentials.login,
                credentials.password,
                Role.ADMIN,
                clock(),
            )
        except LoginTakenError as error:
            raise _CreateAdminError(f"Логин «{login}» уже занят.") from error
        except AuthUnavailableError as error:
            raise _CreateAdminError("База данных недоступна.") from error
    except _CreateAdminError as error:
        print(f"Ошибка: {error}", file=output)
        return 1

    log_event(logger, logging.INFO, "auth.admin.created", user_id=str(user.id))
    print(f"Администратор «{user.login}» создан.", file=output)
    return 0


async def _main(argv: Sequence[str]) -> int:
    from smeshariki_ai.config import load_config
    from smeshariki_ai.db import PostgresUserStore, create_engine

    engine = create_engine(load_config().database)
    try:
        return await run(
            argv, users=PostgresUserStore(engine), hasher=Argon2PasswordHasher()
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
