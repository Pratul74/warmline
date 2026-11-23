from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PendingAction, PendingActionStatus

DEFAULT_TTL = timedelta(minutes=10)
MAX_TTL = timedelta(days=1)
MAX_TOOL_NAME_LENGTH = 100

class PendingActionError(Exception):
    """Base class for expected pending-action failures the caller should handle."""


class InvalidPendingActionError(PendingActionError, ValueError):
    """The proposal itself is malformed (bad tool name, arguments or TTL)."""


class PendingActionNotFoundError(PendingActionError):
    """No such action exists in this conversation."""


class PendingActionExpiredError(PendingActionError):
    """The action's confirmation window has passed."""


class PendingActionNotPendingError(PendingActionError):
    """The action was already confirmed, cancelled or expired.

    Attributes:
        status: The action's current status, so the caller can respond
            sensibly (e.g. CONFIRMED means "already done, don't execute again").
    """

    def __init__(self, action_id: int, status: PendingActionStatus) -> None:
        super().__init__(f"Pending action {action_id} is already {status.value}")
        self.status = status

@dataclass(frozen=True, slots=True)
class CancelPendingActionResult:
    action: PendingAction
    cancelled: bool

def _clean_tool_name(tool_name: str) -> str:
    clean_name = tool_name.strip()
    if not clean_name:
        raise InvalidPendingActionError("tool_name must not be empty")
    if len(clean_name)>MAX_TOOL_NAME_LENGTH:
        raise InvalidPendingActionError(
            f"tool_name exceeds {MAX_TOOL_NAME_LENGTH} characters"
        )
    return clean_name

def _freeze_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise InvalidPendingActionError("arguments must be a JSON object (dict)")
    try:
        return json.loads(json.dumps(arguments, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise InvalidPendingActionError(f"arguments are not JSON-serializable: {exc}") from exc

def _validate_ttl(ttl: timedelta) -> None:
    if ttl <= timedelta(0):
        raise InvalidPendingActionError("ttl must be positive")
    if ttl > MAX_TTL:
        raise InvalidPendingActionError(f"ttl must not exceed {MAX_TTL}")

async def _supersede_open_actions(session: AsyncSession, conversation_id: int) -> None:
    stmt = (
        update(PendingAction)
        .where(
            PendingAction.conversation_id == conversation_id,
            PendingAction.status == PendingActionStatus.PENDING,
        )
        .values(status=PendingActionStatus.CANCELLED)
        .execution_options(synchronize_session="fetch")

    )
    await session.execute(stmt)

async def _load_action(
        session: AsyncSession, *, action_id: int, conversation_id: int
) -> tuple[PendingAction, bool] | None:
    stmt = (
        select(PendingAction, (PendingAction.expires_at <= func.now()).label("is_expired"))
        .where(
            PendingAction.id == action_id,
            PendingAction.conversation_id == conversation_id,
        )
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    action, is_expired = row
    return action, bool(is_expired)

async def create_pending_action(
        session: AsyncSession,
        *,
        conversation_id: int,
        tool_name: str,
        arguments: dict[str, Any],
        ttl: timedelta = DEFAULT_TTL,
) -> PendingAction:
    clean_tool_name = _clean_tool_name(tool_name)
    frozen_arguments = _freeze_arguments(arguments)
    _validate_ttl(ttl)

    await _supersede_open_actions(session, conversation_id)
    stmt = (
        insert(PendingAction)
        .values(
            conversation_id=conversation_id,
            tool_name=clean_tool_name,
            arguments=frozen_arguments,
            status=PendingActionStatus.PENDING,
            expires_at=func.now() + ttl,
        )
        .returning(PendingAction)
    )
    return (await session.scalars(stmt)).one()

async def get_latest_pending_action(
        session: AsyncSession, conversation_id: int
) -> PendingAction | None:
    stmt = (
        select(PendingAction)
        .where(
            PendingAction.conversation_id == conversation_id,
            PendingAction.status == PendingActionStatus.PENDING,
            PendingAction.expires_at > func.now()
        )
        .order_by(PendingAction.created_at.desc(), PendingAction.id.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()

async def claim_pending_action(
        session: AsyncSession, *, action_id: int, conversation_id: int
) -> PendingAction:
    stmt = (
        update(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.conversation_id == conversation_id,
            PendingAction.status == PendingActionStatus.PENDING,
            PendingAction.expires_at > func.now(),
        )
        .values(status=PendingActionStatus.CONFIRMED)
        .returning(PendingAction)
        .execution_options(populate_existing=True)
    )
    claimed_action = (await session.scalars(stmt)).one_or_none()
    if claimed_action is not None:
        return claimed_action
    loaded = await _load_action(session, action_id=action_id, conversation_id=conversation_id)
    if loaded is None:
        raise PendingActionNotFoundError(f"Pending action {action_id} not found")
    action, is_expired = loaded
    if action.status is not PendingActionStatus.PENDING:
        raise PendingActionNotPendingError(action_id, action.status)
    if is_expired:
        raise PendingActionExpiredError(f"Pending action {action_id} has expired")
    raise PendingActionNotPendingError(action_id, action.status)

async def cancel_pending_action(
        session: AsyncSession, *, action_id: int, conversation_id: int
) -> CancelPendingActionResult:
    stmt = (
        update(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.conversation_id == conversation_id,
            PendingAction.status == PendingActionStatus.PENDING,
        )
        .values(status=PendingActionStatus.CANCELLED)
        .returning(PendingAction)
        .execution_options(populate_existing=True)
    )
    cancelled_action = (await session.scalars(stmt)).one_or_none()
    if cancelled_action is not None:
        return CancelPendingActionResult(action=cancelled_action, cancelled=True)
    loaded = await _load_action(session, action_id=action_id, conversation_id=conversation_id)
    if loaded is None:
        raise PendingActionNotFoundError(f"Pending action {action_id} not found")
    action, _ = loaded
    if action.status is PendingActionStatus.CONFIRMED:
        raise PendingActionNotPendingError(action_id, action.status)
    return CancelPendingActionResult(action=action, cancelled=False)
