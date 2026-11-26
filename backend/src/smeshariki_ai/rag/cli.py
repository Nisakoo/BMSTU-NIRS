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

from smeshariki_ai.rag.lore.analyzer import MorphAnalyzer
from smeshariki_ai.rag.lore.benchmark import (
    BenchmarkError,
    BenchmarkReport,
    BenchmarkRunner,
    StaticAnswerer,
    read_benchmark_questions,
)
from smeshariki_ai.rag.lore.cleanup import CleanReport, clean_package
from smeshariki_ai.rag.lore.context import LoreContextBuilder
from smeshariki_ai.rag.lore.models import LoreQuery, LoreSearchResult
from smeshariki_ai.rag.lore.package import LoreCheckReport
from smeshariki_ai.rag.lore.package import check_package as lore_check_package
from smeshariki_ai.rag.lore.ports import LoreIndex, LoreStore, LoreStoreError
from smeshariki_ai.rag.lore.services import LoadLore, LoreLoadReport, SearchLore
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
LoreStoreFactory = Callable[[], AbstractAsyncContextManager[LoreStore]]
LoreIndexFactory = Callable[[], AbstractAsyncContextManager[LoreIndex]]


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


@asynccontextmanager
async def postgres_lore_store() -> AsyncIterator[LoreStore]:
    """The production lore writer; imported lazily so ``check`` needs no config."""

    from smeshariki_ai.config import load_config
    from smeshariki_ai.db import create_engine
    from smeshariki_ai.rag.lore.postgres import PostgresLoreStore

    try:
        config = load_config()
    except ValidationError as error:
        raise ConfigurationError from error
    engine = create_engine(config.database)
    try:
        yield PostgresLoreStore(engine)
    finally:
        await engine.dispose()


@asynccontextmanager
async def postgres_lore_index() -> AsyncIterator[LoreIndex]:
    """The production lore reader; imported lazily so other commands stay light."""

    from smeshariki_ai.config import load_config
    from smeshariki_ai.db import create_engine
    from smeshariki_ai.rag.lore.postgres import PostgresBm25Index

    try:
        config = load_config()
    except ValidationError as error:
        raise ConfigurationError from error
    engine = create_engine(config.database)
    try:
        yield PostgresBm25Index(engine)
    finally:
        await engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO = sys.stdout,
    store: StoreFactory = postgres_store,
    lore_store: LoreStoreFactory = postgres_lore_store,
    lore_index: LoreIndexFactory = postgres_lore_index,
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

    if arguments.command == "lore-check":
        report = lore_check_package(arguments.path)
        _write_lore_check(stdout, arguments.format, report)
        return 0 if report.valid else 1

    if arguments.command == "lore-clean":
        report = clean_package(arguments.path, apply=arguments.apply)
        _write_lore_clean(stdout, arguments.format, report)
        return 0 if not report.issues else 1

    if arguments.command == "lore-load":
        report = asyncio.run(_lore_load(arguments.path, lore_store))
        _write_lore_load(stdout, arguments.format, report)
        return 0 if report.loaded else 1

    if arguments.command == "lore-search":
        result = asyncio.run(_lore_search(arguments.query, arguments.top_k, lore_index))
        _write_lore_search(stdout, arguments.format, result)
        return 0 if result is not None else 1

    if arguments.command == "lore-benchmark":
        report = asyncio.run(
            _lore_benchmark(
                arguments.path,
                arguments.questions,
                arguments.k,
                arguments.answers,
                arguments.context,
            )
        )
        _write_lore_benchmark(stdout, arguments.format, report)
        return 0 if report is not None else 1

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


async def _lore_load(path: Path, store: LoreStoreFactory) -> LoreLoadReport:
    try:
        async with store() as opened:
            return await LoadLore(MorphAnalyzer()).load(path, opened)
    except ConfigurationError:
        return LoreLoadReport(loaded=False, issues=(_configuration_issue(),))


async def _lore_search(
    query: str,
    top_k: int,
    index: LoreIndexFactory,
) -> LoreSearchResult | None:
    try:
        searched = LoreQuery(text=query, top_k=top_k)
    except ValidationError:
        return None
    try:
        async with index() as opened:
            return await SearchLore(opened, MorphAnalyzer()).search(searched)
    except ConfigurationError:
        return None
    except LoreStoreError:
        return None


async def _lore_benchmark(
    package: Path,
    questions_path: Path,
    k: int,
    answers_path: Path | None,
    context: bool,
) -> BenchmarkReport | None:
    try:
        questions = read_benchmark_questions(questions_path)
        if answers_path is not None:
            try:
                raw = json.loads(answers_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if not isinstance(raw, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in raw.items()
            ):
                return None
            answerer = StaticAnswerer(raw)
        else:
            from smeshariki_ai.agent import LiteLLMProvider
            from smeshariki_ai.config import load_config
            from smeshariki_ai.rag.lore.benchmark_llm import LiteLLMAnswerer

            try:
                config = load_config()
            except ValidationError:
                return None
            answerer = LiteLLMAnswerer(LiteLLMProvider(config.llm))
        return await BenchmarkRunner(
            MorphAnalyzer(),
            answerer,
            k=k,
            context=LoreContextBuilder() if context else None,
        ).run(package, questions)
    except (BenchmarkError, ConfigurationError):
        return None


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
    lore_check = commands.add_parser(
        "lore-check", help="проверить YAML-пакет лора без БД"
    )
    lore_check.add_argument("path", type=Path, help="каталог пакета лора")
    lore_check.add_argument("--format", choices=("text", "json"), default="text")

    lore_clean = commands.add_parser(
        "lore-clean", help="удалить технический мусор из пакета лора"
    )
    lore_clean.add_argument("path", type=Path, help="каталог пакета лора")
    lore_clean.add_argument(
        "--apply",
        action="store_true",
        help="записать очищенные файлы; без флага выполняется dry-run",
    )
    lore_clean.add_argument("--format", choices=("text", "json"), default="text")

    lore_load = commands.add_parser(
        "lore-load", help="заменить корпус лора и построить BM25-индекс"
    )
    lore_load.add_argument("path", type=Path, help="каталог пакета лора")
    lore_load.add_argument("--format", choices=("text", "json"), default="text")

    lore_search = commands.add_parser("lore-search", help="найти фрагменты лора")
    lore_search.add_argument("query", help="поисковый запрос")
    lore_search.add_argument("--top-k", type=_positive_int, default=5)
    lore_search.add_argument("--format", choices=("text", "json"), default="text")

    lore_benchmark = commands.add_parser(
        "lore-benchmark", help="оценить BM25 на вопросах и ловушках"
    )
    lore_benchmark.add_argument("path", type=Path, help="каталог пакета лора")
    lore_benchmark.add_argument(
        "--questions", type=Path, required=True, help="YAML с вопросами"
    )
    lore_benchmark.add_argument("--k", type=_positive_int, default=5)
    lore_benchmark.add_argument(
        "--answers", type=Path, help="JSON с готовыми ответами по id вопроса"
    )
    lore_benchmark.add_argument(
        "--context",
        action="store_true",
        help="оценить также контекст агента (путь search_lore)",
    )
    lore_benchmark.add_argument("--format", choices=("text", "json"), default="text")

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


def _write_lore_check(stdout: TextIO, output: str, report: LoreCheckReport) -> None:
    if output == "json":
        _write_json(stdout, report.model_dump(mode="json"))
        return
    _write_issues(stdout, report.issues)
    stdout.write(f"Документов: {report.document_count}\n")
    if report.valid:
        stdout.write("Пакет лора валиден.\n")
    else:
        stdout.write(f"Ошибок: {len(report.issues)}\n")


def _write_lore_clean(stdout: TextIO, output: str, report: CleanReport) -> None:
    if output == "json":
        _write_json(stdout, report.model_dump(mode="json"))
        return
    if report.issues:
        _write_issues(stdout, report.issues)
        stdout.write(
            f"Чистка отменена, файлы не изменены. Ошибок: {len(report.issues)}\n"
        )
        return
    if not report.changed_count:
        stdout.write("Чистить нечего: в пакете лора нет технического мусора.\n")
        return
    action = "Очищено" if report.applied else "Будет очищено"
    stdout.write(
        f"{action} документов: {report.changed_count} из {report.document_count}; "
        f"удалено строк: {report.removed_lines}, символов: {report.removed_chars}.\n"
    )
    if report.applied:
        if report.backup_path is None:
            stdout.write("Резервную копию создать не удалось.\n")
        else:
            stdout.write(f"Резервная копия: {report.backup_path}\n")
    else:
        stdout.write("Запустите с --apply, чтобы записать изменения.\n")


def _write_lore_load(stdout: TextIO, output: str, report: LoreLoadReport) -> None:
    if output == "json":
        _write_json(stdout, report.model_dump(mode="json"))
        return
    if not report.loaded or report.summary is None:
        _write_issues(stdout, report.issues)
        stdout.write(
            f"Загрузка отменена, БД не изменена. Ошибок: {len(report.issues)}\n"
        )
        return
    summary = report.summary
    stdout.write(f"Загрузка {summary.version} выполнена.\n")
    stdout.write(
        f"Документов: {summary.document_count}, чанков: {summary.chunk_count}, "
        f"термов: {summary.term_count}.\n"
    )
    stdout.write(f"Длительность: {report.duration_ms} мс.\n")


def _write_lore_search(
    stdout: TextIO, output: str, result: LoreSearchResult | None
) -> None:
    if output == "json":
        if result is None:
            _write_json(stdout, {"error": "search_failed"})
        else:
            _write_json(stdout, result.model_dump(mode="json"))
        return
    if result is None:
        stdout.write("Поиск не выполнен: проверьте конфигурацию и БД.\n")
        return
    if not result.hits:
        stdout.write("Ничего не найдено.\n")
        return
    for hit in result.hits:
        stdout.write(
            f"{hit.rank}. [{hit.document_id}/{hit.position}] "
            f"{hit.title} — {hit.score:.3f}\n{hit.text}\n"
        )


def _write_lore_benchmark(
    stdout: TextIO, output: str, report: BenchmarkReport | None
) -> None:
    if output == "json":
        if report is None:
            _write_json(stdout, {"error": "benchmark_failed"})
        else:
            _write_json(stdout, report.model_dump(mode="json"))
        return
    if report is None:
        stdout.write(
            "Бенчмарк не выполнен: проверьте пакет, вопросы, ответы или конфиг LLM.\n"
        )
        return
    stdout.write(
        f"Документов: {report.document_count}; вопросов: {report.question_count} "
        f"(обычных {report.normal_count}, ловушек {report.trap_count}); "
        f"k={report.k}.\n"
    )
    stdout.write(f"Recall@{report.k}: {_metric(report.recall_at_k)}\n")
    stdout.write(f"MRR@{report.k}: {_metric(report.mrr)}\n")
    stdout.write(f"Accuracy: {_metric(report.accuracy)}\n")
    stdout.write(f"Correct Rejection Rate: {_metric(report.correct_rejection_rate)}\n")
    if report.context_recall is not None:
        stdout.write(f"Context Recall: {_metric(report.context_recall)}\n")
        stdout.write(f"Context Any-Relevant: {_metric(report.context_any_relevant)}\n")
        stdout.write(f"Context Found: {_metric(report.context_found_rate)}\n")
        stdout.write(f"Trap Passage Rate: {_metric(report.trap_passage_rate)}\n")
    for item in report.results:
        stdout.write(
            f"{item.question_id}: recall={_metric(item.recall)}, "
            f"rr={_metric(item.reciprocal_rank)}, correct={item.correct}\n"
        )


def _metric(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"
