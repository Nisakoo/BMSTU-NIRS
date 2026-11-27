from __future__ import annotations

import asyncio
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.db import DatabaseConfig, create_engine
from smeshariki_ai.db.migrate import downgrade, upgrade
from smeshariki_ai.rag.lore import tables


def only_lore_tables(name: str | None, type_: str, parent_names: Any) -> bool:
    # The embeddings table uses the pgvector type, which SQLAlchemy cannot
    # reflect; its shape is checked by ``test_lore_embeddings_table_shape``.
    if name == "rag_lore_embeddings":
        return False
    if isinstance(parent_names, dict) and "rag_lore_embeddings" in str(
        parent_names.values()
    ):
        return False
    return type_ != "table" or bool(name and name.startswith("rag_lore_"))


async def lore_table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE tablename LIKE 'rag\\_lore\\_%'"
            )
        )
    return {row.tablename for row in rows}


async def test_lore_schema_matches_table_description(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        differences = await connection.run_sync(
            lambda sync: compare_metadata(
                MigrationContext.configure(
                    sync, opts={"include_name": only_lore_tables}
                ),
                tables.metadata,
            )
        )

    assert differences == []
    assert await lore_table_names(engine) == {
        "rag_lore_documents",
        "rag_lore_chunks",
        "rag_lore_terms",
        "rag_lore_postings",
        "rag_lore_stats",
        "rag_lore_loads",
        "rag_lore_embeddings",
    }


async def test_lore_embeddings_table_shape(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT column_name, udt_name, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'rag_lore_embeddings' "
                "ORDER BY ordinal_position"
            )
        )
        columns = {row.column_name: (row.udt_name, row.is_nullable) for row in rows}

    assert columns == {
        "chunk_id": ("int8", "NO"),
        "model": ("text", "NO"),
        "embedding": ("vector", "NO"),
        "created_at": ("timestamptz", "NO"),
    }


async def test_lore_migration_is_reversible(
    engine: AsyncEngine, database_config: DatabaseConfig
) -> None:
    await asyncio.to_thread(downgrade, create_engine(database_config), "0012")
    assert await lore_table_names(engine) == set()

    await asyncio.to_thread(upgrade, create_engine(database_config))
    assert len(await lore_table_names(engine)) == 7
