"""Database reset shared by the RAG integration tests.

The database is reset the same way as in the tests of other modules: the
``public`` schema is recreated and every migration is applied from scratch.
"""

import asyncio

from sqlalchemy import text

from smeshariki_ai.db import DatabaseConfig, create_engine
from smeshariki_ai.db.migrate import upgrade


async def reset_database(config: DatabaseConfig) -> None:
    engine = create_engine(config)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()
    # Alembic's async env runs its own event loop.
    await asyncio.to_thread(upgrade, create_engine(config))
