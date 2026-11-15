"""Stable, safe issues shared by the knowledge maintenance use cases."""

from collections.abc import Sequence
from datetime import datetime

from smeshariki_ai.rag.integrity import Violation
from smeshariki_ai.rag.models import EntityRef
from smeshariki_ai.rag.package import ENTITY_DIRECTORIES, Issue
from smeshariki_ai.rag.ports import (
    KnowledgeDataInvalidError,
    KnowledgeSchemaNotReadyError,
    KnowledgeStoreError,
    KnowledgeStoreUnavailableError,
)


def issue(code: str, message: str, file: str = ".") -> Issue:
    return Issue(file=file, code=code, message=message)


def db_file(ref: EntityRef) -> str:
    return f"db:{ENTITY_DIRECTORIES[ref.type]}/{ref.id}"


def violation_issue(violation: Violation) -> Issue:
    return Issue(
        file=db_file(violation.entity),
        path=violation.path,
        code=violation.code,
        message=violation.message,
    )


def sort_issues(issues: Sequence[Issue]) -> tuple[Issue, ...]:
    return tuple(sorted(issues, key=lambda item: (item.file, item.path)))


def milliseconds(started_at: str, finished_at: datetime) -> int:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    return max(0, round((finished_at - started).total_seconds() * 1000))


def store_issue(error: KnowledgeStoreError) -> Issue:
    if isinstance(error, KnowledgeSchemaNotReadyError):
        return issue(
            "schema_not_ready",
            "таблицы знаний не созданы: примените миграции (make migrate)",
        )
    if isinstance(error, KnowledgeDataInvalidError):
        return issue(
            "stored_data_invalid",
            "данные знаний в БД не проходят проверку моделей",
        )
    if isinstance(error, KnowledgeStoreUnavailableError):
        return issue("database_unavailable", "база данных знаний недоступна")
    return issue("database_unavailable", "база данных знаний недоступна")
