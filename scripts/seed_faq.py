import argparse
import asyncio

from sqlalchemy import select

from app.core.llm import embed_documents
from app.db.models import Account, FaqEntry
from app.db.session import dispose_engine, get_sessionmaker


FAQS: list[tuple[str, str]] = [
    ("What are your opening hours?", "We are open Monday to Saturday, 9am to 6pm. We are closed on Sundays."),
    ("Where are you located?", "We are at 12 Example Street, next to the central library."),
    ("Do you fix flat tyres?", "Yes. A puncture repair costs 15 dollars and usually takes about 20 minutes."),
    ("How much is a full bike service?", "A full service costs 80 dollars and includes brakes, gears, chain and a safety check."),
    ("Do I need to book a repair?", "Small repairs are walk-in. For a full service, please book a slot in advance."),
    ("Which payment methods do you accept?", "We accept cash, debit and credit cards, and mobile wallets."),
    ("What is your return policy?", "Unused parts can be returned within 30 days with the receipt."),
    ("Do you sell second-hand bikes?", "Yes, we sell checked second-hand bikes with a 3-month warranty."),
]


async def seed(account_id: int) -> None:
    async with get_sessionmaker()() as session:
        if await session.get(Account, account_id) is None:
            raise SystemExit(f"Account {account_id} does not exist.")
        existing = set(
            await session.scalars(
                select(FaqEntry.question).where(FaqEntry.account_id == account_id)
            )
        )
        new = [(q, a) for q, a in FAQS if q not in existing]
        if not new:
            print(f"Nothing to do: all {len(FAQS)} FAQ entries already exist.")
            return

        vectors = await embed_documents(new)
        session.add_all(
            FaqEntry(account_id=account_id, question=q, answer=a, embedding=v)
            for (q, a), v in zip(new, vectors, strict=True)
        )
        await session.commit()
        print(
            f"Account {account_id}: inserted {len(new)} FAQ entries "
            f"({len(FAQS) - len(new)} already existed)."
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fake FAQ entries for one account.")
    parser.add_argument("--account-id", type=int, required=True)
    args = parser.parse_args()
    try:
        await seed(args.account_id)
    finally:
        await dispose_engine()

if __name__ == "__main__":
    asyncio.run(main())
