"""tool_calls nullable conversation

Revision ID: 3ab5764201c5
Revises: a19cf05a49bc
Create Date: 2026-11-23 12:51:54.915134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ab5764201c5'
down_revision: Union[str, Sequence[str], None] = 'a19cf05a49bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Keep audit rows of a failed request even when its new conversation was rolled back."""
    op.alter_column('tool_calls', 'conversation_id',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade() -> None:
    """Undo upgrade(). Audit rows without a conversation are deleted, or NOT NULL would fail."""
    op.execute("DELETE FROM tool_calls WHERE conversation_id IS NULL")
    op.alter_column('tool_calls', 'conversation_id',
               existing_type=sa.INTEGER(),
               nullable=False)
