from pathlib import Path

import pytest

from smeshariki_ai.rag.models import EntityRef, EntityType
from smeshariki_ai.rag.package import (
    PackageNotFoundError,
    entity_file,
    read_package,
)

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


def put(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def issues(root: Path) -> list[tuple[str, str, str]]:
    return [(i.file, i.path, i.code) for i in read_package(root).issues]


def test_reads_every_entity_type(tmp_path: Path) -> None:
    put(tmp_path, "continuities/classic.yaml", "id: classic\nname: Классика\n")
    put(
        tmp_path,
        "works/series.yaml",
        "id: series\ntitle: Сериал\nkind: series\ncontinuity: classic\n",
    )
    put(
        tmp_path,
        "episodes/s01e01.yaml",
        "id: s01e01\nwork: series\nnumber: 1\ntitle: Серия\n",
    )
    put(tmp_path, "characters/pin.yaml", CHARACTER)
    put(
        tmp_path,
        "locations/house.yaml",
        "id: house\nname: Дом\ndescription: Дом.\ncontinuities: [classic]\n",
    )
    put(
        tmp_path,
        "artifacts/plane.yaml",
        "id: plane\nname: Самолёт\nartifact_type: машина\ndescription: Летает.\n"
        "continuities: [classic]\n",
    )

    contents = read_package(tmp_path)

    assert contents.issues == ()
    knowledge = contents.knowledge
    assert [c.id for c in knowledge.continuities] == ["classic"]
    assert [w.id for w in knowledge.works] == ["series"]
    assert [e.id for e in knowledge.episodes] == ["s01e01"]
    assert [c.id for c in knowledge.characters] == ["pin"]
    assert [loc.id for loc in knowledge.locations] == ["house"]
    assert [a.id for a in knowledge.artifacts] == ["plane"]


def test_partial_package_is_valid(tmp_path: Path) -> None:
    put(tmp_path, "characters/pin.yaml", CHARACTER)

    assert read_package(tmp_path).issues == ()


def test_hidden_entries_are_skipped(tmp_path: Path) -> None:
    put(tmp_path, "characters/pin.yaml", CHARACTER)
    put(tmp_path, ".git/config", "[core]\n")
    put(tmp_path, ".DS_Store", "binary")
    put(tmp_path, "characters/.DS_Store", "binary")

    assert issues(tmp_path) == []


def test_unexpected_entries_are_reported(tmp_path: Path) -> None:
    put(tmp_path, "characters/pin.yaml", CHARACTER)
    put(tmp_path, "README.md", "text")
    put(tmp_path, "heroes/krosh.yaml", "id: krosh\n")
    put(tmp_path, "characters/notes.txt", "text")
    put(tmp_path, "characters/pin.yml", CHARACTER)
    put(tmp_path, "characters/nested/x.yaml", CHARACTER)

    assert issues(tmp_path) == [
        ("README.md", "", "unexpected_file"),
        ("characters/nested", "", "unexpected_directory"),
        ("characters/notes.txt", "", "unexpected_file"),
        ("characters/pin.yml", "", "unexpected_file"),
        ("heroes", "", "unexpected_directory"),
    ]


def test_file_name_must_match_id(tmp_path: Path) -> None:
    put(tmp_path, "characters/krosh.yaml", CHARACTER)

    assert issues(tmp_path) == [("characters/krosh.yaml", "id", "file_id_mismatch")]


def test_empty_package_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "characters").mkdir()

    assert issues(tmp_path) == [(".", "", "empty_package")]


@pytest.mark.parametrize("make", [lambda p: p / "missing", lambda p: p / "file"])
def test_missing_package(tmp_path: Path, make) -> None:
    (tmp_path / "file").write_text("x", encoding="utf-8")

    with pytest.raises(PackageNotFoundError):
        read_package(make(tmp_path))


def test_yaml_errors_keep_line(tmp_path: Path) -> None:
    put(tmp_path, "characters/pin.yaml", CHARACTER + "species: кот\n")

    (issue,) = read_package(tmp_path).issues
    assert (issue.file, issue.code, issue.line) == (
        "characters/pin.yaml",
        "duplicate_key",
        10,
    )


@pytest.mark.parametrize(
    ("replace", "by", "path", "code"),
    [
        ("species: пингвин\n", "", "species", "missing_field"),
        (
            "species: пингвин\n",
            "species: пингвин\ncolour: red\n",
            "colour",
            "extra_field",
        ),
        ("[classic]", "classic", "versions[0].continuities", "invalid_type"),
        ("[classic]", "[Classic]", "versions[0].continuities[0]", "invalid_id"),
        ("[изобретательный]", "[]", "versions[0].traits", "empty_value"),
        (
            "age_group: adult",
            "age_group: baby",
            "versions[0].age_group",
            "invalid_value",
        ),
        ("[изобретательный]", "[а, а]", "versions[0].traits", "duplicate_value"),
        ("name: Пин", "name: 5", "name", "invalid_type"),
    ],
)
def test_schema_errors_have_codes_and_paths(
    tmp_path: Path, replace: str, by: str, path: str, code: str
) -> None:
    put(tmp_path, "characters/pin.yaml", CHARACTER.replace(replace, by))

    (issue,) = read_package(tmp_path).issues
    assert (issue.file, issue.path, issue.code) == ("characters/pin.yaml", path, code)
    assert issue.message
    assert not issue.message.isascii()


def test_invalid_timecode_and_source(tmp_path: Path) -> None:
    put(
        tmp_path,
        "characters/pin.yaml",
        CHARACTER + "sources:\n  - episode: e1\n    timecode: '4:32'\n  - note: x\n",
    )

    assert issues(tmp_path) == [
        ("characters/pin.yaml", "sources[0].timecode", "invalid_timecode"),
        ("characters/pin.yaml", "sources[1]", "invalid_source"),
    ]


def test_invalid_files_are_unverified(tmp_path: Path) -> None:
    put(tmp_path, "characters/pin.yaml", CHARACTER.replace("species: пингвин\n", ""))
    put(tmp_path, "characters/krosh.yaml", "id: [broken\n")

    knowledge = read_package(tmp_path).knowledge
    assert knowledge.characters == ()
    assert knowledge.unverified == frozenset(
        {
            EntityRef(type=EntityType.CHARACTER, id="krosh"),
            EntityRef(type=EntityType.CHARACTER, id="pin"),
        }
    )


def test_entity_file() -> None:
    ref = EntityRef(type=EntityType.EPISODE, id="s01e01")

    assert entity_file(ref) == "episodes/s01e01.yaml"
