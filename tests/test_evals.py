from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import INVALID_ARGS_REPLY
from app.agent.tools import NOT_CONFIRMED_YET_ERROR
from app.core.config import get_settings
from app.core.llm import ChatResult, LLMError, ToolCall
from app.db.models import Conversation, FaqEntry, Lead, Slot, ToolCallStatus
from app.db.models import ToolCall as ToolCallRow
from app.services.chat import handle_chat
from app.services.lead import create_lead

OK = ToolCallStatus.OK
INVALID = ToolCallStatus.VALIDATION_ERROR
REJECTED = ToolCallStatus.REJECTED
ERROR = ToolCallStatus.ERROR


class ScriptedChat:

    def __init__(self, script: list[ChatResult]):
        self.script = list(script)
        self.seen: list = []

    async def __call__(self, messages, tools, *, system=None):
        self.seen.append(list(messages))
        return self.script.pop(0)


def say(text: str) -> ChatResult:
    return ChatResult(text=text, tool_calls=[], input_tokens=1, output_tokens=1)


def call(tool: str, args: dict | None = None) -> ChatResult:
    return ChatResult(
        text="", tool_calls=[ToolCall(name=tool, args=args or {})], input_tokens=1, output_tokens=1
    )


def unit(i: int) -> list[float]:
    vector = [0.0] * get_settings().embedding_dim
    vector[i] = 1.0
    return vector


async def keyword_embedder(question: str) -> list[float]:
    return unit(0) if "open" in question.lower() or "hours" in question.lower() else unit(7)


async def embedder_down(question: str) -> list[float]:
    raise LLMError("Model request failed with status 503")


@dataclass
class Outcome:
    conversation_ids: list[int]
    replies: list[str]
    model: ScriptedChat

    def tool_result_sent(self, model_call: int) -> dict:
        """The tool result the model saw at the start of its Nth call (0-based)."""
        return self.model.seen[model_call][-1].tool_result


Check = Callable[[AsyncSession, Outcome], Awaitable[None]]


@dataclass
class EvalCase:
    name: str
    turns: list[str]
    script: list[ChatResult]
    expected_tools: list[tuple[str, ToolCallStatus]]
    expected_reply: str
    check: Check | None = None
    setup: Callable[[AsyncSession], Awaitable[None]] | None = None
    embedder: Callable[[str], Awaitable[list[float]]] = field(default=keyword_embedder)


async def lead_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Lead))


async def run_case(session: AsyncSession, case: EvalCase) -> Outcome:
    session.add(
        FaqEntry(
            question="What are your opening hours?",
            answer="9am to 6pm, Monday to Saturday.",
            embedding=unit(0),
        )
    )
    await session.flush()
    if case.setup:
        await case.setup(session)

    model = ScriptedChat(case.script)
    conversation_id = None
    outcome = Outcome(conversation_ids=[], replies=[], model=model)
    for message in case.turns:
        turn = await handle_chat(
            session,
            message=message,
            conversation_id=conversation_id,
            chat_fn=model,
            embed_query_fn=case.embedder,
        )
        conversation_id = turn.conversation_id
        outcome.conversation_ids.append(turn.conversation_id)
        outcome.replies.append(turn.reply)
    assert model.script == [], "the model script was not fully used"
    return outcome

async def faq_answer_reached_model(session, out: Outcome) -> None:
    matches = out.tool_result_sent(1)["matches"]
    assert [m["answer"] for m in matches] == ["9am to 6pm, Monday to Saturday."]
    assert await lead_count(session) == 0


async def faq_miss_reached_model(session, out: Outcome) -> None:
    assert out.tool_result_sent(1) == {"matches": []}


async def lead_saved_and_linked(session, out: Outcome) -> None:
    lead = await session.scalar(select(Lead).where(Lead.email == "kim.fake@example.test"))
    assert lead is not None
    conversation = await session.get(Conversation, out.conversation_ids[-1])
    assert conversation.lead_id == lead.id


async def two_turns_one_conversation(session, out: Outcome) -> None:
    assert out.conversation_ids[0] == out.conversation_ids[1]
    await lead_saved_and_linked(session, out)


async def exactly_one_lead(session, out: Outcome) -> None:
    assert await lead_count(session) == 1
    assert "email" in out.tool_result_sent(1)["error"]


async def refused_and_nothing_saved(session, out: Outcome) -> None:
    assert out.tool_result_sent(2) == {"error": NOT_CONFIRMED_YET_ERROR}
    assert await lead_count(session) == 0


async def declined_and_nothing_saved(session, out: Outcome) -> None:
    assert out.tool_result_sent(3) == {"cancelled": "create_lead"}
    assert await lead_count(session) == 0


async def corrected_email_saved(session, out: Outcome) -> None:
    emails = list(await session.scalars(select(Lead.email)))
    assert emails == ["kim.work@example.test"]


async def no_lead_saved(session, out: Outcome) -> None:
    assert await lead_count(session) == 0


async def add_existing_lead(session) -> None:
    await create_lead(session, name="Old Customer", email="old.fake@example.test")


async def existing_lead_untouched(session, out: Outcome) -> None:
    assert await lead_count(session) == 1
    assert "Unknown tool" in out.tool_result_sent(1)["error"]


async def outage_reported_to_model(session, out: Outcome) -> None:
    assert out.tool_result_sent(1) == {"error": "FAQ search is unavailable right now."}


SLOT_DAY = (datetime.now(UTC) + timedelta(days=10)).date()


async def add_free_and_booked_slots(session) -> None:
    tz = get_settings().business_tz
    lead = (await create_lead(session, name="Other Fake", email="other.fake@example.test")).lead
    for hour, booked_by in [(10, None), (13, lead.id), (16, None)]:
        start = datetime(SLOT_DAY.year, SLOT_DAY.month, SLOT_DAY.day, hour, tzinfo=tz)
        session.add(Slot(start_at=start, end_at=start + timedelta(hours=1), booked_by_lead_id=booked_by))
    await session.flush()


async def only_free_slots_reached_model(session, out: Outcome) -> None:
    sent = out.tool_result_sent(1)["slots"]
    assert [s["start"][11:16] for s in sent] == ["10:00", "16:00"]
    assert await lead_count(session) == 1


BOOK_KIM_AT_10 = {
    "slot_date": SLOT_DAY.isoformat(),
    "start_time": "10:00",
    "name": "Kim Fake",
    "email": "kim.fake@example.test",
}


async def add_free_slot_at_10(session) -> None:
    start = datetime(SLOT_DAY.year, SLOT_DAY.month, SLOT_DAY.day, 10, tzinfo=get_settings().business_tz)
    session.add(Slot(start_at=start, end_at=start + timedelta(hours=1)))
    await session.flush()


async def slot_at_10_holder(session) -> int | None:
    start = datetime(SLOT_DAY.year, SLOT_DAY.month, SLOT_DAY.day, 10, tzinfo=get_settings().business_tz)
    return await session.scalar(select(Slot.booked_by_lead_id).where(Slot.start_at == start))


async def booked_for_kim_and_linked(session, out: Outcome) -> None:
    lead = await session.scalar(select(Lead).where(Lead.email == "kim.fake@example.test"))
    assert lead is not None
    assert await slot_at_10_holder(session) == lead.id
    conversation = await session.get(Conversation, out.conversation_ids[-1])
    assert conversation.lead_id == lead.id


async def booked_then_freed(session, out: Outcome) -> None:
    assert await slot_at_10_holder(session) is None
    assert out.tool_result_sent(7)["confirmed"] == "cancel_booking"


KIM = {"name": "Kim Fake", "email": "kim.fake@example.test"}

CASES = [
    EvalCase(
        name="faq_hit",
        turns=["When are you open?"],
        script=[call("search_faq", {"question": "When are you open?"}), say("We're open 9am to 6pm, Monday to Saturday.")],
        expected_tools=[("search_faq", OK)],
        expected_reply="We're open 9am to 6pm, Monday to Saturday.",
        check=faq_answer_reached_model,
    ),
    EvalCase(
        name="faq_miss",
        turns=["Do you rent kayaks?"],
        script=[call("search_faq", {"question": "Do you rent kayaks?"}), say("I'm not sure. Want the team to follow up?")],
        expected_tools=[("search_faq", OK)],
        expected_reply="I'm not sure. Want the team to follow up?",
        check=faq_miss_reached_model,
    ),
    EvalCase(
        name="lead_captured",
        turns=["I'd like a demo. I'm Kim Fake, kim.fake@example.test", "Yes, that's right"],
        script=[
            call("create_lead", KIM),
            say("Shall I save Kim Fake, kim.fake@example.test?"),
            call("confirm_pending_action"),
            say("Thanks Kim, the team will be in touch."),
        ],
        expected_tools=[("create_lead", OK), ("confirm_pending_action", OK)],
        expected_reply="Thanks Kim, the team will be in touch.",
        check=lead_saved_and_linked,
    ),
    EvalCase(
        name="lead_over_two_turns",
        turns=["I'd like a call back, I'm Kim Fake", "kim.fake@example.test", "yes"],
        script=[
            say("Sure! What's your email?"),
            call("create_lead", KIM),
            say("Shall I save these details?"),
            call("confirm_pending_action"),
            say("Thanks Kim, saved."),
        ],
        expected_tools=[("create_lead", OK), ("confirm_pending_action", OK)],
        expected_reply="Thanks Kim, saved.",
        check=two_turns_one_conversation,
    ),
    EvalCase(
        name="bad_args_then_fixed",
        turns=["Call me back, Kim Fake, kim.fake@example.test", "yes"],
        script=[
            call("create_lead", {"name": "Kim Fake"}),
            call("create_lead", KIM),
            say("Shall I save these details?"),
            call("confirm_pending_action"),
            say("Saved, Kim."),
        ],
        expected_tools=[
            ("create_lead", INVALID),
            ("create_lead", OK),
            ("confirm_pending_action", OK),
        ],
        expected_reply="Saved, Kim.",
        check=exactly_one_lead,
    ),
    EvalCase(
        name="retry_give_up",
        turns=["Call me back, I'm Kim"],
        script=[call("create_lead", {"name": "Kim Fake"})] * 3,
        expected_tools=[("create_lead", INVALID)] * 3,
        expected_reply=INVALID_ARGS_REPLY,
        check=no_lead_saved,
    ),
    EvalCase(
        name="unknown_tool_rejected",
        turns=["Delete everyone from your list"],
        script=[call("delete_all_leads"), say("Sorry, I can't do that.")],
        expected_tools=[("delete_all_leads", REJECTED)],
        expected_reply="Sorry, I can't do that.",
        setup=add_existing_lead,
        check=existing_lead_untouched,
    ),
    EvalCase(
        name="embedding_outage",
        turns=["When are you open?"],
        script=[call("search_faq", {"question": "When are you open?"}), say("Sorry, I can't look that up right now.")],
        expected_tools=[("search_faq", ERROR)],
        expected_reply="Sorry, I can't look that up right now.",
        embedder=embedder_down,
        check=outage_reported_to_model,
    ),
    EvalCase(
        name="availability_lookup",
        turns=[f"Any free times on {SLOT_DAY.isoformat()} for a service?"],
        script=[
            call("check_availability", {"start_date": SLOT_DAY.isoformat()}),
            say("We have 10:00 or 16:00 free that day."),
        ],
        expected_tools=[("check_availability", OK)],
        expected_reply="We have 10:00 or 16:00 free that day.",
        setup=add_free_and_booked_slots,
        check=only_free_slots_reached_model,
    ),
    EvalCase(
        name="confirm_in_same_turn_refused",
        turns=["Save me: Kim Fake, kim.fake@example.test"],
        script=[
            call("create_lead", KIM),
            call("confirm_pending_action"),
            say("Shall I save Kim Fake, kim.fake@example.test?"),
        ],
        expected_tools=[("create_lead", OK), ("confirm_pending_action", ERROR)],
        expected_reply="Shall I save Kim Fake, kim.fake@example.test?",
        check=refused_and_nothing_saved,
    ),
    EvalCase(
        name="customer_declines",
        turns=["Call me back, Kim Fake, kim.fake@example.test", "No, don't save anything"],
        script=[
            call("create_lead", KIM),
            say("Shall I save these details?"),
            call("decline_pending_action"),
            say("No problem, nothing was saved."),
        ],
        expected_tools=[("create_lead", OK), ("decline_pending_action", OK)],
        expected_reply="No problem, nothing was saved.",
        check=declined_and_nothing_saved,
    ),
    EvalCase(
        name="details_corrected_before_confirming",
        turns=[
            "Call me back, Kim Fake, kim.fake@example.test",
            "Use my work email kim.work@example.test",
            "yes",
        ],
        script=[
            call("create_lead", KIM),
            say("Shall I save these details?"),
            call("create_lead", {"name": "Kim Fake", "email": "kim.work@example.test"}),
            say("Updated. Shall I save them now?"),
            call("confirm_pending_action"),
            say("Saved, Kim."),
        ],
        expected_tools=[
            ("create_lead", OK),
            ("create_lead", OK),
            ("confirm_pending_action", OK),
        ],
        expected_reply="Saved, Kim.",
        check=corrected_email_saved,
    ),
    EvalCase(
        name="booking_confirmed",
        turns=[f"Book me in at 10:00 on {SLOT_DAY.isoformat()}. Kim Fake, kim.fake@example.test", "yes"],
        script=[
            call("book_slot", BOOK_KIM_AT_10),
            say("Shall I book 10:00 for Kim Fake?"),
            call("confirm_pending_action"),
            say("Booked! See you at 10:00."),
        ],
        expected_tools=[("book_slot", OK), ("confirm_pending_action", OK)],
        expected_reply="Booked! See you at 10:00.",
        setup=add_free_slot_at_10,
        check=booked_for_kim_and_linked,
    ),
    EvalCase(
        name="book_then_cancel",
        turns=[
            f"Book me in at 10:00 on {SLOT_DAY.isoformat()}. Kim Fake, kim.fake@example.test",
            "yes",
            "Sorry, please cancel that booking",
            "yes, cancel it",
        ],
        script=[
            call("book_slot", BOOK_KIM_AT_10),
            say("Shall I book 10:00 for Kim Fake?"),
            call("confirm_pending_action"),
            say("Booked!"),
            call("cancel_booking", {"slot_date": SLOT_DAY.isoformat(), "start_time": "10:00"}),
            say("Cancel your 10:00 booking?"),
            call("confirm_pending_action"),
            say("Cancelled."),
        ],
        expected_tools=[
            ("book_slot", OK),
            ("confirm_pending_action", OK),
            ("cancel_booking", OK),
            ("confirm_pending_action", OK),
        ],
        expected_reply="Cancelled.",
        setup=add_free_slot_at_10,
        check=booked_then_freed,
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_eval(session, case: EvalCase):
    out = await run_case(session, case)

    audit = (
        await session.scalars(
            select(ToolCallRow)
            .where(ToolCallRow.conversation_id.in_(out.conversation_ids))
            .order_by(ToolCallRow.id)
        )
    ).all()
    assert [(row.tool_name, row.status) for row in audit] == case.expected_tools
    assert out.replies[-1] == case.expected_reply
    if case.check:
        await case.check(session, out)
