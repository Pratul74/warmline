from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey,Integer, Numeric, String, Text, func, Enum as SQLEnum, Uuid, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import EMBEDDING_DIM

class Base(DeclarativeBase):
    pass

class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    BOOKED = "booked"

class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"

class ToolCallStatus(StrEnum):
    OK = "ok"
    VALIDATION_ERROR = "validation_error"
    REJECTED = "rejected"
    ERROR = "error"

class RequestStatus(StrEnum):
    OK = "ok"
    RATE_LIMITED = "rate_limited"
    MODEL_ERROR = "model_error"

class PendingActionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

def enum_column(enum_cls):
    return SQLEnum(
        enum_cls,
        values_callable=lambda e: [m.value for m in e],
        native_enum=False,
    )

class Account(Base):

    __tablename__ = "accounts"
    __table_args__ = (
        Index("uq_accounts_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="account")


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("uq_leads_account_email_lower", "account_id", text("lower(email)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[LeadStatus] = mapped_column(enum_column(LeadStatus))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
    )

    booked_slots: Mapped[list["Slot"]] = relationship(
        back_populates="booked_by_lead"
    )
class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_lead_id", "lead_id"),
        Index("ix_conversations_account_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    account: Mapped["Account"] = relationship(back_populates="conversations")

    lead: Mapped["Lead | None"] = relationship(
        back_populates="conversations"
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    pending_actions: Mapped[list["PendingAction"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    request_logs: Mapped[list["RequestLog"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[MessageRole] = mapped_column(enum_column(MessageRole))
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )

class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_conversation_id", "conversation_id"),
        Index("ix_tool_calls_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
    )

    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)

    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)

    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)

    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[ToolCallStatus] = mapped_column(
        enum_column(ToolCallStatus)
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="tool_calls"
    )

class PendingAction(Base):
    __tablename__ = "pending_actions"
    __table_args__ = (
        Index("ix_pending_actions_conv_status", "conversation_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)

    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[PendingActionStatus] = mapped_column(
        enum_column(PendingActionStatus)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="pending_actions"
    )


class FaqEntry(Base):
    __tablename__ = "faq_entries"
    __table_args__ = (
        Index(
        "ix_faq_embedding_hnsw",
        "embedding",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_faq_entries_account_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        UniqueConstraint("account_id", "start_at", name="uq_slots_account_start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    booked_by_lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id"),
        default=None,
    )

    booked_by_lead: Mapped["Lead | None"] = relationship(
        back_populates="booked_slots"
    )

class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    request_id: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
        unique=True,
    )

    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
    )

    status: Mapped[RequestStatus] = mapped_column(
        enum_column(RequestStatus),
        nullable=False,
        server_default=RequestStatus.OK.value,
    )

    model: Mapped[str] = mapped_column(String(100), nullable=False)

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    steps: Mapped[int] = mapped_column(Integer, nullable=False)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="request_logs"
    )