from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Integration, IntegrationStatus

MAX_NAME_LENGTH = 100
MAX_GREETING_LENGTH = 500
PUBLIC_ID_BYTES = 16
EMBED_PATH = "/c/"

UNSET: Any = object()


class InvalidIntegrationError(ValueError):
    """Integration data breaks a rule (empty or too long name, too long greeting)."""


class IntegrationNotFoundError(Exception):
    """No integration with this id exists in this account (the caller cannot tell which)."""


def new_public_id() -> str:
    return secrets.token_urlsafe(PUBLIC_ID_BYTES)


def embed_url(integration: Integration) -> str:
    return f"{get_settings().public_chat_base_url}{EMBED_PATH}{integration.public_id}"


def _clean_name(name: str | None) -> str:
    clean = (name or "").strip()
    if not clean or len(clean) > MAX_NAME_LENGTH:
        raise InvalidIntegrationError(f"name must be 1 to {MAX_NAME_LENGTH} characters")
    return clean


def _clean_greeting(greeting: str | None) -> str | None:
    if greeting is None:
        return None
    clean = greeting.strip()
    if len(clean) > MAX_GREETING_LENGTH:
        raise InvalidIntegrationError(f"greeting must be at most {MAX_GREETING_LENGTH} characters")
    return clean or None


async def create_integration(
    session: AsyncSession, *, account_id: int, name: str, greeting: str | None = None
) -> Integration:
    integration = Integration(
        account_id=account_id,
        public_id=new_public_id(),
        name=_clean_name(name),
        greeting=_clean_greeting(greeting),
        status=IntegrationStatus.ACTIVE,
    )
    session.add(integration)
    await session.flush()
    await session.refresh(integration)
    return integration


async def list_integrations(session: AsyncSession, *, account_id: int) -> list[Integration]:
    stmt = select(Integration).where(Integration.account_id == account_id).order_by(Integration.id)
    return list((await session.scalars(stmt)).all())


async def get_integration(
    session: AsyncSession, *, account_id: int, integration_id: int
) -> Integration:
    stmt = select(Integration).where(
        Integration.account_id == account_id, Integration.id == integration_id
    )
    integration = await session.scalar(stmt)
    if integration is None:
        raise IntegrationNotFoundError(f"Integration {integration_id} not found")
    return integration


async def update_integration(
    session: AsyncSession,
    *,
    account_id: int,
    integration_id: int,
    name: str | None = UNSET,
    greeting: str | None = UNSET,
    enabled: bool | None = UNSET,
) -> Integration:
    integration = await get_integration(
        session, account_id=account_id, integration_id=integration_id
    )
    if name is not UNSET:
        integration.name = _clean_name(name)
    if greeting is not UNSET:
        integration.greeting = _clean_greeting(greeting)
    if enabled is not UNSET:
        if enabled is None:
            raise InvalidIntegrationError("enabled must be true or false")
        _set_enabled(integration, enabled)
    await session.flush()
    await session.refresh(integration)
    return integration


def _set_enabled(integration: Integration, enabled: bool) -> None:
    if enabled:
        integration.status = IntegrationStatus.ACTIVE
        integration.disabled_at = None
    elif integration.status is not IntegrationStatus.DISABLED:
        integration.status = IntegrationStatus.DISABLED
        integration.disabled_at = func.now()


async def rotate_public_id(
    session: AsyncSession, *, account_id: int, integration_id: int
) -> Integration:
    integration = await get_integration(
        session, account_id=account_id, integration_id=integration_id
    )
    integration.public_id = new_public_id()
    await session.flush()
    return integration
