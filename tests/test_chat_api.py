import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.chat import get_chat_fn, get_embed_query_fn
from app.core.config import get_settings
from app.core.llm import ChatResult, LLMError, ToolCall
from app.db.models import Conversation, FaqEntry, Lead, Message, ToolCallStatus
from app.db.models import ToolCall as ToolCallRow
from app.db.session import get_session
from app.main import app


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
async def client_with(session):

    async def override_session():
        yield session

    def build(fake: ScriptedChat, embed=no_real_embeddings) -> AsyncClient:
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_chat_fn] = lambda: fake
        app.dependency_overrides[get_embed_query_fn] = lambda: embed
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

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
    fake = ScriptedChat([LLMError("Model rate limit reached, please try again shortly")])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "hi"})

    assert response.status_code == 503
    assert "rate limit" in response.json()["detail"]
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


async def test_create_lead_tool_saves_lead_and_links_conversation(client_with, session):
    fake = ScriptedChat([lead_call("Robin@Example.test"), text("Thanks Robin, we'll be in touch.")])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "I'm Robin, robin@example.test, want a demo"})

    assert response.status_code == 200
    lead = await session.scalar(select(Lead).where(Lead.email == "robin@example.test"))
    assert lead is not None and lead.name == "Robin Fake"
    conversation = await session.get(Conversation, response.json()["conversation_id"])
    assert conversation.lead_id == lead.id
    tool_result = fake.seen[1][-1].tool_result
    assert tool_result == {"lead_id": lead.id, "created": True}


async def test_model_failure_after_lead_was_written_rolls_the_lead_back(client_with, session):
    fake = ScriptedChat([lead_call("rollback@example.test"), LLMError("Model rate limit reached")])
    async with client_with(fake) as client:
        response = await client.post("/chat", json={"message": "save me"})

    assert response.status_code == 503
    assert await session.scalar(select(Lead).where(Lead.email == "rollback@example.test")) is None
    assert await count(session, ToolCallRow) == 0


async def test_search_faq_tool_answer_is_sent_back_to_the_model(client_with, session):
    vector = [0.0] * get_settings().embedding_dim
    vector[0] = 1.0
    session.add(FaqEntry(question="What are your hours?", answer="9am to 6pm.", embedding=vector))
    await session.flush()

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
        return [1.0] + [0.0] * (get_settings().embedding_dim - 1)

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
