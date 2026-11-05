"""Add the normalized search key of episode titles.

The key is computed by ``normalize_name`` in Python: SQL ``lower()`` neither
case-folds nor replaces "ё", so existing rows are filled row by row.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from smeshariki_ai.rag.models import normalize_name

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_episodes = sa.table(
    "rag_episodes",
    sa.column("id", sa.Text()),
    sa.column("title", sa.Text()),
    sa.column("normalized_title", sa.Text()),
)


def upgrade() -> None:
    op.add_column(
        "rag_episodes", sa.Column("normalized_title", sa.Text(), nullable=True)
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(_episodes.c.id, _episodes.c.title)).all()
    if rows:
        connection.execute(
            sa.update(_episodes)
            .where(_episodes.c.id == sa.bindparam("episode_id"))
            .values(normalized_title=sa.bindparam("key")),
            [{"episode_id": id_, "key": normalize_name(title)} for id_, title in rows],
        )
    op.alter_column("rag_episodes", "normalized_title", nullable=False)
    op.create_check_constraint(
        "rag_episodes_normalized_title_not_blank",
        "rag_episodes",
        "btrim(normalized_title) <> ''",
    )
    op.create_index(
        "rag_episodes_normalized_title_idx", "rag_episodes", ["normalized_title"]
    )


def downgrade() -> None:
    op.drop_index("rag_episodes_normalized_title_idx", table_name="rag_episodes")
    op.drop_column("rag_episodes", "normalized_title")
