"""Add trigram indexes for knowledge name suggestions.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = (
    ("rag_character_names_normalized_trgm_idx", "rag_character_names", "normalized"),
    ("rag_location_names_normalized_trgm_idx", "rag_location_names", "normalized"),
    ("rag_artifact_names_normalized_trgm_idx", "rag_artifact_names", "normalized"),
    (
        "rag_episodes_normalized_title_trgm_idx",
        "rag_episodes",
        "normalized_title",
    ),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, column in _INDEXES:
        op.create_index(
            name,
            table,
            [column],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={column: "gin_trgm_ops"},
        )


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    # pg_trgm is shared infrastructure: do not drop the extension.
