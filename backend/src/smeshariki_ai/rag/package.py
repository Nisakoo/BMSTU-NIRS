"""Reading of a knowledge package: one YAML file per entity, grouped by type."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    SLUG_PATTERN,
    Artifact,
    Character,
    Continuity,
    EntityRef,
    EntityType,
    Episode,
    Issue,
    KnowledgeModel,
    KnowledgeSet,
    Location,
    Work,
)
from smeshariki_ai.rag.yaml_reader import YamlReadError, read_yaml_file

# Package directories are named after the fields of ``KnowledgeSet``.
ENTITY_DIRECTORIES = ENTITY_FIELDS
ENTITY_MODELS: dict[EntityType, type[KnowledgeModel]] = {
    EntityType.CONTINUITY: Continuity,
    EntityType.WORK: Work,
    EntityType.EPISODE: Episode,
    EntityType.CHARACTER: Character,
    EntityType.LOCATION: Location,
    EntityType.ARTIFACT: Artifact,
}
_TYPES_BY_DIRECTORY = {name: kind for kind, name in ENTITY_DIRECTORIES.items()}
_SLUG = re.compile(SLUG_PATTERN)
_EXTENSION = ".yaml"


class PackageNotFoundError(Exception):
    """The package path does not exist or is not a directory."""


class PackageContents(KnowledgeModel):
    knowledge: KnowledgeSet
    issues: tuple[Issue, ...]


def entity_file(ref: EntityRef) -> str:
    return f"{ENTITY_DIRECTORIES[ref.type]}/{ref.id}{_EXTENSION}"


def read_package(root: Path) -> PackageContents:
    """Validate every file of the package; files never stop the reading early."""

    if not root.is_dir():
        raise PackageNotFoundError(root)

    issues: list[Issue] = []
    entities: dict[EntityType, list[Any]] = {kind: [] for kind in EntityType}
    unverified: set[EntityRef] = set()
    entity_files = 0

    for entry in _visible(root):
        kind = _TYPES_BY_DIRECTORY.get(entry.name)
        if kind is None or not entry.is_dir():
            issues.append(_unexpected(root, entry))
            continue
        for path in _visible(entry):
            if not path.is_file() or path.suffix != _EXTENSION:
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
        **{ENTITY_DIRECTORIES[kind]: tuple(items) for kind, items in entities.items()},
        unverified=frozenset(unverified),
    )
    return PackageContents(knowledge=knowledge, issues=tuple(issues))


def _visible(directory: Path) -> Iterator[Path]:
    return (
        path for path in sorted(directory.iterdir()) if not path.name.startswith(".")
    )


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _unexpected(root: Path, path: Path) -> Issue:
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
    if kind in ("duplicate_value", "invalid_source"):
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
