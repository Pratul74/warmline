import logging
from collections.abc import Awaitable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_account
from app.api.schemas import IntegrationCreate, IntegrationResponse, IntegrationUpdate
from app.db.models import Account, Integration
from app.db.session import DB_ERRORS, get_session
from app.services.integrations import (
    IntegrationNotFoundError,
    InvalidIntegrationError,
    create_integration,
    embed_url,
    get_integration,
    list_integrations,
    rotate_public_id,
    update_integration,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

T = TypeVar("T")


def _response(integration: Integration) -> IntegrationResponse:
    return IntegrationResponse(
        id=integration.id,
        public_id=integration.public_id,
        embed_url=embed_url(integration),
        name=integration.name,
        greeting=integration.greeting,
        status=integration.status.value,
        created_at=integration.created_at,
        disabled_at=integration.disabled_at,
    )


async def _run(session: AsyncSession, work: Awaitable[T], *, commit: bool) -> T:
    try:
        result = await work
        if commit:
            await session.commit()
        return result
    except IntegrationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    except InvalidIntegrationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DB_ERRORS:
        logger.exception("Database error while handling an integration request")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable, please try again",
        )


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: IntegrationCreate,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> IntegrationResponse:
    work = create_integration(session, account_id=account.id, name=body.name, greeting=body.greeting)
    return _response(await _run(session, work, commit=True))


@router.get("", response_model=list[IntegrationResponse])
async def list_all(
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> list[IntegrationResponse]:
    work = list_integrations(session, account_id=account.id)
    return [_response(integration) for integration in await _run(session, work, commit=False)]


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_one(
    integration_id: int,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> IntegrationResponse:
    work = get_integration(session, account_id=account.id, integration_id=integration_id)
    return _response(await _run(session, work, commit=False))


@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def update(
    integration_id: int,
    body: IntegrationUpdate,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> IntegrationResponse:
    changes = body.model_dump(exclude_unset=True)
    work = update_integration(
        session, account_id=account.id, integration_id=integration_id, **changes
    )
    return _response(await _run(session, work, commit=True))


@router.post("/{integration_id}/rotate", response_model=IntegrationResponse)
async def rotate(
    integration_id: int,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> IntegrationResponse:
    work = rotate_public_id(session, account_id=account.id, integration_id=integration_id)
    return _response(await _run(session, work, commit=True))
