import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Integration, RateLimitCounter
from app.services.integrations import create_integration
from app.services.rate_limit import PublicRateLimitError, hit, window_start
from tests.factories import new_account

NOW = datetime(2026, 11, 25, 10, 0, 45, 200_000, tzinfo=UTC)


@pytest_asyncio.fixture
async def link(session):
    owner = await new_account(session)
    return await create_integration(session, account_id=owner.id, name="Website chat")


async def count_for(session, integration_id: int) -> list[int]:
    rows = await session.scalars(
        select(RateLimitCounter.count).where(RateLimitCounter.integration_id == integration_id)
    )
    return list(rows)


async def hit_link(session, integration_id: int, *, now: datetime = NOW, limit: int = 3) -> None:
    await hit(session, integration_id=integration_id, limit=limit, window_seconds=60, now=now)


def test_windows_are_aligned_to_the_clock_in_utc():
    india = timezone(timedelta(hours=5, minutes=30))

    assert window_start(NOW, 60) == datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    assert window_start(NOW, 3600) == datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    assert window_start(NOW.astimezone(india), 60) == datetime(2026, 11, 25, 10, 0, tzinfo=UTC)


async def test_allows_exactly_the_limit_then_refuses(session, link):
    for _ in range(3):
        await hit_link(session, link.id)

    with pytest.raises(PublicRateLimitError) as refused:
        await hit_link(session, link.id)

    assert refused.value.retry_after == 15
    assert await count_for(session, link.id) == [4]


async def test_a_new_window_starts_from_zero(session, link):
    for _ in range(3):
        await hit_link(session, link.id)

    await hit_link(session, link.id, now=NOW + timedelta(seconds=15))

    assert sorted(await count_for(session, link.id)) == [1, 3]


async def test_each_link_has_its_own_counter(session, link):
    other = await create_integration(session, account_id=link.account_id, name="App chat")
    for _ in range(3):
        await hit_link(session, link.id)

    await hit_link(session, other.id)

    with pytest.raises(PublicRateLimitError):
        await hit_link(session, link.id)


async def test_the_count_is_committed_so_a_later_rollback_keeps_it(session, link):
    await hit_link(session, link.id)
    await session.rollback()

    assert await count_for(session, link.id) == [1]


async def test_simultaneous_requests_are_counted_exactly(engine):
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        owner = await new_account(setup)
        integration = await create_integration(setup, account_id=owner.id, name="Busy chat")
        await setup.commit()

    async def one_request() -> bool:
        async with AsyncSession(engine) as own:
            try:
                await hit(own, integration_id=integration.id, limit=5, window_seconds=60, now=NOW)
            except PublicRateLimitError:
                return False
            return True

    try:
        results = await asyncio.gather(*(one_request() for _ in range(12)))
        async with AsyncSession(engine) as check:
            counts = await count_for(check, integration.id)
        assert results.count(True) == 5
        assert counts == [12]
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(Integration).where(Integration.id == integration.id))
            await cleanup.execute(delete(Account).where(Account.id == owner.id))
            await cleanup.commit()
