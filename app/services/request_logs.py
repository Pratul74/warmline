from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import RequestLog, RequestStatus

TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)
COST_PLACES = Decimal("0.000001")


def compute_cost(input_tokens: int, output_tokens: int) -> Decimal:
    settings = get_settings()
    input_price = Decimal(str(settings.llm_input_price_per_1m_tokens))
    output_price = Decimal(str(settings.llm_output_price_per_1m_tokens))
    cost = (input_tokens * input_price + output_tokens * output_price) / TOKENS_PER_PRICE_UNIT
    return cost.quantize(COST_PLACES, rounding=ROUND_HALF_UP)


async def log_request(
    session: AsyncSession,
    *,
    request_id: UUID,
    conversation_id: int | None,
    status: RequestStatus,
    latency_ms: int,
    steps: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> RequestLog:
    row = RequestLog(
        request_id=request_id,
        conversation_id=conversation_id,
        status=status,
        model=get_settings().gemini_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        steps=steps,
        latency_ms=latency_ms,
        cost_usd=compute_cost(input_tokens, output_tokens),
    )
    session.add(row)
    await session.flush()
    return row
