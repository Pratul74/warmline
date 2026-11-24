from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import AgentResult, ChatFn, ToolRun, run_agent
from app.agent.prompts import build_system_prompt
from app.agent.tools import EmbedQueryFn, build_tools, describe_completed_action
from app.core.config import get_settings
from app.core.llm import LLMRateLimitError, Message, chat, embed_query
from app.db.models import Conversation, MessageRole, RequestStatus, ToolCallStatus
from app.db.models import Message as DbMessage
from app.db.session import DB_ERRORS
from app.services.request_logs import log_request
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
    """The conversation does not exist or belongs to another account (the caller cannot tell which)."""


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


def _final_reply(result: AgentResult) -> str:
    if not (result.hit_step_limit or result.gave_up_on_tool):
        return result.reply
    done = [
        describe_completed_action(run.result)
        for run in result.tool_runs
        if run.name == "confirm_pending_action" and run.ok
    ]
    done = [sentence for sentence in done if sentence]
    return " ".join([*done, result.reply]) if done else result.reply


def _saved_lead_id(result: AgentResult) -> int | None:
    for run in reversed(result.tool_runs):
        if run.name == "confirm_pending_action" and run.ok and "lead_id" in run.result:
            return run.result["lead_id"]
    return None


async def _log_tool_runs(
    session: AsyncSession, *, conversation_id: int | None, request_id: UUID, runs: list[ToolRun]
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
    account_id: int,
    message: str,
    conversation_id: int | None = None,
    chat_fn: ChatFn = chat,
    embed_query_fn: EmbedQueryFn = embed_query,
    now: datetime | None = None,
) -> ChatTurn:
    try:
        return await _handle_chat(
            session,
            account_id=account_id,
            message=message,
            conversation_id=conversation_id,
            chat_fn=chat_fn,
            embed_query_fn=embed_query_fn,
            now=now or datetime.now(get_settings().business_tz),
            request_id=uuid4(),
            started=time.perf_counter(),
        )
    except DB_ERRORS as exc:
        logger.exception("Database error while handling a chat turn")
        await _safe_rollback(session)
        raise ChatStorageError("Could not load or save the conversation") from exc


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


async def _record_failed_request(
    session: AsyncSession,
    *,
    request_id: UUID,
    conversation_id: int | None,
    result: AgentResult,
    started: float,
) -> None:
    error = result.error
    status = (
        RequestStatus.RATE_LIMITED if isinstance(error, LLMRateLimitError) else RequestStatus.MODEL_ERROR
    )
    try:
        await _log_tool_runs(
            session, conversation_id=conversation_id, request_id=request_id, runs=result.tool_runs
        )
        await log_request(
            session,
            request_id=request_id,
            conversation_id=conversation_id,
            status=status,
            latency_ms=_elapsed_ms(started),
            steps=result.steps,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        await session.commit()
    except DB_ERRORS:
        logger.exception("Could not record failed request %s", request_id)
        await _safe_rollback(session)


async def _safe_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except DB_ERRORS:
        logger.exception("Rollback failed after a database error")


async def _handle_chat(
    session: AsyncSession,
    *,
    account_id: int,
    message: str,
    conversation_id: int | None,
    chat_fn: ChatFn,
    embed_query_fn: EmbedQueryFn,
    now: datetime,
    request_id: UUID,
    started: float,
) -> ChatTurn:
    conversation: Conversation | None = None
    history: list[Message] = []
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None or conversation.account_id != account_id:
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")
        history = await _load_history(session, conversation_id)
    else:
        conversation = Conversation(account_id=account_id)
        session.add(conversation)
        await session.flush()

    history.append(Message(role="user", text=message))
    result = await run_agent(
        history,
        build_tools(
            session,
            account_id=conversation.account_id,
            conversation_id=conversation.id,
            embed_query_fn=embed_query_fn,
        ),
        system=build_system_prompt(now),
        chat_fn=chat_fn,
    )
    if result.error is not None:
        await _safe_rollback(session)
        await _record_failed_request(
            session,
            request_id=request_id,
            conversation_id=conversation_id,
            result=result,
            started=started,
        )
        raise result.error

    reply = _final_reply(result)
    lead_id = _saved_lead_id(result)
    if lead_id is not None:
        conversation.lead_id = lead_id
    await _log_tool_runs(
        session, conversation_id=conversation.id, request_id=request_id, runs=result.tool_runs
    )
    session.add_all(
        [
            DbMessage(conversation_id=conversation.id, role=MessageRole.USER, content=message),
            DbMessage(
                conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=reply
            ),
        ]
    )
    latency_ms = _elapsed_ms(started)
    await log_request(
        session,
        request_id=request_id,
        conversation_id=conversation.id,
        status=RequestStatus.OK,
        latency_ms=latency_ms,
        steps=result.steps,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    await session.commit()
    logger.info(
        "chat request %s: %d ms, %d steps, %d in / %d out tokens",
        request_id,
        latency_ms,
        result.steps,
        result.input_tokens,
        result.output_tokens,
    )
    return ChatTurn(conversation_id=conversation.id, reply=reply)
