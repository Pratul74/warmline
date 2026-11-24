import argparse
import asyncio
from datetime import datetime, time, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.models import Account, Slot
from app.db.session import dispose_engine, get_sessionmaker

DAYS_AHEAD = 14
SLOT_START_TIMES = (time(10, 0), time(13, 0), time(16, 0))
SLOT_LENGTH = timedelta(hours=1)
SUNDAY = 6


def planned_slots(today: datetime, account_id: int) -> list[dict]:
    tz = get_settings().business_tz
    rows = []
    for offset in range(1, DAYS_AHEAD + 1):
        day = today.date() + timedelta(days=offset)
        if day.weekday() == SUNDAY:
            continue
        for start_time in SLOT_START_TIMES:
            start = datetime.combine(day, start_time, tzinfo=tz)
            rows.append({"account_id": account_id, "start_at": start, "end_at": start + SLOT_LENGTH})
    return rows


async def seed(account_id: int) -> None:
    rows = planned_slots(datetime.now(get_settings().business_tz), account_id)
    async with get_sessionmaker()() as session:
        if await session.get(Account, account_id) is None:
            raise SystemExit(f"Account {account_id} does not exist.")
        stmt = insert(Slot).values(rows).on_conflict_do_nothing(
            index_elements=["account_id", "start_at"]
        )
        result = await session.execute(stmt)
        await session.commit()
    print(
        f"Account {account_id}: inserted {result.rowcount} slots "
        f"({len(rows) - result.rowcount} already existed)."
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fake appointment slots for one account.")
    parser.add_argument("--account-id", type=int, required=True)
    args = parser.parse_args()
    try:
        await seed(args.account_id)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
