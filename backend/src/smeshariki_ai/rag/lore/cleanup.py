"""Deterministic, conservative cleanup of a lore package.

The rules only remove obvious technical noise: link lines that the transcript
export left in the text. Everything that looks like style (repeated
interjections, times in dialogue, ellipses, duplicated lines) is kept on
purpose: a cleanup rule must never rewrite the author's text.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.lore.models import LoreDocument
from smeshariki_ai.rag.lore.package import (
    DOCUMENTS_DIRECTORY,
    check_package,
    iter_documents,
)
from smeshariki_ai.rag.package import Issue
from smeshariki_ai.rag.yaml_reader import YamlReadError, read_yaml_file

logger = logging.getLogger(__name__)

BACKUP_DIRECTORY = ".backups"
_EXTENSION = ".yaml"
_URL_LINE = re.compile(r"^\s*(?:https?://|www\.)\S*\s*$", re.IGNORECASE)
_URL_PREFIX = re.compile(r"^\s*(?:https?://|www\.)\S+\s*", re.IGNORECASE)
_BLANK_RUN = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class CleanupRule:
    """One named, deterministic text transformation."""

    name: str
    clean: Callable[[str], tuple[str, int]]


def remove_urls(text: str) -> tuple[str, int]:
    """Drop link lines and a leading link; keep the rest of the text."""

    removed = 0
    kept: list[str] = []
    for line in text.splitlines():
        if _URL_LINE.match(line):
            removed += 1
            continue
        kept.append(line)
    cleaned = "\n".join(kept)
    while True:
        match = _URL_PREFIX.match(cleaned)
        if match is None:
            break
        cleaned = cleaned[match.end() :]
        removed += 1
    return cleaned, removed


def normalize_whitespace(text: str) -> tuple[str, int]:
    """Trim line tails, collapse blank runs and strip the whole text."""

    cleaned = _TRAILING_SPACE.sub("", text)
    cleaned = _BLANK_RUN.sub("\n\n", cleaned)
    return cleaned.strip(), 0


RULES: tuple[CleanupRule, ...] = (
    CleanupRule(name="url_lines", clean=remove_urls),
    CleanupRule(name="whitespace", clean=normalize_whitespace),
)


class CleanReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    applied: bool
    path: str
    document_count: int = Field(default=0, ge=0)
    changed_count: int = Field(default=0, ge=0)
    removed_lines: int = Field(default=0, ge=0)
    removed_chars: int = Field(default=0, ge=0)
    backup_path: str | None = None
    issues: tuple[Issue, ...] = ()
    duration_ms: int = Field(default=0, ge=0)


def clean_text(text: str) -> tuple[str, int]:
    """Apply every rule in order; rules of later stages see earlier results."""

    cleaned = text
    removed = 0
    for rule in RULES:
        cleaned, rule_removed = rule.clean(cleaned)
        removed += rule_removed
    return cleaned, removed


def clean_package(root: Path, *, apply: bool = False) -> CleanReport:
    """Report the changes and, with ``apply``, rewrite the changed documents."""

    started_at = utc_now()
    started = time.monotonic()
    check = check_package(root)
    if not check.valid:
        return _failed(root, check.issues, started)

    documents = tuple(iter_documents(root))
    changes = _collect(root, documents)
    report = _measure(root, documents, changes, applied=apply)
    if not apply or not changes:
        _log(report, started_at, started)
        return report

    backup = _backup(root, changes)
    try:
        for relative, (data, _) in changes.items():
            _write(root / relative, data)
    except OSError:
        report = CleanReport(
            applied=False,
            path=str(root),
            document_count=len(documents),
            issues=(
                Issue(
                    file=".",
                    code="write_failed",
                    message="не удалось записать очищенные документы",
                ),
            ),
        )
        _log(report, started_at, started, error_type="OSError")
        return report

    after = check_package(root)
    if not after.valid:
        report = report.model_copy(update={"issues": after.issues})
        _log(report, started_at, started, error_type="LorePackageInvalidError")
        return report

    report = report.model_copy(
        update={"backup_path": None if backup is None else str(backup)}
    )
    report = report.model_copy(update={"duration_ms": _milliseconds(started)})
    _log(report, started_at, started)
    return report


def _collect(
    root: Path,
    documents: Sequence[LoreDocument],
) -> dict[str, tuple[dict[str, object], int]]:
    """Map changed relative files to their new YAML data and removed lines."""

    changes: dict[str, tuple[dict[str, object], int]] = {}
    for document in documents:
        relative = f"{DOCUMENTS_DIRECTORY}/{document.id}{_EXTENSION}"
        path = root / relative
        try:
            data = read_yaml_file(path)
        except (YamlReadError, OSError):
            continue
        cleaned, removed = clean_text(document.text)
        if cleaned == document.text:
            continue
        updated = dict(data)
        updated["text"] = cleaned
        changes[relative] = (updated, removed)
    return changes


def _measure(
    root: Path,
    documents: Sequence[LoreDocument],
    changes: dict[str, tuple[dict[str, object], int]],
    *,
    applied: bool,
) -> CleanReport:
    by_id = {document.id: document for document in documents}
    removed_chars = 0
    for relative, (data, _) in changes.items():
        document = by_id[Path(relative).stem]
        removed_chars += max(0, len(document.text) - len(str(data["text"])))
    return CleanReport(
        applied=applied,
        path=str(root),
        document_count=len(documents),
        changed_count=len(changes),
        removed_lines=sum(removed for _, removed in changes.values()),
        removed_chars=removed_chars,
    )


def _backup(
    root: Path,
    changes: dict[str, tuple[dict[str, object], int]],
) -> Path | None:
    """Copy the changed documents aside, outside the package directory."""

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = root.parent / BACKUP_DIRECTORY / f"{root.name}-{stamp}"
    try:
        for relative in changes:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
    except OSError:
        return None
    return target


def _write(path: Path, data: dict[str, object]) -> None:
    dumped = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=88,
    )
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(dumped, encoding="utf-8")
    os.replace(temporary, path)


def _failed(root: Path, issues: Sequence[Issue], started: float) -> CleanReport:
    return CleanReport(
        applied=False,
        path=str(root),
        issues=tuple(issues),
        duration_ms=_milliseconds(started),
    )


def _milliseconds(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _log(
    report: CleanReport,
    started_at: str,
    started: float,
    *,
    error_type: str | None = None,
) -> None:
    failed = bool(report.issues)
    log_event(
        logger,
        logging.WARNING if failed else logging.INFO,
        "lore.clean.completed",
        started_at=started_at,
        duration_ms=round((time.monotonic() - started) * 1000, 3),
        outcome="failed" if failed else ("applied" if report.applied else "planned"),
        document_count=report.document_count,
        entity_count=report.changed_count,
        error_type=error_type,
    )
