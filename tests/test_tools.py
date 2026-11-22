import pytest

from app.agent.tools import build_tools
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
    return await build_tools(session)["create_lead"].handler(args)


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
