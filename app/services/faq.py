from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FaqEntry

DEFAULT_TOP_K = 5

MAX_TOP_K = 20

class FaqSearchError(ValueError):
    """Raised when a search request is malformed."""

@dataclass(frozen=True, slots=True)
class FaqMatch:
    entry_id: int
    question: str
    answer: str
    similarity: float


def _expected_dimension() -> int:
    return FaqEntry.embedding.type.dim

def _validate_embedding(query_embedding: Sequence[float]) -> list[float]:
    expected_dim = _expected_dimension()
    if len(query_embedding) != expected_dim:
        raise FaqSearchError(
            f"query_embedding has {len(query_embedding)} dimensions, expected {expected_dim}"
        )
    vector = [float(value) for value in query_embedding]
    if not all(math.isfinite(value) for value in vector):
        raise FaqSearchError("query_embedding contains NaN or infinite values")
    if not any(vector):
        raise FaqSearchError("query_embedding must not be all zeros")
    return vector

def _validate_top_k(top_k: int) -> int:
    if top_k < 1:
        raise FaqSearchError("top_k must be at least 1")
    return min(top_k, MAX_TOP_K)

def _validate_min_similarity(min_similarity: float | None) -> None:
    if min_similarity is not None and not -1.0 <= min_similarity <= 1.0:
        raise FaqSearchError("min_similarity must be between -1 and 1")

async def search_faq(
        session: AsyncSession,
        query_embedding: Sequence[float],
        *,
        account_id: int,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float | None = None,
) -> list[FaqMatch]:
    vector = _validate_embedding(query_embedding)
    limit = _validate_top_k(top_k)
    _validate_min_similarity(min_similarity)

    distance = FaqEntry.embedding.cosine_distance(vector)
    stmt = (
        select(FaqEntry.id, FaqEntry.question, FaqEntry.answer, distance.label("distance"))
        .where(FaqEntry.account_id == account_id)
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    matches = [
        FaqMatch(
            entry_id=row.id,
            question=row.question,
            answer=row.answer,
            similarity=1.0 - float(row.distance)
        )
        for row in rows
    ]
    if min_similarity is None:
        return matches
    return [match for match in matches if match.similarity >= min_similarity]


MAX_PAGE_SIZE = 100


async def list_faq_entries(
    session: AsyncSession, *, account_id: int, page: int, page_size: int
) -> tuple[list[FaqEntry], int]:
    total = await session.scalar(
        select(func.count()).select_from(FaqEntry).where(FaqEntry.account_id == account_id)
    )
    stmt = (
        select(FaqEntry)
        .where(FaqEntry.account_id == account_id)
        .order_by(FaqEntry.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.scalars(stmt)).all()), total or 0
