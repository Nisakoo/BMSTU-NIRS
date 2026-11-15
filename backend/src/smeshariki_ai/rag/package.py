"""Reading of a knowledge package: one YAML file per entity, grouped by type."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, ValidationError, model_validator
from pydantic_core import ErrorDetails, PydanticCustomError

from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    ENTITY_KINDS,
    KNOWLEDGE_FORMAT_VERSION,
    SLUG_PATTERN,
    EntityRef,
    EntityType,
    KnowledgeModel,
    KnowledgeSet,
    entities_of,
    entity_ref,
)
from smeshariki_ai.rag.yaml_reader import YamlReadError, read_yaml_file

# Package directories are named after the fields of ``KnowledgeSet``.
ENTITY_DIRECTORIES = ENTITY_FIELDS
ENTITY_MODELS: dict[EntityType, type[KnowledgeModel]] = {
    entity_type: kind.model for entity_type, kind in ENTITY_KINDS.items()
}
ENTITY_TYPES_BY_DIRECTORY = {name: kind for kind, name in ENTITY_DIRECTORIES.items()}
_TYPES_BY_DIRECTORY = ENTITY_TYPES_BY_DIRECTORY
_SLUG = re.compile(SLUG_PATTERN)
_EXTENSION = ".yaml"
MANIFEST = "package.yaml"


class PackageNotFoundError(Exception):
    """The package path does not exist or is not a directory."""


class Issue(KnowledgeModel):
    """One problem found in a package, addressed by file and field path."""

    file: str
    path: str = ""
    code: str
    message: str
    line: int | None = None


class PackageManifest(KnowledgeModel):
    """``package.yaml`` at the package root: the format the files are written in."""

    format_version: int = Field(ge=1)
    # Optional lock metadata: package directory -> entity id -> revision.
    revisions: dict[str, dict[str, int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _valid_revisions(self) -> PackageManifest:
        for directory, entries in self.revisions.items():
            if directory not in ENTITY_TYPES_BY_DIRECTORY:
                raise PydanticCustomError(
                    "unknown_revision_entity",
                    "неизвестный каталог в revisions",
                )
            for entity_id, revision in entries.items():
                if not _SLUG.fullmatch(entity_id):
                    raise PydanticCustomError(
                        "invalid_revision", "неверный id в revisions"
                    )
                if revision < 1:
                    raise PydanticCustomError(
                        "invalid_revision", "ревизия должна быть не меньше 1"
                    )
        return self


class PackageContents(KnowledgeModel):
    knowledge: KnowledgeSet
    # Entities whose files exist but failed their own validation.
    unverified: frozenset[EntityRef]
    issues: tuple[Issue, ...]
    # Lock metadata converted to domain types; empty when the package has none.
    revisions: dict[EntityType, dict[str, int]] = Field(default_factory=dict)


def entity_file(ref: EntityRef) -> str:
    return f"{ENTITY_DIRECTORIES[ref.type]}/{ref.id}{_EXTENSION}"


def read_package(root: Path) -> PackageContents:
    """Validate every file of the package; files never stop the reading early."""

    if not root.is_dir():
        raise PackageNotFoundError(root)

    manifest, issues = _read_manifest(root)
    entities: dict[EntityType, list[Any]] = {kind: [] for kind in EntityType}
    unverified: set[EntityRef] = set()
    entity_files = 0

    for entry in _visible(root):
        if entry.name == MANIFEST and not entry.is_symlink():
            continue
        kind = _TYPES_BY_DIRECTORY.get(entry.name)
        if entry.is_symlink() or kind is None or not entry.is_dir():
            issues.append(_unexpected(root, entry))
            continue
        for path in _visible(entry):
            if path.is_symlink() or not path.is_file() or path.suffix != _EXTENSION:
                issues.append(_unexpected(root, path))
                continue
            entity_files += 1
            entity, file_issues = _read_entity(root, path, kind)
            issues.extend(file_issues)
            if entity is not None:
                entities[kind].append(entity)
            elif _SLUG.fullmatch(path.stem):
                unverified.add(EntityRef(type=kind, id=path.stem))

    if entity_files == 0:
        issues.append(
            Issue(file=".", code="empty_package", message="пакет не содержит сущностей")
        )

    knowledge = KnowledgeSet(
        **{ENTITY_DIRECTORIES[kind]: tuple(items) for kind, items in entities.items()}
    )
    revisions = (
        {
            ENTITY_TYPES_BY_DIRECTORY[directory]: dict(entries)
            for directory, entries in manifest.revisions.items()
        }
        if manifest is not None
        else {}
    )
    loaded = {entity_ref(entity) for entity in entities_of(knowledge)}
    for kind, entries in revisions.items():
        for entity_id in entries:
            ref = EntityRef(type=kind, id=entity_id)
            if ref in unverified or ref in loaded:
                continue
            issues.append(
                Issue(
                    file=MANIFEST,
                    path=f"revisions.{ENTITY_DIRECTORIES[kind]}.{entity_id}",
                    code="unknown_revision_entity",
                    message="сущность для ревизии отсутствует в пакете",
                )
            )
    return PackageContents(
        knowledge=knowledge,
        unverified=frozenset(unverified),
        issues=tuple(issues),
        revisions=revisions,
    )


def write_package(
    root: Path,
    knowledge: KnowledgeSet,
    revisions: dict[str, dict[str, int]] | None = None,
) -> None:
    """Write ``knowledge`` as a package; the caller owns atomicity.

    ``revisions`` is the optional lock metadata of ``package.yaml``. The keys
    are package directories, matching the ``revisions`` field of the manifest.
    """

    root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"format_version": KNOWLEDGE_FORMAT_VERSION}
    if revisions:
        manifest["revisions"] = revisions
    (root / MANIFEST).write_text(_dump_yaml(manifest), encoding="utf-8")

    for kind in EntityType:
        for entity in sorted(
            getattr(knowledge, ENTITY_FIELDS[kind]), key=lambda item: item.id
        ):
            path = root / entity_file(entity_ref(entity))
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = entity.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
                exclude_defaults=True,
            )
            path.write_text(_dump_yaml(payload), encoding="utf-8")


def _dump_yaml(value: Any) -> str:
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


def _visible(directory: Path) -> Iterator[Path]:
    return (
        path for path in sorted(directory.iterdir()) if not path.name.startswith(".")
    )


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _read_manifest(
    root: Path,
) -> tuple[PackageManifest | None, list[Issue]]:
    path = root / MANIFEST
    if path.is_symlink():
        return None, []  # Reported with the other entries of the root.
    if not path.is_file():
        return None, [
            Issue(
                file=MANIFEST,
                code="missing_manifest",
                message=f"нет {MANIFEST} с format_version: {KNOWLEDGE_FORMAT_VERSION}",
            )
        ]
    try:
        data = read_yaml_file(path)
    except YamlReadError as error:
        return None, [
            Issue(
                file=MANIFEST, code=error.code, message=error.message, line=error.line
            )
        ]
    try:
        manifest = PackageManifest.model_validate(data)
    except ValidationError as error:
        return None, [_schema_issue(MANIFEST, item) for item in error.errors()]
    if manifest.format_version != KNOWLEDGE_FORMAT_VERSION:
        return None, [
            Issue(
                file=MANIFEST,
                path="format_version",
                code="unsupported_format_version",
                message=f"версия формата {manifest.format_version} не "
                f"поддерживается; поддерживается {KNOWLEDGE_FORMAT_VERSION}",
            )
        ]
    return manifest, []


def _unexpected(root: Path, path: Path) -> Issue:
    if path.is_symlink():
        # The target is never read: it may lie outside the package.
        return Issue(
            file=_relative(root, path),
            code="symlink_not_allowed",
            message="символьные ссылки в пакете не допускаются",
        )
    if path.is_dir():
        return Issue(
            file=_relative(root, path),
            code="unexpected_directory",
            message="неизвестный каталог; ожидаются каталоги типов сущностей: "
            + ", ".join(ENTITY_DIRECTORIES.values()),
        )
    return Issue(
        file=_relative(root, path),
        code="unexpected_file",
        message=f"неожиданный файл; сущность хранится в файле <id>{_EXTENSION} "
        "внутри каталога своего типа",
    )


def _read_entity(
    root: Path, path: Path, kind: EntityType
) -> tuple[KnowledgeModel | None, list[Issue]]:
    file = _relative(root, path)
    try:
        data = read_yaml_file(path)
    except YamlReadError as error:
        return None, [
            Issue(file=file, code=error.code, message=error.message, line=error.line)
        ]

    try:
        entity = ENTITY_MODELS[kind].model_validate(data)
    except ValidationError as error:
        return None, [_schema_issue(file, item) for item in error.errors()]

    if entity.id != path.stem:  # type: ignore[attr-defined]
        return None, [
            Issue(
                file=file,
                path="id",
                code="file_id_mismatch",
                message=f"id должен совпадать с именем файла «{path.stem}»",
            )
        ]
    return entity, []


def _schema_issue(file: str, error: ErrorDetails) -> Issue:
    code, message = _translate(error)
    return Issue(file=file, path=_field_path(error["loc"]), code=code, message=message)


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
    context = error.get("ctx", {})
    if kind == "string_pattern_mismatch":
        if error["loc"] and error["loc"][-1] == "timecode":
            return "invalid_timecode", "ожидается время в виде MM:SS или HH:MM:SS"
        return (
            "invalid_id",
            "ожидается id из строчных латинских букв и цифр, разделённых «_»",
        )
    if kind == "greater_than_equal":
        return "invalid_value", f"значение должно быть не меньше {context['ge']}"
    if kind == "enum":
        return "invalid_value", f"допустимые значения: {context['expected']}"
    if kind in (
        "duplicate_value",
        "invalid_source",
        "unknown_revision_entity",
        "invalid_revision",
    ):
        return kind, error["msg"]
    return _SCHEMA_ERRORS.get(kind, ("schema_error", error["msg"]))


_SCHEMA_ERRORS = {
    "missing": ("missing_field", "обязательное поле не заполнено"),
    "extra_forbidden": ("extra_field", "неизвестное поле"),
    "string_type": ("invalid_type", "ожидается строка"),
    "int_type": ("invalid_type", "ожидается целое число"),
    "tuple_type": ("invalid_type", "ожидается список"),
    "model_type": ("invalid_type", "ожидается набор полей"),
    "model_attributes_type": ("invalid_type", "ожидается набор полей"),
    "string_too_short": ("empty_value", "значение не должно быть пустым"),
    "too_short": ("empty_value", "список не должен быть пустым"),
}
