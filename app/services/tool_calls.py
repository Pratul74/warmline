from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ToolCall, ToolCallStatus

MAX_TOOL_NAME_LENGTH = 100
MAX_ERROR_MESSAGE_LENGTH = 4_000
MAX_PAYLOAD_CHARS = 64_000
TRUNCATED_PREVIEW_CHARS = 2_000
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 500
_INT32_MAX = 2_147_483_647

class ToolCallError(Exception):
    """Base class for tool-call audit failures."""


class InvalidToolCallError(ToolCallError, ValueError):
    """The log entry itself is malformed (a programming error in the caller)."""



def _clean_tool_name(tool_name: str) -> str:
    clean_name = tool_name.strip()
    if not clean_name or len(clean_name) > MAX_TOOL_NAME_LENGTH:
        raise InvalidToolCallError(
            f"tool_name must be 1..{MAX_TOOL_NAME_LENGTH} characters"
        )
    return clean_name

def _validate_non_negative(value: int, *, field: str) -> int:
    if not 0<=value<=_INT32_MAX:
        raise InvalidToolCallError(f"{field} must be between 0 and {_INT32_MAX}")
    return int(value)

def _to_json_object(value: Any) -> dict[str, Any]:
    wrapped = value if isinstance(value, dict) else {"value": value}
    serialized = json.dumps(wrapped, default=str)
    if len(serialized) > MAX_PAYLOAD_CHARS:
        return {
            "_truncated": True,
            "original_chars": len(serialized),
            "preview": serialized[:TRUNCATED_PREVIEW_CHARS],
        }
    return json.loads(serialized)

def _clean_error_message(status:ToolCallStatus, error_message: str | None) -> str | None:
    clean_message = error_message.strip() if error_message else None
    if status is ToolCallStatus.OK:
        if clean_message:
            raise InvalidToolCallError("status OK must not carry an error_message")
        return None
    if not clean_message:
        raise InvalidToolCallError(f"status {status.value} requires an error_message")
    return clean_message[:MAX_ERROR_MESSAGE_LENGTH]

def _outcome_values(
        *,
        status: ToolCallStatus,
        duration_ms: int,
        result: Any | None,
        error_message: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "duration_ms": _validate_non_negative(duration_ms, field="duration_ms"),
        "result": None if result is None else _to_json_object(result),
        "error_message": _clean_error_message(status, error_message),
    }

def _validate_history_limit(limit: int) -> int:
    if limit < 1:
        raise InvalidToolCallError("limit must be at least 1")
    return min(limit, MAX_HISTORY_LIMIT)

async def log_tool_call(
        session: AsyncSession,
        *,
        conversation_id: int | None,
        request_id: UUID,
        step_number: int,
        tool_name: str,
        arguments: dict[str, Any],
        status: ToolCallStatus,
        duration_ms: int,
        result: Any | None = None,
        error_message: str | None = None,
) -> ToolCall:
    stmt = (
        insert(ToolCall)
        .values(
            conversation_id=conversation_id,
            request_id=request_id,
            step_number=_validate_non_negative(step_number, field="step_number"),
            tool_name=_clean_tool_name(tool_name),
            arguments=_to_json_object(arguments),
            **_outcome_values(
                status=status,
                duration_ms=duration_ms,
                result=result,
                error_message=error_message,
            ),
        )
        .returning(ToolCall)
    )
    return (await session.scalars(stmt)).one()

async def get_tool_history(
        session: AsyncSession,
        *,
        conversation_id: int,
        request_id: UUID | None = None,
        limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[ToolCall]:
    conditions = [ToolCall.conversation_id == conversation_id]
    if request_id is not None:
        conditions.append(ToolCall.request_id == request_id)
    stmt = (
        select(ToolCall)
        .where(*conditions)
        .order_by(ToolCall.id.desc())
        .limit(_validate_history_limit(limit))
    )
    newest_first = (await session.scalars(stmt)).all()
    return list(reversed(newest_first))
