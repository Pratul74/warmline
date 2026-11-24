import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.agent.loop import FALLBACK_REPLY, INVALID_ARGS_REPLY
from app.agent.tools import describe_completed_action
from app.api.chat import get_chat_fn, get_embed_query_fn
from app.core.config import EMBEDDING_DIM, get_settings
from app.core.llm import ChatResult, LLMError, LLMRateLimitError, ToolCall
from app.db.models import Conversation, Lead, Message, RequestLog, ToolCallStatus
from app.db.models import ToolCall as ToolCallRow
from app.db.session import get_session
from app.main import app
from tests.factories import auth_headers, new_account, new_faq, new_slot


class ScriptedChat:
    def __init__(self, script: list):
        self.script = list(script)
        self.seen: list = []

    async def __call__(self, messages, tools, *, system=None):
        self.seen.append(list(messages))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def no_real_embeddings(question: str) -> list[float]:
    raise RuntimeError("Tests must never call the real embedding API")


def text(reply: str) -> ChatResult:
    return ChatResult(text=reply, tool_calls=[], input_tokens=1, output_tokens=1)


@pytest_asyncio.fixture
async def account(session):
    return await new_account(session)


@pytest_asyncio.fixture
async def client_with(session, account):
    headers = auth_headers(account)

    async def override_session():
        yield session

    def build(fake: ScriptedChat, embed=no_real_embeddings) -> AsyncClient:
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_chat_fn] = lambda: fake
        app.dependency_overrides[get_embed_query_fn] = lambda: embed
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)

    yield build
    app.dependency_overrides.clear()


async def count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def test_new_conversation_is_created_and_both_messages_saved(client_with, session):
    fake = ScriptedChat([text("Hi! How can I help?")])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "  Hello  "})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hi! How can I help?"
    rows = (
        await session.scalars(
            select(Message).where(Message.conversation_id == body["conversation_id"]).order_by(Message.id)
        )
    ).all()
    assert [(m.role.value, m.content) for m in rows] == [
        ("user", "Hello"),
        ("assistant", "Hi! How can I help?"),
    ]


async def test_follow_up_sends_earlier_messages_to_the_model(client_with):
    fake = ScriptedChat([text("Hi Sam!"), text("You said your name is Sam.")])
    async with client_with(fake) as client:
        first = await client.post("/chat", json={"message": "I'm Sam"})
        conv_id = first.json()["conversation_id"]
        second = await client.post("/chat", json={"conversation_id": conv_id, "message": "Who am I?"})

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conv_id
    history_sent = [(m.role, m.text) for m in fake.seen[1]]
    assert history_sent == [("user", "I'm Sam"), ("assistant", "Hi Sam!"), ("user", "Who am I?")]


async def test_unknown_conversation_returns_404_without_calling_model(client_with):
    fake = ScriptedChat([])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"conversation_id": 999999, "message": "hi"})

    assert response.status_code == 404
    assert fake.seen == []


async def test_model_failure_returns_503_and_saves_nothing(client_with, session):
    conversations_before = await count(session, Conversation)
    messages_before = await count(session, Message)
    fake = ScriptedChat([LLMError("Model request failed with status 500")])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "hi"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Model request failed with status 500"
    assert await count(session, Conversation) == conversations_before
    assert await count(session, Message) == messages_before


async def test_invalid_messages_are_rejected_before_the_model(client_with):
    fake = ScriptedChat([])
    async with client_with(fake) as client:
        blank = await client.post("/chat", json={"message": "   "})
        too_long = await client.post("/chat", json={"message": "x" * 2001})
        bad_id = await client.post("/chat", json={"conversation_id": 0, "message": "hi"})

    assert (blank.status_code, too_long.status_code, bad_id.status_code) == (422, 422, 422)
    assert fake.seen == []


def lead_call(email: str) -> ChatResult:
    call = ToolCall(name="create_lead", args={"name": "Robin Fake", "email": email})
    return ChatResult(text="", tool_calls=[call], input_tokens=1, output_tokens=1)


CONFIRM = ChatResult(
    text="", tool_calls=[ToolCall(name="confirm_pending_action", args={})], input_tokens=1, output_tokens=1
)


async def test_lead_is_saved_only_after_the_customer_confirms(client_with, session):
    fake = ScriptedChat(
        [
            lead_call("Robin@Example.test"),
            text("Shall I save Robin Fake, robin@example.test?"),
            CONFIRM,
            text("Saved. The team will be in touch."),
        ]
    )
    async with client_with(fake) as client:
        first = await client.post("/chat", json={"message": "I'm Robin, robin@example.test, want a demo"})
        conv_id = first.json()["conversation_id"]
        after_first = await session.scalar(select(Lead).where(Lead.email == "robin@example.test"))
        second = await client.post("/chat", json={"conversation_id": conv_id, "message": "yes"})

    assert (first.status_code, second.status_code) == (200, 200)
    assert after_first is None
    proposal = fake.seen[1][-1].tool_result
    assert proposal["status"] == "awaiting_confirmation"
    assert proposal["details"]["email"] == "robin@example.test"
    lead = await session.scalar(select(Lead).where(Lead.email == "robin@example.test"))
    assert lead is not None and lead.name == "Robin Fake"
    assert fake.seen[3][-1].tool_result == {"confirmed": "create_lead", "lead_id": lead.id, "created": True}
    conversation = await session.get(Conversation, conv_id)
    assert conversation.lead_id == lead.id


async def test_model_failure_after_confirming_rolls_back_and_the_action_stays_pending(
    client_with, session
):
    fake = ScriptedChat(
        [
            lead_call("rollback@example.test"),
            text("Shall I save these details?"),
            CONFIRM,
            LLMError("Model request failed with status 500"),
            CONFIRM,
            text("Saved."),
        ]
    )
    async with client_with(fake) as client:
        first = await client.post("/chat", json={"message": "save me"})
        conv_id = first.json()["conversation_id"]
        failed = await client.post("/chat", json={"conversation_id": conv_id, "message": "yes"})
        no_lead_after_failure = (
            await session.scalar(select(Lead).where(Lead.email == "rollback@example.test")) is None
        )
        retried = await client.post("/chat", json={"conversation_id": conv_id, "message": "yes"})

    assert failed.status_code == 503
    assert no_lead_after_failure
    assert retried.status_code == 200
    assert await session.scalar(select(Lead).where(Lead.email == "rollback@example.test")) is not None
    failed_log = await session.scalar(
        select(RequestLog).where(RequestLog.conversation_id == conv_id, RequestLog.status != "ok")
    )
    confirms = (
        await session.scalars(
            select(ToolCallRow.request_id).where(
                ToolCallRow.conversation_id == conv_id, ToolCallRow.tool_name == "confirm_pending_action"
            )
        )
    ).all()
    assert failed_log is not None and failed_log.request_id in confirms
    assert len(confirms) == 2


async def test_search_faq_tool_answer_is_sent_back_to_the_model(client_with, session, account):
    vector = [0.0] * EMBEDDING_DIM
    vector[0] = 1.0
    await new_faq(
        session, account.id, question="What are your hours?", answer="9am to 6pm.", embedding=vector
    )

    async def fake_embed(question: str) -> list[float]:
        return vector

    call = ToolCall(name="search_faq", args={"question": "When are you open?"})
    fake = ScriptedChat(
        [
            ChatResult(text="", tool_calls=[call], input_tokens=1, output_tokens=1),
            text("We are open 9am to 6pm."),
        ]
    )
    async with client_with(fake, embed=fake_embed) as client:
        response = await client.post("/chat", json={"message": "When are you open?"})

    assert response.status_code == 200
    assert response.json()["reply"] == "We are open 9am to 6pm."
    tool_message = fake.seen[1][-1]
    assert tool_message.tool_name == "search_faq"
    assert tool_message.tool_result["matches"][0]["answer"] == "9am to 6pm."


async def test_every_tool_call_is_written_to_the_audit_log(client_with, session):
    async def fake_embed(question: str) -> list[float]:
        return [1.0] + [0.0] * (EMBEDDING_DIM - 1)

    fake = ScriptedChat(
        [
            ChatResult(
                text="",
                tool_calls=[
                    ToolCall(name="search_faq", args={"question": "hours?"}),
                    ToolCall(name="create_lead", args={"name": "No Email"}),
                ],
                input_tokens=1,
                output_tokens=1,
            ),
            ChatResult(
                text="",
                tool_calls=[ToolCall(name="delete_all_leads", args={})],
                input_tokens=1,
                output_tokens=1,
            ),
            text("Done."),
        ]
    )
    async with client_with(fake, embed=fake_embed) as client:
        response = await client.post("/chat", json={"message": "hi"})

    assert response.status_code == 200
    rows = (
        await session.scalars(
            select(ToolCallRow)
            .where(ToolCallRow.conversation_id == response.json()["conversation_id"])
            .order_by(ToolCallRow.id)
        )
    ).all()
    assert [(r.step_number, r.tool_name, r.status) for r in rows] == [
        (1, "search_faq", ToolCallStatus.OK),
        (1, "create_lead", ToolCallStatus.VALIDATION_ERROR),
        (2, "delete_all_leads", ToolCallStatus.REJECTED),
    ]
    assert len({r.request_id for r in rows}) == 1
    assert rows[0].result == {"matches": []}
    assert rows[1].result is None and "email" in rows[1].error_message
    assert rows[1].arguments == {"name": "No Email"}
    assert "Unknown tool" in rows[2].error_message


async def test_rate_limit_returns_429_and_saves_nothing(client_with, session):
    conversations_before = await count(session, Conversation)
    fake = ScriptedChat([LLMRateLimitError("Model rate limit reached, please try again shortly")])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "hi"})

    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"]
    assert await count(session, Conversation) == conversations_before


def db_down(statement: str) -> OperationalError:
    return OperationalError(statement, {}, Exception("connection to server at 10.9.8.7 port 5432 lost"))


async def test_database_failure_on_save_returns_clean_503_and_saves_nothing(
    client_with, session, monkeypatch
):
    conversations_before = await count(session, Conversation)
    messages_before = await count(session, Message)

    async def failing_commit():
        raise db_down("COMMIT")

    monkeypatch.setattr(session, "commit", failing_commit)
    fake = ScriptedChat([lead_call("dbdown@example.test"), text("Saved!")])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "save me"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Service temporarily unavailable, please try again"}
    assert "10.9.8.7" not in response.text and "COMMIT" not in response.text
    assert await count(session, Conversation) == conversations_before
    assert await count(session, Message) == messages_before
    assert await session.scalar(select(Lead).where(Lead.email == "dbdown@example.test")) is None


@pytest.mark.parametrize(
    "error",
    [db_down("SELECT conversations"), ConnectionRefusedError("connect to 10.9.8.7 refused")],
)
async def test_database_failure_before_the_model_returns_503_without_calling_it(
    client_with, session, monkeypatch, error
):
    async def failing_get(*args, **kwargs):
        raise error

    monkeypatch.setattr(session, "get", failing_get)
    fake = ScriptedChat([])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"conversation_id": 1, "message": "hi"})

    assert response.status_code == 503
    assert "10.9.8.7" not in response.text
    assert fake.seen == []


async def test_check_availability_runs_through_chat_and_is_audited(
    client_with, session, account, monkeypatch
):
    monkeypatch.setattr(get_settings(), "business_timezone", "UTC")
    from datetime import UTC, datetime, timedelta

    start = (datetime.now(UTC) + timedelta(days=5)).replace(hour=10, minute=0, second=0, microsecond=0)
    await new_slot(session, account.id, start)
    call = ToolCall(name="check_availability", args={"start_date": start.date().isoformat()})
    fake = ScriptedChat(
        [ChatResult(text="", tool_calls=[call], input_tokens=1, output_tokens=1), text("10:00 is free.")]
    )
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "Anything free?"})

    assert response.status_code == 200
    assert len(fake.seen[1][-1].tool_result["slots"]) == 1
    row = await session.scalar(
        select(ToolCallRow).where(ToolCallRow.conversation_id == response.json()["conversation_id"])
    )
    assert (row.tool_name, row.status) == ("check_availability", ToolCallStatus.OK)


def faq_call(question: str) -> ChatResult:
    return ChatResult(
        text="", tool_calls=[ToolCall(name="search_faq", args={"question": question})], input_tokens=1, output_tokens=1
    )


async def test_step_limit_through_chat_returns_fallback_and_logs_every_step(client_with, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_max_steps", 3)

    async def fake_embed(question: str) -> list[float]:
        return [1.0] + [0.0] * (EMBEDDING_DIM - 1)

    fake = ScriptedChat([faq_call(f"question {i}") for i in range(10)])
    async with client_with(fake, embed=fake_embed) as client:
        response = await client.post("/chat", json={"message": "hours?"})

    assert response.status_code == 200
    assert response.json()["reply"] == FALLBACK_REPLY
    assert len(fake.seen) == 3
    conv_id = response.json()["conversation_id"]
    rows = (
        await session.scalars(
            select(ToolCallRow).where(ToolCallRow.conversation_id == conv_id).order_by(ToolCallRow.id)
        )
    ).all()
    assert [(r.step_number, r.tool_name, r.status) for r in rows] == [
        (step, "search_faq", ToolCallStatus.OK) for step in (1, 2, 3)
    ]
    log = await session.scalar(select(RequestLog).where(RequestLog.conversation_id == conv_id))
    assert (log.steps, log.input_tokens) == (3, 3)


async def test_crashing_tool_through_chat_is_audited_without_leaking_details(client_with, session):
    secret = "internal-token-abc123 at 10.9.8.7"

    async def crashing_embed(question: str) -> list[float]:
        raise RuntimeError(secret)

    fake = ScriptedChat([faq_call("hours?"), text("Sorry, I can't look that up right now.")])
    async with client_with(fake, embed=crashing_embed) as client:
        response = await client.post("/chat", json={"message": "hours?"})

    assert response.status_code == 200
    assert response.json()["reply"] == "Sorry, I can't look that up right now."
    sent_to_model = fake.seen[1][-1].tool_result
    assert sent_to_model == {"error": "Tool 'search_faq' failed with an internal error."}
    row = await session.scalar(
        select(ToolCallRow).where(ToolCallRow.conversation_id == response.json()["conversation_id"])
    )
    assert row.status == ToolCallStatus.ERROR
    assert row.error_message == "Tool 'search_faq' failed with an internal error."
    assert secret not in response.text
    assert secret not in (row.error_message or "") and row.result is None


def test_completed_actions_are_described_for_the_customer():
    booked = {"confirmed": "book_slot", "booked": {"start": "2030-01-07T10:00:00+00:00"}, "lead_id": 1}
    cancelled = {"confirmed": "cancel_booking", "cancelled_booking": {"start": "2030-01-07T16:00:00+05:30"}}

    assert describe_completed_action(booked) == "Your booking for Monday 7 January at 10:00 is confirmed."
    assert describe_completed_action(cancelled) == "Your booking for Monday 7 January at 16:00 is cancelled."
    assert describe_completed_action({"confirmed": "create_lead", "lead_id": 1, "created": True}) == (
        "Your details are saved and the team will be in touch."
    )
    assert describe_completed_action({"error": "nothing pending"}) is None


async def test_step_limit_after_a_confirmed_booking_still_tells_the_customer(
    client_with, session, account, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(get_settings(), "business_timezone", "UTC")
    monkeypatch.setattr(get_settings(), "agent_max_steps", 2)
    start = (datetime.now(UTC) + timedelta(days=5)).replace(hour=10, minute=0, second=0, microsecond=0)
    slot = await new_slot(session, account.id, start)
    book = ToolCall(
        name="book_slot",
        args={
            "slot_date": start.date().isoformat(),
            "start_time": "10:00",
            "name": "Kim Fake",
            "email": "kim.steps@example.test",
        },
    )
    loop_forever = ToolCall(name="check_availability", args={"start_date": start.date().isoformat()})
    fake = ScriptedChat(
        [
            ChatResult(text="", tool_calls=[book], input_tokens=1, output_tokens=1),
            text("Shall I book 10:00?"),
            CONFIRM,
            ChatResult(text="", tool_calls=[loop_forever], input_tokens=1, output_tokens=1),
        ]
    )
    async with client_with(fake) as client:
        first = await client.post("/chat", json={"message": "Book me at 10:00, Kim Fake, kim.steps@example.test"})
        conv_id = first.json()["conversation_id"]
        second = await client.post("/chat", json={"conversation_id": conv_id, "message": "yes"})

    expected = f"Your booking for {start:%A} {start.day} {start:%B} at 10:00 is confirmed. {FALLBACK_REPLY}"
    assert second.status_code == 200
    assert second.json()["reply"] == expected
    await session.refresh(slot)
    assert slot.booked_by_lead_id is not None
    saved = await session.scalar(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.id.desc()).limit(1)
    )
    assert saved.content == expected


async def test_giving_up_after_a_confirmed_lead_still_tells_the_customer(client_with, session):
    bad_lead = ChatResult(
        text="", tool_calls=[ToolCall(name="create_lead", args={"name": "No Email"})], input_tokens=1, output_tokens=1
    )
    fake = ScriptedChat(
        [
            lead_call("giveup@example.test"),
            text("Shall I save your details?"),
            CONFIRM,
            bad_lead,
            bad_lead,
            bad_lead,
        ]
    )
    async with client_with(fake) as client:
        first = await client.post("/chat", json={"message": "save me"})
        conv_id = first.json()["conversation_id"]
        second = await client.post("/chat", json={"conversation_id": conv_id, "message": "yes"})

    assert second.json()["reply"] == f"Your details are saved and the team will be in touch. {INVALID_ARGS_REPLY}"
    assert await session.scalar(select(Lead).where(Lead.email == "giveup@example.test")) is not None
