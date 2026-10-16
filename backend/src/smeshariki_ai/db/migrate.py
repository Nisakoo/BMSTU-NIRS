"""Apply database migrations: ``python -m smeshariki_ai.db.migrate``."""

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.db.config import DatabaseConfig
from smeshariki_ai.db.engine import create_engine

SCRIPT_LOCATION = "smeshariki_ai.db:migrations"


def upgrade(engine: AsyncEngine, revision: str = "head") -> None:
    """Upgrade the database; the engine is disposed afterwards."""

    alembic_config = AlembicConfig()
    alembic_config.set_main_option("script_location", SCRIPT_LOCATION)
    alembic_config.attributes["engine"] = engine
    command.upgrade(alembic_config, revision)


def main(config: DatabaseConfig) -> None:
    upgrade(create_engine(config))


if __name__ == "__main__":
    from smeshariki_ai.config import load_config

    main(load_config().database)
