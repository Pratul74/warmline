from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.db_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)

async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker() as session:
        yield session

async def dispose_engine() -> None:
    await get_engine().dispose()
