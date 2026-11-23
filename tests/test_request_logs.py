from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.api.chat import get_chat_fn, get_embed_query_fn
from app.core.config import get_settings
from app.core.llm import ChatResult, LLMError, LLMRateLimitError, ToolCall
from app.db.models import Conversation, RequestLog, RequestStatus
from app.db.models import ToolCall as ToolCallRow
from app.db.session import get_session
from app.main import app
from app.services import chat as chat_service
from app.services.request_logs import compute_cost


class ScriptedChat:
    def __init__(self, script: list):
        self.script = list(script)

    async def __call__(self, messages, tools, *, system=None):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def reply(text: str, *, tokens_in: int = 10, tokens_out: int = 5) -> ChatResult:
    return ChatResult(text=text, tool_calls=[], input_tokens=tokens_in, output_tokens=tokens_out)


def tool_call(name: str, args: dict, *, tokens_in: int = 20, tokens_out: int = 3) -> ChatResult:
    return ChatResult(
        text="", tool_calls=[ToolCall(name=name, args=args)], input_tokens=tokens_in, output_tokens=tokens_out
    )


@pytest.fixture
def prices(monkeypatch):
    def set_prices(input_price: float, output_price: float) -> None:
        monkeypatch.setattr(get_settings(), "llm_input_price_per_1m_tokens", input_price)
        monkeypatch.setattr(get_settings(), "llm_output_price_per_1m_tokens", output_price)

    return set_prices


@pytest_asyncio.fixture
async def post(session):
    async def override_session():
        yield session

    async def no_embeddings(question: str) -> list[float]:
        raise RuntimeError("not used")

    async def send(fake: ScriptedChat, body: dict):
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_chat_fn] = lambda: fake
        app.dependency_overrides[get_embed_query_fn] = lambda: no_embeddings
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/chat", json=body)

    yield send
    app.dependency_overrides.clear()


async def all_logs(session) -> list[RequestLog]:
    return list(await session.scalars(select(RequestLog).order_by(RequestLog.id)))




@pytest.mark.parametrize(
    ("tokens_in", "tokens_out", "expected"),
    [
        (1_000, 500, Decimal("0.000300")),
        (1_000_000, 1_000_000, Decimal("0.500000")),
        (5, 0, Decimal("0.000001")),
        (4, 0, Decimal("0.000000")),
        (0, 0, Decimal("0.000000")),
    ],
)
def test_cost_uses_configured_prices_and_rounds_to_six_places(prices, tokens_in, tokens_out, expected):
    prices(0.10, 0.40)

    assert compute_cost(tokens_in, tokens_out) == expected


def test_cost_is_zero_on_free_tier_prices(prices):
    prices(0.0, 0.0)

    assert compute_cost(123_456, 7_890) == Decimal("0")


# ---- one row per /chat request ---------------------------------------------------


async def test_successful_request_logs_tokens_steps_cost_and_audit_request_id(session, post, prices):
    prices(0.10, 0.40)
    fake = ScriptedChat(
        [
            tool_call("check_availability", {"start_date": "2030-01-07"}, tokens_in=20, tokens_out=3),
            reply("Nothing free that day.", tokens_in=30, tokens_out=7),
        ]
    )

    response = await post(fake, {"message": "Anything free on 7 January 2030?"})

    assert response.status_code == 200
    [log] = await all_logs(session)
    assert log.status is RequestStatus.OK
    assert log.conversation_id == response.json()["conversation_id"]
    assert (log.steps, log.input_tokens, log.output_tokens) == (2, 50, 10)
    assert log.cost_usd == compute_cost(50, 10)
    assert log.model == get_settings().gemini_model
    assert log.latency_ms >= 0
    audit = await session.scalar(select(ToolCallRow))
    assert audit.request_id == log.request_id


async def test_each_request_gets_its_own_row(session, post):
    first = await post(ScriptedChat([reply("Hi!")]), {"message": "hi"})
    conv_id = first.json()["conversation_id"]
    await post(ScriptedChat([reply("Still here.")]), {"conversation_id": conv_id, "message": "hello?"})

    logs = await all_logs(session)
    assert [log.conversation_id for log in logs] == [conv_id, conv_id]
    assert len({log.request_id for log in logs}) == 2


# ---- failures are logged too -----------------------------------------------------


async def test_rate_limit_on_a_new_conversation_is_logged_without_a_conversation(session, post):
    conversations_before = await session.scalar(select(func.count()).select_from(Conversation))
    fake = ScriptedChat([LLMRateLimitError("Model rate limit reached, please try again shortly")])

    response = await post(fake, {"message": "hi"})

    assert response.status_code == 429
    [log] = await all_logs(session)
    assert log.status is RequestStatus.RATE_LIMITED
    assert log.conversation_id is None
    assert (log.steps, log.input_tokens, log.output_tokens, log.cost_usd) == (0, 0, 0, 0)
    assert await session.scalar(select(func.count()).select_from(Conversation)) == conversations_before


async def test_model_error_on_an_existing_conversation_is_linked_to_it(session, post):
    first = await post(ScriptedChat([reply("Hi!")]), {"message": "hi"})
    conv_id = first.json()["conversation_id"]

    failed = await post(
        ScriptedChat([LLMError("Model request failed with status 500")]),
        {"conversation_id": conv_id, "message": "are you there?"},
    )

    assert failed.status_code == 503
    ok_log, failed_log = await all_logs(session)
    assert (ok_log.status, failed_log.status) == (RequestStatus.OK, RequestStatus.MODEL_ERROR)
    assert failed_log.conversation_id == conv_id


async def test_failure_logging_that_fails_still_returns_the_model_error(session, post, monkeypatch):
    async def broken_log_request(*args, **kwargs):
        raise OperationalError("INSERT INTO request_logs", {}, Exception("db gone"))

    monkeypatch.setattr(chat_service, "log_request", broken_log_request)

    response = await post(ScriptedChat([LLMError("Model request failed with status 500")]), {"message": "hi"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Model request failed with status 500"
    assert await all_logs(session) == []


async def test_model_failure_after_a_tool_keeps_the_audit_rows_and_tokens(session, post):
    conversations_before = await session.scalar(select(func.count()).select_from(Conversation))
    fake = ScriptedChat(
        [
            tool_call("check_availability", {"start_date": "2030-01-07"}, tokens_in=20, tokens_out=3),
            LLMError("Model request failed with status 500"),
        ]
    )

    response = await post(fake, {"message": "Anything free on 7 January 2030?"})

    assert response.status_code == 503
    [log] = await all_logs(session)
    assert log.status is RequestStatus.MODEL_ERROR
    assert (log.steps, log.input_tokens, log.output_tokens) == (1, 20, 3)
    [audit] = list(await session.scalars(select(ToolCallRow)))
    assert (audit.tool_name, audit.request_id, audit.conversation_id) == (
        "check_availability",
        log.request_id,
        None,
    )
    assert await session.scalar(select(func.count()).select_from(Conversation)) == conversations_before
