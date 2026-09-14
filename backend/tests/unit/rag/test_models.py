from __future__ import annotations

from pydantic import TypeAdapter, ValidationError
import pytest

from smeshariki_ai.rag.models import (
    AgeGroup,
    ArtifactProfile,
    CharacterProfile,
    EntityType,
    KnowledgeAmbiguous,
    KnowledgeCatalog,
    KnowledgeFound,
    KnowledgeLookupResult,
    KnowledgeNotFound,
    LocationProfile,
    SourceRef,
    SpeechStyle,
    SystemContext,
)


def source_ref(locator: str = "series_15.md:42") -> SourceRef:
    return SourceRef(
        source_id="series-15",
        source_version="1",
        locator=locator,
        checksum="sha256:example",
    )


def character(
    *,
    record_id: str = "pin",
    name: str = "Пин",
    aliases: tuple[str, ...] = ("пингвин",),
) -> CharacterProfile:
    return CharacterProfile(
        entity_type=EntityType.CHARACTER,
        id=record_id,
        name=name,
        aliases=aliases,
        canon_variants=("classic",),
        source_refs=(source_ref(),),
        species="пингвин",
        age_group=AgeGroup.ADULT,
        traits=("изобретательный",),
        speech_style=SpeechStyle(
            register="разговорный",
            markers=("акцент",),
            constraints=("разборчиво",),
        ),
    )


def test_models_are_strict_and_frozen() -> None:
    context = SystemContext(version="1", prompt="Правила")

    with pytest.raises(ValidationError):
        SystemContext(version="1", prompt="Правила", extra_field="forbidden")
    with pytest.raises(ValidationError):
        SystemContext(version=" ", prompt="Правила")
    with pytest.raises(ValidationError):
        context.version = "2"


@pytest.mark.parametrize(
    "locator",
    ["series_15.md:42", "episode-15:04:32", "episode-15:01:04:32"],
)
def test_source_locator_accepts_supported_formats(locator: str) -> None:
    assert source_ref(locator).locator == locator


@pytest.mark.parametrize(
    "locator",
    ["series_15.md", "series_15.md:0", "episode:4:72", "bad locator:42"],
)
def test_source_locator_rejects_other_formats(locator: str) -> None:
    with pytest.raises(ValidationError):
        source_ref(locator)


def test_profile_union_round_trips_as_json() -> None:
    profile = character()
    result: KnowledgeLookupResult = KnowledgeFound(entity=profile)

    decoded = TypeAdapter(KnowledgeLookupResult).validate_json(result.model_dump_json())

    assert decoded == result


def test_closed_enums_reject_unknown_values() -> None:
    data = character().model_dump()
    data["age_group"] = "timeless"

    with pytest.raises(ValidationError):
        CharacterProfile.model_validate(data)


def test_catalog_accepts_all_three_profile_types() -> None:
    pin = character()
    home = LocationProfile(
        entity_type=EntityType.LOCATION,
        id="pin_house",
        name="Дом Пина",
        aliases=("мастерская",),
        canon_variants=("classic",),
        source_refs=(source_ref(),),
        description="Дом и мастерская Пина.",
        resident_ids=(pin.id,),
    )
    plane = ArtifactProfile(
        entity_type=EntityType.ARTIFACT,
        id="pin_plane",
        name="Пинолёт",
        aliases=("самолет пина",),
        canon_variants=("classic",),
        source_refs=(source_ref("episode-15:04:32"),),
        artifact_type="летательный аппарат",
        description="Изобретение Пина.",
        capabilities=("летать",),
        limitations=("нуждается в ремонте",),
        creator_ids=(pin.id,),
    )

    catalog = KnowledgeCatalog(schema_version="1", records=(pin, home, plane))

    assert [record.entity_type for record in catalog.records] == [
        EntityType.CHARACTER,
        EntityType.LOCATION,
        EntityType.ARTIFACT,
    ]


def test_catalog_rejects_duplicate_id_within_entity_type() -> None:
    with pytest.raises(ValidationError, match="duplicate knowledge id"):
        KnowledgeCatalog(
            schema_version="1",
            records=(character(), character(aliases=("инженер",))),
        )


def test_catalog_rejects_globally_conflicting_normalized_aliases() -> None:
    first = character(aliases=("Ёж",))
    second = character(record_id="losyash", name="Лосяш", aliases=("еж",))

    with pytest.raises(ValidationError, match="duplicate normalized alias"):
        KnowledgeCatalog(schema_version="1", records=(first, second))


def test_catalog_rejects_dangling_resident_and_creator_references() -> None:
    location = LocationProfile(
        entity_type=EntityType.LOCATION,
        id="empty_house",
        name="Дом",
        aliases=(),
        canon_variants=("classic",),
        source_refs=(source_ref(),),
        description="Дом.",
        resident_ids=("missing",),
    )

    with pytest.raises(ValidationError, match="unknown character id"):
        KnowledgeCatalog(schema_version="1", records=(location,))


def test_lookup_result_statuses_are_discriminated() -> None:
    found = KnowledgeFound(entity=character())
    missing = KnowledgeNotFound(
        entity_type=EntityType.CHARACTER,
        key="unknown",
        canon_variants=(),
    )
    ambiguous = KnowledgeAmbiguous(
        entity_type=EntityType.CHARACTER,
        key="пин",
        canon_variants=(),
        candidates=(),
    )

    adapter = TypeAdapter(KnowledgeLookupResult)
    assert adapter.validate_python(found).status == "found"
    assert adapter.validate_python(missing).status == "not_found"
    assert adapter.validate_python(ambiguous).status == "ambiguous"
