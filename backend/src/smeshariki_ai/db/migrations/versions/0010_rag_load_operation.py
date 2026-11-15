"""Add the operation kind to the knowledge journal.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rag_loads",
        sa.Column(
            "operation",
            sa.Text(),
            server_default=sa.text("'load'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "rag_loads_operation_valid",
        "rag_loads",
        "operation IN ('load', 'delete')",
    )


def downgrade() -> None:
    op.drop_constraint("rag_loads_operation_valid", "rag_loads", type_="check")
    op.drop_column("rag_loads", "operation")
