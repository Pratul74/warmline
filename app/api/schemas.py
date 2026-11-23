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


class RegisterRequest(BaseModel):
    email: Annotated[str, StringConstraints(max_length=320)]
    password: Annotated[str, StringConstraints(max_length=128)]
    business_name: Annotated[str, StringConstraints(max_length=200)]


class LoginRequest(BaseModel):
    email: Annotated[str, StringConstraints(max_length=320)]
    password: Annotated[str, StringConstraints(max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AccountResponse(BaseModel):
    id: int
    email: str
    business_name: str
