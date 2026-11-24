from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import Tool
from app.core.config import get_settings
from app.core.llm import LLMError, ToolSpec, embed_query
from app.db.models import Conversation, Slot
from app.services.booking import (
    BookingError,
    InvalidBookingRequestError,
    book_slot,
    cancel_booking,
    check_availability,
    find_slot_by_start,
)
from app.services.emails import MAX_EMAIL_LENGTH
from app.services.faq import search_faq
from app.services.lead import (
    MAX_NAME_LENGTH,
    MAX_PHONE_LENGTH,
    InvalidLeadError,
    clean_lead_fields,
    create_lead,
)
from app.services.pending_actions import (
    PendingActionError,
    cancel_pending_action,
    claim_pending_action,
    create_pending_action,
    get_latest_pending_action,
)

MAX_NOTES_LENGTH = 1000
MAX_QUESTION_LENGTH = 500

FAQ_MIN_SIMILARITY = 0.70
FAQ_TOP_K = 3

MAX_AVAILABILITY_DAYS = 14
MAX_SLOTS_RETURNED = 10

EmbedQueryFn = Callable[[str], Awaitable[list[float]]]
WriteFn = Callable[[Any], Awaitable[dict[str, Any]]]

CONFIRM_NEXT_STEP = (
    "Nothing is saved yet. Read these details back to the customer and ask them to confirm. "
    "In their next message: if they agree, call confirm_pending_action; if they decline, "
    "call decline_pending_action; if they correct something, call the tool again with the "
    "corrected details."
)
NOTHING_PENDING_ERROR = (
    "Nothing is waiting for confirmation. It may have expired; collect the details again."
)
NOT_CONFIRMED_YET_ERROR = (
    "The customer has not confirmed yet. Ask them first and wait for their reply."
)
ALREADY_HANDLED_ERROR = "That request was already handled or has expired."
ALREADY_WAITING_NEXT_STEP = (
    "These exact details are already waiting for confirmation from an earlier message. "
    "If the customer has agreed, call confirm_pending_action now; do not propose again."
)


class CreateLeadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, description="Customer's full name")
    email: str = Field(min_length=3, max_length=MAX_EMAIL_LENGTH, description="Customer's email address")
    phone: str | None = Field(default=None, max_length=MAX_PHONE_LENGTH, description="Phone number, if given")
    notes: str | None = Field(
        default=None,
        max_length=MAX_NOTES_LENGTH,
        description="Short summary of what the customer wants",
    )


CREATE_LEAD_SPEC = ToolSpec(
    name="create_lead",
    description=(
        "Prepare to save an interested customer as a sales lead so the team can follow up. "
        "Call it once you have at least their name and email address. It does not save "
        "straight away: it returns the details for the customer to confirm."
    ),
    parameters=CreateLeadArgs.model_json_schema(),
)


class SearchFaqArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_LENGTH,
        description="The customer's question, in their own words",
    )


SEARCH_FAQ_SPEC = ToolSpec(
    name="search_faq",
    description=(
        "Search the business's FAQ for answers about hours, services, prices, policies "
        "and similar. Returns the closest matching FAQ entries, or none if nothing matches."
    ),
    parameters=SearchFaqArgs.model_json_schema(),
)


class CheckAvailabilityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date = Field(description="First day to check, as YYYY-MM-DD")
    days: int = Field(
        default=1,
        ge=1,
        le=MAX_AVAILABILITY_DAYS,
        description=f"How many days to check, starting at start_date (1 to {MAX_AVAILABILITY_DAYS})",
    )


CHECK_AVAILABILITY_SPEC = ToolSpec(
    name="check_availability",
    description=(
        "List free appointment slots, for example for a bike service. "
        "Returns up to 10 free slots in the business's local time, earliest first."
    ),
    parameters=CheckAvailabilityArgs.model_json_schema(),
)


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


CONFIRM_PENDING_ACTION_SPEC = ToolSpec(
    name="confirm_pending_action",
    description=(
        "Carry out the action waiting for confirmation in this conversation (saving a lead, "
        "booking a slot or cancelling a booking). Call it only after the customer has "
        "clearly agreed in their reply, including when they agree to a cancellation."
    ),
    parameters=NoArgs.model_json_schema(),
)

DECLINE_PENDING_ACTION_SPEC = ToolSpec(
    name="decline_pending_action",
    description=(
        "The customer said no to the action waiting for confirmation: drop it without "
        "doing it. Not for cancelling a booking; a 'yes' to a proposed cancellation is "
        "confirm_pending_action."
    ),
    parameters=NoArgs.model_json_schema(),
)



class SlotTimeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_date: date = Field(description="Day of the slot, as YYYY-MM-DD")
    start_time: time = Field(description="Start time of the slot in local time, as HH:MM")


class BookSlotArgs(SlotTimeArgs, CreateLeadArgs):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


BOOK_SLOT_SPEC = ToolSpec(
    name="book_slot",
    description=(
        "Prepare to book a free slot (from check_availability) for a customer. Needs the "
        "date and start time of the slot plus the name and email of the customer. It does "
        "not book straight away: it returns the details for the customer to confirm."
    ),
    parameters=BookSlotArgs.model_json_schema(),
)

CANCEL_BOOKING_SPEC = ToolSpec(
    name="cancel_booking",
    description=(
        "Prepare to cancel a booking made in this conversation, given the date and start "
        "time of the slot. It does not cancel straight away: the customer must confirm."
    ),
    parameters=SlotTimeArgs.model_json_schema(),
)


class BookingAction(BaseModel):

    slot_id: int
    lead: CreateLeadArgs


class CancelBookingAction(BaseModel):
    slot_id: int
    lead_id: int


def _describe_slot(slot: Slot) -> dict[str, Any]:
    tz = get_settings().business_tz
    start = slot.start_at.astimezone(tz)
    return {
        "slot_id": slot.id,
        "weekday": start.strftime("%A"),
        "start": start.isoformat(),
        "end": slot.end_at.astimezone(tz).isoformat(),
    }


def _local_day_window(start_date: date, days: int) -> tuple[datetime, datetime]:
    tz = get_settings().business_tz
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(start_date + timedelta(days=days), time.min, tzinfo=tz)
    return start, end


def _readable_time(iso_start: str) -> str:
    start = datetime.fromisoformat(iso_start)
    return f"{start:%A} {start.day} {start:%B} at {start:%H:%M}"


def describe_completed_action(tool_result: dict[str, Any]) -> str | None:
    confirmed = tool_result.get("confirmed")
    if confirmed == "create_lead":
        return "Your details are saved and the team will be in touch."
    if confirmed == "book_slot":
        return f"Your booking for {_readable_time(tool_result['booked']['start'])} is confirmed."
    if confirmed == "cancel_booking":
        when = _readable_time(tool_result["cancelled_booking"]["start"])
        return f"Your booking for {when} is cancelled."
    return None


def build_tools(
    session: AsyncSession,
    *,
    account_id: int,
    conversation_id: int,
    embed_query_fn: EmbedQueryFn = embed_query,
) -> dict[str, Tool]:
    proposed_this_request: set[int] = set()

    async def save_lead(args: CreateLeadArgs) -> dict[str, Any]:
        result = await create_lead(session, account_id=account_id, **args.model_dump())
        return {"lead_id": result.lead.id, "created": result.created}

    async def save_booking(action: BookingAction) -> dict[str, Any]:
        lead = (await create_lead(session, account_id=account_id, **action.lead.model_dump())).lead
        booking = await book_slot(
            session, account_id=account_id, slot_id=action.slot_id, lead_id=lead.id
        )
        return {"booked": _describe_slot(booking.slot), "lead_id": lead.id}

    async def save_cancellation(action: CancelBookingAction) -> dict[str, Any]:
        result = await cancel_booking(
            session, account_id=account_id, slot_id=action.slot_id, lead_id=action.lead_id
        )
        return {"cancelled_booking": _describe_slot(result.slot)}

    write_executors: dict[str, tuple[type[BaseModel], WriteFn]] = {
        "create_lead": (CreateLeadArgs, save_lead),
        "book_slot": (BookingAction, save_booking),
        "cancel_booking": (CancelBookingAction, save_cancellation),
    }

    async def find_slot(args: SlotTimeArgs) -> Slot | None:
        start = datetime.combine(args.slot_date, args.start_time, tzinfo=get_settings().business_tz)
        return await find_slot_by_start(session, account_id=account_id, start_at=start)

    async def propose(tool_name: str, details: dict[str, Any]) -> dict[str, Any]:
        open_action = await get_latest_pending_action(session, conversation_id)
        if (
            open_action is not None
            and open_action.id not in proposed_this_request
            and open_action.tool_name == tool_name
            and open_action.arguments == details
        ):
            return {
                "status": "awaiting_confirmation",
                "action": tool_name,
                "details": details,
                "next_step": ALREADY_WAITING_NEXT_STEP,
            }
        async with session.begin_nested():
            action = await create_pending_action(
                session, conversation_id=conversation_id, tool_name=tool_name, arguments=details
            )
        proposed_this_request.add(action.id)
        return {
            "status": "awaiting_confirmation",
            "action": tool_name,
            "details": details,
            "next_step": CONFIRM_NEXT_STEP,
        }

    async def create_lead_handler(args: CreateLeadArgs) -> dict[str, Any]:
        try:
            details = clean_lead_fields(**args.model_dump())
        except InvalidLeadError as exc:
            return {"error": str(exc)}
        return await propose("create_lead", details)

    async def book_slot_handler(args: BookSlotArgs) -> dict[str, Any]:
        try:
            lead_fields = clean_lead_fields(
                name=args.name, email=args.email, phone=args.phone, notes=args.notes
            )
        except InvalidLeadError as exc:
            return {"error": str(exc)}
        slot = await find_slot(args)
        if slot is None:
            return {"error": "There is no slot at that time. Check availability again."}
        if slot.booked_by_lead_id is not None:
            return {"error": "That slot is already booked. Check availability again."}
        if slot.start_at <= datetime.now(UTC):
            return {"error": "That slot has already started. Check availability again."}
        response = await propose(
            "book_slot", BookingAction(slot_id=slot.id, lead=lead_fields).model_dump()
        )
        response["details"] = {"slot": _describe_slot(slot), **lead_fields}
        return response

    async def cancel_booking_handler(args: SlotTimeArgs) -> dict[str, Any]:
        conversation = await session.get(Conversation, conversation_id)
        lead_id = conversation.lead_id if conversation else None
        slot = await find_slot(args)
        if lead_id is None or slot is None or slot.booked_by_lead_id != lead_id:
            return {"error": "No booking made in this conversation starts at that time."}
        response = await propose(
            "cancel_booking", CancelBookingAction(slot_id=slot.id, lead_id=lead_id).model_dump()
        )
        response["details"] = {"slot": _describe_slot(slot)}
        return response

    async def confirm_handler(_: NoArgs) -> dict[str, Any]:
        action = await get_latest_pending_action(session, conversation_id)
        if action is None:
            return {"error": NOTHING_PENDING_ERROR}
        if action.id in proposed_this_request:
            return {"error": NOT_CONFIRMED_YET_ERROR}
        if action.tool_name not in write_executors:
            return {"error": f"Unknown pending action '{action.tool_name}'."}
        args_model, write = write_executors[action.tool_name]
        try:
            async with session.begin_nested():
                await claim_pending_action(
                    session, action_id=action.id, conversation_id=conversation_id
                )
                result = await write(args_model.model_validate(action.arguments))
        except PendingActionError:
            return {"error": ALREADY_HANDLED_ERROR}
        except BookingError as exc:
            return {"error": f"{exc}. Check availability again and offer another time."}
        return {"confirmed": action.tool_name, **result}

    async def decline_handler(_: NoArgs) -> dict[str, Any]:
        action = await get_latest_pending_action(session, conversation_id)
        if action is None:
            return {"status": "nothing_to_cancel"}
        try:
            await cancel_pending_action(
                session, action_id=action.id, conversation_id=conversation_id
            )
        except PendingActionError:
            return {"error": ALREADY_HANDLED_ERROR}
        return {"cancelled": action.tool_name}

    async def search_faq_handler(args: SearchFaqArgs) -> dict[str, Any]:
        try:
            vector = await embed_query_fn(args.question)
        except LLMError:
            return {"error": "FAQ search is unavailable right now."}
        matches = await search_faq(
            session,
            vector,
            account_id=account_id,
            top_k=FAQ_TOP_K,
            min_similarity=FAQ_MIN_SIMILARITY,
        )
        return {
            "matches": [
                {"question": m.question, "answer": m.answer, "similarity": round(m.similarity, 2)}
                for m in matches
            ]
        }

    async def check_availability_handler(args: CheckAvailabilityArgs) -> dict[str, Any]:
        window_start, window_end = _local_day_window(args.start_date, args.days)
        try:
            slots = await check_availability(
                session,
                account_id=account_id,
                window_start=window_start,
                window_end=window_end,
                limit=MAX_SLOTS_RETURNED,
            )
        except InvalidBookingRequestError as exc:
            return {"error": str(exc)}
        return {
            "timezone": get_settings().business_timezone,
            "slots": [_describe_slot(slot) for slot in slots],
        }

    return {
        "create_lead": Tool(CREATE_LEAD_SPEC, CreateLeadArgs, create_lead_handler),
        "search_faq": Tool(SEARCH_FAQ_SPEC, SearchFaqArgs, search_faq_handler),
        "check_availability": Tool(
            CHECK_AVAILABILITY_SPEC, CheckAvailabilityArgs, check_availability_handler
        ),
        "book_slot": Tool(BOOK_SLOT_SPEC, BookSlotArgs, book_slot_handler),
        "cancel_booking": Tool(CANCEL_BOOKING_SPEC, SlotTimeArgs, cancel_booking_handler),
        "confirm_pending_action": Tool(CONFIRM_PENDING_ACTION_SPEC, NoArgs, confirm_handler),
        "decline_pending_action": Tool(DECLINE_PENDING_ACTION_SPEC, NoArgs, decline_handler),
    }
