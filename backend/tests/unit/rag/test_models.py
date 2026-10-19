from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from smeshariki_ai.rag.models import (
    AgeGroup,
    Artifact,
    Character,
    Continuity,
    Episode,
    InteractionType,
    Location,
    RelationshipType,
    SourceRef,
    Work,
    WorkKind,
    normalize_name,
)

VERSION = {
    "continuities": ["classic"],
    "age_group": "adult",
    "traits": ["изобретательный"],
    "speech_style": {"register": "разговорный"},
}
CHARACTER = {"id": "pin", "name": "Пин", "species": "пингвин", "versions": [VERSION]}
EPISODE = {"id": "s01e01", "work": "series", "number": 1, "title": "Серия"}
LOCATION = {
    "id": "pin_house",
    "name": "Дом Пина",
    "description": "Мастерская.",
    "continuities": ["classic"],
}
ARTIFACT = {
    "id": "plane",
    "name": "Самолёт",
    "artifact_type": "летательный аппарат",
    "description": "Самолёт Пина.",
    "continuities": ["classic"],
}


def error_types(model: type[BaseModel], data: dict[str, Any]) -> list[tuple]:
    with pytest.raises(ValidationError) as error:
        model.model_validate(data)
    return [(item["loc"], item["type"]) for item in error.value.errors()]


def with_field(data: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {**data, **changes}


def test_minimal_records_use_empty_defaults() -> None:
    character = Character.model_validate(CHARACTER)
    episode = Episode.model_validate(EPISODE)
    location = Location.model_validate(LOCATION)
    artifact = Artifact.model_validate(ARTIFACT)

    assert character.aliases == () and character.relationships == ()
    assert character.sources == ()
    assert character.versions[0].catchphrases == ()
    assert character.versions[0].speech_style.markers == ()
    assert episode.season is None and episode.characters == ()
    assert episode.interactions == ()
    assert location.residents == () and artifact.creators == ()
    assert artifact.capabilities == () and artifact.limitations == ()


def test_full_records_are_parsed_into_tuples() -> None:
    character = Character.model_validate(
        with_field(
            CHARACTER,
            aliases=["механик"],
            relationships=[
                {"to": "krosh", "type": "friendship", "continuities": ["classic"]}
            ],
            sources=[{"document": "Справочник", "note": "вид"}],
        )
    )

    assert character.aliases == ("механик",)
    assert character.relationships[0].type is RelationshipType.FRIENDSHIP
    assert character.versions[0].age_group is AgeGroup.ADULT
    assert character.sources[0].document == "Справочник"


def test_continuity_and_work() -> None:
    work = Work.model_validate(
        {"id": "series", "title": "Смешарики", "kind": "series", "continuity": "a"}
    )

    assert work.kind is WorkKind.SERIES
    assert Continuity.model_validate({"id": "a", "name": "А"}).name == "А"


def test_interaction_uses_from_key() -> None:
    episode = Episode.model_validate(
        with_field(
            EPISODE,
            interactions=[
                {
                    "from": "krosh",
                    "to": "ezhik",
                    "type": "conflict",
                    "description": "Спор о том, кто прав.",
                }
            ],
        )
    )

    interaction = episode.interactions[0]
    assert (interaction.from_, interaction.to) == ("krosh", "ezhik")
    assert interaction.type is InteractionType.CONFLICT


@pytest.mark.parametrize("field", ["id", "name", "species", "versions"])
def test_required_character_fields(field: str) -> None:
    data = {key: value for key, value in CHARACTER.items() if key != field}

    assert error_types(Character, data) == [((field,), "missing")]


def test_extra_field_is_rejected() -> None:
    assert error_types(Character, with_field(CHARACTER, colour="blue")) == [
        (("colour",), "extra_forbidden")
    ]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"name": 5}, (("name",), "string_type")),
        ({"name": True}, (("name",), "string_type")),
        ({"aliases": [5]}, (("aliases", 0), "string_type")),
        ({"aliases": None}, (("aliases",), "tuple_type")),
        ({"aliases": "механик"}, (("aliases",), "tuple_type")),
    ],
)
def test_types_are_strict(changes: dict[str, Any], expected: tuple) -> None:
    assert error_types(Character, with_field(CHARACTER, **changes)) == [expected]


@pytest.mark.parametrize("number", ["1", True, 1.0])
def test_integer_fields_are_strict(number: Any) -> None:
    assert error_types(Episode, with_field(EPISODE, number=number)) == [
        (("number",), "int_type")
    ]


@pytest.mark.parametrize(("field", "value"), [("number", 0), ("season", 0)])
def test_episode_numbers_start_at_one(field: str, value: int) -> None:
    assert error_types(Episode, with_field(EPISODE, **{field: value})) == [
        ((field,), "greater_than_equal")
    ]


def test_strings_are_stripped_and_must_not_be_empty() -> None:
    assert Character.model_validate(with_field(CHARACTER, name="  Пин ")).name == "Пин"
    assert error_types(Character, with_field(CHARACTER, name="   ")) == [
        (("name",), "string_too_short")
    ]


@pytest.mark.parametrize(
    ("model", "data", "field"),
    [
        (Character, CHARACTER, "versions"),
        (Location, LOCATION, "continuities"),
        (Artifact, ARTIFACT, "continuities"),
    ],
)
def test_non_empty_lists(model: type[BaseModel], data: dict, field: str) -> None:
    assert error_types(model, with_field(data, **{field: []})) == [
        ((field,), "too_short")
    ]


def test_version_traits_must_not_be_empty() -> None:
    version = with_field(VERSION, traits=[])

    assert error_types(Character, with_field(CHARACTER, versions=[version])) == [
        (("versions", 0, "traits"), "too_short")
    ]


def test_list_values_must_be_unique() -> None:
    assert error_types(Character, with_field(CHARACTER, aliases=["а", "а"])) == [
        (("aliases",), "duplicate_value")
    ]


@pytest.mark.parametrize("value", ["Pin", "pin-house", "pin__house", "_pin", "pin_"])
def test_id_format(value: str) -> None:
    assert error_types(Character, with_field(CHARACTER, id=value)) == [
        (("id",), "string_pattern_mismatch")
    ]


@pytest.mark.parametrize(
    ("model", "data", "field", "value"),
    [
        (Character, CHARACTER, "versions", [with_field(VERSION, age_group="baby")]),
        (Work, {"id": "w", "title": "Т", "continuity": "a"}, "kind", "show"),
    ],
)
def test_enum_values(
    model: type[BaseModel], data: dict, field: str, value: Any
) -> None:
    types = [item_type for _, item_type in error_types(model, {**data, field: value})]

    assert types == ["enum"]


@pytest.mark.parametrize("timecode", ["04:32", "01:12:30"])
def test_valid_timecode(timecode: str) -> None:
    assert SourceRef.model_validate({"episode": "e", "timecode": timecode})


@pytest.mark.parametrize("timecode", ["4:32", "04:60", "1:12:30", "04:32:1"])
def test_invalid_timecode(timecode: str) -> None:
    assert error_types(SourceRef, {"episode": "e", "timecode": timecode}) == [
        (("timecode",), "string_pattern_mismatch")
    ]


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"note": "без источника"},
        {"episode": "e", "document": "Справочник"},
        {"episode": "e", "locator": "стр. 3"},
        {"document": "Справочник", "timecode": "04:32"},
    ],
)
def test_source_has_exactly_one_kind(data: dict) -> None:
    assert error_types(SourceRef, data) == [((), "invalid_source")]


def test_relationship_and_interaction_registries() -> None:
    assert {t for t in RelationshipType if t.symmetric} == {
        RelationshipType.FRIENDSHIP,
        RelationshipType.NEIGHBORHOOD,
    }
    assert {t for t in InteractionType if t.symmetric} == {InteractionType.CONFLICT}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  Ёжик ", "ежик"),
        ("Дом   Пина", "дом пина"),
        ("КРОШ", "крош"),
        # "Ё" typed as "Е" plus a combining diaeresis, as some editors produce.
        ("\u0415\u0308жик", "ежик"),
        ("сме\u0308шарик", "смешарик"),
        ("Straße", "strasse"),
    ],
)
def test_normalize_name(value: str, expected: str) -> None:
    assert normalize_name(value) == expected


def test_json_schema_exposes_constraints() -> None:
    schema = Episode.model_json_schema()
    properties = schema["properties"]
    interaction = schema["$defs"]["Interaction"]["properties"]

    assert properties["id"]["pattern"] == r"^[a-z0-9]+(_[a-z0-9]+)*$"
    assert properties["number"]["minimum"] == 1
    assert properties["characters"]["uniqueItems"] is True
    assert "from" in interaction and "from_" not in interaction
    assert schema["additionalProperties"] is False


def test_models_are_immutable() -> None:
    character = Character.model_validate(CHARACTER)

    with pytest.raises(ValidationError):
        character.name = "Другой"  # type: ignore[misc]
