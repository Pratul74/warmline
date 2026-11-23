from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.agent.loop import run_tool
from app.agent.tools import (
    ALREADY_WAITING_NEXT_STEP,
    NOT_CONFIRMED_YET_ERROR,
    NOTHING_PENDING_ERROR,
    build_tools,
)
from app.core.llm import ToolCall
from app.db.models import Conversation, Lead, PendingAction, PendingActionStatus
from app.services.pending_actions import (
    PendingActionExpiredError,
    PendingActionNotPendingError,
    claim_pending_action,
    create_pending_action,
)

PENDING = PendingActionStatus.PENDING
ROBIN = {"name": " Robin Fake ", "email": "Robin@Example.TEST"}


@pytest.fixture
async def conversation_id(session) -> int:
    conversation = Conversation()
    session.add(conversation)
    await session.flush()
    return conversation.id


async def lead_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Lead))


async def statuses(session, conversation_id: int) -> list[PendingActionStatus]:
    rows = await session.scalars(
        select(PendingAction.status)
        .where(PendingAction.conversation_id == conversation_id)
        .order_by(PendingAction.id)
    )
    return list(rows)


async def expire_all(session, conversation_id: int) -> None:
    await session.execute(
        update(PendingAction)
        .where(PendingAction.conversation_id == conversation_id)
        .values(expires_at=func.now() - timedelta(minutes=1))
    )


class Request:

    def __init__(self, session, conversation_id: int):
        self.tools = build_tools(session, conversation_id=conversation_id)

    async def call(self, name: str, args: dict | None = None) -> tuple[dict, str]:
        return await run_tool(ToolCall(name=name, args=args or {}), self.tools)


async def test_service_stores_the_cleaned_tool_name(session, conversation_id):
    action = await create_pending_action(
        session, conversation_id=conversation_id, tool_name="  create_lead ", arguments={"a": 1}
    )

    assert action.tool_name == "create_lead"
    assert action.status is PENDING


async def test_service_claim_returns_the_action_and_a_second_claim_fails(session, conversation_id):
    action = await create_pending_action(
        session, conversation_id=conversation_id, tool_name="create_lead", arguments={}
    )

    claimed = await claim_pending_action(
        session, action_id=action.id, conversation_id=conversation_id
    )
    assert claimed.id == action.id
    assert claimed.status is PendingActionStatus.CONFIRMED

    with pytest.raises(PendingActionNotPendingError):
        await claim_pending_action(session, action_id=action.id, conversation_id=conversation_id)


async def test_service_claim_of_an_expired_action_fails(session, conversation_id):
    action = await create_pending_action(
        session, conversation_id=conversation_id, tool_name="create_lead", arguments={}
    )
    await expire_all(session, conversation_id)

    with pytest.raises(PendingActionExpiredError):
        await claim_pending_action(session, action_id=action.id, conversation_id=conversation_id)


async def test_create_lead_only_proposes_and_saves_nothing(session, conversation_id):
    output, status = await Request(session, conversation_id).call("create_lead", ROBIN)

    assert status == "ok"
    assert output["status"] == "awaiting_confirmation"
    assert output["details"] == {
        "name": "Robin Fake",
        "email": "robin@example.test",
        "phone": None,
        "notes": None,
    }
    assert await lead_count(session) == 0
    assert await statuses(session, conversation_id) == [PENDING]


async def test_invalid_email_is_rejected_before_asking_the_customer(session, conversation_id):
    output, status = await Request(session, conversation_id).call(
        "create_lead", {"name": "Robin", "email": "no-at-sign"}
    )

    assert (status, output) == ("error", {"error": "Invalid email address"})
    assert await statuses(session, conversation_id) == []


async def test_confirm_in_the_same_request_is_refused(session, conversation_id):
    request = Request(session, conversation_id)
    await request.call("create_lead", ROBIN)

    output, status = await request.call("confirm_pending_action")

    assert (status, output) == ("error", {"error": NOT_CONFIRMED_YET_ERROR})
    assert await lead_count(session) == 0
    assert await statuses(session, conversation_id) == [PENDING]


async def test_confirm_in_a_later_request_saves_the_lead_once(session, conversation_id):
    await Request(session, conversation_id).call("create_lead", ROBIN)

    output, status = await Request(session, conversation_id).call("confirm_pending_action")
    again, again_status = await Request(session, conversation_id).call("confirm_pending_action")

    lead = await session.scalar(select(Lead))
    assert status == "ok"
    assert output == {"confirmed": "create_lead", "lead_id": lead.id, "created": True}
    assert (lead.name, lead.email) == ("Robin Fake", "robin@example.test")
    assert (again_status, again) == ("error", {"error": NOTHING_PENDING_ERROR})
    assert await lead_count(session) == 1
    assert await statuses(session, conversation_id) == [PendingActionStatus.CONFIRMED]


async def test_cancel_drops_the_action_and_nothing_is_saved(session, conversation_id):
    await Request(session, conversation_id).call("create_lead", ROBIN)

    cancelled, _ = await Request(session, conversation_id).call("decline_pending_action")
    confirm, _ = await Request(session, conversation_id).call("confirm_pending_action")
    nothing, nothing_status = await Request(session, conversation_id).call("decline_pending_action")

    assert cancelled == {"cancelled": "create_lead"}
    assert confirm == {"error": NOTHING_PENDING_ERROR}
    assert (nothing_status, nothing) == ("ok", {"status": "nothing_to_cancel"})
    assert await lead_count(session) == 0
    assert await statuses(session, conversation_id) == [PendingActionStatus.CANCELLED]


async def test_corrected_details_replace_the_earlier_proposal(session, conversation_id):
    await Request(session, conversation_id).call("create_lead", ROBIN)
    await Request(session, conversation_id).call(
        "create_lead", {"name": "Robin Fake", "email": "robin.work@example.test"}
    )

    await Request(session, conversation_id).call("confirm_pending_action")

    emails = list(await session.scalars(select(Lead.email)))
    assert emails == ["robin.work@example.test"]
    assert await statuses(session, conversation_id) == [
        PendingActionStatus.CANCELLED,
        PendingActionStatus.CONFIRMED,
    ]


async def test_expired_action_cannot_be_confirmed(session, conversation_id):
    await Request(session, conversation_id).call("create_lead", ROBIN)
    await expire_all(session, conversation_id)

    output, status = await Request(session, conversation_id).call("confirm_pending_action")

    assert (status, output) == ("error", {"error": NOTHING_PENDING_ERROR})
    assert await lead_count(session) == 0


async def test_another_conversation_cannot_confirm(session, conversation_id):
    other = Conversation()
    session.add(other)
    await session.flush()
    await Request(session, conversation_id).call("create_lead", ROBIN)

    output, _ = await Request(session, other.id).call("confirm_pending_action")

    assert output == {"error": NOTHING_PENDING_ERROR}
    assert await lead_count(session) == 0


async def test_failed_write_undoes_the_claim_so_the_action_stays_pending(session, conversation_id):
    await Request(session, conversation_id).call("create_lead", ROBIN)
    await session.execute(
        update(PendingAction)
        .where(PendingAction.conversation_id == conversation_id)
        .values(arguments={"name": "Robin", "email": "broken"})
    )

    output, status = await Request(session, conversation_id).call("confirm_pending_action")

    assert status == "error"
    assert "internal error" in output["error"]
    assert await lead_count(session) == 0
    assert await statuses(session, conversation_id) == [PENDING]


async def test_confirm_rejects_arguments(session, conversation_id):
    output, status = await Request(session, conversation_id).call(
        "confirm_pending_action", {"action_id": 1}
    )

    assert status == "invalid_args"
    assert "action_id" in output["error"]


async def test_identical_proposal_in_a_later_request_keeps_the_action_and_confirm_works(
    session, conversation_id
):
    await Request(session, conversation_id).call("create_lead", ROBIN)

    yes_turn = Request(session, conversation_id)
    repeated, _ = await yes_turn.call("create_lead", ROBIN)
    confirmed, status = await yes_turn.call("confirm_pending_action")

    assert repeated["next_step"] == ALREADY_WAITING_NEXT_STEP
    assert status == "ok" and confirmed["confirmed"] == "create_lead"
    assert await lead_count(session) == 1
    assert await statuses(session, conversation_id) == [PendingActionStatus.CONFIRMED]


async def test_changed_proposal_in_a_later_request_still_replaces_and_needs_a_new_yes(
    session, conversation_id
):
    await Request(session, conversation_id).call("create_lead", ROBIN)

    turn = Request(session, conversation_id)
    changed, _ = await turn.call("create_lead", {**ROBIN, "email": "robin.new@example.test"})
    refused, _ = await turn.call("confirm_pending_action")

    assert changed["next_step"] != ALREADY_WAITING_NEXT_STEP
    assert refused == {"error": NOT_CONFIRMED_YET_ERROR}
    assert await lead_count(session) == 0
    assert await statuses(session, conversation_id) == [PendingActionStatus.CANCELLED, PENDING]


async def test_identical_proposal_twice_in_the_same_request_cannot_be_confirmed(
    session, conversation_id
):
    turn = Request(session, conversation_id)
    await turn.call("create_lead", ROBIN)
    repeated, _ = await turn.call("create_lead", ROBIN)

    refused, _ = await turn.call("confirm_pending_action")

    assert repeated["next_step"] != ALREADY_WAITING_NEXT_STEP
    assert refused == {"error": NOT_CONFIRMED_YET_ERROR}
    assert await lead_count(session) == 0
