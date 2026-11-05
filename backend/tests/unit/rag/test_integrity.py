import copy
from typing import Any

import pytest

from smeshariki_ai.rag.integrity import check_integrity
from smeshariki_ai.rag.models import (
    Artifact,
    Character,
    Continuity,
    EntityRef,
    EntityType,
    Episode,
    KnowledgeSet,
    Location,
    Work,
)


def version(*continuities: str) -> dict[str, Any]:
    return {
        "continuities": list(continuities),
        "age_group": "child",
        "traits": ["весёлый"],
        "speech_style": {"register": "разговорный"},
    }


def base() -> dict[str, list[dict[str, Any]]]:
    """A small valid universe: two continuities, a series, a film and heroes."""

    return {
        "continuities": [
            {"id": "classic", "name": "Классика"},
            {"id": "movies", "name": "Фильмы"},
        ],
        "works": [
            {
                "id": "series",
                "title": "Сериал",
                "kind": "series",
                "continuity": "classic",
            },
            {"id": "film", "title": "Фильм", "kind": "film", "continuity": "movies"},
        ],
        "episodes": [
            {
                "id": "s01e01",
                "work": "series",
                "season": 1,
                "number": 1,
                "title": "Первая",
                "characters": ["krosh", "ezhik"],
                "locations": ["house"],
                "artifacts": ["plane"],
                "interactions": [
                    {
                        "from": "krosh",
                        "to": "ezhik",
                        "type": "conflict",
                        "description": "Спорят, чья очередь.",
                        "sources": [{"episode": "s01e01", "timecode": "01:00"}],
                    }
                ],
            },
            {
                "id": "film_main",
                "work": "film",
                "number": 1,
                "title": "Фильм",
                "characters": ["krosh"],
            },
        ],
        "characters": [
            {
                "id": "krosh",
                "name": "Крош",
                "aliases": ["Кролик"],
                "species": "кролик",
                "versions": [version("classic"), version("movies")],
                "relationships": [
                    {"to": "ezhik", "type": "friendship", "continuities": ["classic"]}
                ],
            },
            {
                "id": "ezhik",
                "name": "Ёжик",
                "species": "ёж",
                "versions": [version("classic")],
            },
        ],
        "locations": [
            {
                "id": "house",
                "name": "Дом",
                "description": "Дом.",
                "continuities": ["classic"],
                "residents": ["krosh"],
            }
        ],
        "artifacts": [
            {
                "id": "plane",
                "name": "Самолёт",
                "artifact_type": "машина",
                "description": "Летает.",
                "continuities": ["classic"],
                "creators": ["ezhik"],
            }
        ],
    }


MODELS = {
    "continuities": Continuity,
    "works": Work,
    "episodes": Episode,
    "characters": Character,
    "locations": Location,
    "artifacts": Artifact,
}


def build(data: dict[str, list[dict[str, Any]]], **extra: Any) -> KnowledgeSet:
    return KnowledgeSet(
        **{
            key: tuple(MODELS[key].model_validate(item) for item in items)
            for key, items in data.items()
        },
        **extra,
    )


def violations(data: dict, *, complete: bool = True) -> list[tuple[str, str, str]]:
    report = check_integrity(build(data), complete=complete)
    return [(v.entity.id, v.path, v.code) for v in report.violations]


def find(data: dict, key: str, entity_id: str) -> dict[str, Any]:
    return next(item for item in data[key] if item["id"] == entity_id)


def test_valid_universe_has_no_violations() -> None:
    report = check_integrity(build(base()), complete=True)

    assert report.violations == ()
    assert report.external == ()


@pytest.mark.parametrize(
    ("key", "entity_id", "field", "value", "path"),
    [
        ("works", "series", "continuity", "missing", "continuity"),
        ("episodes", "s01e01", "work", "missing", "work"),
        ("episodes", "s01e01", "locations", ["missing"], "locations[0]"),
        ("episodes", "s01e01", "artifacts", ["missing"], "artifacts[0]"),
        ("locations", "house", "residents", ["missing"], "residents[0]"),
        ("artifacts", "plane", "creators", ["missing"], "creators[0]"),
        ("locations", "house", "continuities", ["missing"], "continuities[0]"),
        (
            "characters",
            "ezhik",
            "sources",
            [{"episode": "missing"}],
            "sources[0].episode",
        ),
    ],
)
def test_unknown_reference(
    key: str, entity_id: str, field: str, value: Any, path: str
) -> None:
    data = base()
    find(data, key, entity_id)[field] = value

    assert (entity_id, path, "unknown_reference") in violations(data)


def test_unknown_reference_in_nested_records() -> None:
    data = base()
    krosh = find(data, "characters", "krosh")
    krosh["versions"][0]["continuities"] = ["classic", "missing"]
    krosh["relationships"][0]["to"] = "missing"

    found = violations(data)
    assert ("krosh", "versions[0].continuities[1]", "unknown_reference") in found
    assert ("krosh", "relationships[0].to", "unknown_reference") in found


def test_reference_to_wrong_type_is_unknown() -> None:
    data = base()
    find(data, "episodes", "s01e01")["characters"] = ["krosh", "ezhik", "house"]

    assert ("s01e01", "characters[2]", "unknown_reference") in violations(data)


def test_overlapping_versions() -> None:
    data = base()
    find(data, "characters", "krosh")["versions"] = [
        version("classic"),
        version("movies", "classic"),
    ]

    assert violations(data) == [
        ("krosh", "versions[1].continuities[1]", "overlapping_versions")
    ]


def test_self_relationship() -> None:
    data = base()
    find(data, "characters", "ezhik")["relationships"] = [
        {"to": "ezhik", "type": "mentor", "continuities": ["classic"]}
    ]

    assert violations(data) == [("ezhik", "relationships[0].to", "self_reference")]


@pytest.mark.parametrize("owner", ["krosh", "ezhik"])
def test_relationship_outside_versions(owner: str) -> None:
    data = base()
    target = "ezhik" if owner == "krosh" else "krosh"
    find(data, "characters", owner)["relationships"] = [
        {"to": target, "type": "affection", "continuities": ["movies"]}
    ]

    assert (owner, "relationships[0].continuities[0]", "continuity_mismatch") in (
        violations(data)
    )


def test_duplicate_relationship_with_overlapping_continuities() -> None:
    data = base()
    find(data, "characters", "krosh")["relationships"].append(
        {
            "to": "ezhik",
            "type": "friendship",
            "continuities": ["classic"],
            "description": "Ещё раз.",
        }
    )

    assert violations(data) == [("krosh", "relationships[1]", "duplicate_relationship")]


def test_symmetric_relationship_reverse_pair_is_duplicate() -> None:
    data = base()
    find(data, "characters", "ezhik")["relationships"] = [
        {"to": "krosh", "type": "friendship", "continuities": ["classic"]}
    ]

    assert violations(data) == [("krosh", "relationships[0]", "duplicate_relationship")]


def test_directed_relationship_reverse_pair_is_allowed() -> None:
    data = base()
    find(data, "characters", "krosh")["relationships"].append(
        {"to": "ezhik", "type": "guardian", "continuities": ["classic"]}
    )
    find(data, "characters", "ezhik")["relationships"] = [
        {"to": "krosh", "type": "guardian", "continuities": ["classic"]}
    ]

    assert violations(data) == []


def test_relationships_without_overlap_are_not_duplicates() -> None:
    data = base()
    find(data, "characters", "ezhik")["versions"] = [version("classic", "movies")]
    krosh = find(data, "characters", "krosh")
    krosh["relationships"].append(
        {"to": "ezhik", "type": "friendship", "continuities": ["movies"]}
    )

    assert violations(data) == []


@pytest.mark.parametrize(
    ("field", "value", "path"),
    [
        ("characters", ["krosh", "ezhik", "sovunya"], "characters[2]"),
        ("locations", ["cave"], "locations[0]"),
        ("artifacts", ["ring"], "artifacts[0]"),
    ],
)
def test_participant_outside_episode_continuity(
    field: str, value: list[str], path: str
) -> None:
    data = base()
    data["characters"].append(
        {
            "id": "sovunya",
            "name": "Совунья",
            "species": "сова",
            "versions": [version("movies")],
        }
    )
    data["locations"].append(
        {
            "id": "cave",
            "name": "Пещера",
            "description": "Тёмная.",
            "continuities": ["movies"],
        }
    )
    data["artifacts"].append(
        {
            "id": "ring",
            "name": "Кольцо",
            "artifact_type": "украшение",
            "description": "Блестит.",
            "continuities": ["movies"],
        }
    )
    find(data, "episodes", "s01e01")[field] = value

    assert violations(data) == [("s01e01", path, "continuity_mismatch")]


@pytest.mark.parametrize(
    ("key", "entity_id", "field"),
    [("locations", "house", "residents"), ("artifacts", "plane", "creators")],
)
def test_resident_and_creator_outside_continuities(
    key: str, entity_id: str, field: str
) -> None:
    data = base()
    data["characters"].append(
        {
            "id": "sovunya",
            "name": "Совунья",
            "species": "сова",
            "versions": [version("movies")],
        }
    )
    find(data, key, entity_id)[field] = ["sovunya"]

    assert violations(data) == [(entity_id, f"{field}[0]", "continuity_mismatch")]


def test_interaction_participant_outside_episode() -> None:
    data = base()
    episode = find(data, "episodes", "s01e01")
    episode["characters"] = ["krosh"]

    assert violations(data) == [
        ("s01e01", "interactions[0].to", "interaction_participant")
    ]


def test_self_interaction() -> None:
    data = base()
    find(data, "episodes", "s01e01")["interactions"][0]["to"] = "krosh"

    assert violations(data) == [("s01e01", "interactions[0].to", "self_reference")]


@pytest.mark.parametrize("pair", [("ezhik", "krosh"), ("krosh", "ezhik")])
def test_duplicate_symmetric_interaction(pair: tuple[str, str]) -> None:
    data = base()
    find(data, "episodes", "s01e01")["interactions"].append(
        {
            "from": pair[0],
            "to": pair[1],
            "type": "conflict",
            "description": "Снова спорят.",
        }
    )

    assert violations(data) == [("s01e01", "interactions[1]", "duplicate_interaction")]


def test_directed_interaction_reverse_pair_is_allowed() -> None:
    data = base()
    interactions = find(data, "episodes", "s01e01")["interactions"]
    interactions[:] = [
        {"from": "krosh", "to": "ezhik", "type": "support", "description": "Помог."},
        {"from": "ezhik", "to": "krosh", "type": "support", "description": "Ответил."},
    ]

    assert violations(data) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"name": "крош"}, ("krosh", "name", "duplicate_name")),
        ({"aliases": ["кролик"]}, ("krosh", "aliases[0]", "duplicate_name")),
        ({"aliases": ["ежик"]}, ("ezhik", "aliases[0]", "duplicate_name")),
        (
            {"aliases": ["\u0415\u0308жик"]},
            ("ezhik", "aliases[0]", "duplicate_name"),
        ),
    ],
)
def test_character_names_are_unique(change: dict, expected: tuple) -> None:
    """The entity later in ``id`` order gets the violation."""

    data = base()
    find(data, "characters", "ezhik").update(change)

    assert violations(data) == [expected]


def test_location_names_unique_only_with_overlapping_continuities() -> None:
    data = base()
    data["locations"].append(
        {
            "id": "house_movie",
            "name": "дом",
            "description": "Другой.",
            "continuities": ["movies"],
        }
    )
    assert violations(data) == []

    copy_in_classic = copy.deepcopy(data)
    find(copy_in_classic, "locations", "house_movie")["continuities"] = ["classic"]
    assert violations(copy_in_classic) == [("house_movie", "name", "duplicate_name")]


def test_duplicate_episode_number() -> None:
    data = base()
    data["episodes"].append(
        {
            "id": "s01e01_copy",
            "work": "series",
            "season": 1,
            "number": 1,
            "title": "Копия",
        }
    )

    assert violations(data) == [("s01e01_copy", "number", "duplicate_episode_number")]


def test_same_number_in_other_season_is_allowed() -> None:
    data = base()
    data["episodes"].append(
        {"id": "s02e01", "work": "series", "season": 2, "number": 1, "title": "Вторая"}
    )

    assert violations(data) == []


def test_film_has_at_most_one_episode() -> None:
    data = base()
    data["episodes"].append(
        {"id": "film_extra", "work": "film", "number": 2, "title": "Ещё"}
    )

    assert violations(data) == [
        ("film_extra", "work", "film_episode_count"),
        ("film_main", "work", "film_episode_count"),
    ]


def test_incomplete_set_reports_external_references() -> None:
    data = {"episodes": [find(base(), "episodes", "s01e01")]}

    report = check_integrity(build(data), complete=False)

    assert report.violations == ()
    assert report.external == (
        EntityRef(type=EntityType.WORK, id="series"),
        EntityRef(type=EntityType.CHARACTER, id="ezhik"),
        EntityRef(type=EntityType.CHARACTER, id="krosh"),
        EntityRef(type=EntityType.LOCATION, id="house"),
        EntityRef(type=EntityType.ARTIFACT, id="plane"),
    )


def test_incomplete_set_defers_rules_needing_missing_data() -> None:
    data = {"characters": [find(base(), "characters", "krosh")]}
    data["characters"][0]["relationships"][0]["continuities"] = ["movies"]

    report = check_integrity(build(data), complete=False)

    assert report.violations == ()
    assert EntityRef(type=EntityType.CHARACTER, id="ezhik") in report.external


def test_unverified_entities_are_neither_errors_nor_external() -> None:
    data = base()
    data["characters"] = [find(data, "characters", "krosh")]
    unverified = frozenset({EntityRef(type=EntityType.CHARACTER, id="ezhik")})

    report = check_integrity(build(data), complete=True, unverified=unverified)

    assert report.violations == ()
    assert report.external == ()
