"""Add story voice and interests to character versions.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rag_character_versions",
        sa.Column(
            "interests",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "rag_character_versions",
        sa.Column("voice_story_role", sa.Text(), nullable=True),
    )
    op.add_column(
        "rag_character_versions",
        sa.Column(
            "voice_examples",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "rag_character_versions",
        sa.Column(
            "voice_never_says",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "rag_character_dynamics",
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("version_position", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("with_character_id", sa.Text(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.PrimaryKeyConstraint(
            "character_id",
            "version_position",
            "position",
            name="rag_character_dynamics_pkey",
        ),
        sa.ForeignKeyConstraint(
            ["character_id", "version_position"],
            [
                "rag_character_versions.character_id",
                "rag_character_versions.position",
            ],
            ondelete="CASCADE",
            name="rag_character_dynamics_version_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["with_character_id"],
            ["rag_characters.id"],
            ondelete="RESTRICT",
            name="rag_character_dynamics_with_character_id_fkey",
        ),
        sa.CheckConstraint(
            "character_id <> with_character_id",
            name="rag_character_dynamics_distinct_characters",
        ),
        sa.CheckConstraint(
            "btrim(pattern) <> ''",
            name="rag_character_dynamics_pattern_not_blank",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="rag_character_dynamics_position_not_negative",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'",
            name="rag_character_dynamics_sources_array",
        ),
    )
    op.create_index(
        "rag_character_dynamics_with_character_id_idx",
        "rag_character_dynamics",
        ["with_character_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "rag_character_dynamics_with_character_id_idx",
        table_name="rag_character_dynamics",
    )
    op.drop_table("rag_character_dynamics")
    op.drop_column("rag_character_versions", "voice_never_says")
    op.drop_column("rag_character_versions", "voice_examples")
    op.drop_column("rag_character_versions", "voice_story_role")
    op.drop_column("rag_character_versions", "interests")
