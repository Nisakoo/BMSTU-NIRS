"""Safe reading of one knowledge file.

Plain scalars follow the YAML 1.2 core schema, so values such as ``12:05``,
``no`` or dates stay strings instead of turning into numbers or booleans.
Duplicate keys, tags and anchors are rejected rather than silently resolved.
"""

import re
from pathlib import Path
from typing import Any

import yaml
from yaml.events import AliasEvent, CollectionStartEvent, NodeEvent, ScalarEvent


class YamlReadError(Exception):
    def __init__(self, code: str, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line


class _DuplicateKeyError(Exception):
    def __init__(self, key: object, line: int) -> None:
        self.key = key
        self.line = line


class _Loader(yaml.SafeLoader):
    yaml_implicit_resolvers: dict[str, list[tuple[str, re.Pattern[str]]]] = {}

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> Any:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise _DuplicateKeyError(key, key_node.start_mark.line + 1)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)

    def construct_yaml_int(self, node: yaml.ScalarNode) -> int:
        # The YAML 1.1 constructor reads "010" as octal; YAML 1.2 core is decimal.
        return int(self.construct_scalar(node))


_Loader.add_constructor("tag:yaml.org,2002:int", _Loader.construct_yaml_int)
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^[-+]?[0-9]+$"), list("-+0123456789")
)
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:null",
    re.compile(r"^(?:~|null|Null|NULL|)$"),
    ["~", "n", "N", ""],
)


def read_yaml_file(path: Path) -> dict[Any, Any]:
    """Return the mapping stored in ``path`` or raise ``YamlReadError``."""

    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise YamlReadError("invalid_encoding", "файл не в кодировке UTF-8") from error

    try:
        _reject_tags_and_anchors(text)
        data = yaml.load(text, Loader=_Loader)  # _Loader derives from SafeLoader
    except _DuplicateKeyError as error:
        raise YamlReadError(
            "duplicate_key", f"ключ «{error.key}» указан повторно", error.line
        ) from None
    except yaml.MarkedYAMLError as error:
        line = error.problem_mark.line + 1 if error.problem_mark else None
        raise YamlReadError(
            "yaml_syntax", f"ошибка синтаксиса YAML: {error.problem}", line
        ) from error

    if not isinstance(data, dict):
        raise YamlReadError(
            "not_a_mapping", "файл должен содержать YAML-отображение (набор полей)"
        )
    return data


def _reject_tags_and_anchors(text: str) -> None:
    for event in yaml.parse(text, Loader=_Loader):
        line = event.start_mark.line + 1
        if isinstance(event, AliasEvent) or (
            isinstance(event, NodeEvent) and event.anchor is not None
        ):
            raise YamlReadError(
                "yaml_anchor", "YAML-якоря и ссылки не поддерживаются", line
            )
        if isinstance(event, ScalarEvent | CollectionStartEvent) and event.tag:
            raise YamlReadError("yaml_tag", "YAML-теги не поддерживаются", line)
