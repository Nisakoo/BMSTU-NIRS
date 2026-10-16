"""Alembic environment; the URL is passed in by ``smeshariki_ai.db.migrate``."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.db.tables import metadata


def run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(run_with_connection)
    await engine.dispose()


engine = context.config.attributes["engine"]
asyncio.run(run_online(engine))
