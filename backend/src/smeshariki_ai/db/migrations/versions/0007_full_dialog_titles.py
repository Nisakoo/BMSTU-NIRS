"""Restore full dialog titles from the first user request.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same rule as smeshariki_ai.dialogs.dialog_title: one line, at most 200
# characters, a longer text ends with an ellipsis.
FULL_TITLES = r"""
UPDATE dialogs
SET title = CASE
    WHEN char_length(first.line) <= 200 THEN first.line
    ELSE rtrim(left(first.line, 200)) || '…'
END
FROM (
    SELECT DISTINCT ON (dialog_id)
        dialog_id,
        regexp_replace(btrim(content, E' \t\n\r\f\v'), '\s+', ' ', 'g') AS line
    FROM messages
    WHERE role = 'user'
    ORDER BY dialog_id, position
) AS first
WHERE dialogs.id = first.dialog_id
"""


def upgrade() -> None:
    op.execute(FULL_TITLES)


def downgrade() -> None:
    # The cut titles cannot be restored and the full ones suit the old code.
    pass
