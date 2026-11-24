from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Slot, Lead

DEFAULT_AVAILABILITY_LIMIT = 20
MAX_AVAILABILITY_LIMIT = 100

class BookingError(Exception):
    """Base class for expected booking failures the caller should handle."""

class InvalidBookingRequestError(BookingError, ValueError):
    """The request itself is malformed (bad window, naive datetime, bad limit)."""

class SlotNotFoundError(BookingError):
    """No slot with the given id exists in this account."""

class SlotUnavailableError(BookingError):
    """The slot is booked by someone else, or changed while we were booking it."""

class SlotInPastError(BookingError):
    """The slot has already started, so it can no longer be booked or cancelled."""

class LeadNotFoundError(BookingError):
    """No lead with the given id exists in this account."""

class BookingNotFoundError(BookingError):
    """This lead holds no booking on this slot."""

@dataclass(frozen=True, slots=True)
class BookingResult:
    slot: Slot
    created: bool

@dataclass(frozen=True, slots=True)
class CancellationResult:
    slot: Slot
    cancelled: bool

@dataclass(frozen=True, slots=True)
class _SlotSnapshot:
    slot: Slot
    is_past: bool

def _require_aware(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidBookingRequestError(f"{field} must be timezone-aware")

def _validate_limit(limit: int) -> int:
    if limit < 1:
        raise InvalidBookingRequestError("limit must be at least 1")
    return min(limit, MAX_AVAILABILITY_LIMIT)

async def _load_slot_snapshot(
        session: AsyncSession, *, account_id: int, slot_id: int
) -> _SlotSnapshot | None:
    stmt = (
        select(Slot, (Slot.start_at <= func.now()).label("is_past"))
        .where(Slot.id == slot_id, Slot.account_id == account_id)
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    slot, is_past = row
    return _SlotSnapshot(slot=slot, is_past=bool(is_past))

def _lead_in_account(account_id: int, lead_id: int):
    return select(Lead.id).where(Lead.id == lead_id, Lead.account_id == account_id).exists()

async def _lead_exists(session: AsyncSession, *, account_id: int, lead_id: int) -> bool:
    stmt = select(_lead_in_account(account_id, lead_id))
    return bool(await session.scalar(stmt))

async def _explain_failed_booking(
        session: AsyncSession, *, account_id: int, slot_id: int, lead_id: int
) -> BookingResult:
    snapshot = await _load_slot_snapshot(session, account_id=account_id, slot_id=slot_id)
    if snapshot is None:
        raise SlotNotFoundError(f"Slot {slot_id} does not exist")
    holder_id = snapshot.slot.booked_by_lead_id
    if holder_id == lead_id:
        return BookingResult(slot=snapshot.slot, created=False)
    if snapshot.is_past:
        raise SlotInPastError(f"Slot {slot_id} has already started")
    if holder_id is not None:
        raise SlotUnavailableError(f"Slot {slot_id} is already booked")
    if not await _lead_exists(session, account_id=account_id, lead_id=lead_id):
        raise LeadNotFoundError(f"Lead {lead_id} does not exist")
    raise SlotUnavailableError(f"Slot {slot_id} changed concurrently; please retry")

async def _explain_failed_cancellation(
        session: AsyncSession, *, account_id: int, slot_id: int, lead_id: int
) -> CancellationResult:
    snapshot = await _load_slot_snapshot(session, account_id=account_id, slot_id=slot_id)
    if snapshot is None:
        raise SlotNotFoundError(f"Slot {slot_id} does not exist")
    holder_id = snapshot.slot.booked_by_lead_id
    if holder_id is None:
        return CancellationResult(slot=snapshot.slot, cancelled=False)
    if holder_id != lead_id:
        raise BookingNotFoundError(f"Lead {lead_id} has no booking on slot {slot_id}")
    if snapshot.is_past:
        raise SlotInPastError(f"Slot {slot_id} has already started")
    raise SlotUnavailableError(f"Slot {slot_id} changed concurrently; please retry")

async def find_slot_by_start(
        session: AsyncSession, *, account_id: int, start_at: datetime
) -> Slot | None:
    _require_aware(start_at, field="start_at")
    stmt = (
        select(Slot)
        .where(Slot.account_id == account_id, Slot.start_at == start_at)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()

async def check_availability(
        session: AsyncSession,
        *,
        account_id: int,
        window_start: datetime,
        window_end: datetime,
        limit: int = DEFAULT_AVAILABILITY_LIMIT,
) -> list[Slot]:
    _require_aware(window_start, field="window_start")
    _require_aware(window_end, field="window_end")
    if window_start>=window_end:
        raise InvalidBookingRequestError("window_start must be before window_end")
    stmt = (
        select(Slot)
        .where(
            Slot.account_id == account_id,
            Slot.booked_by_lead_id.is_(None),
            Slot.start_at>=window_start,
            Slot.start_at<window_end,
            Slot.start_at > func.now(),
        )
        .order_by(Slot.start_at)
        .limit(_validate_limit(limit))
    )
    return list((await session.scalars(stmt)).all())

async def book_slot(
        session: AsyncSession, *, account_id: int, slot_id: int, lead_id: int
) -> BookingResult:
    stmt = (
        update(Slot)
        .where(
            Slot.id == slot_id,
            Slot.account_id == account_id,
            Slot.booked_by_lead_id.is_(None),
            Slot.start_at>func.now(),
            _lead_in_account(account_id, lead_id),
        )
        .values(booked_by_lead_id = lead_id)
        .returning(Slot)
        .execution_options(populate_existing=True)
    )
    booked_slot = (await session.scalars(stmt)).one_or_none()
    if booked_slot is not None:
        return BookingResult(slot=booked_slot, created=True)
    return await _explain_failed_booking(
        session, account_id=account_id, slot_id=slot_id, lead_id=lead_id
    )

async def cancel_booking(
        session: AsyncSession, *, account_id: int, slot_id: int, lead_id: int
) -> CancellationResult:
    stmt = (
        update(Slot)
        .where(
            Slot.id == slot_id,
            Slot.account_id == account_id,
            Slot.booked_by_lead_id == lead_id,
            Slot.start_at > func.now(),
        )
        .values(booked_by_lead_id=None)
        .returning(Slot)
        .execution_options(populate_existing=True)
    )
    freed_slot = (await session.scalars(stmt)).one_or_none()
    if freed_slot is not None:
        return CancellationResult(slot=freed_slot, cancelled=True)
    return await _explain_failed_cancellation(
        session, account_id=account_id, slot_id=slot_id, lead_id=lead_id
    )
