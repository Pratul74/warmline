from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import ChatFn
from app.agent.tools import EmbedQueryFn
from app.api.schemas import ChatRequest, ChatResponse
from app.core.llm import LLMError, LLMRateLimitError, chat, embed_query
from app.db.session import get_session
from app.services.chat import ChatStorageError, ConversationNotFoundError, handle_chat

router = APIRouter()


def get_chat_fn() -> ChatFn:
    return chat


def get_embed_query_fn() -> EmbedQueryFn:
    return embed_query


@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
    chat_fn: ChatFn = Depends(get_chat_fn),
    embed_query_fn: EmbedQueryFn = Depends(get_embed_query_fn),
) -> ChatResponse:
    try:
        turn = await handle_chat(
            session,
            message=body.message,
            conversation_id=body.conversation_id,
            chat_fn=chat_fn,
            embed_query_fn=embed_query_fn,
        )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ChatStorageError:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable, please try again")
    return ChatResponse(conversation_id=turn.conversation_id, reply=turn.reply)
