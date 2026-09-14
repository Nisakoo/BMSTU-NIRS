from __future__ import annotations

import json

import pytest

from smeshariki_ai.rag.in_memory import InMemoryStructuredKnowledgeStore
from smeshariki_ai.rag.models import (
    AgeGroup,
    CharacterProfile,
    EntityType,
    SourceRef,
    SpeechStyle,
    SystemContext,
)
from smeshariki_ai.rag.service import StructuredKnowledgeService


def profile(
    record_id: str,
    *,
    name: str = "Пин",
    aliases: tuple[str, ...],
    canon_variants: tuple[str, ...],
) -> CharacterProfile:
    return CharacterProfile(
        entity_type=EntityType.CHARACTER,
        id=record_id,
        name=name,
        aliases=aliases,
        canon_variants=canon_variants,
        source_refs=(
            SourceRef(
                source_id=record_id,
                source_version="1",
                locator="characters.json:1",
                checksum="sha256:fixture",
            ),
        ),
        species="пингвин" if name == "Пин" else "ёж",
        age_group=AgeGroup.ADULT if name == "Пин" else AgeGroup.CHILD,
        traits=("изобретательный",),
        speech_style=SpeechStyle(
            register="разговорный",
            markers=("характерный",),
            constraints=("разборчиво",),
        ),
    )


@pytest.fixture
def service() -> StructuredKnowledgeService:
    records = (
        profile(
            "pin",
            aliases=("пингвин",),
            canon_variants=("classic", "shorts"),
        ),
        profile(
            "pin_movie",
            aliases=("кинопин",),
            canon_variants=("movie",),
        ),
        profile(
            "yozhik",
            name="Ёжик",
            aliases=("Ёж",),
            canon_variants=("classic",),
        ),
    )
    store = InMemoryStructuredKnowledgeStore(
        system_context=SystemContext(version="1", prompt="Правила"),
        records=records,
    )
    return StructuredKnowledgeService(store)


@pytest.mark.parametrize("key", ["pin", "  PIN  ", "пингвин"])
def test_lookup_finds_exact_id_name_or_alias(
    service: StructuredKnowledgeService,
    key: str,
) -> None:
    result = service.lookup_knowledge(EntityType.CHARACTER, key, ("classic",))

    assert result.status == "found"
    assert result.entity.id == "pin"


def test_lookup_normalizes_yo_and_case(service: StructuredKnowledgeService) -> None:
    result = service.lookup_knowledge(EntityType.CHARACTER, "  ёЖ  ")

    assert result.status == "found"
    assert result.entity.id == "yozhik"


def test_empty_canon_filter_returns_ambiguity_in_stable_order(
    service: StructuredKnowledgeService,
) -> None:
    first = service.lookup_knowledge(EntityType.CHARACTER, "Пин")
    second = service.lookup_knowledge(EntityType.CHARACTER, "ПИН", ())

    assert first.status == "ambiguous"
    assert [candidate.id for candidate in first.candidates] == ["pin", "pin_movie"]
    assert first.model_dump_json() == second.model_dump_json()


def test_canon_filter_uses_or(service: StructuredKnowledgeService) -> None:
    result = service.lookup_knowledge(
        EntityType.CHARACTER,
        "Пин",
        ("movie", "classic"),
    )

    assert result.status == "ambiguous"
    assert [candidate.id for candidate in result.candidates] == ["pin", "pin_movie"]


def test_single_canon_variant_disambiguates(service: StructuredKnowledgeService) -> None:
    result = service.lookup_knowledge(EntityType.CHARACTER, "Пин", ("movie",))

    assert result.status == "found"
    assert result.entity.id == "pin_movie"


def test_not_found_contains_normalized_request(service: StructuredKnowledgeService) -> None:
    result = service.lookup_knowledge(
        EntityType.CHARACTER,
        "  НЕТ  ",
        (" SHORTS ", "classic", "classic"),
    )

    assert result.status == "not_found"
    assert result.key == "нет"
    assert result.canon_variants == ("classic", "shorts")


@pytest.mark.parametrize("key", ["пин!", "п  ин", "пи н"])
def test_lookup_does_not_change_punctuation_or_internal_spaces(
    service: StructuredKnowledgeService,
    key: str,
) -> None:
    assert service.lookup_knowledge(EntityType.CHARACTER, key).status == "not_found"


def test_result_has_stable_utf8_json_shape(service: StructuredKnowledgeService) -> None:
    result = service.lookup_knowledge(EntityType.CHARACTER, "Ёжик")
    payload = json.loads(result.model_dump_json())

    assert payload["status"] == "found"
    assert payload["entity"]["name"] == "Ёжик"
    assert payload["entity"]["speech_style"]["register"] == "разговорный"
