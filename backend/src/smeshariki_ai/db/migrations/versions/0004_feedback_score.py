"""Rate answers with a score from 1 to 5 instead of like or dislike.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("message_feedback", sa.Column("score", sa.SmallInteger()))
    op.execute(
        "UPDATE message_feedback SET score = CASE value WHEN 'like' THEN 5 ELSE 1 END"
    )
    op.alter_column("message_feedback", "score", nullable=False)
    op.create_check_constraint(
        "message_feedback_score_valid", "message_feedback", "score BETWEEN 1 AND 5"
    )
    op.drop_constraint("message_feedback_value_valid", "message_feedback")
    op.drop_column("message_feedback", "value")


def downgrade() -> None:
    op.add_column("message_feedback", sa.Column("value", sa.Text()))
    op.execute(
        "UPDATE message_feedback "
        "SET value = CASE WHEN score >= 3 THEN 'like' ELSE 'dislike' END"
    )
    op.alter_column("message_feedback", "value", nullable=False)
    op.create_check_constraint(
        "message_feedback_value_valid",
        "message_feedback",
        "value IN ('like', 'dislike')",
    )
    op.drop_constraint("message_feedback_score_valid", "message_feedback")
    op.drop_column("message_feedback", "score")
