from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead, LeadStatus
from app.services.emails import canonicalize_email, email_problem

MAX_NAME_LENGTH = 200
MAX_PHONE_LENGTH = 32

_INITIAL_STATUS = LeadStatus.NEW

class InvalidLeadError(ValueError):
    """Raised when lead data violates a business rule."""

@dataclass(frozen=True, slots=True)
class CreateLeadResult:
    lead: Lead
    created: bool

def _validate_email(canonical_email: str) -> None:
    problem = email_problem(canonical_email)
    if problem is not None:
        raise InvalidLeadError(problem)

def _clean_optional(value: str | None, *, field: str, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if max_length is not None and len(stripped) > max_length:
        raise InvalidLeadError(f"{field} exceeds {max_length} characters")
    return stripped

def _require_name(name: str) -> str:
    clean_name = _clean_optional(name, field="name", max_length=MAX_NAME_LENGTH)
    if clean_name is None:
        raise InvalidLeadError("Lead name must not be empty")
    return clean_name

def clean_lead_fields(
        *, name: str, email: str, phone: str | None = None, notes: str | None = None
) -> dict[str, str | None]:
    canonical_email = canonicalize_email(email)
    _validate_email(canonical_email)
    return {
        "name": _require_name(name),
        "email": canonical_email,
        "phone": _clean_optional(phone, field="phone", max_length=MAX_PHONE_LENGTH),
        "notes": _clean_optional(notes, field="notes"),
    }

async def create_lead(
        session: AsyncSession,
        *,
        name: str,
        email: str,
        phone: str | None = None,
        notes: str | None = None,
) -> CreateLeadResult:
    fields = clean_lead_fields(name=name, email=email, phone=phone, notes=notes)
    insert_stmt = pg_insert(Lead).values(**fields, status=_INITIAL_STATUS)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[func.lower(Lead.email)],
        set_={
            "phone": func.coalesce(Lead.phone, insert_stmt.excluded.phone),
            "notes": func.coalesce(Lead.notes, insert_stmt.excluded.notes),
        }

    ).returning(
        Lead,
        literal_column("(xmax = 0)").label("created"),
    )
    result = await session.execute(
        upsert_stmt,
        execution_options={"populate_existing": True},
    )
    lead, created = result.one()
    return CreateLeadResult(lead=lead, created=bool(created))

async def get_lead_by_email(session: AsyncSession, email: str) -> Lead | None:
    canonical_email = canonicalize_email(email)
    stmt = select(Lead).where(func.lower(Lead.email)== canonical_email)
    return (await session.execute(stmt)).scalar_one_or_none()

async def get_lead(session: AsyncSession, lead_id: int) -> Lead | None:
    return await session.get(Lead, lead_id)