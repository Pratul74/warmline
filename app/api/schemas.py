from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

MAX_MESSAGE_CHARS = 2000


class ChatRequest(BaseModel):
    conversation_id: int | None = Field(default=None, ge=1)
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]


class ChatResponse(BaseModel):
    conversation_id: int
    reply: str
