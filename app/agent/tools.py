from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import Tool
from app.core.config import get_settings
from app.core.llm import LLMError, ToolSpec, embed_query
from app.services.booking import InvalidBookingRequestError, check_availability
from app.services.faq import search_faq
from app.services.lead import (
    MAX_EMAIL_LENGTH,
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
    "call cancel_pending_action; if they correct something, call the tool again with the "
    "corrected details."
)
NOTHING_PENDING_ERROR = (
    "Nothing is waiting for confirmation. It may have expired; collect the details again."
)
NOT_CONFIRMED_YET_ERROR = (
    "The customer has not confirmed yet. Ask them first and wait for their reply."
)
ALREADY_HANDLED_ERROR = "That request was already handled or has expired."


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
        "Carry out the action waiting for confirmation in this conversation (for example, "
        "saving a lead). Call it only after the customer has clearly agreed in their reply."
    ),
    parameters=NoArgs.model_json_schema(),
)

CANCEL_PENDING_ACTION_SPEC = ToolSpec(
    name="cancel_pending_action",
    description="Drop the action waiting for confirmation, when the customer says no.",
    parameters=NoArgs.model_json_schema(),
)


def _local_day_window(start_date: date, days: int) -> tuple[datetime, datetime]:
    """Midnight at the start of start_date to midnight after the last day, in business time."""
    tz = get_settings().business_tz
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(start_date + timedelta(days=days), time.min, tzinfo=tz)
    return start, end


def build_tools(
    session: AsyncSession,
    *,
    conversation_id: int,
    embed_query_fn: EmbedQueryFn = embed_query,
) -> dict[str, Tool]:
    proposed_this_request: set[int] = set()

    async def save_lead(args: CreateLeadArgs) -> dict[str, Any]:
        result = await create_lead(session, **args.model_dump())
        return {"lead_id": result.lead.id, "created": result.created}

    write_executors: dict[str, tuple[type[BaseModel], WriteFn]] = {
        "create_lead": (CreateLeadArgs, save_lead),
    }

    async def propose(tool_name: str, details: dict[str, Any]) -> dict[str, Any]:
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
        return {"confirmed": action.tool_name, **result}

    async def cancel_handler(_: NoArgs) -> dict[str, Any]:
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
            session, vector, top_k=FAQ_TOP_K, min_similarity=FAQ_MIN_SIMILARITY
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
                session, window_start=window_start, window_end=window_end, limit=MAX_SLOTS_RETURNED
            )
        except InvalidBookingRequestError as exc:
            return {"error": str(exc)}
        tz = window_start.tzinfo
        return {
            "timezone": get_settings().business_timezone,
            "slots": [
                {
                    "slot_id": slot.id,
                    "weekday": slot.start_at.astimezone(tz).strftime("%A"),
                    "start": slot.start_at.astimezone(tz).isoformat(),
                    "end": slot.end_at.astimezone(tz).isoformat(),
                }
                for slot in slots
            ],
        }

    return {
        "create_lead": Tool(CREATE_LEAD_SPEC, CreateLeadArgs, create_lead_handler),
        "search_faq": Tool(SEARCH_FAQ_SPEC, SearchFaqArgs, search_faq_handler),
        "check_availability": Tool(
            CHECK_AVAILABILITY_SPEC, CheckAvailabilityArgs, check_availability_handler
        ),
        "confirm_pending_action": Tool(CONFIRM_PENDING_ACTION_SPEC, NoArgs, confirm_handler),
        "cancel_pending_action": Tool(CANCEL_PENDING_ACTION_SPEC, NoArgs, cancel_handler),
    }
