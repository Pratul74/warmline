import pytest

from app.agent.loop import run_tool
from app.agent.tools import FAQ_MIN_SIMILARITY, build_tools
from app.core.config import EMBEDDING_DIM
from app.core.llm import LLMError, ToolCall
from app.services.lead import InvalidLeadError, create_lead
from tests.factories import new_account, new_conversation, new_faq


@pytest.fixture
async def account(session):
    return await new_account(session)


async def test_service_creates_new_lead_with_canonical_email(session, account):
    result = await create_lead(session, account_id=account.id, name="  Kim Fake ", email=" Kim@Example.TEST ")

    assert result.created is True
    assert result.lead.name == "Kim Fake"
    assert result.lead.email == "kim@example.test"
    assert result.lead.status.value == "new"


async def test_service_same_email_any_case_reuses_lead_and_fills_missing_phone(session, account):
    first = await create_lead(session, account_id=account.id, name="Lee Fake", email="lee@example.test")
    second = await create_lead(session, account_id=account.id, name="Lee F", email="LEE@example.test", phone="555-0100")

    assert second.created is False
    assert second.lead.id == first.lead.id
    assert second.lead.phone == "555-0100"
    assert second.lead.name == "Lee Fake"


@pytest.mark.parametrize("bad_email", ["not-an-email", "a@b", "two@@example.test", "sp ace@example.test"])
async def test_service_rejects_invalid_email(session, account, bad_email):
    with pytest.raises(InvalidLeadError):
        await create_lead(session, account_id=account.id, name="X", email=bad_email)



def unit(i: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[i] = 1.0
    return vector


def fixed_embedder(vector: list[float]):
    seen: list[str] = []

    async def embed(question: str) -> list[float]:
        seen.append(question)
        return vector

    embed.seen = seen
    return embed


async def add_faqs(session, account) -> None:
    await new_faq(session, account.id, question="What are your hours?", answer="9 to 6.", embedding=unit(0))
    await new_faq(
        session, account.id, question="Do you fix tyres?", answer="Yes, 15 dollars.", embedding=unit(1)
    )


async def run_search(session, account, args: dict, embed) -> dict:
    conversation = await new_conversation(session, account)
    tools = build_tools(
        session, account_id=account.id, conversation_id=conversation.id, embed_query_fn=embed
    )
    output, _status = await run_tool(ToolCall(name="search_faq", args=args), tools)
    return output


async def test_search_faq_returns_the_matching_entry_only(session, account):
    await add_faqs(session, account)
    embed = fixed_embedder(unit(1))

    output = await run_search(session, account, {"question": "  flat tyre?  "}, embed)

    assert output == {"matches": [{"question": "Do you fix tyres?", "answer": "Yes, 15 dollars.", "similarity": 1.0}]}
    assert embed.seen == ["flat tyre?"]


async def test_search_faq_drops_matches_below_the_threshold(session, account):
    await add_faqs(session, account)
    weak = unit(0)
    weak[0], weak[5] = 0.6, 0.8
    assert 0.6 < FAQ_MIN_SIMILARITY

    output = await run_search(session, account, {"question": "do you rent kayaks"}, fixed_embedder(weak))

    assert output == {"matches": []}


async def test_search_faq_rejects_bad_arguments_without_calling_the_embedder(session, account):
    embed = fixed_embedder(unit(0))

    missing = await run_search(session, account, {}, embed)
    extra = await run_search(session, account, {"question": "hours?", "lang": "en"}, embed)
    blank = await run_search(session, account, {"question": "   "}, embed)

    assert "question" in missing["error"]
    assert "lang" in extra["error"]
    assert blank["error"].startswith("Invalid arguments. question:")
    assert embed.seen == []


async def test_search_faq_embedding_failure_is_reported_to_the_model(session, account):
    async def failing(question: str) -> list[float]:
        raise LLMError("Model rate limit reached, please try again shortly")

    output = await run_search(session, account, {"question": "hours?"}, failing)

    assert output == {"error": "FAQ search is unavailable right now."}
