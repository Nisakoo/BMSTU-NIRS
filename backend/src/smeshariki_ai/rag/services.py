"""Use cases of structured knowledge: checking and loading packages."""

import logging
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.integrity import Violation, check_integrity
from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    KNOWLEDGE_FORMAT_VERSION,
    EntityRef,
    EntityType,
    KnowledgeEntity,
    KnowledgeModel,
    KnowledgeSet,
    entities_of,
    entity_ref,
)
from smeshariki_ai.rag.package import (
    ENTITY_DIRECTORIES,
    ENTITY_MODELS,
    Issue,
    PackageContents,
    PackageManifest,
    PackageNotFoundError,
    entity_file,
    read_package,
)
from smeshariki_ai.rag.ports import (
    ChangeCounts,
    EntityChange,
    KnowledgeDataInvalidError,
    KnowledgeSchemaNotReadyError,
    KnowledgeStore,
    KnowledgeStoreUnavailableError,
    LoadSummary,
)

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"(\d+)")


class CheckReport(KnowledgeModel):
    valid: bool
    counts: dict[str, int]
    external: tuple[EntityRef, ...]
    issues: tuple[Issue, ...]


class LoadReport(KnowledgeModel):
    loaded: bool
    load_id: int | None = None
    counts: dict[str, ChangeCounts]
    entity_count: int = 0
    duration_ms: int = 0
    issues: tuple[Issue, ...] = ()


def check_package(root: Path) -> CheckReport:
    """Validate a package on its own; missing entities are external references."""

    return _check(root)[1]


def _check(root: Path) -> tuple[PackageContents, CheckReport]:
    try:
        contents = read_package(root)
    except PackageNotFoundError:
        issue = Issue(
            file=".", code="package_not_found", message=f"пакет «{root}» не найден"
        )
        report = CheckReport(
            valid=False, counts=_zero(int), external=(), issues=(issue,)
        )
        return (
            PackageContents(
                knowledge=KnowledgeSet(), unverified=frozenset(), issues=()
            ),
            report,
        )

    knowledge = contents.knowledge
    integrity = check_integrity(
        knowledge, complete=False, unverified=contents.unverified
    )
    issues = _sorted(
        [*contents.issues, *_violation_issues(integrity.violations, knowledge)]
    )
    counts = {
        directory: len(getattr(knowledge, directory))
        for directory in ENTITY_DIRECTORIES.values()
    }
    report = CheckReport(
        valid=not issues,
        counts=counts,
        external=integrity.external,
        issues=issues,
    )
    return contents, report


async def load_package(
    root: Path,
    store: KnowledgeStore,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> LoadReport:
    """Check the package, then merge it into the store in one transaction.

    The rules run on the whole merged set, so a package may rely on stored
    entities and may not break them. Entities equal to the stored ones are not
    written again, which makes repeated loads of one package idempotent.
    """

    log_started_at = utc_now()
    started = time.monotonic()
    contents, check = _check(root)
    if not check.valid:
        report = LoadReport(
            loaded=False, counts=_zero(ChangeCounts), issues=check.issues
        )
        _log_load(
            report,
            log_started_at,
            started,
            outcome="rejected",
            reason="package_invalid",
        )
        return report

    started_at = clock()
    outcome = "loaded"
    reason = None
    error_type = None
    conflict_count = 0
    try:
        async with store.transaction() as transaction:
            current = await transaction.read_all()
            conflicts = _revision_conflicts(
                contents.revisions,
                current,
                await transaction.revision_index(),
            )
            if conflicts:
                conflict_count = len(conflicts)
                outcome, reason = "rejected", "revision_conflict"
                raise _Rejected(conflicts)

            merged = _merge(current, contents.knowledge)
            violations = check_integrity(merged, complete=True).violations
            if violations:
                outcome, reason = "rejected", "integrity_violation"
                raise _Rejected(_violation_issues(violations, contents.knowledge))

            changes, counts = _changes(current, contents.knowledge)
            load_id = await transaction.start_load(started_at)
            await transaction.save(load_id, changes)
            finished_at = clock()
            report = LoadReport(
                loaded=True,
                load_id=load_id,
                counts=counts,
                entity_count=len(entities_of(merged)),
                duration_ms=_milliseconds(started_at, finished_at),
            )
            await transaction.finish_load(
                load_id,
                LoadSummary(
                    finished_at=finished_at,
                    duration_ms=report.duration_ms,
                    entity_count=report.entity_count,
                    counts=report.counts,
                ),
            )
    except _Rejected as rejected:
        report = _failed(rejected.issues)
    except KnowledgeSchemaNotReadyError as error:
        outcome, error_type = "failed", type(error).__name__
        report = _failed(
            (
                Issue(
                    file=".",
                    code="schema_not_ready",
                    message="таблицы знаний не созданы: примените миграции "
                    "(make migrate)",
                ),
            )
        )
    except KnowledgeDataInvalidError as error:
        outcome, error_type = "failed", type(error).__name__
        report = _failed(
            (
                Issue(
                    file=".",
                    code="stored_data_invalid",
                    message="данные знаний в БД не проходят проверку моделей: "
                    "загрузка невозможна, пока данные не исправлены",
                ),
            )
        )
    except KnowledgeStoreUnavailableError as error:
        outcome, error_type = "failed", type(error).__name__
        report = _failed(
            (
                Issue(
                    file=".",
                    code="database_unavailable",
                    message="база данных знаний недоступна",
                ),
            )
        )
    _log_load(
        report,
        log_started_at,
        started,
        outcome=outcome,
        conflict_count=conflict_count,
        reason=reason,
        error_type=error_type,
    )
    return report


def _revision_conflicts(
    expected: dict[EntityType, dict[str, int]],
    current: KnowledgeSet,
    revisions: dict[EntityRef, int],
) -> tuple[Issue, ...]:
    current_refs = {entity_ref(entity) for entity in entities_of(current)}
    issues: list[Issue] = []
    for kind, entries in expected.items():
        for entity_id, revision in entries.items():
            ref = EntityRef(type=kind, id=entity_id)
            if ref not in current_refs:
                issues.append(
                    Issue(
                        file=entity_file(ref),
                        path="revisions",
                        code="revision_mismatch",
                        message="сущность отсутствует в БД",
                    )
                )
                continue
            actual = revisions.get(ref, 0)
            if actual != revision:
                issues.append(
                    Issue(
                        file=entity_file(ref),
                        path="revisions",
                        code="revision_mismatch",
                        message=f"ожидалась ревизия {revision}, в БД {actual}",
                    )
                )
    return _sorted(issues)


def _log_load(
    report: LoadReport,
    started_at: str,
    started: float,
    *,
    outcome: str,
    conflict_count: int = 0,
    reason: str | None = None,
    error_type: str | None = None,
) -> None:
    log_event(
        logger,
        logging.WARNING if outcome != "loaded" else logging.INFO,
        "rag.load.completed",
        started_at=started_at,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        outcome=outcome,
        conflict_count=conflict_count,
        entity_count=report.entity_count,
        reason=reason,
        error_type=error_type,
    )


def package_schema() -> dict[str, Any]:
    """Format version, the schema of ``package.yaml`` and of each entity file."""

    return {
        "format_version": KNOWLEDGE_FORMAT_VERSION,
        "manifest": PackageManifest.model_json_schema(),
        "entities": {
            ENTITY_DIRECTORIES[kind]: ENTITY_MODELS[kind].model_json_schema()
            for kind in EntityType
        },
    }


class _Rejected(Exception):
    """Raised inside the transaction so that nothing of the load is kept."""

    def __init__(self, issues: tuple[Issue, ...]) -> None:
        self.issues = issues


def _failed(issues: tuple[Issue, ...]) -> LoadReport:
    return LoadReport(loaded=False, counts=_zero(ChangeCounts), issues=issues)


def _zero(factory: Callable[[], Any]) -> dict[str, Any]:
    return {directory: factory() for directory in ENTITY_DIRECTORIES.values()}


def _merge(current: KnowledgeSet, package: KnowledgeSet) -> KnowledgeSet:
    """Package entities replace stored entities with the same type and id."""

    merged: dict[EntityRef, KnowledgeEntity] = {
        entity_ref(entity): entity for entity in entities_of(current)
    }
    merged.update({entity_ref(entity): entity for entity in entities_of(package)})
    grouped: dict[EntityType, list[KnowledgeEntity]] = {kind: [] for kind in EntityType}
    for ref, entity in merged.items():
        grouped[ref.type].append(entity)
    return KnowledgeSet(
        **{ENTITY_FIELDS[kind]: tuple(items) for kind, items in grouped.items()}
    )


def _changes(
    current: KnowledgeSet, package: KnowledgeSet
) -> tuple[list[EntityChange], dict[str, ChangeCounts]]:
    stored = {entity_ref(entity): entity for entity in entities_of(current)}
    totals: dict[EntityType, dict[str, int]] = {
        kind: {"added": 0, "updated": 0, "unchanged": 0} for kind in EntityType
    }
    changes = []
    for entity in entities_of(package):
        ref = entity_ref(entity)
        previous = stored.get(ref)
        if previous is None:
            totals[ref.type]["added"] += 1
            changes.append(EntityChange(operation="create", entity=entity))
        elif previous != entity:
            totals[ref.type]["updated"] += 1
            changes.append(EntityChange(operation="update", entity=entity))
        else:
            totals[ref.type]["unchanged"] += 1
    counts = {
        ENTITY_FIELDS[kind]: ChangeCounts(**values) for kind, values in totals.items()
    }
    return changes, counts


def _violation_issues(
    violations: Sequence[Violation], package: KnowledgeSet
) -> tuple[Issue, ...]:
    """Address a violation by its package file, or by ``db:`` for stored entities."""

    in_package = {entity_ref(entity) for entity in entities_of(package)}
    return _sorted(
        [
            Issue(
                file=entity_file(violation.entity)
                if violation.entity in in_package
                else f"db:{ENTITY_DIRECTORIES[violation.entity.type]}/"
                f"{violation.entity.id}",
                path=violation.path,
                code=violation.code,
                message=violation.message,
            )
            for violation in violations
        ]
    )


def _sorted(issues: list[Issue]) -> tuple[Issue, ...]:
    return tuple(sorted(issues, key=lambda issue: (issue.file, _natural(issue.path))))


def _milliseconds(started_at: datetime, finished_at: datetime) -> int:
    return max(0, round((finished_at - started_at).total_seconds() * 1000))


def _natural(path: str) -> tuple[Any, ...]:
    # "traits[2]" goes before "traits[10]".
    return tuple(int(part) if part.isdigit() else part for part in _NUMBER.split(path))
