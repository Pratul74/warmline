import pytest

from app.agent.loop import run_tool
from app.agent.tools import FAQ_MIN_SIMILARITY, build_tools
from app.core.config import get_settings
from app.core.llm import LLMError, ToolCall
from app.db.models import FaqEntry
from app.services.lead import InvalidLeadError, create_lead


async def test_service_creates_new_lead_with_canonical_email(session):
    result = await create_lead(session, name="  Kim Fake ", email=" Kim@Example.TEST ")

    assert result.created is True
    assert result.lead.name == "Kim Fake"
    assert result.lead.email == "kim@example.test"
    assert result.lead.status.value == "new"


async def test_service_same_email_any_case_reuses_lead_and_fills_missing_phone(session):
    first = await create_lead(session, name="Lee Fake", email="lee@example.test")
    second = await create_lead(session, name="Lee F", email="LEE@example.test", phone="555-0100")

    assert second.created is False
    assert second.lead.id == first.lead.id
    assert second.lead.phone == "555-0100"
    assert second.lead.name == "Lee Fake"


@pytest.mark.parametrize("bad_email", ["not-an-email", "a@b", "two@@example.test", "sp ace@example.test"])
async def test_service_rejects_invalid_email(session, bad_email):
    with pytest.raises(InvalidLeadError):
        await create_lead(session, name="X", email=bad_email)



async def run_create_lead(session, args: dict) -> dict:
    output, _status = await run_tool(ToolCall(name="create_lead", args=args), build_tools(session))
    return output


async def test_tool_returns_only_ids_on_success(session):
    output = await run_create_lead(session, {"name": "Ana Fake", "email": "ana@example.test"})

    assert set(output) == {"lead_id", "created"}
    assert output["created"] is True


async def test_tool_reports_missing_email_to_the_model(session):
    output = await run_create_lead(session, {"name": "Ana Fake"})

    assert output["error"].startswith("Invalid arguments.")
    assert "email" in output["error"]


async def test_tool_reports_unknown_argument(session):
    output = await run_create_lead(
        session, {"name": "Ana", "email": "ana2@example.test", "budget": "1M"}
    )

    assert "budget" in output["error"]


async def test_tool_reports_business_rule_error_and_session_stays_usable(session):
    output = await run_create_lead(session, {"name": "Ana", "email": "no-at-sign"})
    assert output == {"error": "Invalid email address"}
    ok = await run_create_lead(session, {"name": "Ana", "email": "ana3@example.test"})
    assert ok["created"] is True




def unit(i: int) -> list[float]:
    vector = [0.0] * get_settings().embedding_dim
    vector[i] = 1.0
    return vector


def fixed_embedder(vector: list[float]):
    seen: list[str] = []

    async def embed(question: str) -> list[float]:
        seen.append(question)
        return vector

    embed.seen = seen
    return embed


async def add_faqs(session) -> None:
    session.add_all(
        [
            FaqEntry(question="What are your hours?", answer="9 to 6.", embedding=unit(0)),
            FaqEntry(question="Do you fix tyres?", answer="Yes, 15 dollars.", embedding=unit(1)),
        ]
    )
    await session.flush()


async def run_search(session, args: dict, embed) -> dict:
    tools = build_tools(session, embed_query_fn=embed)
    output, _status = await run_tool(ToolCall(name="search_faq", args=args), tools)
    return output


async def test_search_faq_returns_the_matching_entry_only(session):
    await add_faqs(session)
    embed = fixed_embedder(unit(1))

    output = await run_search(session, {"question": "  flat tyre?  "}, embed)

    assert output == {"matches": [{"question": "Do you fix tyres?", "answer": "Yes, 15 dollars.", "similarity": 1.0}]}
    assert embed.seen == ["flat tyre?"]


async def test_search_faq_drops_matches_below_the_threshold(session):
    await add_faqs(session)
    weak = unit(0)
    weak[0], weak[5] = 0.6, 0.8
    assert 0.6 < FAQ_MIN_SIMILARITY

    output = await run_search(session, {"question": "do you rent kayaks"}, fixed_embedder(weak))

    assert output == {"matches": []}


async def test_search_faq_rejects_bad_arguments_without_calling_the_embedder(session):
    embed = fixed_embedder(unit(0))

    missing = await run_search(session, {}, embed)
    extra = await run_search(session, {"question": "hours?", "lang": "en"}, embed)
    blank = await run_search(session, {"question": "   "}, embed)

    assert "question" in missing["error"]
    assert "lang" in extra["error"]
    assert blank["error"].startswith("Invalid arguments. question:")
    assert embed.seen == []


async def test_search_faq_embedding_failure_is_reported_to_the_model(session):
    async def failing(question: str) -> list[float]:
        raise LLMError("Model rate limit reached, please try again shortly")

    output = await run_search(session, {"question": "hours?"}, failing)

    assert output == {"error": "FAQ search is unavailable right now."}
