import logging

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import ChatFn
from app.agent.tools import EmbedQueryFn
from app.api.chat import get_chat_fn, get_embed_query_fn
from app.api.schemas import PublicChatRequest, PublicChatResponse, PublicProfileResponse
from app.core.llm import LLMError, LLMRateLimitError
from app.db.session import DB_ERRORS, get_session
from app.services.chat import ChatStorageError, ConversationNotFoundError
from app.services.public_chat import (
    LinkDisabledError,
    LinkNotFoundError,
    get_public_profile,
    handle_public_chat,
)
from app.services.rate_limit import PublicRateLimitError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/c", tags=["public chat"])

PublicId = Path(max_length=32)
UNAVAILABLE = "Service temporarily unavailable, please try again"
TOO_MANY = "This chat is receiving too many messages, please try again shortly"


@router.get("/{public_id}", response_model=PublicProfileResponse)
async def profile(
    public_id: str = PublicId, session: AsyncSession = Depends(get_session)
) -> PublicProfileResponse:
    try:
        found = await get_public_profile(session, public_id)
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LinkDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except DB_ERRORS:
        logger.exception("Database error while reading a public chat link")
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return PublicProfileResponse(
        name=found.name, greeting=found.greeting, business_name=found.business_name
    )


@router.post("/{public_id}/messages", response_model=PublicChatResponse)
async def post_message(
    body: PublicChatRequest,
    public_id: str = PublicId,
    session: AsyncSession = Depends(get_session),
    chat_fn: ChatFn = Depends(get_chat_fn),
    embed_query_fn: EmbedQueryFn = Depends(get_embed_query_fn),
) -> PublicChatResponse:
    try:
        turn = await handle_public_chat(
            session,
            public_id=public_id,
            message=body.message,
            conversation_token=body.conversation_token,
            chat_fn=chat_fn,
            embed_query_fn=embed_query_fn,
        )
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LinkDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except PublicRateLimitError as exc:
        raise HTTPException(
            status_code=429, detail=TOO_MANY, headers={"Retry-After": str(exc.retry_after)}
        )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ChatStorageError:
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return PublicChatResponse(conversation_token=turn.conversation_token, reply=turn.reply)
