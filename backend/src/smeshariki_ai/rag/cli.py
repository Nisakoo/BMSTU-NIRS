"""Knowledge commands: ``python -m smeshariki_ai.rag <command>``.

The commands are non-interactive and offer JSON output, so the content
author's agent can run them as well as a person. ``check`` and ``schema`` never
read the environment; only ``load`` loads the backend config for the database.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from smeshariki_ai.rag.models import Issue
from smeshariki_ai.rag.ports import KnowledgeStore
from smeshariki_ai.rag.services import (
    CheckReport,
    LoadReport,
    check_package,
    load_package,
    package_schema,
)

StoreFactory = Callable[[], AbstractAsyncContextManager[KnowledgeStore]]


@asynccontextmanager
async def postgres_store() -> AsyncIterator[KnowledgeStore]:
    """The production store; imported lazily so other commands need no config."""

    from smeshariki_ai.config import load_config
    from smeshariki_ai.db import create_engine
    from smeshariki_ai.rag.postgres import PostgresKnowledgeStore

    engine = create_engine(load_config().database)
    try:
        yield PostgresKnowledgeStore(engine)
    finally:
        await engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO = sys.stdout,
    store: StoreFactory = postgres_store,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exit_:
        return int(exit_.code or 0)

    if arguments.command == "schema":
        _write_json(stdout, package_schema())
        return 0

    if arguments.command == "check":
        report = check_package(arguments.path)
        _write(stdout, arguments.format, report, _write_check)
        return 0 if report.valid else 1

    load = asyncio.run(_load(arguments.path, store))
    _write(stdout, arguments.format, load, _write_load)
    return 0 if load.loaded else 1


async def _load(path: Path, store: StoreFactory) -> LoadReport:
    try:
        async with store() as opened:
            return await load_package(path, opened)
    except ValidationError:
        # Secrets of the config never reach the message: only its absence does.
        issue = Issue(
            file=".",
            code="configuration_error",
            message="конфигурация backend не загружена: проверьте docker/.env",
        )
        return LoadReport(loaded=False, counts={}, issues=(issue,))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m smeshariki_ai.rag",
        description="Проверка и загрузка пакетов структурированных знаний.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="проверить пакет без загрузки в БД")
    load = commands.add_parser("load", help="проверить пакет и загрузить его в БД")
    for command in (check, load):
        command.add_argument("path", type=Path, help="каталог пакета")
        command.add_argument("--format", choices=("text", "json"), default="text")
    commands.add_parser("schema", help="напечатать JSON Schema формата сущностей")
    return parser


def _write(
    stdout: TextIO,
    output: str,
    report: CheckReport | LoadReport,
    write_text: Callable[[TextIO, Any], None],
) -> None:
    if output == "json":
        _write_json(stdout, report.model_dump(mode="json"))
    else:
        write_text(stdout, report)


def _write_json(stdout: TextIO, value: object) -> None:
    stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_issues(stdout: TextIO, issues: Sequence[Issue]) -> None:
    for issue in issues:
        location = (
            issue.file if issue.line is None else f"{issue.file} (строка {issue.line})"
        )
        field = f" {issue.path}:" if issue.path else ""
        stdout.write(f"{location}:{field} {issue.message} [{issue.code}]\n")


def _write_check(stdout: TextIO, report: CheckReport) -> None:
    _write_issues(stdout, report.issues)
    counts = ", ".join(f"{name}: {count}" for name, count in report.counts.items())
    stdout.write(f"Сущностей: {counts}\n")
    if report.external:
        references = ", ".join(f"{ref.type.value} {ref.id}" for ref in report.external)
        stdout.write(f"Внешние ссылки (проверяются при загрузке): {references}\n")
    if report.valid:
        stdout.write("Пакет валиден.\n")
    else:
        stdout.write(f"Ошибок: {len(report.issues)}\n")


def _write_load(stdout: TextIO, report: LoadReport) -> None:
    if not report.loaded:
        _write_issues(stdout, report.issues)
        stdout.write(
            f"Загрузка отменена, БД не изменена. Ошибок: {len(report.issues)}\n"
        )
        return
    stdout.write(f"Загрузка {report.load_id} выполнена.\n")
    for name, counts in report.counts.items():
        stdout.write(
            f"{name}: добавлено {counts.added}, изменено {counts.updated}, "
            f"без изменений {counts.unchanged}\n"
        )
    stdout.write(
        f"Всего сущностей в БД: {report.entity_count}. "
        f"Длительность: {report.duration_ms} мс.\n"
    )
