"""faq unique question and updated_at

Revision ID: 853613967781
Revises: 04113669379b
Create Date: 2026-11-25 12:05:31.528483

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '853613967781'
down_revision: Union[str, Sequence[str], None] = '04113669379b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DUPLICATES_SQL = """
    SELECT account_id, count(*) AS duplicated_questions
    FROM (
        SELECT account_id
        FROM faq_entries
        GROUP BY account_id, lower(btrim(question))
        HAVING count(*) > 1
    ) AS duplicated
    GROUP BY account_id
    ORDER BY account_id
"""


def upgrade() -> None:
    """One FAQ entry per question per account (case and outer spaces ignored), which the
    CSV upload's ON CONFLICT targets, plus updated_at so the owner can see when an
    upload changed an answer.

    If duplicates already exist, the unique index cannot be built. Instead of letting
    CREATE UNIQUE INDEX fail with a raw error, stop first with a message that names the
    accounts. Postgres runs this migration in one transaction, so nothing is changed.
    Nothing is deleted automatically: which answer to keep is the owner's decision."""
    duplicates = op.get_bind().execute(sa.text(DUPLICATES_SQL)).all()
    if duplicates:
        listed = ", ".join(f"account {row.account_id}: {row.duplicated_questions} question(s)" for row in duplicates)
        raise RuntimeError(
            "Cannot add the unique FAQ question index: some accounts have the same question "
            f"more than once (ignoring case and outer spaces). {listed}. "
            "Delete or merge those rows, then run the migration again."
        )

    op.add_column(
        'faq_entries',
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(
        'uq_faq_entries_account_question',
        'faq_entries',
        ['account_id', sa.text('lower(btrim(question))')],
        unique=True,
    )


def downgrade() -> None:
    """Undo upgrade(). Rows are kept; only the uniqueness rule and updated_at go."""
    op.drop_index('uq_faq_entries_account_question', table_name='faq_entries')
    op.drop_column('faq_entries', 'updated_at')
