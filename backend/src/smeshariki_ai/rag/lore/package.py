"""Reading and validation of a YAML lore package.

The package is read one document at a time, so a large corpus does not have to
be held in memory. ``iter_documents`` raises ``LorePackageInvalidError`` after
yielding the documents it could validate; the caller can collect the issues
without losing the streaming behaviour.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_core import ErrorDetails

from smeshariki_ai.rag.lore.models import (
    LORE_PACKAGE_FORMAT_VERSION,
    LoreDocument,
)
from smeshariki_ai.rag.package import Issue
from smeshariki_ai.rag.yaml_reader import YamlReadError, read_yaml_file

MANIFEST = "package.yaml"
DOCUMENTS_DIRECTORY = "documents"
_EXTENSION = ".yaml"


class LorePackageInvalidError(Exception):
    def __init__(self, issues: tuple[Issue, ...]) -> None:
        self.issues = issues
        super().__init__(f"lore package has {len(issues)} issue(s)")


class LoreManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: int = Field(ge=1)


class LorePackageContents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    documents: tuple[LoreDocument, ...] = ()
    issues: tuple[Issue, ...] = ()


class LoreCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    document_count: int = Field(ge=0)
    issues: tuple[Issue, ...] = ()


def iter_documents(root: Path) -> Iterator[LoreDocument]:
    """Yield valid documents and raise with all issues at the end."""

    issues: list[Issue] = []
    manifest = _read_manifest(root, issues)
    if manifest is not None:
        yield from _iter_document_files(root, issues)
    if issues:
        raise LorePackageInvalidError(tuple(issues))


def read_package(root: Path) -> LorePackageContents:
    documents: list[LoreDocument] = []
    try:
        documents.extend(iter_documents(root))
    except LorePackageInvalidError as error:
        issues = error.issues
    else:
        issues = ()
    return LorePackageContents(documents=tuple(documents), issues=issues)


def check_package(root: Path) -> LoreCheckReport:
    count = 0
    try:
        for _ in iter_documents(root):
            count += 1
    except LorePackageInvalidError as error:
        return LoreCheckReport(valid=False, document_count=count, issues=error.issues)
    return LoreCheckReport(valid=True, document_count=count)


def _read_manifest(root: Path, issues: list[Issue]) -> LoreManifest | None:
    if not root.is_dir():
        issues.append(
            Issue(
                file=".",
                code="package_not_found",
                message=f"пакет «{root}» не найден",
            )
        )
        return None

    path = root / MANIFEST
    if path.is_symlink():
        issues.append(
            Issue(
                file=MANIFEST,
                code="symlink_not_allowed",
                message="символьные ссылки в пакете не допускаются",
            )
        )
        return None
    if not path.is_file():
        issues.append(
            Issue(
                file=MANIFEST,
                code="missing_manifest",
                message=f"нет {MANIFEST} с format_version: "
                f"{LORE_PACKAGE_FORMAT_VERSION}",
            )
        )
        return None

    try:
        data = read_yaml_file(path)
    except YamlReadError as error:
        issues.append(
            Issue(
                file=MANIFEST,
                code=error.code,
                message=error.message,
                line=error.line,
            )
        )
        return None

    try:
        manifest = LoreManifest.model_validate(data)
    except ValidationError as error:
        issues.extend(_validation_issues(MANIFEST, error))
        return None
    if manifest.format_version != LORE_PACKAGE_FORMAT_VERSION:
        issues.append(
            Issue(
                file=MANIFEST,
                path="format_version",
                code="unsupported_format_version",
                message=f"версия формата {manifest.format_version} не "
                f"поддерживается; поддерживается {LORE_PACKAGE_FORMAT_VERSION}",
            )
        )
        return None
    return manifest


def _iter_document_files(root: Path, issues: list[Issue]) -> Iterator[LoreDocument]:
    entries = sorted(root.iterdir())
    documents_path = root / DOCUMENTS_DIRECTORY
    if not documents_path.is_dir() or documents_path.is_symlink():
        issues.append(
            Issue(
                file=DOCUMENTS_DIRECTORY,
                code="missing_documents_directory",
                message="нет каталога documents с YAML-документами",
            )
        )
        return

    for entry in entries:
        if entry.name == MANIFEST:
            continue
        if (
            entry.name == DOCUMENTS_DIRECTORY
            and entry.is_dir()
            and not entry.is_symlink()
        ):
            continue
        issues.append(_unexpected(root, entry))

    for path in sorted(documents_path.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_symlink() or not path.is_file() or path.suffix != _EXTENSION:
            issues.append(_unexpected(root, path))
            continue
        document = _read_document(root, path, issues)
        if document is not None:
            yield document


def _read_document(root: Path, path: Path, issues: list[Issue]) -> LoreDocument | None:
    file = path.relative_to(root).as_posix()
    try:
        data = read_yaml_file(path)
    except YamlReadError as error:
        issues.append(
            Issue(file=file, code=error.code, message=error.message, line=error.line)
        )
        return None

    try:
        document = LoreDocument.model_validate(data)
    except ValidationError as error:
        issues.extend(_validation_issues(file, error))
        return None

    if document.id != path.stem:
        issues.append(
            Issue(
                file=file,
                path="id",
                code="file_id_mismatch",
                message=f"id должен совпадать с именем файла «{path.stem}»",
            )
        )
        return None
    return document


def _unexpected(root: Path, path: Path) -> Issue:
    file = path.relative_to(root).as_posix()
    if path.is_symlink():
        return Issue(
            file=file,
            code="symlink_not_allowed",
            message="символьные ссылки в пакете не допускаются",
        )
    if path.is_dir():
        return Issue(
            file=file,
            code="unexpected_directory",
            message="неизвестный каталог; ожидается только documents",
        )
    return Issue(
        file=file,
        code="unexpected_file",
        message="неожиданный файл; документ хранится в "
        f"{DOCUMENTS_DIRECTORY}/<id>{_EXTENSION}",
    )


def _validation_issues(file: str, error: ValidationError) -> list[Issue]:
    return [_schema_issue(file, item) for item in error.errors()]


def _schema_issue(file: str, error: ErrorDetails) -> Issue:
    code, message = _translate(error)
    return Issue(
        file=file,
        path=_field_path(error["loc"]),
        code=code,
        message=message,
    )


def _field_path(loc: tuple[int | str, ...]) -> str:
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else part
    return path


def _translate(error: ErrorDetails) -> tuple[str, str]:
    kind = error["type"]
    context: dict[str, Any] = error.get("ctx", {})
    if kind == "string_pattern_mismatch":
        return (
            "invalid_id",
            "ожидается id из строчных латинских букв и цифр, разделённых «_»",
        )
    if kind == "greater_than_equal":
        return "invalid_value", f"значение должно быть не меньше {context['ge']}"
    if kind == "string_too_short":
        return "empty_value", "значение не должно быть пустым"
    if kind == "missing":
        return "missing_field", "обязательное поле не заполнено"
    if kind == "extra_forbidden":
        return "extra_field", "неизвестное поле"
    if kind in ("string_type", "tuple_type"):
        return "invalid_type", "ожидается строка или список строк"
    if kind == "model_type":
        return "invalid_type", "ожидается набор полей"
    return "schema_error", error["msg"]
