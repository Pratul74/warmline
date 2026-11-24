"""owner scoping for leads faq slots

Revision ID: 2c2365f87341
Revises: 6e84ea509d06
Create Date: 2026-11-24 19:35:44.709540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c2365f87341'
down_revision: Union[str, Sequence[str], None] = '6e84ea509d06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same legacy owner as in 6e84ea509d06: it owns every row created before accounts existed.
LEGACY_EMAIL = "legacy@warmline.invalid"
SCOPED_TABLES = ("leads", "faq_entries", "slots")


def _fk_name(table: str) -> str:
    return f"{table}_account_id_fkey"  # the name Postgres would choose by default


def upgrade() -> None:
    """Give every lead, FAQ entry and slot an owning account."""
    # The legacy account exists only if 6e84ea509d06 found old conversations. Old leads,
    # FAQs or slots also need an owner, so create it now if any such rows exist.
    any_old_rows = " OR ".join(f"EXISTS (SELECT 1 FROM {table})" for table in SCOPED_TABLES)
    op.execute(
        sa.text(
            "INSERT INTO accounts (email, password_hash, business_name) "
            "SELECT :email, NULL, 'Legacy (pre-Phase 3)' "
            f"WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE email = :email) AND ({any_old_rows})"
        ).bindparams(email=LEGACY_EMAIL)
    )

    for table in SCOPED_TABLES:
        # Three stages, because existing rows have no owner yet: add as nullable, fill, require.
        op.add_column(table, sa.Column('account_id', sa.Integer(), nullable=True))
        op.execute(
            sa.text(
                f"UPDATE {table} SET account_id = (SELECT id FROM accounts WHERE email = :email)"
            ).bindparams(email=LEGACY_EMAIL)
        )
        op.alter_column(table, 'account_id', existing_type=sa.Integer(), nullable=False)
        op.create_foreign_key(
            _fk_name(table), table, 'accounts', ['account_id'], ['id'], ondelete='RESTRICT'
        )

    op.create_index('ix_faq_entries_account_id', 'faq_entries', ['account_id'], unique=False)

    # Uniqueness becomes per account: two businesses may share a customer email or a start time.
    op.drop_index('uq_leads_email_lower', table_name='leads')
    op.create_index(
        'uq_leads_account_email_lower',
        'leads',
        ['account_id', sa.literal_column('lower(email)')],
        unique=True,
    )
    op.drop_constraint('slots_start_at_key', 'slots', type_='unique')
    op.create_unique_constraint('uq_slots_account_start_at', 'slots', ['account_id', 'start_at'])


def downgrade() -> None:
    """Undo upgrade(). Fails on purpose if two accounts share a lead email or a slot start time,
    because the old global unique rules cannot hold; nothing is deleted to make it pass."""
    op.drop_constraint('uq_slots_account_start_at', 'slots', type_='unique')
    op.create_unique_constraint('slots_start_at_key', 'slots', ['start_at'])
    op.drop_index('uq_leads_account_email_lower', table_name='leads')
    op.create_index(
        'uq_leads_email_lower', 'leads', [sa.literal_column('lower(email)')], unique=True
    )
    op.drop_index('ix_faq_entries_account_id', table_name='faq_entries')
    for table in reversed(SCOPED_TABLES):
        op.drop_constraint(_fk_name(table), table, type_='foreignkey')
        op.drop_column(table, 'account_id')
