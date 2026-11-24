from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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


class IntegrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(max_length=100)]
    greeting: Annotated[str, StringConstraints(max_length=500)] | None = None


class IntegrationUpdate(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(max_length=100)] | None = None
    greeting: Annotated[str, StringConstraints(max_length=500)] | None = None
    enabled: bool | None = None


class IntegrationResponse(BaseModel):
    id: int
    public_id: str
    embed_url: str
    name: str
    greeting: str | None
    status: str
    created_at: datetime
    disabled_at: datetime | None
