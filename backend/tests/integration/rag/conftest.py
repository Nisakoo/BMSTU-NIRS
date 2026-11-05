"""PostgreSQL fixtures of the RAG integration tests."""

import os
from collections.abc import AsyncIterator

import pytest
from knowledge_database import reset_database
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.db import DatabaseConfig, create_engine

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def database_config() -> DatabaseConfig:
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    return DatabaseConfig(url=DATABASE_URL)


@pytest.fixture
async def engine(database_config: DatabaseConfig) -> AsyncIterator[AsyncEngine]:
    await reset_database(database_config)
    value = create_engine(database_config)
    try:
        yield value
    finally:
        await value.dispose()
