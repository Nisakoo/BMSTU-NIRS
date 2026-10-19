import json
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import StringIO
from pathlib import Path

import pytest

from smeshariki_ai.rag.cli import ConfigurationError, main
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.ports import KnowledgeDataInvalidError

CHARACTER = """\
id: pin
name: Пин
species: пингвин
versions:
  - continuities: [classic]
    age_group: adult
    traits: [изобретательный]
    speech_style:
      register: разговорный
"""
EPISODE = "id: s01e01\nwork: series\nnumber: 1\ntitle: Серия\ncharacters: [pin]\n"


@pytest.fixture(autouse=True)
def manifest(tmp_path: Path) -> Path:
    """Every package of these tests declares the current format version."""

    path = tmp_path / "package.yaml"
    path.write_text("format_version: 1\n", encoding="utf-8")
    return path


def put(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(*argv: str) -> tuple[int, str]:
    output = StringIO()
    code = main(list(argv), stdout=output)
    return code, output.getvalue()


def test_valid_package_text(tmp_path: Path) -> None:
    put(tmp_path, "characters/pin.yaml", CHARACTER)
    put(tmp_path, "episodes/s01e01.yaml", EPISODE)

    code, output = run("check", str(tmp_path))

    assert code == 0
    assert "Пакет валиден" in output
    assert "characters: 1" in output and "episodes: 1" in output
    assert "work series" in output
    assert "continuity classic" in output


def test_invalid_package_lists_all_issues_in_order(tmp_path: Path) -> None:
    put(tmp_path, "episodes/s01e01.yaml", EPISODE.replace("number: 1\n", ""))
    put(
        tmp_path,
        "characters/pin.yaml",
        CHARACTER.replace("species: пингвин\n", "species: пингвин\nspecies: кот\n"),
    )
    put(
        tmp_path,
        "characters/krosh.yaml",
        CHARACTER.replace("id: pin", "id: krosh").replace("name: Пин", "name: Крош")
        + "colour: blue\n",
    )

    code, output = run("check", str(tmp_path))

    assert code == 1
    lines = [line for line in output.splitlines() if line.startswith(("ch", "ep"))]
    assert lines[0].startswith("characters/krosh.yaml: colour:")
    assert lines[0].endswith("[extra_field]")
    assert lines[1].startswith("characters/pin.yaml (строка 4):")
    assert lines[1].endswith("[duplicate_key]")
    assert lines[2].startswith("episodes/s01e01.yaml: number:")
    assert "Ошибок: 3" in output


def test_field_paths_are_ordered_naturally(tmp_path: Path) -> None:
    traits = ", ".join('""' if i in (2, 10) else f"t{i}" for i in range(12))
    put(
        tmp_path,
        "characters/pin.yaml",
        CHARACTER.replace("[изобретательный]", f"[{traits}]"),
    )

    code, output = run("check", str(tmp_path), "--format", "json")

    paths = [issue["path"] for issue in json.loads(output)["issues"]]
    assert code == 1
    assert paths == ["versions[0].traits[2]", "versions[0].traits[10]"]


def test_json_output_structure(tmp_path: Path) -> None:
    put(tmp_path, "episodes/s01e01.yaml", EPISODE)
    put(tmp_path, "characters/pin.yaml", CHARACTER.replace("age_group: adult", ""))

    code, output = run("check", str(tmp_path), "--format", "json")

    report = json.loads(output)
    assert code == 1
    assert report["valid"] is False
    assert report["counts"]["episodes"] == 1 and report["counts"]["characters"] == 0
    assert {"type": "work", "id": "series"} in report["external"]
    assert report["issues"] == [
        {
            "file": "characters/pin.yaml",
            "path": "versions[0].age_group",
            "code": "missing_field",
            "message": "обязательное поле не заполнено",
            "line": None,
        }
    ]


def test_missing_package(tmp_path: Path) -> None:
    code, output = run("check", str(tmp_path / "missing"), "--format", "json")

    report = json.loads(output)
    assert code == 1
    assert report["valid"] is False
    assert report["issues"][0]["code"] == "package_not_found"


def test_missing_package_text(tmp_path: Path) -> None:
    code, output = run("check", str(tmp_path / "missing"))

    assert code == 1
    assert "[package_not_found]" in output


@pytest.mark.parametrize(
    "argv",
    [[], ["check"], ["load"], ["unknown"], ["check", ".", "--format", "xml"]],
)
def test_bad_arguments_exit_with_2(argv: list[str], capsys) -> None:
    assert run(*argv)[0] == 2
    assert "usage" in capsys.readouterr().err


def test_schema_lists_every_entity_type() -> None:
    code, output = run("schema")

    schema = json.loads(output)
    assert code == 0
    assert schema["format_version"] == 1
    assert schema["manifest"]["required"] == ["format_version"]
    assert set(schema["entities"]) == {
        "continuities",
        "works",
        "episodes",
        "characters",
        "locations",
        "artifacts",
    }
    assert schema["entities"]["characters"]["properties"]["id"]["pattern"]
    assert "Interaction" in schema["entities"]["episodes"]["$defs"]


def test_module_runs_without_environment(tmp_path: Path) -> None:
    """Loading the backend config would fail here: its variables are absent."""

    put(tmp_path, "characters/pin.yaml", CHARACTER)

    result = subprocess.run(
        [sys.executable, "-m", "smeshariki_ai.rag", "check", str(tmp_path)],
        env={},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Пакет валиден" in result.stdout


def memory(store: InMemoryKnowledgeStore):
    @asynccontextmanager
    async def factory() -> AsyncIterator[InMemoryKnowledgeStore]:
        yield store

    return factory


def run_load(store: InMemoryKnowledgeStore, *argv: str) -> tuple[int, str]:
    output = StringIO()
    code = main(["load", *argv], stdout=output, store=memory(store))
    return code, output.getvalue()


def valid_package(root: Path) -> Path:
    put(root, "continuities/classic.yaml", "id: classic\nname: Классика\n")
    put(root, "characters/pin.yaml", CHARACTER)
    return root


def test_load_reports_added_then_unchanged(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    root = valid_package(tmp_path)

    first_code, first = run_load(store, str(root))
    second_code, second = run_load(store, str(root))

    assert (first_code, second_code) == (0, 0)
    assert "Загрузка 1 выполнена." in first
    assert "characters: добавлено 1, изменено 0, без изменений 0" in first
    assert "Всего сущностей в БД: 2." in first
    assert "characters: добавлено 0, изменено 0, без изменений 1" in second


def test_load_of_invalid_package_writes_nothing(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    put(tmp_path, "characters/pin.yaml", CHARACTER.replace("age_group: adult", ""))

    code, output = run_load(store, str(tmp_path))

    assert code == 1
    assert "characters/pin.yaml: versions[0].age_group:" in output
    assert "Загрузка отменена, БД не изменена. Ошибок: 1" in output


def test_load_json_output(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()

    code, output = run_load(store, str(valid_package(tmp_path)), "--format", "json")

    report = json.loads(output)
    assert code == 0
    assert report["loaded"] is True and report["load_id"] == 1
    assert report["counts"]["characters"] == {"added": 1, "updated": 0, "unchanged": 0}
    assert report["entity_count"] == 2 and report["issues"] == []


def test_load_without_backend_config_is_a_clear_error(tmp_path: Path) -> None:
    @asynccontextmanager
    async def unconfigured() -> AsyncIterator[InMemoryKnowledgeStore]:
        raise ConfigurationError
        yield InMemoryKnowledgeStore()  # pragma: no cover

    output = StringIO()
    code = main(
        ["load", str(valid_package(tmp_path))], stdout=output, store=unconfigured
    )

    assert code == 1
    assert "[configuration_error]" in output.getvalue()


def test_invalid_stored_data_is_not_a_configuration_error(tmp_path: Path) -> None:
    class CorruptedStore(InMemoryKnowledgeStore):
        @asynccontextmanager
        async def transaction(self):  # type: ignore[override]
            raise KnowledgeDataInvalidError
            yield  # pragma: no cover

    code, output = run_load(CorruptedStore(), str(valid_package(tmp_path)))

    assert code == 1
    assert "[stored_data_invalid]" in output
    assert "configuration_error" not in output
