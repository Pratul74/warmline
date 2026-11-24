from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import ChatFn
from app.agent.tools import EmbedQueryFn
from app.core.config import get_settings
from app.core.llm import chat, embed_query
from app.db.models import Account, Conversation, Integration, IntegrationStatus
from app.db.session import DB_ERRORS
from app.services.chat import ChatStorageError, ConversationNotFoundError, handle_chat
from app.services.rate_limit import hit

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32


class LinkNotFoundError(Exception):
    """No integration has this public_id: a wrong link, or an old one replaced by rotation."""


class LinkDisabledError(Exception):
    """The integration exists but its owner has disabled it."""


@dataclass(frozen=True)
class PublicProfile:
    name: str
    greeting: str | None
    business_name: str


@dataclass(frozen=True)
class PublicChatTurn:
    conversation_token: str
    reply: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_conversation_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_active(integration: Integration | None) -> Integration:
    if integration is None:
        raise LinkNotFoundError("Chat link not found")
    if integration.status is not IntegrationStatus.ACTIVE:
        raise LinkDisabledError("This chat is currently unavailable")
    return integration


async def open_integration(session: AsyncSession, public_id: str) -> Integration:
    integration = await session.scalar(
        select(Integration).where(Integration.public_id == public_id)
    )
    return _check_active(integration)


async def get_public_profile(session: AsyncSession, public_id: str) -> PublicProfile:
    row = (
        await session.execute(
            select(Integration, Account.business_name)
            .join(Account, Account.id == Integration.account_id)
            .where(Integration.public_id == public_id)
        )
    ).one_or_none()
    integration = _check_active(row[0] if row else None)
    return PublicProfile(
        name=integration.name, greeting=integration.greeting, business_name=row.business_name
    )


async def _find_conversation_id(
    session: AsyncSession, *, integration_id: int, token: str
) -> int:
    conversation_id = await session.scalar(
        select(Conversation.id).where(
            Conversation.public_token_hash == hash_token(token),
            Conversation.integration_id == integration_id,
        )
    )
    if conversation_id is None:
        raise ConversationNotFoundError("Conversation not found")
    return conversation_id


async def handle_public_chat(
    session: AsyncSession,
    *,
    public_id: str,
    message: str,
    conversation_token: str | None = None,
    chat_fn: ChatFn = chat,
    embed_query_fn: EmbedQueryFn = embed_query,
) -> PublicChatTurn:
    try:
        integration = await open_integration(session, public_id)
        settings = get_settings()
        await hit(
            session,
            integration_id=integration.id,
            limit=settings.public_chat_rate_limit,
            window_seconds=settings.public_chat_rate_window_seconds,
            now=utc_now(),
        )
        conversation_id = None
        if conversation_token is not None:
            conversation_id = await _find_conversation_id(
                session, integration_id=integration.id, token=conversation_token
            )
    except DB_ERRORS as exc:
        logger.exception("Database error while opening a public chat link")
        raise ChatStorageError("Could not open the chat") from exc

    token = conversation_token or new_conversation_token()
    turn = await handle_chat(
        session,
        account_id=integration.account_id,
        message=message,
        conversation_id=conversation_id,
        integration_id=integration.id,
        public_token_hash=hash_token(token),
        chat_fn=chat_fn,
        embed_query_fn=embed_query_fn,
    )
    return PublicChatTurn(conversation_token=token, reply=turn.reply)
