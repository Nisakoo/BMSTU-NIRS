import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from io import StringIO

import pytest

from smeshariki_ai.auth import (
    Argon2PasswordHasher,
    AuthUnavailableError,
    InMemoryUserStore,
    Role,
)
from smeshariki_ai.create_admin import run

PASSWORD = "admin-password-123"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


class Prompt:
    """Stands in for ``getpass``: returns prepared answers and records prompts."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


class UnavailableUserStore(InMemoryUserStore):
    async def create(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AuthUnavailableError


@pytest.fixture
def hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture
def log_output() -> Iterator[StringIO]:
    output = StringIO()
    handler = logging.StreamHandler(output)
    app_logger = logging.getLogger("smeshariki_ai")
    original_level = app_logger.level
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.DEBUG)
    try:
        yield output
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(original_level)


async def call(
    argv: list[str],
    users: InMemoryUserStore,
    hasher: Argon2PasswordHasher,
    prompt: Prompt,
) -> tuple[int, str]:
    output = StringIO()
    code = await run(
        argv,
        users=users,
        hasher=hasher,
        read_password=prompt,
        output=output,
        clock=lambda: NOW,
    )
    return code, output.getvalue()


async def test_creates_admin_with_verifiable_password_hash(
    hasher: Argon2PasswordHasher,
    log_output: StringIO,
) -> None:
    users = InMemoryUserStore()
    prompt = Prompt(PASSWORD, PASSWORD)

    code, output = await call(["--login", "Sovunya"], users, hasher, prompt)

    assert code == 0
    assert "Sovunya" in output
    assert len(prompt.prompts) == 2
    record = await users.get_by_login("sovunya")
    assert record is not None
    assert record.user.login == "Sovunya"
    assert record.user.role is Role.ADMIN
    assert record.password_hash != PASSWORD
    assert await hasher.verify(record.password_hash, PASSWORD)
    assert PASSWORD not in output + log_output.getvalue()


async def test_rejects_login_taken_in_another_case(
    hasher: Argon2PasswordHasher,
) -> None:
    users = InMemoryUserStore()
    await call(["--login", "Krosh"], users, hasher, Prompt(PASSWORD, PASSWORD))

    code, output = await call(
        ["--login", "krosh"], users, hasher, Prompt("other-password", "other-password")
    )

    assert code == 1
    assert "занят" in output
    record = await users.get_by_login("krosh")
    assert record is not None
    assert await hasher.verify(record.password_hash, PASSWORD)


@pytest.mark.parametrize(
    ("login", "answers"),
    [
        pytest.param("no", (), id="short-login"),
        pytest.param("bad login!", (), id="login-characters"),
        pytest.param("Nyusha", ("short", "short"), id="short-password"),
        pytest.param("Nyusha", (PASSWORD, PASSWORD + "x"), id="mismatch"),
    ],
)
async def test_invalid_input_creates_nothing(
    hasher: Argon2PasswordHasher,
    login: str,
    answers: tuple[str, ...],
) -> None:
    users = InMemoryUserStore()

    code, output = await call(["--login", login], users, hasher, Prompt(*answers))

    assert code == 1
    assert output
    assert await users.get_by_login(login) is None
    for answer in answers:
        assert answer not in output


async def test_invalid_login_is_rejected_before_password_prompt(
    hasher: Argon2PasswordHasher,
) -> None:
    prompt = Prompt()

    code, _ = await call(["--login", "x"], InMemoryUserStore(), hasher, prompt)

    assert code == 1
    assert prompt.prompts == []


async def test_unavailable_storage_reports_error(
    hasher: Argon2PasswordHasher,
) -> None:
    code, output = await call(
        ["--login", "Pin"], UnavailableUserStore(), hasher, Prompt(PASSWORD, PASSWORD)
    )

    assert code == 1
    assert "недоступна" in output
    assert PASSWORD not in output


async def test_password_cannot_be_passed_as_argument(
    hasher: Argon2PasswordHasher,
) -> None:
    with pytest.raises(SystemExit):
        await call(
            ["--login", "Pin", "--password", PASSWORD],
            InMemoryUserStore(),
            hasher,
            Prompt(),
        )
