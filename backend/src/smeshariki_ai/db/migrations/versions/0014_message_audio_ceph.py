"""Move voiceover audio metadata to per-voice Ceph objects.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("message_audio", sa.Column("voice_id", sa.Text(), nullable=True))
    op.execute(
        "UPDATE message_audio "
        "SET voice_id = split_part(voice_version, ':', 3) "
        "WHERE voice_id IS NULL"
    )
    op.alter_column("message_audio", "voice_id", nullable=False)
    op.add_column("message_audio", sa.Column("object_key", sa.Text(), nullable=True))
    op.add_column("message_audio", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("message_audio", sa.Column("etag", sa.Text(), nullable=True))
    op.drop_constraint("message_audio_pkey", "message_audio", type_="primary")
    op.create_primary_key(
        "message_audio_pkey",
        "message_audio",
        ["message_id", "voice_id"],
    )
    op.create_check_constraint(
        "message_audio_size_valid",
        "message_audio",
        "size_bytes IS NULL OR size_bytes >= 0",
    )
    op.create_index(
        "message_audio_object_key_idx",
        "message_audio",
        ["object_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("message_audio_object_key_idx", table_name="message_audio")
    op.drop_constraint("message_audio_size_valid", "message_audio", type_="check")
    op.drop_constraint("message_audio_pkey", "message_audio", type_="primary")
    op.create_primary_key("message_audio_pkey", "message_audio", ["message_id"])
    op.drop_column("message_audio", "etag")
    op.drop_column("message_audio", "size_bytes")
    op.drop_column("message_audio", "object_key")
    op.drop_column("message_audio", "voice_id")
