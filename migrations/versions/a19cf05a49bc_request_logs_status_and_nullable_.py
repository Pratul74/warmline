"""request_logs status and nullable conversation

Revision ID: a19cf05a49bc
Revises: 4e9ad14e6dfb
Create Date: 2026-11-23 12:09:29.207469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a19cf05a49bc'
down_revision: Union[str, Sequence[str], None] = '4e9ad14e6dfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Record failed requests too: a status, and no conversation when a new one was rolled back."""
    # server_default='ok' fills the column for any rows that already exist.
    op.add_column('request_logs', sa.Column('status', sa.Enum('ok', 'rate_limited', 'model_error', name='requeststatus', native_enum=False), server_default='ok', nullable=False))
    op.alter_column('request_logs', 'conversation_id',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade() -> None:
    """Undo upgrade(). Failure rows without a conversation are deleted, or NOT NULL would fail."""
    op.execute("DELETE FROM request_logs WHERE conversation_id IS NULL")
    op.alter_column('request_logs', 'conversation_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_column('request_logs', 'status')
