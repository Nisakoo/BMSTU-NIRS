"""Use cases of knowledge maintenance: export and deletion.

Both use cases work with the domain models only. The package writer is an
outbound adapter of the package format; the store is the existing port. A
deletion is planned against a consistent set first, so references and
integrity are checked before anything is written.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.integrity import check_integrity
from smeshariki_ai.rag.issues import (
    db_file,
    issue,
    milliseconds,
    sort_issues,
    store_issue,
    violation_issue,
)
from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    EntityRef,
    EntityType,
    KnowledgeEntity,
    KnowledgeModel,
    KnowledgeSet,
    entities_of,
    entity_ref,
)
from smeshariki_ai.rag.package import ENTITY_DIRECTORIES, Issue, write_package
from smeshariki_ai.rag.ports import (
    ChangeCounts,
    EntityChange,
    KnowledgeSnapshot,
    KnowledgeStore,
    KnowledgeStoreError,
    LoadSummary,
)

logger = logging.getLogger(__name__)

_DELETE_ENTITY_NOT_FOUND = "сущность не найдена"


class ExportReport(KnowledgeModel):
    exported: bool
    path: str
    entity_count: int = Field(default=0, ge=0)
    counts: dict[str, int] = Field(default_factory=dict)
    issues: tuple[Issue, ...] = ()


class DeleteReport(KnowledgeModel):
    applied: bool
    operation_id: int | None = None
    counts: dict[str, ChangeCounts] = Field(default_factory=dict)
    entity_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    issues: tuple[Issue, ...] = ()


class _Rejected(Exception):
    def __init__(self, issues: Sequence[Issue]) -> None:
        self.issues = tuple(issues)


async def export_package(
    path: Path,
    store: KnowledgeStore,
    types: Sequence[EntityType] | None = None,
) -> ExportReport:
    """Write the current store state as a package, without changing the DB."""

    started_at = utc_now()
    started = time.monotonic()
    report = _export_failed(path, _destination_issue(path))
    if report is not None:
        _log_export(report, started_at, started)
        return report

    try:
        snapshot = await store.snapshot()
    except KnowledgeStoreError as error:
        report = _export_failed(path, store_issue(error))
        _log_export(report, started_at, started, error)
        return report

    selected = _select_types(snapshot.knowledge, types)
    if not entities_of(snapshot.knowledge):
        report = _export_failed(path, issue("empty_store", "в БД нет знаний"))
    elif not entities_of(selected):
        report = _export_failed(
            path, issue("empty_selection", "выбранные типы не содержат сущностей")
        )

    if report is not None:
        _log_export(report, started_at, started, reason=report.issues[0].code)
        return report

    try:
        _write_atomically(path, selected, _revision_map(snapshot, selected))
    except OSError as error:
        report = _export_failed(
            path, issue("export_failed", "не удалось записать пакет")
        )
        _log_export(report, started_at, started, error)
        return report

    report = ExportReport(
        exported=True,
        path=str(path),
        entity_count=len(entities_of(selected)),
        counts=_type_counts(selected),
    )
    _log_export(report, started_at, started)
    return report


async def delete_entities(
    refs: Sequence[EntityRef],
    store: KnowledgeStore,
    *,
    apply: bool,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> DeleteReport:
    """Plan a deletion and, with ``apply``, perform it in one transaction."""

    started_at = utc_now()
    started = time.monotonic()
    unique_refs = tuple(dict.fromkeys(refs))
    if not apply:
        try:
            snapshot = await store.snapshot()
        except KnowledgeStoreError as error:
            report = _delete_failed(store_issue(error), None)
            _log_delete(report, started_at, started, error)
            return report
        plan = _delete_plan(snapshot.knowledge, unique_refs)
        report = _delete_report(plan, None, clock, started_at)
        _log_delete(report, started_at, started, reason=_rejection_reason(plan))
        return report

    plan: _DeletePlan | None = None
    try:
        async with store.transaction() as transaction:
            plan = _delete_plan(await transaction.read_all(), unique_refs)
            if plan.issues:
                raise _Rejected(plan.issues)

            operation_id = await transaction.start_load(clock(), operation="delete")
            await transaction.save(
                operation_id,
                [
                    EntityChange(operation="delete", entity=entity)
                    for entity in plan.deleted
                ],
            )
            finished_at = clock()
            await transaction.finish_load(
                operation_id,
                LoadSummary(
                    finished_at=finished_at,
                    duration_ms=milliseconds(started_at, finished_at),
                    entity_count=len(entities_of(plan.remaining)),
                    counts=plan.counts,
                ),
            )
    except _Rejected as rejected:
        report = _delete_report(
            plan or _empty_delete_plan(), None, clock, started_at, rejected.issues
        )
        _log_delete(report, started_at, started, reason="rejected")
        return report
    except KnowledgeStoreError as error:
        report = _delete_failed(store_issue(error), plan)
        _log_delete(report, started_at, started, error)
        return report

    report = _delete_report(plan, operation_id, clock, started_at)
    _log_delete(report, started_at, started)
    return report


class _DeletePlan(KnowledgeModel):
    remaining: KnowledgeSet
    deleted: tuple[KnowledgeEntity, ...] = ()
    counts: dict[str, ChangeCounts] = Field(default_factory=dict)
    issues: tuple[Issue, ...] = ()


def _delete_plan(knowledge: KnowledgeSet, refs: Sequence[EntityRef]) -> _DeletePlan:
    current = {entity_ref(entity): entity for entity in entities_of(knowledge)}
    issues = [
        Issue(
            file=db_file(ref),
            code="entity_not_found",
            message=_DELETE_ENTITY_NOT_FOUND,
        )
        for ref in refs
        if ref not in current
    ]
    remaining = _without(knowledge, refs)
    if not issues:
        issues = [
            violation_issue(item)
            for item in check_integrity(remaining, complete=True).violations
        ]
    deleted = tuple(current[ref] for ref in refs if ref in current)
    return _DeletePlan(
        remaining=remaining,
        deleted=deleted,
        counts=_deleted_counts(deleted),
        issues=sort_issues(issues),
    )


def _empty_delete_plan() -> _DeletePlan:
    return _DeletePlan(
        remaining=KnowledgeSet(),
        counts=_zero_change_counts(),
    )


def _delete_report(
    plan: _DeletePlan,
    operation_id: int | None,
    clock: Callable[[], datetime],
    started_at: str,
    issues: Sequence[Issue] | None = None,
) -> DeleteReport:
    finished_at = clock()
    return DeleteReport(
        applied=operation_id is not None,
        operation_id=operation_id,
        counts=plan.counts,
        entity_count=len(entities_of(plan.remaining)),
        duration_ms=milliseconds(started_at, finished_at),
        issues=tuple(issues if issues is not None else plan.issues),
    )


def _delete_failed(
    issue: Issue,
    plan: _DeletePlan | None,
) -> DeleteReport:
    plan = plan or _empty_delete_plan()
    return DeleteReport(
        applied=False,
        counts=plan.counts,
        entity_count=len(entities_of(plan.remaining)),
        duration_ms=0,
        issues=(issue,),
    )


def _export_failed(path: Path, issue: Issue | None) -> ExportReport | None:
    if issue is None:
        return None
    return ExportReport(
        exported=False,
        path=str(path),
        entity_count=0,
        counts=_zero_int_counts(),
        issues=(issue,),
    )


def _destination_issue(path: Path) -> Issue | None:
    if path.is_symlink():
        return Issue(
            file=str(path),
            code="destination_not_empty",
            message="каталог назначения не должен быть символьной ссылкой",
        )
    if path.exists():
        if not path.is_dir():
            return Issue(
                file=str(path),
                code="destination_not_empty",
                message="каталог назначения не должен быть файлом",
            )
        if any(path.iterdir()):
            return Issue(
                file=str(path),
                code="destination_not_empty",
                message="каталог назначения должен быть пустым",
            )
    return None


def _revision_map(
    snapshot: KnowledgeSnapshot, knowledge: KnowledgeSet
) -> dict[str, dict[str, int]]:
    revisions: dict[str, dict[str, int]] = {}
    for entity in entities_of(knowledge):
        ref = entity_ref(entity)
        revision = snapshot.revisions.get(ref, 0)
        if revision:
            revisions.setdefault(ENTITY_FIELDS[ref.type], {})[ref.id] = revision
    return revisions


def _write_atomically(
    path: Path,
    knowledge: KnowledgeSet,
    revisions: dict[str, dict[str, int]],
) -> None:
    if path.exists():
        # An existing empty directory may be a bind mount: it cannot be
        # replaced, so write into it and clean up if anything fails.
        try:
            write_package(path, knowledge, revisions or None)
        except Exception:
            _clear_directory(path)
            raise
        return

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{path.name}-", dir=parent))
    try:
        write_package(temporary, knowledge, revisions or None)
        os.replace(temporary, path)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _clear_directory(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _select_types(
    knowledge: KnowledgeSet, types: Sequence[EntityType] | None
) -> KnowledgeSet:
    if not types:
        return knowledge
    selected = set(types)
    return KnowledgeSet(
        **{
            field: getattr(knowledge, field) if kind in selected else ()
            for kind, field in ENTITY_FIELDS.items()
        }
    )


def _without(knowledge: KnowledgeSet, refs: Sequence[EntityRef]) -> KnowledgeSet:
    removed = set(refs)
    return KnowledgeSet(
        **{
            field: tuple(
                entity
                for entity in getattr(knowledge, field)
                if entity_ref(entity) not in removed
            )
            for field in ENTITY_FIELDS.values()
        }
    )


def _type_counts(knowledge: KnowledgeSet) -> dict[str, int]:
    return {
        field: len(getattr(knowledge, field)) for field in ENTITY_DIRECTORIES.values()
    }


def _zero_int_counts() -> dict[str, int]:
    return {field: 0 for field in ENTITY_DIRECTORIES.values()}


def _zero_change_counts() -> dict[str, ChangeCounts]:
    return {field: ChangeCounts() for field in ENTITY_DIRECTORIES.values()}


def _deleted_counts(entities: Sequence[KnowledgeEntity]) -> dict[str, ChangeCounts]:
    totals = {field: 0 for field in ENTITY_DIRECTORIES.values()}
    for entity in entities:
        totals[ENTITY_FIELDS[entity_ref(entity).type]] += 1
    return {field: ChangeCounts(deleted=count) for field, count in totals.items()}


def _rejection_reason(plan: _DeletePlan) -> str | None:
    if not plan.issues:
        return None
    if any(issue.code == "entity_not_found" for issue in plan.issues):
        return "entity_not_found"
    return "integrity_violation"


def _log_export(
    report: ExportReport,
    started_at: str,
    started: float,
    error: Exception | None = None,
    *,
    reason: str | None = None,
) -> None:
    log_event(
        logger,
        logging.WARNING if not report.exported else logging.INFO,
        "rag.export.completed",
        started_at=started_at,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        outcome="exported" if report.exported else ("failed" if error else "rejected"),
        entity_count=report.entity_count,
        reason=reason
        or (report.issues[0].code if report.issues and not error else None),
        error_type=type(error).__name__ if error else None,
    )


def _log_delete(
    report: DeleteReport,
    started_at: str,
    started: float,
    error: Exception | None = None,
    *,
    reason: str | None = None,
) -> None:
    outcome = (
        "failed"
        if error
        else "applied"
        if report.applied
        else "rejected"
        if report.issues
        else "dry_run"
    )
    log_event(
        logger,
        logging.WARNING if outcome in {"failed", "rejected"} else logging.INFO,
        "rag.delete.completed",
        started_at=started_at,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        outcome=outcome,
        deleted_count=sum(counts.deleted for counts in report.counts.values()),
        reason=reason
        or (report.issues[0].code if report.issues and not error else None),
        error_type=type(error).__name__ if error else None,
    )
