import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Conversation,
    Lead,
    LeadStatus,
    Message,
    MessageRole,
)


async def test_expected_indexes_exist():
    assert "ix_conversations_lead_id" in {
        i.name for i in Conversation.__table__.indexes
    }
    assert "ix_messages_conversation_created" in {
        i.name for i in Message.__table__.indexes
    }


async def test_lead_email_unique_case_insensitive(session):
    session.add(
        Lead(
            name="A",
            email="Bob@Example.com",
            status=LeadStatus.NEW,
        )
    )
    await session.commit()

    session.add(
        Lead(
            name="B",
            email="bob@example.com",
            status=LeadStatus.NEW,
        )
    )

    with pytest.raises(IntegrityError):
        await session.commit()

    await session.rollback()


async def test_messages_in_one_transaction_load_in_insert_order(session):
    conv = Conversation()
    session.add(conv)
    await session.flush()

    session.add_all(
        [
            Message(
                conversation_id=conv.id,
                role=MessageRole.USER,
                content="hi",
            ),
            Message(
                conversation_id=conv.id,
                role=MessageRole.ASSISTANT,
                content="hello",
            ),
        ]
    )

    await session.commit()

    result = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id)
    )

    rows = result.all()

    assert len(rows) == 2
    assert [m.role for m in rows] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert rows[0].id < rows[1].id