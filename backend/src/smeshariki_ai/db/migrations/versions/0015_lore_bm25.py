"""Create the ``rag_lore_*`` tables of the BM25 lore search.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLUG = r"^[a-z0-9]+(_[a-z0-9]+)*$"


def upgrade() -> None:
    op.create_table(
        "rag_lore_documents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("continuity", sa.Text(), nullable=True),
        sa.Column(
            "characters",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(f"id ~ '{SLUG}'", name="rag_lore_documents_id_format"),
        sa.CheckConstraint(
            "btrim(title) <> ''", name="rag_lore_documents_title_not_blank"
        ),
        sa.CheckConstraint(
            "btrim(text) <> ''", name="rag_lore_documents_text_not_blank"
        ),
    )

    op.create_table(
        "rag_lore_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "document_id",
            sa.Text(),
            sa.ForeignKey("rag_lore_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("term_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "document_id",
            "position",
            name="rag_lore_chunks_document_position_key",
        ),
        sa.CheckConstraint(
            "position >= 0", name="rag_lore_chunks_position_non_negative"
        ),
        sa.CheckConstraint(
            "term_count >= 0", name="rag_lore_chunks_term_count_non_negative"
        ),
        sa.CheckConstraint("btrim(text) <> ''", name="rag_lore_chunks_text_not_blank"),
    )
    op.create_index(
        "rag_lore_chunks_document_id_idx",
        "rag_lore_chunks",
        ["document_id"],
    )

    op.create_table(
        "rag_lore_terms",
        sa.Column("term", sa.Text(), primary_key=True),
        sa.Column("df", sa.Integer(), nullable=False),
        sa.CheckConstraint("df >= 1", name="rag_lore_terms_df_positive"),
        sa.CheckConstraint("btrim(term) <> ''", name="rag_lore_terms_term_not_blank"),
    )

    op.create_table(
        "rag_lore_postings",
        sa.Column(
            "term",
            sa.Text(),
            primary_key=True,
        ),
        sa.Column(
            "chunk_id",
            sa.BigInteger(),
            sa.ForeignKey("rag_lore_chunks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tf", sa.Integer(), nullable=False),
        sa.CheckConstraint("tf >= 1", name="rag_lore_postings_tf_positive"),
    )
    op.create_index(
        "rag_lore_postings_term_idx",
        "rag_lore_postings",
        ["term"],
    )

    op.create_table(
        "rag_lore_stats",
        sa.Column(
            "id",
            sa.SmallInteger(),
            primary_key=True,
            server_default=sa.text("1"),
        ),
        sa.Column("n_chunks", sa.Integer(), nullable=False),
        sa.Column("avgdl", sa.Float(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name="rag_lore_stats_singleton"),
        sa.CheckConstraint(
            "n_chunks >= 0", name="rag_lore_stats_n_chunks_non_negative"
        ),
        sa.CheckConstraint("avgdl >= 0", name="rag_lore_stats_avgdl_non_negative"),
        sa.CheckConstraint("version >= 0", name="rag_lore_stats_version_non_negative"),
    )

    op.create_table(
        "rag_lore_loads",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("term_count", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "document_count IS NULL OR document_count >= 0",
            name="rag_lore_loads_document_count_non_negative",
        ),
        sa.CheckConstraint(
            "chunk_count IS NULL OR chunk_count >= 0",
            name="rag_lore_loads_chunk_count_non_negative",
        ),
        sa.CheckConstraint(
            "term_count IS NULL OR term_count >= 0",
            name="rag_lore_loads_term_count_non_negative",
        ),
    )


def downgrade() -> None:
    op.drop_table("rag_lore_loads")
    op.drop_table("rag_lore_stats")
    op.drop_index("rag_lore_postings_term_idx", table_name="rag_lore_postings")
    op.drop_table("rag_lore_postings")
    op.drop_table("rag_lore_terms")
    op.drop_index("rag_lore_chunks_document_id_idx", table_name="rag_lore_chunks")
    op.drop_table("rag_lore_chunks")
    op.drop_table("rag_lore_documents")
