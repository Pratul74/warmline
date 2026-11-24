"""integrations

Revision ID: 92bf31e64394
Revises: 2c2365f87341
Create Date: 2026-11-24 21:28:44.304663

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92bf31e64394'
down_revision: Union[str, Sequence[str], None] = '2c2365f87341'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add integrations: an owner's chat links. A new table, so no existing rows to fill."""
    op.create_table('integrations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('public_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('greeting', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('active', 'disabled', name='integrationstatus', native_enum=False), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('public_id')
    )
    op.create_index('ix_integrations_account_id', 'integrations', ['account_id'], unique=False)


def downgrade() -> None:
    """Undo upgrade(). All integrations are deleted (data loss by design)."""
    op.drop_index('ix_integrations_account_id', table_name='integrations')
    op.drop_table('integrations')
