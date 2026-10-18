import codecs
from pathlib import Path

import pytest

from smeshariki_ai.rag.yaml_reader import YamlReadError, read_yaml_file


def write(tmp_path: Path, text: str | bytes) -> Path:
    path = tmp_path / "entity.yaml"
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def read(tmp_path: Path, text: str | bytes) -> object:
    return read_yaml_file(write(tmp_path, text))


def read_error(tmp_path: Path, text: str | bytes) -> YamlReadError:
    with pytest.raises(YamlReadError) as error:
        read(tmp_path, text)
    return error.value


def test_reads_mapping_with_nested_values(tmp_path: Path) -> None:
    data = read(tmp_path, "id: pin\ntraits:\n  - добрый\nspeech_style:\n  x: 1\n")

    assert data == {"id": "pin", "traits": ["добрый"], "speech_style": {"x": 1}}


@pytest.mark.parametrize(
    "value",
    ["12:05", "1:30", "yes", "no", "on", "off", "y", "2026-10-18", "1.5", "0x1F"],
)
def test_yaml_1_1_implicit_types_stay_strings(tmp_path: Path, value: str) -> None:
    assert read(tmp_path, f"value: {value}\n") == {"value": value}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("42", 42),
        ("-7", -7),
        ("010", 10),
        ("null", None),
        ("~", None),
        ("", None),
    ],
)
def test_yaml_1_2_core_scalars(tmp_path: Path, value: str, expected: object) -> None:
    assert read(tmp_path, f"value: {value}\n") == {"value": expected}


def test_quoted_scalars_are_strings(tmp_path: Path) -> None:
    assert read(tmp_path, "a: \"42\"\nb: 'true'\n") == {"a": "42", "b": "true"}


def test_utf8_bom_is_accepted(tmp_path: Path) -> None:
    assert read(tmp_path, codecs.BOM_UTF8 + b"id: pin\n") == {"id": "pin"}


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("traits: [a]\ntraits: [b]\n", 2),
        ("speech_style:\n  register: a\n  register: b\n", 3),
    ],
)
def test_duplicate_key_is_an_error(tmp_path: Path, text: str, line: int) -> None:
    error = read_error(tmp_path, text)

    assert error.code == "duplicate_key"
    assert error.line == line
    assert "повторно" in error.message


@pytest.mark.parametrize(
    "text", ["id: !!str pin\n", "id: !custom pin\n", "traits: !!seq [a]\n"]
)
def test_explicit_tag_is_an_error(tmp_path: Path, text: str) -> None:
    assert read_error(tmp_path, text).code == "yaml_tag"


def test_python_object_tag_is_rejected(tmp_path: Path) -> None:
    error = read_error(tmp_path, "x: !!python/object/apply:os.system ['true']\n")

    assert error.code == "yaml_tag"


@pytest.mark.parametrize(
    "text", ["a: &x [1]\nb: *x\n", "a: &x value\n", "base: &b {k: v}\nm:\n  <<: *b\n"]
)
def test_anchor_and_alias_are_errors(tmp_path: Path, text: str) -> None:
    error = read_error(tmp_path, text)

    assert error.code == "yaml_anchor"
    assert error.line == 1


def test_syntax_error_reports_line(tmp_path: Path) -> None:
    error = read_error(tmp_path, "id: pin\ntraits: [a\nname: x\n")

    assert error.code == "yaml_syntax"
    assert error.line is not None
    assert "синтаксис" in error.message


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just text\n"])
def test_root_must_be_a_mapping(tmp_path: Path, text: str) -> None:
    assert read_error(tmp_path, text).code == "not_a_mapping"


def test_non_utf8_file_is_an_error(tmp_path: Path) -> None:
    error = read_error(tmp_path, "id: пин\n".encode("cp1251"))

    assert error.code == "invalid_encoding"
    assert "UTF-8" in error.message


def test_multiple_documents_are_an_error(tmp_path: Path) -> None:
    assert read_error(tmp_path, "id: a\n---\nid: b\n").code == "yaml_syntax"
