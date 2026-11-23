from __future__ import annotations

import logging

import pytest
from test_lookup import BASE, load

from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import Artifact, Character
from smeshariki_ai.rag.story_canon import (
    NO_VERSION_MESSAGE,
    NOT_FOUND_MESSAGE,
    UNAVAILABLE_MESSAGE,
    StoryCanonLookup,
)

BARASH = Character.model_validate(
    {
        "id": "barash",
        "name": "Бараш",
        "species": "баран",
        "versions": [
            {
                "continuities": ["classic"],
                "age_group": "teen",
                "traits": ["мечтательный"],
                "speech_style": {"register": "поэтический"},
            }
        ],
    }
)
KROSH_WITH_BENCH = Character.model_validate(
    {
        "id": "krosh",
        "name": "Крош",
        "species": "кролик",
        "versions": [
            {
                "continuities": ["classic"],
                "age_group": "child",
                "traits": ["весёлый", "нетерпеливый"],
                "speech_style": {
                    "register": "разговорный",
                    "markers": ["Ёлки-иголки!"],
                    "constraints": ["не кричит"],
                },
                "catchphrases": ["Ёлки-иголки!"],
            }
        ],
        "relationships": [
            {
                "to": "barash",
                "type": "friendship",
                "continuities": ["classic"],
                "description": "Крош дорожит Барашем больше, чем своей скамейкой.",
            }
        ],
    }
)
YOZHIK_WITH_HOBBIES = Character.model_validate(
    {
        "id": "yozhik",
        "name": "Ёжик",
        "species": "ёж",
        "versions": [
            {
                "continuities": ["classic"],
                "age_group": "child",
                "traits": [
                    "застенчивый",
                    "коллекционирует фантики",
                    "сентиментальный, дорожит старыми вещами",
                ],
                "speech_style": {"register": "тихий"},
            }
        ],
    }
)
WRAPPERS = Artifact.model_validate(
    {
        "id": "candy_wrapper_collection",
        "name": "Коллекция фантиков",
        "artifact_type": "коллекция",
        "description": "Редкие фантики.",
        "continuities": ["classic"],
    }
)
OLD_UMBRELLA = Artifact.model_validate(
    {
        "id": "old_umbrella",
        "name": "Старый зонтик Бараша",
        "artifact_type": "зонтик",
        "description": "Памятная вещь.",
        "continuities": ["classic"],
    }
)


@pytest.fixture
async def store() -> InMemoryKnowledgeStore:
    value = InMemoryKnowledgeStore()
    await load(value, BASE)
    await load(
        value,
        [BARASH, KROSH_WITH_BENCH, YOZHIK_WITH_HOBBIES, WRAPPERS, OLD_UMBRELLA],
    )
    return value


async def test_story_profile_has_no_free_text_or_artifacts(
    store: InMemoryKnowledgeStore,
) -> None:
    result = await StoryCanonLookup(store).lookup(["Крош"])

    assert result.status == "found"
    [character] = result.characters
    payload = result.model_dump(mode="json", by_alias=True)
    text = str(payload)

    assert character.name == "Крош"
    assert character.age_group.value == "child"
    assert character.traits == ("весёлый", "нетерпеливый")
    assert character.speech_style.register_ == "разговорный"
    assert character.relationships[0].to == "Бараш"
    assert character.relationships[0].type.value == "friendship"
    assert "скамейк" not in text
    assert "description" not in text
    assert "sources" not in text
    assert "locations" not in text
    assert "artifacts" not in text


async def test_traits_that_name_an_artifact_are_dropped(
    store: InMemoryKnowledgeStore,
) -> None:
    result = await StoryCanonLookup(store).lookup(["Ёжик"])

    assert result.status == "found"
    [character] = result.characters
    assert "коллекционирует фантики" not in character.traits
    assert "сентиментальный, дорожит старыми вещами" in character.traits
    assert "фантик" not in str(result.model_dump(mode="json", by_alias=True))


async def test_multiple_names_are_deduplicated(
    store: InMemoryKnowledgeStore,
) -> None:
    result = await StoryCanonLookup(store).lookup(["Крош", "Пин", "Крош"])

    assert result.status == "found"
    assert [character.id for character in result.characters] == ["krosh", "pin"]


async def test_missing_continuity_does_not_fall_back(
    store: InMemoryKnowledgeStore,
) -> None:
    result = await StoryCanonLookup(store).lookup(["Крош"], continuity="movies")

    assert result.status == "not_found"
    assert result.characters == ()
    assert result.message == NO_VERSION_MESSAGE


async def test_unknown_name_is_not_found(store: InMemoryKnowledgeStore) -> None:
    result = await StoryCanonLookup(store).lookup(["Бармалей"])

    assert result.status == "not_found"
    assert result.characters == ()
    assert result.message == NOT_FOUND_MESSAGE


async def test_empty_store_is_unavailable() -> None:
    store = InMemoryKnowledgeStore()

    result = await StoryCanonLookup(store).lookup(["Крош"])

    assert result.status == "unavailable"
    assert result.message == UNAVAILABLE_MESSAGE


async def test_invalid_names_are_rejected_before_reading(
    store: InMemoryKnowledgeStore,
) -> None:
    lookup = StoryCanonLookup(store)

    with pytest.raises(ValueError):
        await lookup.lookup([])
    with pytest.raises(ValueError):
        await lookup.lookup(["Крош", "Пин", "Ёжик", "Нюша"])


async def test_logs_do_not_contain_character_names(
    store: InMemoryKnowledgeStore, caplog
) -> None:
    caplog.set_level(logging.INFO)

    await StoryCanonLookup(store).lookup(["Крош"])

    assert "rag.story_canon.completed" in caplog.text
    assert "Крош" not in caplog.text
    assert "скамейк" not in caplog.text


def test_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        StoryCanonLookup(InMemoryKnowledgeStore(), limit=0)
