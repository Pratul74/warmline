import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import run_tool
from app.agent.tools import NOT_CONFIRMED_YET_ERROR, build_tools
from app.core.config import get_settings
from app.core.llm import ToolCall
from app.db.models import Conversation, Lead, PendingAction, PendingActionStatus, Slot
from app.services.booking import (
    BookingNotFoundError,
    LeadNotFoundError,
    SlotInPastError,
    SlotNotFoundError,
    SlotUnavailableError,
    book_slot,
    cancel_booking,
)
from app.services.lead import create_lead
from tests.factories import new_conversation

HOUR = timedelta(hours=1)
KIM = {"name": "Kim Fake", "email": "Kim@Example.TEST"}


@pytest.fixture(autouse=True)
def business_in_utc(monkeypatch):
    monkeypatch.setattr(get_settings(), "business_timezone", "UTC")


def utc_day(days_from_today: int) -> datetime:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=days_from_today)


async def add_slot(session, start: datetime, booked_by: int | None = None) -> Slot:
    slot = Slot(start_at=start, end_at=start + HOUR, booked_by_lead_id=booked_by)
    session.add(slot)
    await session.flush()
    return slot


async def add_lead(session, email: str) -> Lead:
    return (await create_lead(session, name="Fake Person", email=email)).lead

async def test_service_books_a_free_slot_and_rebooking_by_the_same_lead_is_a_no_op(session):
    lead = await add_lead(session, "a@example.test")
    slot = await add_slot(session, utc_day(5) + 10 * HOUR)

    first = await book_slot(session, slot_id=slot.id, lead_id=lead.id)
    again = await book_slot(session, slot_id=slot.id, lead_id=lead.id)

    assert (first.created, first.slot.booked_by_lead_id) == (True, lead.id)
    assert again.created is False


async def test_service_refuses_a_slot_booked_by_someone_else(session):
    owner = await add_lead(session, "owner@example.test")
    other = await add_lead(session, "other@example.test")
    slot = await add_slot(session, utc_day(5) + 10 * HOUR, booked_by=owner.id)

    with pytest.raises(SlotUnavailableError, match="already booked"):
        await book_slot(session, slot_id=slot.id, lead_id=other.id)


async def test_service_refuses_past_missing_slot_and_missing_lead(session):
    lead = await add_lead(session, "a@example.test")
    past = await add_slot(session, utc_day(-1) + 10 * HOUR)
    future = await add_slot(session, utc_day(5) + 10 * HOUR)

    with pytest.raises(SlotInPastError):
        await book_slot(session, slot_id=past.id, lead_id=lead.id)
    with pytest.raises(SlotNotFoundError):
        await book_slot(session, slot_id=999_999, lead_id=lead.id)
    with pytest.raises(LeadNotFoundError):  # needs the fixed _lead_exists query
        await book_slot(session, slot_id=future.id, lead_id=999_999)

async def test_service_cancels_own_booking_once(session):
    lead = await add_lead(session, "a@example.test")
    slot = await add_slot(session, utc_day(5) + 10 * HOUR, booked_by=lead.id)

    first = await cancel_booking(session, slot_id=slot.id, lead_id=lead.id)
    again = await cancel_booking(session, slot_id=slot.id, lead_id=lead.id)

    assert (first.cancelled, first.slot.booked_by_lead_id) == (True, None)
    assert again.cancelled is False


async def test_service_refuses_to_cancel_someone_elses_or_a_past_booking(session):
    lead = await add_lead(session, "a@example.test")
    other = await add_lead(session, "b@example.test")
    theirs = await add_slot(session, utc_day(5) + 10 * HOUR, booked_by=other.id)
    past = await add_slot(session, utc_day(-1) + 10 * HOUR, booked_by=lead.id)

    with pytest.raises(BookingNotFoundError):
        await cancel_booking(session, slot_id=theirs.id, lead_id=lead.id)
    with pytest.raises(SlotInPastError):  # was SlotUnavailableError before the fix
        await cancel_booking(session, slot_id=past.id, lead_id=lead.id)


async def test_two_connections_cannot_book_the_same_slot(engine):
    tag = uuid4().hex[:8]
    start = utc_day(300) + timedelta(minutes=int(tag, 16) % 1000)
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        first_lead = await add_lead(setup, f"first-{tag}@example.test")
        second_lead = await add_lead(setup, f"second-{tag}@example.test")
        slot = await add_slot(setup, start)
        await setup.commit()

    try:
        async with AsyncSession(engine) as a, AsyncSession(engine) as b:
            await book_slot(a, slot_id=slot.id, lead_id=first_lead.id)  # holds the row lock
            second = asyncio.create_task(book_slot(b, slot_id=slot.id, lead_id=second_lead.id))
            await asyncio.sleep(0.3)
            assert not second.done(), "the second booking should be waiting for the lock"

            await a.commit()
            with pytest.raises(SlotUnavailableError):
                await second

        async with AsyncSession(engine) as check:
            holder = await check.scalar(select(Slot.booked_by_lead_id).where(Slot.id == slot.id))
        assert holder == first_lead.id
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(Slot).where(Slot.id == slot.id))
            await cleanup.execute(delete(Lead).where(Lead.id.in_([first_lead.id, second_lead.id])))
            await cleanup.commit()


@pytest.fixture
async def conversation(session) -> Conversation:
    conversation = await new_conversation(session)
    return conversation


class Request:

    def __init__(self, session, conversation_id: int):
        self.tools = build_tools(session, conversation_id=conversation_id)

    async def call(self, name: str, args: dict | None = None) -> tuple[dict, str]:
        return await run_tool(ToolCall(name=name, args=args or {}), self.tools)


def slot_args(start: datetime, **extra) -> dict:
    return {"slot_date": start.date().isoformat(), "start_time": start.strftime("%H:%M"), **extra}


async def lead_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Lead))


async def test_book_slot_only_proposes(session, conversation):
    start = utc_day(5) + 13 * HOUR
    slot = await add_slot(session, start)

    output, status = await Request(session, conversation.id).call("book_slot", slot_args(start, **KIM))

    assert status == "ok"
    assert output["status"] == "awaiting_confirmation"
    assert output["details"]["slot"]["start"] == start.isoformat()
    assert output["details"]["email"] == "kim@example.test"
    assert slot.booked_by_lead_id is None
    assert await lead_count(session) == 0


@pytest.mark.parametrize("problem", ["no_slot", "taken", "past"])
async def test_book_slot_refuses_bad_slots_before_asking(session, conversation, problem):
    start = utc_day(-1 if problem == "past" else 5) + 13 * HOUR
    if problem == "taken":
        await add_slot(session, start, booked_by=(await add_lead(session, "x@example.test")).id)
    elif problem == "past":
        await add_slot(session, start)

    output, status = await Request(session, conversation.id).call("book_slot", slot_args(start, **KIM))

    assert status == "error"
    assert "Check availability again" in output["error"]
    assert await session.scalar(select(func.count()).select_from(PendingAction)) == 0


async def test_book_slot_confirmed_later_saves_lead_and_booking_together(session, conversation):
    start = utc_day(5) + 13 * HOUR
    slot = await add_slot(session, start)
    first = Request(session, conversation.id)
    await first.call("book_slot", slot_args(start, **KIM))

    same_request, _ = await first.call("confirm_pending_action")
    output, status = await Request(session, conversation.id).call("confirm_pending_action")

    assert same_request == {"error": NOT_CONFIRMED_YET_ERROR}
    lead = await session.scalar(select(Lead).where(Lead.email == "kim@example.test"))
    assert status == "ok"
    assert output["confirmed"] == "book_slot"
    assert output["lead_id"] == lead.id
    assert output["booked"]["start"] == start.isoformat()
    await session.refresh(slot)
    assert slot.booked_by_lead_id == lead.id


async def test_slot_taken_between_proposal_and_confirmation_saves_nothing(session, conversation):
    start = utc_day(5) + 13 * HOUR
    slot = await add_slot(session, start)
    await Request(session, conversation.id).call("book_slot", slot_args(start, **KIM))
    someone_else = await add_lead(session, "fast@example.test")
    slot.booked_by_lead_id = someone_else.id
    await session.flush()

    output, status = await Request(session, conversation.id).call("confirm_pending_action")

    assert status == "error"
    assert "already booked" in output["error"]
    assert await session.scalar(select(Lead).where(Lead.email == "kim@example.test")) is None
    action_status = await session.scalar(select(PendingAction.status))
    assert action_status is PendingActionStatus.PENDING


async def test_cancel_booking_of_this_conversations_lead_after_confirmation(session, conversation):
    lead = await add_lead(session, "kim@example.test")
    start = utc_day(5) + 13 * HOUR
    slot = await add_slot(session, start, booked_by=lead.id)
    conversation.lead_id = lead.id
    await session.flush()

    proposal, _ = await Request(session, conversation.id).call("cancel_booking", slot_args(start))
    await session.refresh(slot)
    still_booked = slot.booked_by_lead_id
    output, status = await Request(session, conversation.id).call("confirm_pending_action")

    assert proposal["status"] == "awaiting_confirmation"
    assert still_booked == lead.id
    assert status == "ok"
    assert output["confirmed"] == "cancel_booking"
    await session.refresh(slot)
    assert slot.booked_by_lead_id is None


async def test_cancel_booking_refuses_bookings_not_made_in_this_conversation(session, conversation):
    owner = await add_lead(session, "owner@example.test")
    start = utc_day(5) + 13 * HOUR
    await add_slot(session, start, booked_by=owner.id)

    no_lead, _ = await Request(session, conversation.id).call("cancel_booking", slot_args(start))
    conversation.lead_id = (await add_lead(session, "me@example.test")).id
    await session.flush()
    not_mine, status = await Request(session, conversation.id).call("cancel_booking", slot_args(start))

    expected = {"error": "No booking made in this conversation starts at that time."}
    assert no_lead == expected
    assert (status, not_mine) == ("error", expected)
