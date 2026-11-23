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
    create_lead,
)

MAX_NOTES_LENGTH = 1000
MAX_QUESTION_LENGTH = 500

FAQ_MIN_SIMILARITY = 0.70
FAQ_TOP_K = 3

MAX_AVAILABILITY_DAYS = 14
MAX_SLOTS_RETURNED = 10

EmbedQueryFn = Callable[[str], Awaitable[list[float]]]



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
        "Save an interested customer as a sales lead so the team can follow up. "
        "Call it once you have at least their name and email address."
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


def _local_day_window(start_date: date, days: int) -> tuple[datetime, datetime]:
    """Midnight at the start of start_date to midnight after the last day, in business time."""
    tz = get_settings().business_tz
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(start_date + timedelta(days=days), time.min, tzinfo=tz)
    return start, end


def build_tools(
    session: AsyncSession, *, embed_query_fn: EmbedQueryFn = embed_query
) -> dict[str, Tool]:

    async def create_lead_handler(args: CreateLeadArgs) -> dict[str, Any]:
        try:
            async with session.begin_nested():
                result = await create_lead(session, **args.model_dump())
        except InvalidLeadError as exc:
            return {"error": str(exc)}
        return {"lead_id": result.lead.id, "created": result.created}

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
    }
