import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from smeshariki_ai.rag.cli import main

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
    "argv", [[], ["check"], ["unknown"], ["check", ".", "--format", "xml"]]
)
def test_bad_arguments_exit_with_2(argv: list[str], capsys) -> None:
    assert run(*argv)[0] == 2
    assert "usage" in capsys.readouterr().err


def test_schema_lists_every_entity_type() -> None:
    code, output = run("schema")

    schema = json.loads(output)
    assert code == 0
    assert set(schema) == {
        "continuities",
        "works",
        "episodes",
        "characters",
        "locations",
        "artifacts",
    }
    assert schema["characters"]["properties"]["id"]["pattern"]
    assert "Interaction" in schema["episodes"]["$defs"]


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
