import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AccountResponse, LoginRequest, RegisterRequest, TokenResponse
from app.core.config import get_settings
from app.db.models import Account
from app.db.session import DB_ERRORS, get_session
from app.services.accounts import (
    EmailTakenError,
    InvalidAccountError,
    InvalidTokenError,
    authenticate,
    create_access_token,
    decode_access_token,
    get_account,
    register_account,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)

_DB_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Service temporarily unavailable, please try again",
)

_NOT_AUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Account:
    if credentials is None:
        raise _NOT_AUTHENTICATED
    try:
        account_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _NOT_AUTHENTICATED
    try:
        account = await get_account(session, account_id)
    except DB_ERRORS:
        logger.exception("Database error while checking an access token")
        raise _DB_UNAVAILABLE
    if account is None:
        raise _NOT_AUTHENTICATED
    return account


def _account_response(account: Account) -> AccountResponse:
    return AccountResponse(id=account.id, email=account.email, business_name=account.business_name)


@router.post("/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)) -> AccountResponse:
    try:
        account = await register_account(
            session, email=body.email, password=body.password, business_name=body.business_name
        )
        await session.commit()
    except InvalidAccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except EmailTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except DB_ERRORS:
        logger.exception("Database error during registration")
        raise _DB_UNAVAILABLE
    return _account_response(account)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    try:
        account = await authenticate(session, email=body.email, password=body.password)
    except DB_ERRORS:
        logger.exception("Database error during login")
        raise _DB_UNAVAILABLE
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(account.id),
        expires_in=get_settings().access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=AccountResponse)
async def me(account: Account = Depends(get_current_account)) -> AccountResponse:
    return _account_response(account)
