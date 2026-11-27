"""Add pgvector embeddings for the lore chunks.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE rag_lore_embeddings (
            chunk_id BIGINT PRIMARY KEY
                REFERENCES rag_lore_chunks (id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            embedding vector(384) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT rag_lore_embeddings_model_not_blank
                CHECK (btrim(model) <> '')
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE rag_lore_embeddings")
