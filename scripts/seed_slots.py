import asyncio
from datetime import datetime, time, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.models import Slot
from app.db.session import dispose_engine, get_sessionmaker

DAYS_AHEAD = 14
SLOT_START_TIMES = (time(10, 0), time(13, 0), time(16, 0))
SLOT_LENGTH = timedelta(hours=1)
SUNDAY = 6


def planned_slots(today: datetime) -> list[dict]:
    tz = get_settings().business_tz
    rows = []
    for offset in range(1, DAYS_AHEAD + 1):
        day = today.date() + timedelta(days=offset)
        if day.weekday() == SUNDAY:
            continue
        for start_time in SLOT_START_TIMES:
            start = datetime.combine(day, start_time, tzinfo=tz)
            rows.append({"start_at": start, "end_at": start + SLOT_LENGTH})
    return rows


async def seed() -> None:
    rows = planned_slots(datetime.now(get_settings().business_tz))
    async with get_sessionmaker()() as session:
        stmt = insert(Slot).values(rows).on_conflict_do_nothing(index_elements=["start_at"])
        result = await session.execute(stmt)
        await session.commit()
    print(f"Inserted {result.rowcount} slots ({len(rows) - result.rowcount} already existed).")


async def main() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
