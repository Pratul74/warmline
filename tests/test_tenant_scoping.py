from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agent.loop import run_tool
from app.agent.tools import build_tools
from app.core.config import EMBEDDING_DIM, get_settings
from app.core.llm import ToolCall
from app.db.models import Account, Lead, PendingAction, Slot
from app.services.booking import (
    LeadNotFoundError,
    SlotNotFoundError,
    book_slot,
    cancel_booking,
    check_availability,
    find_slot_by_start,
)
from app.services.faq import search_faq
from app.services.lead import create_lead, get_lead, get_lead_by_email
from tests.factories import new_account, new_conversation, new_faq, new_lead, new_slot

HOUR = timedelta(hours=1)
START = (datetime.now(UTC) + timedelta(days=5)).replace(hour=10, minute=0, second=0, microsecond=0)


@pytest.fixture(autouse=True)
def business_in_utc(monkeypatch):
    monkeypatch.setattr(get_settings(), "business_timezone", "UTC")


@pytest.fixture
async def shop_a(session) -> Account:
    return await new_account(session, business_name="Fake Shop A")


@pytest.fixture
async def shop_b(session) -> Account:
    return await new_account(session, business_name="Fake Shop B")


def unit(i: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[i] = 1.0
    return vector


async def tool_call(session, account: Account, name: str, args: dict, embed=None) -> tuple[dict, str]:
    conversation = await new_conversation(session, account)
    extra = {"embed_query_fn": embed} if embed else {}
    tools = build_tools(session, account_id=account.id, conversation_id=conversation.id, **extra)
    return await run_tool(ToolCall(name=name, args=args), tools)

async def test_same_email_is_a_separate_lead_in_each_account(session, shop_a, shop_b):
    in_a = await create_lead(session, account_id=shop_a.id, name="Kim Fake", email="kim@example.test")
    in_b = await create_lead(session, account_id=shop_b.id, name="Kim F", email="KIM@example.test")

    assert (in_a.created, in_b.created) == (True, True)
    assert in_a.lead.id != in_b.lead.id
    assert (in_a.lead.account_id, in_b.lead.account_id) == (shop_a.id, shop_b.id)
    assert in_b.lead.name == "Kim F"


async def test_same_email_twice_in_one_account_still_reuses_the_lead(session, shop_a, shop_b):
    first = await create_lead(session, account_id=shop_a.id, name="Kim Fake", email="kim@example.test")
    await create_lead(session, account_id=shop_b.id, name="Kim Fake", email="kim@example.test")
    again = await create_lead(session, account_id=shop_a.id, name="Kim Fake", email="Kim@Example.test")

    assert (again.created, again.lead.id) == (False, first.lead.id)


async def test_lead_lookups_only_find_the_accounts_own_leads(session, shop_a, shop_b):
    lead = await new_lead(session, shop_a.id, email="kim@example.test")

    assert await get_lead(session, account_id=shop_a.id, lead_id=lead.id) is not None
    assert await get_lead(session, account_id=shop_b.id, lead_id=lead.id) is None
    assert await get_lead_by_email(session, account_id=shop_b.id, email="kim@example.test") is None


async def test_database_refuses_a_lead_without_an_owner(session):
    session.add(Lead(name="No Owner", email="nobody@example.test", status="new"))

    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_faq_search_only_returns_the_accounts_own_entries(session, shop_a, shop_b):
    await new_faq(session, shop_a.id, question="Hours?", answer="A: 9 to 6.", embedding=unit(0))

    in_a = await search_faq(session, unit(0), account_id=shop_a.id)
    in_b = await search_faq(session, unit(0), account_id=shop_b.id)

    assert [m.answer for m in in_a] == ["A: 9 to 6."]
    assert in_b == []


async def test_faq_tool_answers_from_the_conversation_owners_faq(session, shop_a, shop_b):
    await new_faq(session, shop_a.id, question="Hours?", answer="A: 9 to 6.", embedding=unit(0))
    await new_faq(session, shop_b.id, question="Hours?", answer="B: 10 to 4.", embedding=unit(0))

    async def embed(question: str) -> list[float]:
        return unit(0)

    output, status = await tool_call(session, shop_b, "search_faq", {"question": "hours?"}, embed)

    assert status == "ok"
    assert [m["answer"] for m in output["matches"]] == ["B: 10 to 4."]

async def test_two_accounts_can_offer_the_same_start_time(session, shop_a, shop_b):
    await new_slot(session, shop_a.id, START)
    await new_slot(session, shop_b.id, START)

    count = await session.scalar(select(func.count()).select_from(Slot).where(Slot.start_at == START))
    assert count == 2


async def test_one_account_cannot_have_the_same_start_time_twice(session, shop_a):
    await new_slot(session, shop_a.id, START)

    with pytest.raises(IntegrityError):
        await new_slot(session, shop_a.id, START)
    await session.rollback()


async def test_availability_and_slot_lookup_only_see_the_accounts_own_slots(session, shop_a, shop_b):
    slot = await new_slot(session, shop_a.id, START)
    window = {"window_start": START - HOUR, "window_end": START + HOUR}

    assert [s.id for s in await check_availability(session, account_id=shop_a.id, **window)] == [slot.id]
    assert await check_availability(session, account_id=shop_b.id, **window) == []
    assert await find_slot_by_start(session, account_id=shop_b.id, start_at=START) is None


async def test_an_account_cannot_book_another_accounts_slot(session, shop_a, shop_b):
    slot = await new_slot(session, shop_a.id, START)
    b_lead = await new_lead(session, shop_b.id, email="kim@example.test")

    with pytest.raises(SlotNotFoundError):
        await book_slot(session, account_id=shop_b.id, slot_id=slot.id, lead_id=b_lead.id)
    await session.refresh(slot)
    assert slot.booked_by_lead_id is None


async def test_a_slot_cannot_be_booked_for_another_accounts_lead(session, shop_a, shop_b):
    slot = await new_slot(session, shop_a.id, START)
    b_lead = await new_lead(session, shop_b.id, email="kim@example.test")

    with pytest.raises(LeadNotFoundError):
        await book_slot(session, account_id=shop_a.id, slot_id=slot.id, lead_id=b_lead.id)
    await session.refresh(slot)
    assert slot.booked_by_lead_id is None


async def test_an_account_cannot_cancel_another_accounts_booking(session, shop_a, shop_b):
    a_lead = await new_lead(session, shop_a.id, email="kim@example.test")
    slot = await new_slot(session, shop_a.id, START, booked_by=a_lead.id)

    with pytest.raises(SlotNotFoundError):
        await cancel_booking(session, account_id=shop_b.id, slot_id=slot.id, lead_id=a_lead.id)
    await session.refresh(slot)
    assert slot.booked_by_lead_id == a_lead.id


async def test_book_slot_tool_does_not_find_another_accounts_slot(session, shop_a, shop_b):
    await new_slot(session, shop_a.id, START)
    args = {
        "slot_date": START.date().isoformat(),
        "start_time": "10:00",
        "name": "Kim Fake",
        "email": "kim@example.test",
    }

    output, status = await tool_call(session, shop_b, "book_slot", args)

    assert status == "error"
    assert output == {"error": "There is no slot at that time. Check availability again."}
    assert await session.scalar(select(func.count()).select_from(PendingAction)) == 0


async def test_booking_in_each_account_at_the_same_time_books_the_right_slot(session, shop_a, shop_b):
    a_slot = await new_slot(session, shop_a.id, START)
    b_slot = await new_slot(session, shop_b.id, START)
    b_lead = await new_lead(session, shop_b.id, email="kim@example.test")

    result = await book_slot(session, account_id=shop_b.id, slot_id=b_slot.id, lead_id=b_lead.id)

    await session.refresh(a_slot)
    assert (result.created, result.slot.id) == (True, b_slot.id)
    assert a_slot.booked_by_lead_id is None
