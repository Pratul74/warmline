"""accounts and conversation owner

Revision ID: 6e84ea509d06
Revises: 3ab5764201c5
Create Date: 2026-11-23 16:56:18.101474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e84ea509d06'
down_revision: Union[str, Sequence[str], None] = '3ab5764201c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Owner of conversations created before accounts existed. ".invalid" is a reserved domain,
# and password_hash is NULL, so nobody can ever log in as this account.
LEGACY_EMAIL = "legacy@warmline.invalid"
FK_NAME = "conversations_account_id_fkey"  # the name Postgres would choose by default


def upgrade() -> None:
    """Add accounts and give every conversation an owner."""
    op.create_table('accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('business_name', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_accounts_email_lower', 'accounts', [sa.literal_column('lower(email)')], unique=True)

    # Three stages, because existing rows have no owner yet: add as nullable, fill, then require.
    op.add_column('conversations', sa.Column('account_id', sa.Integer(), nullable=True))
    # Create the legacy account only when there is old data to own; a fresh database gets none.
    op.execute(
        sa.text(
            "INSERT INTO accounts (email, password_hash, business_name) "
            "SELECT :email, NULL, 'Legacy (pre-Phase 3)' "
            "WHERE EXISTS (SELECT 1 FROM conversations)"
        ).bindparams(email=LEGACY_EMAIL)
    )
    op.execute(
        sa.text(
            "UPDATE conversations SET account_id = (SELECT id FROM accounts WHERE email = :email)"
        ).bindparams(email=LEGACY_EMAIL)
    )
    op.alter_column('conversations', 'account_id', existing_type=sa.Integer(), nullable=False)
    op.create_index('ix_conversations_account_id', 'conversations', ['account_id'], unique=False)
    op.create_foreign_key(FK_NAME, 'conversations', 'accounts', ['account_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    """Undo upgrade(). Accounts and the conversation owners are deleted (data loss by design)."""
    op.drop_constraint(FK_NAME, 'conversations', type_='foreignkey')
    op.drop_index('ix_conversations_account_id', table_name='conversations')
    op.drop_column('conversations', 'account_id')
    op.drop_index('uq_accounts_email_lower', table_name='accounts')
    op.drop_table('accounts')
