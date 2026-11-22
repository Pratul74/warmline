from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import ChatFn, run_agent
from app.agent.prompts import SYSTEM_PROMPT
from app.core.llm import Message, chat
from app.db.models import Conversation, MessageRole
from app.db.models import Message as DbMessage

HISTORY_LIMIT = 20


class ConversationNotFoundError(Exception):
    """The client sent a conversation_id that does not exist."""


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


async def handle_chat(
    session: AsyncSession,
    *,
    message: str,
    conversation_id: int | None = None,
    chat_fn: ChatFn = chat,
) -> ChatTurn:
    conversation: Conversation | None = None
    history: list[Message] = []
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")
        history = await _load_history(session, conversation_id)

    history.append(Message(role="user", text=message))
    result = await run_agent(history, tools={}, system=SYSTEM_PROMPT, chat_fn=chat_fn)

    if conversation is None:
        conversation = Conversation()
        session.add(conversation)
        await session.flush()
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
