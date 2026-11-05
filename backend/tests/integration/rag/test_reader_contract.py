"""One lookup contract for every ``KnowledgeReader`` implementation.

The in-memory store runs everywhere; the PostgreSQL store needs
``TEST_DATABASE_URL`` and is skipped without it.
"""

import os
from collections.abc import AsyncIterator

import pytest
from knowledge_database import reset_database
from test_store_contract import save, universe, with_pin_code

from smeshariki_ai.db import DatabaseConfig, create_engine
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import (
    EntityType,
    Episode,
    KnowledgeSet,
    Location,
    entities_of,
    normalize_name,
)
from smeshariki_ai.rag.ports import FoundKnowledge
from smeshariki_ai.rag.postgres import PostgresKnowledgeStore

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
KNOWLEDGE = with_pin_code(universe())

Store = InMemoryKnowledgeStore | PostgresKnowledgeStore


@pytest.fixture(params=["memory", "postgres"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[Store]:
    if request.param == "memory":
        yield InMemoryKnowledgeStore()
        return
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    config = DatabaseConfig(url=DATABASE_URL)
    await reset_database(config)
    engine = create_engine(config)
    try:
        yield PostgresKnowledgeStore(engine)
    finally:
        await engine.dispose()


@pytest.fixture
async def loaded(store: Store) -> Store:
    await save(store, entities_of(KNOWLEDGE))
    return store


def ids(found: FoundKnowledge) -> dict[str, list[str]]:
    return {
        field: [entity.id for entity in getattr(found.entities, field)]
        for field in ("characters", "locations", "artifacts", "episodes")
        if getattr(found.entities, field)
    }


async def test_empty_store_finds_nothing_and_has_no_knowledge(store: Store) -> None:
    assert await store.find("крош") == FoundKnowledge()
    assert await store.has_knowledge() is False


async def test_completed_load_means_knowledge(loaded: Store) -> None:
    assert await loaded.has_knowledge() is True


@pytest.mark.parametrize("query", ["Крош", "  КРОШ ", "Непоседа", "кролик", "krosh"])
async def test_character_is_found_by_name_alias_and_id(
    loaded: Store, query: str
) -> None:
    found = await loaded.find(normalize_name(query))

    assert ids(found) == {"characters": ["krosh"]}
    assert found.entities.characters == tuple(
        c for c in KNOWLEDGE.characters if c.id == "krosh"
    )


async def test_yo_and_e_give_the_same_key(loaded: Store) -> None:
    assert ids(await loaded.find(normalize_name("ежик"))) == {"characters": ["ezhik"]}
    assert ids(await loaded.find(normalize_name("Самолет"))) == {"artifacts": ["plane"]}


async def test_names_of_character_references(loaded: Store) -> None:
    found = await loaded.find("krosh")

    assert found.names == {
        EntityType.CONTINUITY: {
            "classic": "Классика",
            "movies": "Фильмы",
            "pin_code": "Пин-код",
        },
        EntityType.CHARACTER: {"ezhik": "Ёжик"},
    }


async def test_location_and_artifact_with_their_references(loaded: Store) -> None:
    location = await loaded.find(normalize_name("Домик"))
    artifact = await loaded.find("plane")

    assert location.entities.locations == KNOWLEDGE.locations
    assert location.names == {
        EntityType.CONTINUITY: {"classic": "Классика"},
        EntityType.CHARACTER: {"krosh": "Крош"},
    }
    assert artifact.entities.artifacts == KNOWLEDGE.artifacts
    assert artifact.names[EntityType.CHARACTER] == {"ezhik": "Ёжик"}


async def test_episode_is_found_by_title_with_its_work(loaded: Store) -> None:
    found = await loaded.find(normalize_name("СЕРИЯ"))

    assert ids(found) == {"episodes": ["e1"]}
    assert [work.id for work in found.entities.works] == ["series"]
    assert found.names == {
        EntityType.CONTINUITY: {"classic": "Классика"},
        EntityType.WORK: {"series": "Сериал"},
        EntityType.CHARACTER: {"krosh": "Крош", "ezhik": "Ёжик"},
        EntityType.LOCATION: {"house": "Дом"},
        EntityType.ARTIFACT: {"plane": "Самолёт"},
    }


async def test_works_and_continuities_are_not_looked_up(loaded: Store) -> None:
    # The film work and its only episode share the title «Фильм».
    found = await loaded.find(normalize_name("Фильм"))

    assert ids(found) == {"episodes": ["film_main"]}
    assert await loaded.find("classic") == FoundKnowledge()


async def test_one_name_of_several_types_and_episodes(loaded: Store) -> None:
    namesake = Location.model_validate(
        {
            "id": "krosh_hill",
            "name": "Крош",
            "description": "Холм.",
            "continuities": ["classic"],
        }
    )
    repeat = Episode.model_validate(
        {"id": "e2", "work": "series", "number": 2, "title": "Крош"}
    )
    other = Episode.model_validate(
        {"id": "e0", "work": "film", "number": 2, "title": " крош"}
    )
    await save(loaded, [namesake, repeat, other])

    found = await loaded.find(normalize_name("Крош"))

    assert ids(found) == {
        "characters": ["krosh"],
        "locations": ["krosh_hill"],
        "episodes": ["e0", "e2"],
    }
    assert [work.id for work in found.entities.works] == ["film", "series"]


async def test_unknown_key_finds_nothing(loaded: Store) -> None:
    assert await loaded.find(normalize_name("Бармалей")) == FoundKnowledge(
        entities=KnowledgeSet(), names={}
    )
