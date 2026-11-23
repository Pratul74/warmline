from uuid import uuid4

import pytest

from app.db.models import ToolCallStatus
from app.services.tool_calls import InvalidToolCallError, get_tool_history, log_tool_call
from tests import factories


async def new_conversation(session) -> int:
    return (await factories.new_conversation(session)).id


async def log(session, conversation_id, request_id, step, name, status=ToolCallStatus.OK, **kw):
    return await log_tool_call(
        session,
        conversation_id=conversation_id,
        request_id=request_id,
        step_number=step,
        tool_name=name,
        arguments={"q": name},
        status=status,
        duration_ms=5,
        **kw,
    )


async def test_logged_call_is_stored_with_its_outcome(session):
    conversation_id = await new_conversation(session)
    request_id = uuid4()

    row = await log(
        session, conversation_id, request_id, 1, "search_faq", result={"matches": []}
    )

    assert row.id is not None
    assert (row.tool_name, row.status, row.request_id) == ("search_faq", ToolCallStatus.OK, request_id)
    assert row.arguments == {"q": "search_faq"}
    assert row.result == {"matches": []}
    assert row.error_message is None


async def test_history_is_oldest_first_and_can_filter_by_request(session):
    conversation_id = await new_conversation(session)
    first_request, second_request = uuid4(), uuid4()
    await log(session, conversation_id, first_request, 1, "a")
    await log(session, conversation_id, first_request, 2, "b")
    await log(session, conversation_id, second_request, 1, "c")

    everything = await get_tool_history(session, conversation_id=conversation_id)
    newest_two = await get_tool_history(session, conversation_id=conversation_id, limit=2)
    first_only = await get_tool_history(
        session, conversation_id=conversation_id, request_id=first_request
    )

    assert [r.tool_name for r in everything] == ["a", "b", "c"]
    assert [r.tool_name for r in newest_two] == ["b", "c"]
    assert [r.tool_name for r in first_only] == ["a", "b"]


async def test_failed_call_must_carry_an_error_message(session):
    conversation_id = await new_conversation(session)

    with pytest.raises(InvalidToolCallError):
        await log(session, conversation_id, uuid4(), 1, "x", status=ToolCallStatus.ERROR)
