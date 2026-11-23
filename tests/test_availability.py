from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.agent.loop import run_tool
from app.agent.prompts import build_system_prompt
from app.agent.tools import MAX_SLOTS_RETURNED, build_tools
from app.core.config import Settings, get_settings
from app.core.llm import ChatResult, ToolCall
from app.db.models import Slot
from app.services.booking import InvalidBookingRequestError, check_availability
from app.services.chat import handle_chat
from app.services.lead import create_lead

HOUR = timedelta(hours=1)


@pytest.fixture(autouse=True)
def business_in_utc(monkeypatch):
    monkeypatch.setattr(get_settings(), "business_timezone", "UTC")


def utc_day(days_from_today: int) -> datetime:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=days_from_today)


async def add_slot(session, start: datetime, *, booked_by: int | None = None) -> Slot:
    slot = Slot(start_at=start, end_at=start + HOUR, booked_by_lead_id=booked_by)
    session.add(slot)
    await session.flush()
    return slot


async def test_service_returns_only_free_future_slots_in_the_window_earliest_first(session):
    day = utc_day(10)
    lead = (await create_lead(session, name="Booked Fake", email="booked@example.test")).lead
    later = await add_slot(session, day + 15 * HOUR)
    earlier = await add_slot(session, day + 10 * HOUR)
    await add_slot(session, day + 12 * HOUR, booked_by=lead.id)
    await add_slot(session, day + 30 * HOUR)
    await add_slot(session, utc_day(-1) + 10 * HOUR)

    slots = await check_availability(
        session, window_start=utc_day(-2), window_end=day + 24 * HOUR
    )

    assert [s.id for s in slots] == [earlier.id, later.id]


async def test_service_respects_the_limit(session):
    day = utc_day(10)
    for hour in range(8, 13):
        await add_slot(session, day + hour * HOUR)

    slots = await check_availability(session, window_start=day, window_end=day + 24 * HOUR, limit=2)

    assert len(slots) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_start": datetime(2030, 1, 1), "window_end": datetime(2030, 1, 2, tzinfo=UTC)},
        {"window_start": datetime(2030, 1, 2, tzinfo=UTC), "window_end": datetime(2030, 1, 1, tzinfo=UTC)},
        {"window_start": datetime(2030, 1, 1, tzinfo=UTC), "window_end": datetime(2030, 1, 2, tzinfo=UTC), "limit": 0},
    ],
    ids=["naive_datetime", "end_before_start", "zero_limit"],
)
async def test_service_rejects_bad_requests(session, kwargs):
    with pytest.raises(InvalidBookingRequestError):
        await check_availability(session, **kwargs)


async def run_check(session, args: dict) -> tuple[dict, str]:
    return await run_tool(ToolCall(name="check_availability", args=args), build_tools(session))


async def test_tool_uses_the_business_time_zone_for_the_day(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "business_timezone", "Asia/Kolkata")
    day = utc_day(10)
    just_after_local_midnight = await add_slot(session, day - 5 * HOUR)
    morning = await add_slot(session, day + 4.5 * HOUR)
    await add_slot(session, day + 20 * HOUR)

    output, status = await run_check(session, {"start_date": day.date().isoformat()})

    assert status == "ok"
    assert output["timezone"] == "Asia/Kolkata"
    assert [s["slot_id"] for s in output["slots"]] == [just_after_local_midnight.id, morning.id]
    second = output["slots"][1]
    assert second["start"] == f"{day.date().isoformat()}T10:00:00+05:30"
    assert second["end"] == f"{day.date().isoformat()}T11:00:00+05:30"
    assert second["weekday"] == day.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%A")


async def test_tool_days_argument_widens_the_window(session):
    day = utc_day(10)
    await add_slot(session, day + 10 * HOUR)
    await add_slot(session, day + 2 * 24 * HOUR + 10 * HOUR)

    one_day, _ = await run_check(session, {"start_date": day.date().isoformat()})
    three_days, _ = await run_check(session, {"start_date": day.date().isoformat(), "days": 3})

    assert (len(one_day["slots"]), len(three_days["slots"])) == (1, 2)


async def test_tool_returns_at_most_the_cap(session):
    day = utc_day(10)
    for i in range(MAX_SLOTS_RETURNED + 3):
        await add_slot(session, day + i * HOUR)

    output, _ = await run_check(session, {"start_date": day.date().isoformat()})

    assert len(output["slots"]) == MAX_SLOTS_RETURNED


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"start_date": "next thursday"},
        {"start_date": "2030-02-30"},
        {"start_date": "2030-01-01", "days": 0},
        {"start_date": "2030-01-01", "days": 15},
        {"start_date": "2030-01-01", "time": "10:00"},
    ],
    ids=["missing_date", "words", "impossible_date", "zero_days", "too_many_days", "unknown_field"],
)
async def test_tool_rejects_bad_arguments(session, args):
    output, status = await run_check(session, args)

    assert status == "invalid_args"
    assert output["error"].startswith("Invalid arguments.")


def test_prompt_contains_todays_date_and_zone():
    prompt = build_system_prompt(datetime(2026, 11, 26, 9, 30, tzinfo=ZoneInfo("Europe/London")))

    assert "Today is Thursday, 26 November 2026." in prompt
    assert "Europe/London" in prompt


async def test_handle_chat_sends_the_dated_prompt_to_the_model(session):
    seen_system: list[str] = []

    async def fake_chat(messages, tools, *, system=None):
        seen_system.append(system)
        return ChatResult(text="Hi!", tool_calls=[], input_tokens=1, output_tokens=1)

    await handle_chat(
        session,
        message="hi",
        chat_fn=fake_chat,
        now=datetime(2026, 12, 1, 8, 0, tzinfo=UTC),
    )

    assert "Today is Tuesday, 1 December 2026." in seen_system[0]



def test_unknown_business_timezone_is_rejected_at_startup():
    with pytest.raises(ValidationError, match="Unknown time zone"):
        Settings(business_timezone="Mars/Olympus_Mons")

