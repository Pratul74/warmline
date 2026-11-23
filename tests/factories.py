from itertools import count

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Conversation
from app.services.accounts import create_access_token

_numbers = count(1)


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


def auth_headers(account: Account) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(account.id)}"}
