from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from functools import cache

import jwt
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Account
from app.services.emails import canonicalize_email, email_problem

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
MAX_BUSINESS_NAME_LENGTH = 200

_password_hash = PasswordHash.recommended()


class InvalidAccountError(ValueError):
    """Registration data breaks a rule (email shape, password length, empty name)."""


class EmailTakenError(Exception):
    """An account with this email already exists."""


class InvalidTokenError(Exception):
    """The access token is missing, expired, tampered with or malformed."""


def _clean_registration(email: str, password: str, business_name: str) -> tuple[str, str]:
    canonical_email = canonicalize_email(email)
    problem = email_problem(canonical_email)
    if problem is not None:
        raise InvalidAccountError(problem)
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidAccountError(
            f"password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters"
        )
    clean_name = business_name.strip()
    if not clean_name or len(clean_name) > MAX_BUSINESS_NAME_LENGTH:
        raise InvalidAccountError(f"business name must be 1 to {MAX_BUSINESS_NAME_LENGTH} characters")
    return canonical_email, clean_name


async def register_account(
    session: AsyncSession, *, email: str, password: str, business_name: str
) -> Account:
    canonical_email, clean_name = _clean_registration(email, password, business_name)
    password_hash = await asyncio.to_thread(_password_hash.hash, password)
    account = Account(email=canonical_email, password_hash=password_hash, business_name=clean_name)
    try:
        async with session.begin_nested():
            session.add(account)
    except IntegrityError as exc:
        raise EmailTakenError("An account with this email already exists") from exc
    return account


@cache
def _dummy_hash() -> str:
    return _password_hash.hash("dummy password used only to spend time")


async def authenticate(session: AsyncSession, *, email: str, password: str) -> Account | None:
    if len(password) > MAX_PASSWORD_LENGTH:
        return None
    account = await session.scalar(
        select(Account).where(func.lower(Account.email) == canonicalize_email(email))
    )
    if account is None or account.password_hash is None:
        await asyncio.to_thread(_password_hash.verify, password, _dummy_hash())
        return None
    if not await asyncio.to_thread(_password_hash.verify, password, account.password_hash):
        return None
    return account


def create_access_token(account_id: int, *, now: datetime | None = None) -> str:
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(account_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)


def decode_access_token(token: str) -> int:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError("Invalid or expired token") from exc


async def get_account(session: AsyncSession, account_id: int) -> Account | None:
    return await session.scalar(select(Account).where(Account.id == account_id))
