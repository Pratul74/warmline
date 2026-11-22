from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import Tool
from app.core.llm import ToolSpec
from app.services.lead import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_PHONE_LENGTH,
    InvalidLeadError,
    create_lead,
)

MAX_NOTES_LENGTH = 1000


class CreateLeadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH, description="Customer's full name")
    email: str = Field(min_length=3, max_length=MAX_EMAIL_LENGTH, description="Customer's email address")
    phone: str | None = Field(default=None, max_length=MAX_PHONE_LENGTH, description="Phone number, if given")
    notes: str | None = Field(
        default=None,
        max_length=MAX_NOTES_LENGTH,
        description="Short summary of what the customer wants",
    )


CREATE_LEAD_SPEC = ToolSpec(
    name="create_lead",
    description=(
        "Save an interested customer as a sales lead so the team can follow up. "
        "Call it once you have at least their name and email address."
    ),
    parameters=CreateLeadArgs.model_json_schema(),
)


def describe_validation_error(exc: ValidationError) -> str:
    problems = [
        f"{'.'.join(str(part) for part in err['loc']) or 'input'}: {err['msg']}"
        for err in exc.errors(include_url=False)
    ]
    return "Invalid arguments. " + "; ".join(problems)


def build_tools(session: AsyncSession) -> dict[str, Tool]:

    async def create_lead_handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = CreateLeadArgs.model_validate(args)
        except ValidationError as exc:
            return {"error": describe_validation_error(exc)}
        try:
            async with session.begin_nested():
                result = await create_lead(session, **parsed.model_dump())
        except InvalidLeadError as exc:
            return {"error": str(exc)}
        return {"lead_id": result.lead.id, "created": result.created}

    return {"create_lead": Tool(CREATE_LEAD_SPEC, create_lead_handler)}
