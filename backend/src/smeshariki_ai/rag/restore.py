"""Use case of restoring one entity from its revision history.

A revision payload is already written in the package format. Restore selects a
revision, validates it with the domain model, checks the full set and writes the
entity as a new ``create`` or ``update`` revision. Nothing is written in
dry-run.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, ValidationError

from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.integrity import check_integrity
from smeshariki_ai.rag.issues import (
    milliseconds,
    sort_issues,
    store_issue,
    violation_issue,
)
from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    ENTITY_KINDS,
    KNOWLEDGE_FORMAT_VERSION,
    EntityRef,
    KnowledgeEntity,
    KnowledgeModel,
    KnowledgeSet,
    entities_of,
    entity_ref,
)
from smeshariki_ai.rag.package import ENTITY_DIRECTORIES, Issue, entity_file
from smeshariki_ai.rag.ports import (
    ChangeCounts,
    EntityChange,
    KnowledgeStore,
    KnowledgeStoreError,
    LoadSummary,
    Revision,
)

logger = logging.getLogger(__name__)


class RestoreReport(KnowledgeModel):
    restored: bool
    operation_id: int | None = None
    revision: int | None = None
    counts: dict[str, ChangeCounts] = Field(default_factory=dict)
    entity_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    issues: tuple[Issue, ...] = ()


class _Plan(KnowledgeModel):
    revision: int | None = None
    entity: KnowledgeEntity | None = None
    merged: KnowledgeSet = Field(default_factory=KnowledgeSet)
    operation: Literal["create", "update"] | None = None
    counts: dict[str, ChangeCounts] = Field(default_factory=dict)
    issues: tuple[Issue, ...] = ()


class _Rejected(Exception):
    def __init__(self, issues: Sequence[Issue]) -> None:
        self.issues = tuple(issues)


class _RevisionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message


async def restore_entity(
    ref: EntityRef,
    store: KnowledgeStore,
    *,
    revision: int | None = None,
    apply: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RestoreReport:
    """Restore one entity from its history, optionally applying the result."""

    started_at = utc_now()
    started = time.monotonic()
    if not apply:
        try:
            snapshot = await store.snapshot()
            history = await store.revision_history(ref)
        except KnowledgeStoreError as error:
            report = _failed_restore(_empty_plan(), store_issue(error))
            _log_restore(report, started_at, started, error)
            return report
        plan = _plan_restore(snapshot.knowledge, history, ref, revision)
        report = _report(plan, None, clock, started_at, applied=False)
        _log_restore(report, started_at, started, reason=_reason(plan))
        return report

    plan: _Plan | None = None
    operation_id: int | None = None
    try:
        async with store.transaction() as transaction:
            current = await transaction.read_all()
            history = await transaction.read_revisions(ref)
            plan = _plan_restore(current, history, ref, revision)
            if plan.issues:
                raise _Rejected(plan.issues)

            operation_id = await transaction.start_load(clock(), operation="restore")
            if plan.operation is not None and plan.entity is not None:
                await transaction.save(
                    operation_id,
                    [EntityChange(operation=plan.operation, entity=plan.entity)],
                )
            finished_at = clock()
            await transaction.finish_load(
                operation_id,
                LoadSummary(
                    finished_at=finished_at,
                    duration_ms=milliseconds(started_at, finished_at),
                    entity_count=len(entities_of(plan.merged)),
                    counts=plan.counts,
                ),
            )
    except _Rejected as rejected:
        report = _report(
            plan or _empty_plan(),
            None,
            clock,
            started_at,
            applied=False,
            issues=rejected.issues,
        )
        _log_restore(report, started_at, started, reason="rejected")
        return report
    except KnowledgeStoreError as error:
        report = _failed_restore(plan or _empty_plan(), store_issue(error))
        _log_restore(report, started_at, started, error)
        return report

    report = _report(plan, operation_id, clock, started_at, applied=True)
    _log_restore(report, started_at, started)
    return report


def _plan_restore(
    current: KnowledgeSet,
    history: Sequence[Revision],
    ref: EntityRef,
    revision: int | None,
) -> _Plan:
    selected = _select_revision(history, revision)
    if selected is None:
        return _Plan(
            merged=current,
            issues=(_revision_issue(ref, "revision_not_found", "ревизия не найдена"),),
        )
    if selected.format_version != KNOWLEDGE_FORMAT_VERSION:
        return _Plan(
            revision=selected.revision,
            merged=current,
            issues=(
                _revision_issue(
                    ref,
                    "unsupported_revision_format",
                    "версия формата снимка не поддерживается",
                    path="format_version",
                ),
            ),
        )
    try:
        entity = _parse_entity(ref, selected.payload)
    except _RevisionError as error:
        return _Plan(
            revision=selected.revision,
            merged=current,
            issues=(_revision_issue(ref, error.code, error.message),),
        )

    merged = _replace(current, ref, entity)
    issues = [
        violation_issue(item)
        for item in check_integrity(merged, complete=True).violations
    ]
    counts, operation = _counts(current, ref, entity)
    return _Plan(
        revision=selected.revision,
        entity=entity,
        merged=merged,
        operation=operation,
        counts=counts,
        issues=sort_issues(issues),
    )


def _select_revision(
    history: Sequence[Revision], revision: int | None
) -> Revision | None:
    if revision is None:
        return history[-1] if history else None
    return next((item for item in history if item.revision == revision), None)


def _parse_entity(ref: EntityRef, payload: dict) -> KnowledgeEntity:
    model = ENTITY_KINDS[ref.type].model
    try:
        entity = model.model_validate(payload)
    except ValidationError as error:
        raise _RevisionError(
            "revision_invalid", "снимок ревизии не проходит доменную модель"
        ) from error
    if getattr(entity, "id", None) != ref.id:
        raise _RevisionError("revision_invalid", "id снимка не совпадает со ссылкой")
    return entity


def _replace(
    knowledge: KnowledgeSet, ref: EntityRef, entity: KnowledgeEntity
) -> KnowledgeSet:
    by_ref = {entity_ref(item): item for item in entities_of(knowledge)}
    by_ref[ref] = entity
    return KnowledgeSet(
        **{
            field: tuple(
                sorted(
                    (
                        item
                        for item_ref, item in by_ref.items()
                        if item_ref.type is kind
                    ),
                    key=lambda item: item.id,
                )
            )
            for kind, field in ENTITY_FIELDS.items()
        }
    )


def _counts(
    current: KnowledgeSet, ref: EntityRef, entity: KnowledgeEntity
) -> tuple[dict[str, ChangeCounts], Literal["create", "update"] | None]:
    field = ENTITY_FIELDS[ref.type]
    counts = {name: ChangeCounts() for name in ENTITY_DIRECTORIES.values()}
    existing = next(
        (item for item in getattr(current, field) if entity_ref(item) == ref),
        None,
    )
    if existing is None:
        counts[field] = ChangeCounts(added=1)
        return counts, "create"
    if existing != entity:
        counts[field] = ChangeCounts(updated=1)
        return counts, "update"
    counts[field] = ChangeCounts(unchanged=1)
    return counts, None


def _report(
    plan: _Plan,
    operation_id: int | None,
    clock: Callable[[], datetime],
    started_at: str,
    *,
    applied: bool,
    issues: Sequence[Issue] | None = None,
) -> RestoreReport:
    finished_at = clock()
    return RestoreReport(
        restored=applied,
        operation_id=operation_id,
        revision=plan.revision,
        counts=plan.counts,
        entity_count=len(entities_of(plan.merged)),
        duration_ms=milliseconds(started_at, finished_at),
        issues=tuple(issues if issues is not None else plan.issues),
    )


def _empty_plan() -> _Plan:
    return _Plan(
        merged=KnowledgeSet(),
        counts={name: ChangeCounts() for name in ENTITY_DIRECTORIES.values()},
    )


def _failed_restore(plan: _Plan, issue_: Issue) -> RestoreReport:
    return RestoreReport(
        restored=False,
        revision=plan.revision,
        counts=plan.counts,
        entity_count=len(entities_of(plan.merged)),
        issues=(issue_,),
    )


def _revision_issue(
    ref: EntityRef, code: str, message: str, *, path: str = ""
) -> Issue:
    return Issue(file=entity_file(ref), path=path, code=code, message=message)


def _reason(plan: _Plan) -> str | None:
    return plan.issues[0].code if plan.issues else None


def _log_restore(
    report: RestoreReport,
    started_at: str,
    started: float,
    error: Exception | None = None,
    *,
    reason: str | None = None,
) -> None:
    outcome = (
        "failed"
        if error
        else "restored"
        if report.restored
        else "rejected"
        if report.issues
        else "dry_run"
    )
    log_event(
        logger,
        logging.WARNING if outcome in {"failed", "rejected"} else logging.INFO,
        "rag.restore.completed",
        started_at=started_at,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        outcome=outcome,
        entity_count=report.entity_count,
        reason=reason
        or (report.issues[0].code if report.issues and not error else None),
        error_type=type(error).__name__ if error else None,
    )
