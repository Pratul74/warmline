import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.chat import get_chat_fn
from app.core.llm import ChatResult, LLMError
from app.db.models import Conversation, Message
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


def text(reply: str) -> ChatResult:
    return ChatResult(text=reply, tool_calls=[], input_tokens=1, output_tokens=1)


@pytest_asyncio.fixture
async def client_with(session):

    async def override_session():
        yield session

    def build(fake: ScriptedChat) -> AsyncClient:
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_chat_fn] = lambda: fake
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
