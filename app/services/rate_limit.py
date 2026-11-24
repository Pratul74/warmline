import math
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RateLimitCounter


class PublicRateLimitError(Exception):

    def __init__(self, retry_after: int):
        super().__init__(f"Rate limit reached, retry after {retry_after} seconds")
        self.retry_after = retry_after


def window_start(now: datetime, window_seconds: int) -> datetime:
    seconds = int(now.timestamp())
    return datetime.fromtimestamp(seconds - seconds % window_seconds, UTC)


async def hit(
    session: AsyncSession,
    *,
    integration_id: int,
    limit: int,
    window_seconds: int,
    now: datetime,
) -> None:
    start = window_start(now, window_seconds)
    statement = (
        insert(RateLimitCounter)
        .values(integration_id=integration_id, window_start=start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitCounter.integration_id, RateLimitCounter.window_start],
            set_={"count": RateLimitCounter.count + 1},
        )
        .returning(RateLimitCounter.count)
    )
    count = await session.scalar(statement)
    await session.commit()
    if count > limit:
        wait = (start + timedelta(seconds=window_seconds) - now).total_seconds()
        raise PublicRateLimitError(retry_after=max(1, math.ceil(wait)))
