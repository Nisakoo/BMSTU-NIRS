import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from smeshariki_ai.db import DatabaseConfig, create_engine
from smeshariki_ai.db.migrate import downgrade
from smeshariki_ai.rag import tables
from smeshariki_ai.rag.models import Character, Continuity, KnowledgeEntity
from smeshariki_ai.rag.ports import (
    EntityChange,
    KnowledgeDataInvalidError,
    KnowledgeSchemaNotReadyError,
    KnowledgeStoreUnavailableError,
    LoadSummary,
)
from smeshariki_ai.rag.postgres import PostgresKnowledgeStore
from smeshariki_ai.rag.services import load_package

STARTED = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def character(index: int) -> Character:
    return Character.model_validate(
        {
            "id": f"hero_{index}",
            "name": f"Герой {index}",
            "aliases": [f"Алиас {index}"],
            "species": "кролик",
            "versions": [
                {
                    "continuities": ["classic"],
                    "age_group": "child",
                    "traits": ["весёлый"],
                    "speech_style": {"register": "разговорный"},
                }
            ],
            "relationships": [
                {
                    "to": f"hero_{(index + 1) % 1000}",
                    "type": "friendship",
                    "continuities": ["classic"],
                }
            ]
            if index
            else [],
        }
    )


@contextmanager
def counted_queries(engine: AsyncEngine) -> Iterator[list[str]]:
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


async def save(
    store: PostgresKnowledgeStore,
    entities: list[KnowledgeEntity],
    operation: str = "create",
) -> None:
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(STARTED)
        await transaction.save(
            load_id,
            [EntityChange(operation=operation, entity=entity) for entity in entities],
        )
        await transaction.finish_load(
            load_id,
            LoadSummary(finished_at=STARTED, duration_ms=0, entity_count=0, counts={}),
        )


def heroes(count: int) -> list[KnowledgeEntity]:
    # Each hero befriends the next one, so the last one closes nothing.
    items: list[KnowledgeEntity] = [character(0)]
    for index in range(1, count):
        hero = character(index)
        target = f"hero_{index - 1}"
        relationship = hero.relationships[0].model_copy(update={"to": target})
        items.append(hero.model_copy(update={"relationships": (relationship,)}))
    return items


async def test_query_count_does_not_grow_with_entities(engine: AsyncEngine) -> None:
    store = PostgresKnowledgeStore(engine)
    await save(store, [Continuity(id="classic", name="Классика")])
    counts = []
    # Both sizes have relationships, so the same tables receive rows.
    for size in (2, 50):
        await save(store, heroes(size))
        with counted_queries(engine) as statements:
            await save(store, heroes(size), "update")
            async with store.transaction() as transaction:
                await transaction.read_all()
        counts.append(len(statements))

    assert counts[0] == counts[1]


async def test_updated_at_changes_only_for_saved_entities(
    engine: AsyncEngine,
) -> None:
    store = PostgresKnowledgeStore(engine)
    classic = Continuity(id="classic", name="Классика")
    movies = Continuity(id="movies", name="Фильмы")
    await save(store, [classic, movies])

    async def stamps() -> dict[str, tuple[datetime, datetime]]:
        async with engine.connect() as connection:
            rows = await connection.execute(
                select(
                    tables.continuities.c.id,
                    tables.continuities.c.created_at,
                    tables.continuities.c.updated_at,
                )
            )
            return {row.id: (row.created_at, row.updated_at) for row in rows}

    before = await stamps()
    await asyncio.sleep(0.01)
    await save(store, [classic.model_copy(update={"name": "Классика 2"})], "update")
    after = await stamps()

    assert after["movies"] == before["movies"]
    assert after["classic"][0] == before["classic"][0]
    assert after["classic"][1] > before["classic"][1]


async def test_unreachable_database_is_unavailable() -> None:
    # A short connect timeout keeps the test fast where closed ports drop packets.
    engine = create_async_engine(
        "postgresql+asyncpg://test:test@127.0.0.1:1/test",
        connect_args={"timeout": 1},
    )
    try:
        with pytest.raises(KnowledgeStoreUnavailableError) as error:
            async with PostgresKnowledgeStore(engine).transaction():
                pass
    finally:
        await engine.dispose()

    assert "127.0.0.1" not in str(error.value)


async def test_missing_migration_means_schema_not_ready(
    engine: AsyncEngine, database_config: DatabaseConfig
) -> None:
    await asyncio.to_thread(downgrade, create_engine(database_config), "0002")

    with pytest.raises(KnowledgeSchemaNotReadyError):
        async with PostgresKnowledgeStore(engine).transaction() as transaction:
            await transaction.read_all()


async def test_load_package_end_to_end(engine: AsyncEngine, tmp_path) -> None:
    store = PostgresKnowledgeStore(engine)
    package = tmp_path / "package"
    for relative, body in {
        "package.yaml": "format_version: 1\n",
        "continuities/classic.yaml": "id: classic\nname: Классика\n",
        "characters/krosh.yaml": (
            "id: krosh\nname: Крош\nspecies: кролик\nversions:\n"
            "  - continuities: [classic]\n    age_group: child\n"
            "    traits: [весёлый]\n    speech_style:\n      register: разговорный\n"
        ),
    }.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    first = await load_package(package, store)
    second = await load_package(package, store)

    assert first.loaded and first.counts["characters"].added == 1
    assert second.loaded and second.counts["characters"].unchanged == 1
    async with engine.connect() as connection:
        loads = await connection.scalar(select(func.count()).select_from(tables.loads))
        revisions = await connection.scalar(
            select(func.count()).select_from(tables.revisions)
        )
    assert (loads, revisions) == (2, 2)


async def test_corrupted_rows_are_reported_as_invalid_data(
    engine: AsyncEngine,
) -> None:
    # A character root without its name row does not form a valid entity.
    async with engine.begin() as connection:
        await connection.execute(
            insert(tables.characters).values(id="ghost", species="призрак")
        )

    with pytest.raises(KnowledgeDataInvalidError):
        async with PostgresKnowledgeStore(engine).transaction() as transaction:
            await transaction.read_all()


async def test_lookup_query_count_does_not_grow_with_entities(
    engine: AsyncEngine,
) -> None:
    store = PostgresKnowledgeStore(engine)
    await save(store, [Continuity(id="classic", name="Классика")])
    counts = []
    for size in (2, 50):
        await save(store, heroes(size))
        with counted_queries(engine) as statements:
            found = await store.find("hero_1")
            await store.has_knowledge()
        assert [hero.id for hero in found.entities.characters] == ["hero_1"]
        counts.append(len(statements))

    assert counts[0] == counts[1]


async def test_lookup_reads_in_a_read_only_snapshot(engine: AsyncEngine) -> None:
    store = PostgresKnowledgeStore(engine)
    await save(store, [Continuity(id="classic", name="Классика"), *heroes(2)])

    with counted_queries(engine) as statements:
        await store.find("hero_0")

    assert statements[0] == (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    )
    assert not any("pg_advisory" in statement for statement in statements)


async def test_lookup_without_tables_means_schema_not_ready(
    engine: AsyncEngine, database_config: DatabaseConfig
) -> None:
    await asyncio.to_thread(downgrade, create_engine(database_config), "0002")
    store = PostgresKnowledgeStore(engine)

    with pytest.raises(KnowledgeSchemaNotReadyError):
        await store.find("krosh")
    with pytest.raises(KnowledgeSchemaNotReadyError):
        await store.has_knowledge()


async def test_lookup_on_unreachable_database_is_unavailable() -> None:
    engine = create_async_engine(
        "postgresql+asyncpg://test:test@127.0.0.1:1/test",
        connect_args={"timeout": 1},
    )
    try:
        with pytest.raises(KnowledgeStoreUnavailableError) as error:
            await PostgresKnowledgeStore(engine).find("krosh")
    finally:
        await engine.dispose()

    assert "127.0.0.1" not in str(error.value)


async def test_lookup_of_corrupted_rows_is_invalid_data(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(tables.characters).values(id="ghost", species="призрак")
        )

    with pytest.raises(KnowledgeDataInvalidError):
        await PostgresKnowledgeStore(engine).find("ghost")
