from datetime import datetime, timedelta
from itertools import count

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Conversation, FaqEntry, Lead, Slot
from app.services.accounts import create_access_token
from app.services.lead import create_lead

_numbers = count(1)

SLOT_LENGTH = timedelta(hours=1)


async def new_account(session: AsyncSession, *, business_name: str = "Fake Bike Shop") -> Account:
    account = Account(email=f"owner{next(_numbers)}@example.test", business_name=business_name)
    session.add(account)
    await session.flush()
    return account


async def new_conversation(session: AsyncSession, account: Account | None = None) -> Conversation:
    if account is None:
        account = await new_account(session)
    conversation = Conversation(account_id=account.id)
    session.add(conversation)
    await session.flush()
    return conversation


async def new_lead(
    session: AsyncSession, account_id: int, *, email: str, name: str = "Fake Person"
) -> Lead:
    return (await create_lead(session, account_id=account_id, name=name, email=email)).lead


async def new_slot(
    session: AsyncSession, account_id: int, start: datetime, *, booked_by: int | None = None
) -> Slot:
    slot = Slot(
        account_id=account_id, start_at=start, end_at=start + SLOT_LENGTH, booked_by_lead_id=booked_by
    )
    session.add(slot)
    await session.flush()
    return slot


async def new_faq(
    session: AsyncSession, account_id: int, *, question: str, answer: str, embedding: list[float]
) -> FaqEntry:
    entry = FaqEntry(account_id=account_id, question=question, answer=answer, embedding=embedding)
    session.add(entry)
    await session.flush()
    return entry


def auth_headers(account: Account) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(account.id)}"}
