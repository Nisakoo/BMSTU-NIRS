from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from smeshariki_ai.db.config import DatabaseConfig


def create_engine(config: DatabaseConfig) -> AsyncEngine:
    """Create a lazy engine; no connection is opened until the first query."""

    return create_async_engine(
        config.url.get_secret_value(),
        pool_size=config.pool_size,
        pool_pre_ping=True,
        # Keep SQL parameters (password hashes, token hashes) out of exceptions.
        hide_parameters=True,
    )
