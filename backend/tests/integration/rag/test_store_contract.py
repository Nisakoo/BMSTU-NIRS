"""One behaviour contract for every ``KnowledgeStore`` implementation.

The in-memory store runs everywhere; the PostgreSQL store needs
``TEST_DATABASE_URL`` and is skipped without it.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from knowledge_database import reset_database

from smeshariki_ai.db import DatabaseConfig, create_engine
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import (
    Artifact,
    Character,
    CharacterVersion,
    Continuity,
    EntityRef,
    EntityType,
    Episode,
    KnowledgeEntity,
    KnowledgeSet,
    Location,
    Work,
    entities_of,
)
from smeshariki_ai.rag.ports import EntityChange, KnowledgeStore, LoadSummary
from smeshariki_ai.rag.postgres import PostgresKnowledgeStore

STARTED = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
FINISHED = datetime(2026, 10, 19, 12, 0, 1, tzinfo=UTC)
KROSH = EntityRef(type=EntityType.CHARACTER, id="krosh")
DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def version(*continuities: str, traits: tuple[str, ...] = ("весёлый",)) -> dict:
    return {
        "continuities": list(continuities),
        "age_group": "child",
        "traits": list(traits),
        "speech_style": {"register": "разговорный", "markers": ["быстрая речь"]},
        "catchphrases": ["Ёлки-иголки!"],
        "sources": [{"episode": "e1", "timecode": "01:02", "note": "черта"}],
    }


def universe() -> KnowledgeSet:
    """A small universe touching every table, valid for real foreign keys."""

    return KnowledgeSet(
        continuities=(
            Continuity(id="classic", name="Классика"),
            Continuity(id="movies", name="Фильмы"),
        ),
        works=(
            Work.model_validate(
                {"id": "film", "title": "Фильм", "kind": "film", "continuity": "movies"}
            ),
            Work.model_validate(
                {
                    "id": "series",
                    "title": "Сериал",
                    "kind": "series",
                    "continuity": "classic",
                }
            ),
        ),
        characters=(
            Character.model_validate(
                {
                    "id": "ezhik",
                    "name": "Ёжик",
                    "species": "ёж",
                    "versions": [version("classic")],
                }
            ),
            Character.model_validate(
                {
                    "id": "krosh",
                    "name": "Крош",
                    "aliases": ["Кролик", "Непоседа"],
                    "species": "кролик",
                    "versions": [version("movies", "classic"), version("pin_code")],
                    "relationships": [
                        {
                            "to": "ezhik",
                            "type": "friendship",
                            "continuities": ["classic"],
                            "description": "Лучшие друзья",
                            "sources": [
                                {"document": "Справочник", "locator": "стр. 2"}
                            ],
                        }
                    ],
                    "sources": [{"document": "Справочник"}],
                }
            ),
        ),
        locations=(
            Location.model_validate(
                {
                    "id": "house",
                    "name": "Дом",
                    "aliases": ["Домик"],
                    "description": "Дом.",
                    "continuities": ["classic"],
                    "residents": ["krosh"],
                }
            ),
        ),
        artifacts=(
            Artifact.model_validate(
                {
                    "id": "plane",
                    "name": "Самолёт",
                    "artifact_type": "машина",
                    "description": "Летает.",
                    "capabilities": ["летает", "гудит"],
                    "limitations": ["ломается"],
                    "continuities": ["classic"],
                    "creators": ["ezhik"],
                }
            ),
        ),
        episodes=(
            Episode.model_validate(
                {
                    "id": "e1",
                    "work": "series",
                    "season": 1,
                    "number": 1,
                    "title": "Серия",
                    "characters": ["krosh", "ezhik"],
                    "locations": ["house"],
                    "artifacts": ["plane"],
                    "interactions": [
                        {
                            "from": "ezhik",
                            "to": "krosh",
                            "type": "support",
                            "description": "Помог.",
                            "sources": [{"episode": "e1", "timecode": "02:00"}],
                        },
                        {
                            "from": "krosh",
                            "to": "ezhik",
                            "type": "conflict",
                            "description": "Спор.",
                        },
                    ],
                }
            ),
            Episode.model_validate(
                {
                    "id": "film_main",
                    "work": "film",
                    "number": 1,
                    "title": "Фильм",
                    "characters": ["krosh"],
                }
            ),
        ),
    )


def with_pin_code(knowledge: KnowledgeSet) -> KnowledgeSet:
    return knowledge.model_copy(
        update={
            "continuities": (
                *knowledge.continuities,
                Continuity(id="pin_code", name="Пин-код"),
            )
        }
    )


def changes(
    entities: list[KnowledgeEntity], operation: str = "create"
) -> list[EntityChange]:
    return [EntityChange(operation=operation, entity=entity) for entity in entities]


async def save(
    store: KnowledgeStore, entities: list[KnowledgeEntity], operation: str = "create"
) -> int:
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(STARTED)
        await transaction.save(load_id, changes(entities, operation))
        await transaction.finish_load(
            load_id,
            LoadSummary(
                finished_at=FINISHED, duration_ms=1000, entity_count=0, report={}
            ),
        )
    return load_id


async def read_all(store: KnowledgeStore) -> KnowledgeSet:
    async with store.transaction() as transaction:
        return await transaction.read_all()


@pytest.fixture(params=["memory", "postgres"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[KnowledgeStore]:
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


async def test_empty_store_reads_an_empty_set(store: KnowledgeStore) -> None:
    assert await read_all(store) == KnowledgeSet()


async def test_saved_entities_read_back_unchanged(store: KnowledgeStore) -> None:
    knowledge = with_pin_code(universe())

    await save(store, entities_of(knowledge))

    stored = await read_all(store)
    for field in (
        "continuities",
        "works",
        "episodes",
        "characters",
        "locations",
        "artifacts",
    ):
        expected = sorted(getattr(knowledge, field), key=lambda item: item.id)
        assert list(getattr(stored, field)) == expected


async def test_saving_replaces_the_whole_aggregate(store: KnowledgeStore) -> None:
    knowledge = with_pin_code(universe())
    await save(store, entities_of(knowledge))
    krosh = next(c for c in knowledge.characters if c.id == "krosh")
    replaced = krosh.model_copy(
        update={
            "aliases": ("Попрыгун",),
            "versions": (
                CharacterVersion.model_validate(
                    version("classic", "movies", traits=("смелый",))
                ),
            ),
            "relationships": (),
        }
    )

    await save(store, [replaced], "update")

    stored = await read_all(store)
    assert next(c for c in stored.characters if c.id == "krosh") == replaced
    # Aggregates that reference Krosh are untouched.
    assert stored.episodes == tuple(sorted(knowledge.episodes, key=lambda e: e.id))
    assert stored.locations == knowledge.locations


async def test_revisions_keep_every_version_of_an_entity(
    store: KnowledgeStore,
) -> None:
    knowledge = with_pin_code(universe())
    first = await save(store, entities_of(knowledge))
    krosh = next(c for c in knowledge.characters if c.id == "krosh")
    renamed = krosh.model_copy(update={"species": "заяц"})
    second = await save(store, [renamed], "update")

    async with store.transaction() as transaction:
        history = await transaction.read_revisions(KROSH)
        missing = await transaction.read_revisions(
            EntityRef(type=EntityType.CHARACTER, id="nobody")
        )

    assert [(r.revision, r.operation, r.load_id) for r in history] == [
        (1, "create", first),
        (2, "update", second),
    ]
    assert Character.model_validate(history[0].payload) == krosh
    assert Character.model_validate(history[1].payload) == renamed
    assert history[1].payload["versions"][0]["speech_style"]["register"]
    assert missing == ()


async def test_load_is_recorded_and_completed(store: KnowledgeStore) -> None:
    summary = LoadSummary(
        finished_at=FINISHED, duration_ms=5, entity_count=2, report={"a": 1}
    )
    async with store.transaction() as transaction:
        first = await transaction.start_load(STARTED)
        await transaction.finish_load(first, summary)
    async with store.transaction() as transaction:
        second = await transaction.start_load(STARTED)
        record = await transaction.read_load(first)
        unfinished = await transaction.read_load(second)
        absent = await transaction.read_load(second + 100)

    assert second > first
    assert record is not None and record.summary == summary
    assert record.started_at == STARTED
    assert unfinished is not None and unfinished.summary is None
    assert absent is None


async def test_exception_rolls_the_transaction_back(store: KnowledgeStore) -> None:
    knowledge = universe()

    with pytest.raises(RuntimeError):
        async with store.transaction() as transaction:
            load_id = await transaction.start_load(STARTED)
            await transaction.save(load_id, changes(list(knowledge.continuities)))
            raise RuntimeError("boom")

    async with store.transaction() as transaction:
        assert await transaction.read_all() == KnowledgeSet()
        assert await transaction.read_load(load_id) is None
        assert (
            await transaction.read_revisions(
                EntityRef(type=EntityType.CONTINUITY, id="classic")
            )
            == ()
        )


async def test_transactions_are_serialized(store: KnowledgeStore) -> None:
    events: list[str] = []
    entered = asyncio.Event()

    async def first() -> None:
        async with store.transaction():
            events.append("first in")
            entered.set()
            await asyncio.sleep(0.2)
            events.append("first out")

    async def second() -> None:
        await entered.wait()
        async with store.transaction():
            events.append("second in")

    await asyncio.gather(first(), second())

    assert events == ["first in", "first out", "second in"]
