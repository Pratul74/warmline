import hashlib
import re
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.api.chat import get_chat_fn, get_embed_query_fn
from app.core.config import EMBEDDING_DIM, get_settings
from app.core.llm import ChatResult, LLMError, LLMRateLimitError, ToolCall
from app.db.models import Conversation, RateLimitCounter
from app.db.session import get_session
from app.main import app
from app.services import public_chat
from app.services.integrations import create_integration, rotate_public_id, update_integration
from tests.factories import auth_headers, new_account, new_conversation, new_faq

TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")


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


def say(reply: str) -> ChatResult:
    return ChatResult(text=reply, tool_calls=[], input_tokens=1, output_tokens=1)


def unit(i: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[i] = 1.0
    return vector


async def hours_embedder(question: str) -> list[float]:
    return unit(0)


@pytest_asyncio.fixture
async def shop_a(session):
    return await new_account(session, business_name="Fake Bikes A")


@pytest_asyncio.fixture
async def shop_b(session):
    return await new_account(session, business_name="Fake Bikes B")


@pytest_asyncio.fixture
async def link_a(session, shop_a):
    return await create_integration(session, account_id=shop_a.id, name="Website chat", greeting="Hi!")


@pytest_asyncio.fixture
async def client(session):

    async def override_session():
        yield session

    holder = {"model": ScriptedChat([])}
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_chat_fn] = lambda: holder["model"]
    app.dependency_overrides[get_embed_query_fn] = lambda: hours_embedder

    def set_script(*items) -> ScriptedChat:
        holder["model"] = ScriptedChat(items)
        return holder["model"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.script = set_script
        yield c
    app.dependency_overrides.clear()


async def send(client, public_id: str, message: str, token: str | None = None):
    body = {"message": message} if token is None else {"message": message, "conversation_token": token}
    return await client.post(f"/public/c/{public_id}/messages", json=body)


async def public_conversations(session, integration_id: int) -> list[Conversation]:
    rows = await session.scalars(
        select(Conversation).where(Conversation.integration_id == integration_id)
    )
    return list(rows)



async def test_profile_shows_only_what_a_chat_page_needs(client, link_a):
    response = await client.get(f"/public/c/{link_a.public_id}")

    assert response.status_code == 200
    assert response.json() == {"name": "Website chat", "greeting": "Hi!", "business_name": "Fake Bikes A"}


async def test_unknown_disabled_and_rotated_links_are_refused(client, session, shop_a, link_a):
    old_public_id = link_a.public_id
    unknown = await client.get("/public/c/notARealLinkAtAll123456")

    await rotate_public_id(session, account_id=shop_a.id, integration_id=link_a.id)
    rotated_old = await client.get(f"/public/c/{old_public_id}")
    rotated_new = await client.get(f"/public/c/{link_a.public_id}")

    await update_integration(session, account_id=shop_a.id, integration_id=link_a.id, enabled=False)
    disabled = await client.get(f"/public/c/{link_a.public_id}")

    assert (unknown.status_code, rotated_old.status_code) == (404, 404)
    assert unknown.json() == rotated_old.json()  # an old link looks exactly like a wrong one
    assert rotated_new.status_code == 200
    assert disabled.status_code == 403
    assert disabled.json() == {"detail": "This chat is currently unavailable"}


async def test_too_long_public_id_is_rejected_before_the_database(client):
    response = await client.get("/public/c/" + "x" * 33)

    assert response.status_code == 422

async def test_first_message_opens_a_conversation_for_the_links_owner(client, session, shop_a, link_a):
    model = client.script(say("Hello! How can I help?"))

    response = await send(client, link_a.public_id, "Hi there")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"conversation_token", "reply"}
    assert TOKEN.match(body["conversation_token"])
    assert body["reply"] == "Hello! How can I help?"
    [conversation] = await public_conversations(session, link_a.id)
    assert conversation.account_id == shop_a.id
    assert conversation.public_token_hash == hashlib.sha256(body["conversation_token"].encode()).hexdigest()
    assert body["conversation_token"] not in conversation.public_token_hash
    assert len(model.seen) == 1


async def test_token_continues_the_same_conversation_with_its_history(client, session, link_a):
    client.script(say("Hello!"), say("We open at 9."))

    first = await send(client, link_a.public_id, "Hi there")
    token = first.json()["conversation_token"]
    second = await send(client, link_a.public_id, "When do you open?", token)

    assert second.status_code == 200
    assert second.json()["conversation_token"] == token
    assert len(await public_conversations(session, link_a.id)) == 1


async def test_continuing_sends_earlier_messages_to_the_model(client, link_a):
    model = client.script(say("Hello!"), say("Sure."))

    token = (await send(client, link_a.public_id, "Hi there")).json()["conversation_token"]
    await send(client, link_a.public_id, "Thanks", token)

    assert [m.text for m in model.seen[1]] == ["Hi there", "Hello!", "Thanks"]


@pytest.mark.parametrize("case", ["made_up", "other_link_same_owner", "other_owners_link"])
async def test_a_token_only_works_on_its_own_link(client, session, shop_a, shop_b, link_a, case):
    other_link = await create_integration(
        session, account_id=(shop_a if case == "other_link_same_owner" else shop_b).id, name="Other"
    )
    model = client.script(say("Hello!"))
    token = (await send(client, link_a.public_id, "Hi")).json()["conversation_token"]
    target = link_a.public_id if case == "made_up" else other_link.public_id
    use_token = "x" * 43 if case == "made_up" else token

    response = await send(client, target, "Continue please", use_token)

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}
    assert len(model.seen) == 1


async def test_owner_conversations_cannot_be_reached_from_a_link(client, session, shop_a, link_a):
    await new_conversation(session, shop_a)
    model = client.script()

    response = await send(client, link_a.public_id, "Hi", "x" * 43)

    assert response.status_code == 404
    assert model.seen == []


async def test_disabled_link_refuses_even_an_existing_conversation(client, session, shop_a, link_a):
    model = client.script(say("Hello!"))
    token = (await send(client, link_a.public_id, "Hi")).json()["conversation_token"]
    await update_integration(session, account_id=shop_a.id, integration_id=link_a.id, enabled=False)

    response = await send(client, link_a.public_id, "Still there?", token)

    assert response.status_code == 403
    assert len(model.seen) == 1


async def test_after_rotation_the_old_link_is_gone_but_the_conversation_stays(client, session, shop_a, link_a):
    client.script(say("Hello!"), say("Yes."))
    old_public_id = link_a.public_id
    token = (await send(client, old_public_id, "Hi")).json()["conversation_token"]

    await rotate_public_id(session, account_id=shop_a.id, integration_id=link_a.id)
    on_old_link = await send(client, old_public_id, "Hello?", token)
    on_new_link = await send(client, link_a.public_id, "Hello?", token)

    assert on_old_link.status_code == 404
    assert on_new_link.status_code == 200
    assert len(await public_conversations(session, link_a.id)) == 1


@pytest.mark.parametrize(
    "extra", [{"account_id": 1}, {"conversation_id": 1}, {"integration_id": 1}]
)
async def test_visitor_cannot_send_owner_or_conversation_ids(client, link_a, extra):
    model = client.script()

    response = await client.post(
        f"/public/c/{link_a.public_id}/messages", json={"message": "Hi", **extra}
    )

    assert response.status_code == 422
    assert model.seen == []


async def test_the_links_owner_decides_which_faq_answers(client, session, shop_a, shop_b, link_a):
    await new_faq(session, shop_a.id, question="Hours?", answer="A: 9 to 6.", embedding=unit(0))
    await new_faq(session, shop_b.id, question="Hours?", answer="B: 10 to 4.", embedding=unit(0))
    call = ToolCall(name="search_faq", args={"question": "When are you open?"})
    model = client.script(
        ChatResult(text="", tool_calls=[call], input_tokens=1, output_tokens=1), say("9 to 6.")
    )

    response = await send(client, link_a.public_id, "When are you open?")

    assert response.status_code == 200
    assert [m["answer"] for m in model.seen[1][-1].tool_result["matches"]] == ["A: 9 to 6."]


async def test_model_failure_on_the_first_message_saves_nothing(client, session, link_a):
    link_id, public_id = link_a.id, link_a.public_id  # the rollback expires loaded objects
    client.script(LLMError("Model request failed with status 503"))

    response = await send(client, public_id, "Hi")

    assert response.status_code == 503
    assert await public_conversations(session, link_id) == []


async def test_rate_limit_returns_429(client, link_a):
    client.script(LLMRateLimitError("Model rate limit reached, please try again shortly"))

    response = await send(client, link_a.public_id, "Hi")

    assert response.status_code == 429


async def test_database_failure_while_opening_the_link_returns_clean_503(client, session, link_a, monkeypatch):
    async def db_down(*args, **kwargs):
        raise OperationalError("SELECT integrations", {}, Exception("server at 10.9.8.7 closed"))

    monkeypatch.setattr(session, "scalar", db_down)
    model = client.script()
    response = await send(client, link_a.public_id, "Hi")

    assert response.status_code == 503
    assert "10.9.8.7" not in response.text
    assert model.seen == []


async def test_owner_api_is_unchanged_and_still_needs_a_login(client, shop_a):
    without = await client.post("/chat", json={"message": "Hi"})
    with_login = await client.get("/integrations", headers=auth_headers(shop_a))

    assert without.status_code == 401
    assert with_login.status_code == 200



CLOCK = datetime(2026, 11, 25, 10, 0, 30, tzinfo=UTC)


@pytest.fixture
def limit_of_two(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "public_chat_rate_limit", 2)
    monkeypatch.setattr(settings, "public_chat_rate_window_seconds", 60)
    clock = {"now": CLOCK}
    monkeypatch.setattr(public_chat, "utc_now", lambda: clock["now"])
    return clock


async def test_a_link_over_its_limit_gets_429_without_calling_the_model(client, session, link_a, limit_of_two):
    model = client.script(say("One"), say("Two"))

    first = await send(client, link_a.public_id, "Hi")
    second = await send(client, link_a.public_id, "Hi again")
    third = await send(client, link_a.public_id, "And again")

    assert (first.status_code, second.status_code, third.status_code) == (200, 200, 429)
    assert third.headers["Retry-After"] == "30"
    assert third.json() == {"detail": "This chat is receiving too many messages, please try again shortly"}
    assert len(model.seen) == 2
    assert len(await public_conversations(session, link_a.id)) == 2


async def test_failed_model_calls_and_wrong_tokens_still_count(client, link_a, limit_of_two):
    public_id = link_a.public_id
    model = client.script(LLMError("Model request failed with status 503"))

    failed = await send(client, public_id, "Hi")
    guessed = await send(client, public_id, "Hi", token="x" * 43)
    refused = await send(client, public_id, "Hi")

    assert (failed.status_code, guessed.status_code, refused.status_code) == (503, 404, 429)
    assert len(model.seen) == 1


async def test_the_next_window_accepts_messages_again(client, link_a, limit_of_two):
    client.script(say("One"), say("Two"), say("Three"))
    await send(client, link_a.public_id, "Hi")
    await send(client, link_a.public_id, "Hi")
    refused = await send(client, link_a.public_id, "Hi")

    limit_of_two["now"] = CLOCK + timedelta(seconds=30)
    accepted = await send(client, link_a.public_id, "Hi")

    assert (refused.status_code, accepted.status_code) == (429, 200)


async def test_one_links_limit_does_not_block_another_owner(client, session, shop_b, link_a, limit_of_two):
    link_b = await create_integration(session, account_id=shop_b.id, name="Shop B chat")
    client.script(say("A1"), say("A2"), say("B1"))
    await send(client, link_a.public_id, "Hi")
    await send(client, link_a.public_id, "Hi")

    blocked = await send(client, link_a.public_id, "Hi")
    other = await send(client, link_b.public_id, "Hi")

    assert (blocked.status_code, other.status_code) == (429, 200)


async def test_unknown_and_disabled_links_are_not_counted(client, session, shop_a, link_a, limit_of_two):
    await update_integration(session, account_id=shop_a.id, integration_id=link_a.id, enabled=False)

    unknown = await send(client, "notARealLinkAtAll123456", "Hi")
    disabled = await send(client, link_a.public_id, "Hi")

    assert (unknown.status_code, disabled.status_code) == (404, 403)
    assert await session.scalar(select(func.count()).select_from(RateLimitCounter)) == 0


async def test_the_profile_is_not_rate_limited(client, link_a, limit_of_two):
    client.script(say("One"), say("Two"))
    for _ in range(3):
        await send(client, link_a.public_id, "Hi")

    profile = await client.get(f"/public/c/{link_a.public_id}")

    assert profile.status_code == 200
