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

from smeshariki_ai.rag.maintenance import (
    DeleteReport,
    ExportReport,
    delete_entities,
    export_package,
)
from smeshariki_ai.rag.models import EntityRef, EntityType
from smeshariki_ai.rag.package import ENTITY_TYPES_BY_DIRECTORY, Issue
from smeshariki_ai.rag.ports import KnowledgeStore
from smeshariki_ai.rag.restore import RestoreReport, restore_entity
from smeshariki_ai.rag.services import (
    CheckReport,
    LoadReport,
    check_package,
    load_package,
    package_schema,
)

StoreFactory = Callable[[], AbstractAsyncContextManager[KnowledgeStore]]


class ConfigurationError(Exception):
    """The backend config could not be loaded from the environment."""


@asynccontextmanager
async def postgres_store() -> AsyncIterator[KnowledgeStore]:
    """The production store; imported lazily so other commands need no config."""

    from smeshariki_ai.config import load_config
    from smeshariki_ai.db import create_engine
    from smeshariki_ai.rag.postgres import PostgresKnowledgeStore

    try:
        config = load_config()
    except ValidationError as error:
        # Secrets of the config never reach the message: only its absence does.
        raise ConfigurationError from error
    engine = create_engine(config.database)
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

    if arguments.command == "export":
        types = (
            [ENTITY_TYPES_BY_DIRECTORY[name] for name in arguments.type]
            if arguments.type
            else None
        )
        report = asyncio.run(_export(arguments.path, store, types))
        _write(stdout, arguments.format, report, _write_export)
        return 0 if report.exported else 1

    if arguments.command == "delete":
        report = asyncio.run(_delete(arguments.refs, store, apply=arguments.apply))
        _write(stdout, arguments.format, report, _write_delete)
        return 0 if not report.issues else 1

    if arguments.command == "restore":
        report = asyncio.run(
            _restore(
                arguments.ref,
                store,
                revision=arguments.revision,
                apply=arguments.apply,
            )
        )
        _write(stdout, arguments.format, report, _write_restore)
        return 0 if not report.issues else 1

    load = asyncio.run(_load(arguments.path, store))
    _write(stdout, arguments.format, load, _write_load)
    return 0 if load.loaded else 1


async def _load(path: Path, store: StoreFactory) -> LoadReport:
    try:
        async with store() as opened:
            return await load_package(path, opened)
    except ConfigurationError:
        return LoadReport(loaded=False, counts={}, issues=(_configuration_issue(),))


async def _export(
    path: Path, store: StoreFactory, types: Sequence[EntityType] | None
) -> ExportReport:
    try:
        async with store() as opened:
            return await export_package(path, opened, types)
    except ConfigurationError:
        return ExportReport(
            exported=False, path=str(path), issues=(_configuration_issue(),)
        )


async def _delete(
    refs: Sequence[EntityRef], store: StoreFactory, *, apply: bool
) -> DeleteReport:
    try:
        async with store() as opened:
            return await delete_entities(refs, opened, apply=apply)
    except ConfigurationError:
        return DeleteReport(applied=False, issues=(_configuration_issue(),))


async def _restore(
    ref: EntityRef,
    store: StoreFactory,
    *,
    revision: int | None,
    apply: bool,
) -> RestoreReport:
    try:
        async with store() as opened:
            return await restore_entity(ref, opened, revision=revision, apply=apply)
    except ConfigurationError:
        return RestoreReport(restored=False, issues=(_configuration_issue(),))


def _configuration_issue() -> Issue:
    return Issue(
        file=".",
        code="configuration_error",
        message="конфигурация backend не загружена: проверьте docker/.env",
    )


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
    export = commands.add_parser("export", help="выгрузить знания в пакет")
    export.add_argument("path", type=Path, help="каталог назначения")
    export.add_argument(
        "--type",
        action="append",
        choices=tuple(sorted(ENTITY_TYPES_BY_DIRECTORY)),
        help="выгрузить только этот тип; можно повторять",
    )
    export.add_argument("--format", choices=("text", "json"), default="text")
    delete = commands.add_parser("delete", help="удалить сущности с проверкой ссылок")
    delete.add_argument(
        "refs",
        nargs="+",
        type=_parse_ref,
        metavar="<type>/<id>",
        help="например characters/pin",
    )
    delete.add_argument(
        "--apply",
        action="store_true",
        help="выполнить удаление; без флага выполняется dry-run",
    )
    delete.add_argument("--format", choices=("text", "json"), default="text")
    restore = commands.add_parser(
        "restore", help="восстановить сущность из журнала ревизий"
    )
    restore.add_argument(
        "ref",
        type=_parse_ref,
        metavar="<type>/<id>",
        help="например characters/pin",
    )
    restore.add_argument(
        "--revision",
        type=_positive_int,
        help="номер ревизии; без флага берётся последняя",
    )
    restore.add_argument(
        "--apply",
        action="store_true",
        help="выполнить восстановление; без флага выполняется dry-run",
    )
    restore.add_argument("--format", choices=("text", "json"), default="text")
    commands.add_parser("schema", help="напечатать JSON Schema формата сущностей")
    return parser


def _parse_ref(value: str) -> EntityRef:
    directory, separator, entity_id = value.partition("/")
    kind = ENTITY_TYPES_BY_DIRECTORY.get(directory)
    if not separator or kind is None:
        raise argparse.ArgumentTypeError(
            "ожидается <type>/<id>, например characters/pin"
        )
    try:
        return EntityRef(type=kind, id=entity_id)
    except ValidationError as error:
        raise argparse.ArgumentTypeError(
            "id должен состоять из строчных латинских букв, цифр и «_»"
        ) from error


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("ожидается целое число") from error
    if number < 1:
        raise argparse.ArgumentTypeError("ревизия должна быть не меньше 1")
    return number


def _write(
    stdout: TextIO,
    output: str,
    report: CheckReport | LoadReport | ExportReport | DeleteReport | RestoreReport,
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


def _write_export(stdout: TextIO, report: ExportReport) -> None:
    if not report.exported:
        _write_issues(stdout, report.issues)
        stdout.write("Выгрузка отменена.\n")
        return
    stdout.write(f"Экспортировано сущностей: {report.entity_count} в {report.path}.\n")
    for name, count in report.counts.items():
        stdout.write(f"{name}: {count}\n")


def _write_delete(stdout: TextIO, report: DeleteReport) -> None:
    if report.issues:
        _write_issues(stdout, report.issues)
        stdout.write("Удаление отменено, БД не изменена.\n")
        return
    stdout.write("Удаление выполнено.\n" if report.applied else "Будет удалено.\n")
    for name, counts in report.counts.items():
        if counts.deleted:
            stdout.write(f"{name}: {counts.deleted}\n")
    if report.operation_id is not None:
        stdout.write(f"Операция {report.operation_id}.\n")
    stdout.write(
        f"Всего сущностей в БД: {report.entity_count}. "
        f"Длительность: {report.duration_ms} мс.\n"
    )


def _write_restore(stdout: TextIO, report: RestoreReport) -> None:
    if report.issues:
        _write_issues(stdout, report.issues)
        stdout.write("Восстановление отменено, БД не изменена.\n")
        return
    stdout.write(
        "Восстановление выполнено.\n" if report.restored else "Будет восстановлено.\n"
    )
    if report.revision is not None:
        stdout.write(f"Ревизия: {report.revision}.\n")
    for name, counts in report.counts.items():
        if counts.added or counts.updated or counts.unchanged:
            stdout.write(
                f"{name}: добавлено {counts.added}, изменено {counts.updated}, "
                f"без изменений {counts.unchanged}\n"
            )
    if report.operation_id is not None:
        stdout.write(f"Операция {report.operation_id}.\n")
    stdout.write(
        f"Всего сущностей в БД: {report.entity_count}. "
        f"Длительность: {report.duration_ms} мс.\n"
    )
