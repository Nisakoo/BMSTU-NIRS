import asyncio
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from knowledge_database import reset_database
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.db import DatabaseConfig, create_engine
from smeshariki_ai.db.migrate import downgrade, upgrade
from smeshariki_ai.rag import tables
from smeshariki_ai.rag.models import (
    AgeGroup,
    InteractionType,
    RelationshipType,
    WorkKind,
)


def only_rag_tables(name: str | None, type_: str, parent_names: Any) -> bool:
    return type_ != "table" or bool(name and name.startswith("rag_"))


async def rag_table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'rag\\_%'")
        )
    return {row.tablename for row in rows}


async def seed(engine: AsyncEngine) -> None:
    """A continuity, a series with one episode and two of its characters."""

    async with engine.begin() as connection:
        await connection.execute(
            insert(tables.continuities).values(id="classic", name="Классика")
        )
        await connection.execute(
            insert(tables.works).values(
                id="series", title="Сериал", kind="series", continuity_id="classic"
            )
        )
        await connection.execute(
            insert(tables.episodes).values(
                id="e1", work_id="series", number=1, title="Серия"
            )
        )
        await connection.execute(
            insert(tables.characters),
            [{"id": "krosh", "species": "кролик"}, {"id": "ezhik", "species": "ёж"}],
        )
        await connection.execute(
            insert(tables.character_versions),
            [
                {
                    "character_id": character,
                    "position": 0,
                    "age_group": "child",
                    "traits": ["весёлый"],
                    "speech_register": "разговорный",
                }
                for character in ("krosh", "ezhik")
            ],
        )
        await connection.execute(
            insert(tables.character_version_continuities),
            [
                {
                    "character_id": character,
                    "version_position": 0,
                    "position": 0,
                    "continuity_id": "classic",
                }
                for character in ("krosh", "ezhik")
            ],
        )
        await connection.execute(
            insert(tables.episode_characters),
            [
                {"episode_id": "e1", "position": 0, "character_id": "krosh"},
                {"episode_id": "e1", "position": 1, "character_id": "ezhik"},
            ],
        )


async def execute(engine: AsyncEngine, statement: Any, values: Any = None) -> None:
    async with engine.begin() as connection:
        await connection.execute(statement, values)


async def test_schema_matches_table_description(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        differences = await connection.run_sync(
            lambda sync: compare_metadata(
                MigrationContext.configure(
                    sync, opts={"include_name": only_rag_tables}
                ),
                tables.metadata,
            )
        )

    assert differences == []
    assert len(await rag_table_names(engine)) == 23


async def test_downgrade_removes_tables_and_upgrade_restores_them(
    engine: AsyncEngine, database_config: DatabaseConfig
) -> None:
    await asyncio.to_thread(downgrade, create_engine(database_config), "0002")
    assert await rag_table_names(engine) == set()

    await asyncio.to_thread(upgrade, create_engine(database_config))
    assert len(await rag_table_names(engine)) == 23


async def test_public_schema_reset_of_other_modules_is_compatible(
    database_config: DatabaseConfig,
) -> None:
    await reset_database(database_config)
    await reset_database(database_config)


@pytest.mark.parametrize(
    ("table", "values"),
    [
        (tables.continuities, {"id": "Bad-Id", "name": "Плохой"}),
        (tables.continuities, {"id": "movies", "name": "  "}),
        (
            tables.works,
            {"id": "w", "title": "Т", "kind": "show", "continuity_id": "classic"},
        ),
        (
            tables.episodes,
            {"id": "e2", "work_id": "series", "number": 0, "title": "Т"},
        ),
        (
            tables.episodes,
            {"id": "e2", "work_id": "series", "season": 0, "number": 2, "title": "Т"},
        ),
        (
            tables.episodes,
            {"id": "e2", "work_id": "series", "number": 1, "title": "Повтор"},
        ),
        (tables.characters, {"id": "pin", "species": "пингвин", "sources": {}}),
        (
            tables.character_names,
            {
                "character_id": "ezhik",
                "position": 0,
                "value": "Крош",
                "normalized": "крош",
            },
        ),
        (
            tables.character_version_continuities,
            {
                "character_id": "krosh",
                "version_position": 0,
                "position": 1,
                "continuity_id": "classic",
            },
        ),
        (
            tables.episode_interactions,
            {
                "episode_id": "e1",
                "position": 0,
                "from_character_id": "krosh",
                "to_character_id": "sovunya",
                "type": "conflict",
                "description": "Спор",
            },
        ),
        (
            tables.episode_interactions,
            {
                "episode_id": "e1",
                "position": 0,
                "from_character_id": "krosh",
                "to_character_id": "krosh",
                "type": "conflict",
                "description": "Спор",
            },
        ),
        (
            tables.relationships,
            {
                "character_id": "krosh",
                "position": 0,
                "to_character_id": "krosh",
                "type": "friendship",
            },
        ),
    ],
)
async def test_constraints_reject_invalid_rows(
    engine: AsyncEngine, table: Any, values: dict[str, Any]
) -> None:
    await seed(engine)
    await execute(
        engine,
        insert(tables.character_names).values(
            character_id="krosh", position=0, value="Крош", normalized="крош"
        ),
    )

    with pytest.raises(IntegrityError):
        await execute(engine, insert(table).values(**values))


async def test_relationship_continuity_must_be_in_owner_versions(
    engine: AsyncEngine,
) -> None:
    await seed(engine)
    await execute(
        engine, insert(tables.continuities).values(id="movies", name="Фильмы")
    )
    await execute(
        engine,
        insert(tables.relationships).values(
            character_id="krosh", position=0, to_character_id="ezhik", type="mentor"
        ),
    )

    with pytest.raises(IntegrityError):
        await execute(
            engine,
            insert(tables.relationship_continuities).values(
                character_id="krosh",
                relationship_position=0,
                position=0,
                continuity_id="movies",
            ),
        )


async def test_references_between_aggregates_restrict_deletion(
    engine: AsyncEngine,
) -> None:
    await seed(engine)

    with pytest.raises(IntegrityError):
        await execute(
            engine, delete(tables.characters).where(tables.characters.c.id == "krosh")
        )


async def test_deleting_a_root_cascades_inside_its_aggregate(
    engine: AsyncEngine,
) -> None:
    await seed(engine)
    await execute(
        engine,
        insert(tables.episode_interactions).values(
            episode_id="e1",
            position=0,
            from_character_id="krosh",
            to_character_id="ezhik",
            type="support",
            description="Помог.",
        ),
    )

    await execute(engine, delete(tables.episodes).where(tables.episodes.c.id == "e1"))

    async with engine.connect() as connection:
        for table in (tables.episode_characters, tables.episode_interactions):
            count = await connection.scalar(select(func.count()).select_from(table))
            assert count == 0
        assert (
            await connection.scalar(select(func.count()).select_from(tables.characters))
            == 2
        )


async def test_database_accepts_every_registry_value(engine: AsyncEngine) -> None:
    await seed(engine)
    async with engine.begin() as connection:
        await connection.execute(
            insert(tables.works),
            [
                {
                    "id": f"work_{kind}",
                    "title": "Т",
                    "kind": kind,
                    "continuity_id": "classic",
                }
                for kind in WorkKind
            ],
        )
        await connection.execute(
            insert(tables.character_versions),
            [
                {
                    "character_id": "krosh",
                    "position": position,
                    "age_group": group,
                    "traits": ["весёлый"],
                    "speech_register": "разговорный",
                }
                for position, group in enumerate(AgeGroup, start=1)
            ],
        )
        await connection.execute(
            insert(tables.relationships),
            [
                {
                    "character_id": "krosh",
                    "position": position,
                    "to_character_id": "ezhik",
                    "type": kind,
                }
                for position, kind in enumerate(RelationshipType)
            ],
        )
        await connection.execute(
            insert(tables.episode_interactions),
            [
                {
                    "episode_id": "e1",
                    "position": position,
                    "from_character_id": "krosh",
                    "to_character_id": "ezhik",
                    "type": kind,
                    "description": "Ситуация.",
                }
                for position, kind in enumerate(InteractionType)
            ],
        )


async def test_revision_number_is_unique_per_entity(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        load_id = await connection.scalar(
            insert(tables.loads)
            .values(started_at=func.now())
            .returning(tables.loads.c.id)
        )
    revision = {
        "load_id": load_id,
        "entity_type": "character",
        "entity_id": "krosh",
        "revision": 1,
        "operation": "create",
        "payload": {"id": "krosh"},
    }
    await execute(engine, insert(tables.revisions).values(**revision))

    with pytest.raises(IntegrityError):
        await execute(engine, insert(tables.revisions).values(**revision))
