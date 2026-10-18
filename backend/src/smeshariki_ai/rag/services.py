"""Use cases of structured knowledge that work without the database."""

import re
from pathlib import Path
from typing import Any

from smeshariki_ai.rag.integrity import check_integrity
from smeshariki_ai.rag.models import EntityRef, EntityType, Issue, KnowledgeModel
from smeshariki_ai.rag.package import (
    ENTITY_DIRECTORIES,
    ENTITY_MODELS,
    PackageNotFoundError,
    entity_file,
    read_package,
)

_NUMBER = re.compile(r"(\d+)")


class CheckReport(KnowledgeModel):
    valid: bool
    counts: dict[str, int]
    external: tuple[EntityRef, ...]
    issues: tuple[Issue, ...]


def check_package(root: Path) -> CheckReport:
    """Validate a package on its own; missing entities are external references."""

    empty_counts = {directory: 0 for directory in ENTITY_DIRECTORIES.values()}
    try:
        contents = read_package(root)
    except PackageNotFoundError:
        issue = Issue(
            file=".", code="package_not_found", message=f"пакет «{root}» не найден"
        )
        return CheckReport(
            valid=False, counts=empty_counts, external=(), issues=(issue,)
        )

    knowledge = contents.knowledge
    integrity = check_integrity(knowledge, complete=False)
    issues = [
        *contents.issues,
        *(
            Issue(
                file=entity_file(violation.entity),
                path=violation.path,
                code=violation.code,
                message=violation.message,
            )
            for violation in integrity.violations
        ),
    ]
    issues.sort(key=lambda issue: (issue.file, _natural(issue.path)))
    counts = {
        directory: len(getattr(knowledge, directory))
        for directory in ENTITY_DIRECTORIES.values()
    }
    return CheckReport(
        valid=not issues,
        counts=counts,
        external=integrity.external,
        issues=tuple(issues),
    )


def package_schema() -> dict[str, dict[str, Any]]:
    """JSON Schema of each entity file, keyed by the package directory."""

    return {
        ENTITY_DIRECTORIES[kind]: ENTITY_MODELS[kind].model_json_schema()
        for kind in EntityType
    }


def _natural(path: str) -> tuple[Any, ...]:
    # "traits[2]" goes before "traits[10]".
    return tuple(int(part) if part.isdigit() else part for part in _NUMBER.split(path))
