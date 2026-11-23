from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import AgentResult, ChatFn, ToolRun, run_agent
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import EmbedQueryFn, build_tools
from app.core.llm import LLMError, Message, chat, embed_query
from app.db.models import Conversation, MessageRole, ToolCallStatus
from app.db.models import Message as DbMessage
from app.db.session import DB_ERRORS
from app.services.tool_calls import log_tool_call

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20

AUDIT_STATUS = {
    "ok": ToolCallStatus.OK,
    "invalid_args": ToolCallStatus.VALIDATION_ERROR,
    "rejected": ToolCallStatus.REJECTED,
    "error": ToolCallStatus.ERROR,
}


class ConversationNotFoundError(Exception):
    """The client sent a conversation_id that does not exist."""


class ChatStorageError(Exception):
    """The database failed while loading or saving the turn. Nothing from the turn was saved."""


@dataclass
class ChatTurn:
    conversation_id: int
    reply: str


async def _load_history(session: AsyncSession, conversation_id: int) -> list[Message]:
    stmt = (
        select(DbMessage)
        .where(DbMessage.conversation_id == conversation_id)
        .order_by(DbMessage.id.desc())
        .limit(HISTORY_LIMIT)
    )
    newest_first = (await session.scalars(stmt)).all()
    return [Message(role=row.role.value, text=row.content) for row in reversed(newest_first)]


def _created_lead_id(result: AgentResult) -> int | None:
    for run in reversed(result.tool_runs):
        if run.name == "create_lead" and run.ok:
            return run.result["lead_id"]
    return None


async def _log_tool_runs(
    session: AsyncSession, *, conversation_id: int, request_id: UUID, runs: list[ToolRun]
) -> None:
    for run in runs:
        await log_tool_call(
            session,
            conversation_id=conversation_id,
            request_id=request_id,
            step_number=run.step,
            tool_name=run.name,
            arguments=run.args,
            status=AUDIT_STATUS[run.status],
            duration_ms=run.duration_ms,
            result=run.result if run.ok else None,
            error_message=None if run.ok else str(run.result.get("error") or "unknown error"),
        )


async def handle_chat(
    session: AsyncSession,
    *,
    message: str,
    conversation_id: int | None = None,
    chat_fn: ChatFn = chat,
    embed_query_fn: EmbedQueryFn = embed_query,
) -> ChatTurn:
    try:
        return await _handle_chat(
            session,
            message=message,
            conversation_id=conversation_id,
            chat_fn=chat_fn,
            embed_query_fn=embed_query_fn,
        )
    except DB_ERRORS as exc:
        logger.exception("Database error while handling a chat turn")
        await _safe_rollback(session)
        raise ChatStorageError("Could not load or save the conversation") from exc


async def _safe_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except DB_ERRORS:
        logger.exception("Rollback failed after a database error")


async def _handle_chat(
    session: AsyncSession,
    *,
    message: str,
    conversation_id: int | None,
    chat_fn: ChatFn,
    embed_query_fn: EmbedQueryFn,
) -> ChatTurn:
    conversation: Conversation | None = None
    history: list[Message] = []
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")
        history = await _load_history(session, conversation_id)

    history.append(Message(role="user", text=message))
    try:
        result = await run_agent(
            history,
            build_tools(session, embed_query_fn=embed_query_fn),
            system=SYSTEM_PROMPT,
            chat_fn=chat_fn,
        )
    except LLMError:
        await _safe_rollback(session)
        raise

    lead_id = _created_lead_id(result)
    if conversation is None:
        conversation = Conversation(lead_id=lead_id)
        session.add(conversation)
        await session.flush()
    elif lead_id is not None:
        conversation.lead_id = lead_id
    await _log_tool_runs(
        session, conversation_id=conversation.id, request_id=uuid4(), runs=result.tool_runs
    )
    session.add_all(
        [
            DbMessage(conversation_id=conversation.id, role=MessageRole.USER, content=message),
            DbMessage(
                conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=result.reply
            ),
        ]
    )
    await session.commit()
    return ChatTurn(conversation_id=conversation.id, reply=result.reply)
