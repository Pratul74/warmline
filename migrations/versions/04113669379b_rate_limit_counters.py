"""rate limit counters

Revision ID: 04113669379b
Revises: 2cef29ada8e6
Create Date: 2026-11-25 00:43:30.909513

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04113669379b'
down_revision: Union[str, Sequence[str], None] = '2cef29ada8e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """One counter row per integration per time window. The primary key is what the
    rate limiter's ON CONFLICT targets. Rows are disposable, so they cascade with the integration."""
    op.create_table(
        'rate_limit_counters',
        sa.Column('integration_id', sa.Integer(), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('integration_id', 'window_start'),
    )


def downgrade() -> None:
    """Undo upgrade(). Only counters are lost; they are rebuilt from zero."""
    op.drop_table('rate_limit_counters')
