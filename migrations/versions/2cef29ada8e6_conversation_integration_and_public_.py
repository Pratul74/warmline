"""conversation integration and public token

Revision ID: 2cef29ada8e6
Revises: 92bf31e64394
Create Date: 2026-11-24 22:02:01.868287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2cef29ada8e6'
down_revision: Union[str, Sequence[str], None] = '92bf31e64394'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Explicit names (the ones Postgres would choose) so the downgrade can drop them.
FK_NAME = "conversations_integration_id_fkey"
UNIQUE_NAME = "conversations_public_token_hash_key"


def upgrade() -> None:
    """Link conversations to the integration they came through, and store the visitor token's
    hash. Both nullable: owner /chat conversations and all existing rows have neither."""
    op.add_column('conversations', sa.Column('integration_id', sa.Integer(), nullable=True))
    op.add_column('conversations', sa.Column('public_token_hash', sa.String(length=64), nullable=True))
    op.create_index('ix_conversations_integration_id', 'conversations', ['integration_id'], unique=False)
    op.create_unique_constraint(UNIQUE_NAME, 'conversations', ['public_token_hash'])
    op.create_foreign_key(
        FK_NAME, 'conversations', 'integrations', ['integration_id'], ['id'], ondelete='RESTRICT'
    )


def downgrade() -> None:
    """Undo upgrade(). Conversations stay, but lose their integration link and visitor token."""
    op.drop_constraint(FK_NAME, 'conversations', type_='foreignkey')
    op.drop_constraint(UNIQUE_NAME, 'conversations', type_='unique')
    op.drop_index('ix_conversations_integration_id', table_name='conversations')
    op.drop_column('conversations', 'public_token_hash')
    op.drop_column('conversations', 'integration_id')
