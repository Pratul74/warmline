from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.chat import get_chat_fn
from app.core.config import Settings, get_settings
from app.core.llm import ChatResult
from app.db.models import Account, Conversation
from app.db.session import get_session
from app.main import app
from app.services import accounts
from app.services.accounts import (
    EmailTakenError,
    InvalidAccountError,
    InvalidTokenError,
    authenticate,
    create_access_token,
    decode_access_token,
    register_account,
)
from tests.factories import auth_headers, new_account, new_conversation

PASSWORD = "correct horse battery"


class ScriptedChat:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls = 0

    async def __call__(self, messages, tools, *, system=None):
        self.calls += 1
        return ChatResult(text=self.replies.pop(0), tool_calls=[], input_tokens=1, output_tokens=1)


@pytest_asyncio.fixture
async def client(session):
    fake = ScriptedChat(["Hello from the bot"])

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_chat_fn] = lambda: fake
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.fake = fake
        yield c
    app.dependency_overrides.clear()

async def test_register_stores_a_password_hash_and_a_canonical_email(session):
    account = await register_account(
        session, email="  Owner@Example.TEST ", password=PASSWORD, business_name="  Fake Bikes "
    )

    assert account.email == "owner@example.test"
    assert account.business_name == "Fake Bikes"
    assert account.password_hash != PASSWORD
    assert account.password_hash.startswith("$argon2id$")


@pytest.mark.parametrize(
    "email, password, name",
    [
        ("not-an-email", PASSWORD, "Shop"),
        ("owner@example.test", "short", "Shop"),
        ("owner@example.test", "x" * 129, "Shop"),
        ("owner@example.test", PASSWORD, "   "),
    ],
    ids=["bad_email", "short_password", "long_password", "blank_name"],
)
async def test_register_rejects_bad_input(session, email, password, name):
    with pytest.raises(InvalidAccountError):
        await register_account(session, email=email, password=password, business_name=name)


async def test_duplicate_email_in_any_case_is_refused_and_the_first_account_survives(session):
    first = await register_account(session, email="dup@example.test", password=PASSWORD, business_name="A")

    with pytest.raises(EmailTakenError):
        await register_account(session, email="DUP@example.test", password=PASSWORD, business_name="B")

    rows = (await session.scalars(select(Account).where(Account.email == "dup@example.test"))).all()
    assert [a.id for a in rows] == [first.id]


async def test_authenticate_accepts_only_the_right_password(session):
    account = await register_account(session, email="login@example.test", password=PASSWORD, business_name="A")

    assert await authenticate(session, email="LOGIN@example.test", password=PASSWORD) == account
    assert await authenticate(session, email="login@example.test", password=PASSWORD + "x") is None
    assert await authenticate(session, email="nobody@example.test", password=PASSWORD) is None


async def test_account_without_a_password_can_never_log_in(session):
    legacy = await new_account(session)

    assert await authenticate(session, email=legacy.email, password="") is None
    assert await authenticate(session, email=legacy.email, password=PASSWORD) is None


async def test_unknown_email_still_runs_a_password_check(session, monkeypatch):
    checks = []
    real_verify = accounts._password_hash.verify
    monkeypatch.setattr(
        accounts._password_hash, "verify", lambda pw, h: checks.append(h) or real_verify(pw, h)
    )

    assert await authenticate(session, email="nobody@example.test", password=PASSWORD) is None
    assert len(checks) == 1


def test_token_round_trip_returns_the_account_id():
    assert decode_access_token(create_access_token(42)) == 42


def test_expired_token_is_refused():
    minutes = get_settings().access_token_expire_minutes
    old = create_access_token(42, now=datetime.now(UTC) - timedelta(minutes=minutes + 1))

    with pytest.raises(InvalidTokenError):
        decode_access_token(old)


def _forge(payload: dict, *, key: str, algorithm: str) -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


@pytest.mark.parametrize(
    "token_maker",
    [
        lambda: create_access_token(42)[:-3] + "abc",
        lambda: _forge(
            {"sub": "42", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)},
            key="an-attacker-key-that-is-long-enough-123",
            algorithm="HS256",
        ),
        lambda: _forge(
            {"sub": "42", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)},
            key="",
            algorithm="none",
        ),
        lambda: _forge(
            {"sub": "42", "iat": datetime.now(UTC)},
            key=get_settings().secret_key.get_secret_value(),
            algorithm=get_settings().algorithm,
        ),
        lambda: _forge(
            {"sub": "admin", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)},
            key=get_settings().secret_key.get_secret_value(),
            algorithm=get_settings().algorithm,
        ),
        lambda: "not-a-jwt",
    ],
    ids=["tampered", "wrong_key", "alg_none", "no_exp", "non_numeric_sub", "garbage"],
)
def test_bad_tokens_are_refused(token_maker):
    with pytest.raises(InvalidTokenError):
        decode_access_token(token_maker())


def test_short_secret_key_is_rejected_at_startup():
    with pytest.raises(ValidationError, match="SECRET_KEY must be at least 32"):
        Settings(secret_key="too-short")

async def test_register_then_login_then_me(client):
    registered = await client.post(
        "/auth/register",
        json={"email": "flow@example.test", "password": PASSWORD, "business_name": "Fake Yoga"},
    )
    assert registered.status_code == 201
    assert "password" not in registered.text

    login = await client.post("/auth/login", json={"email": "flow@example.test", "password": PASSWORD})
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json() == {"id": registered.json()["id"], "email": "flow@example.test", "business_name": "Fake Yoga"}


async def test_register_reports_duplicates_and_weak_passwords(client):
    body = {"email": "taken@example.test", "password": PASSWORD, "business_name": "A"}
    assert (await client.post("/auth/register", json=body)).status_code == 201

    duplicate = await client.post("/auth/register", json=body)
    weak = await client.post("/auth/register", json={**body, "email": "new@example.test", "password": "short"})

    assert duplicate.status_code == 409
    assert weak.status_code == 422


async def test_wrong_password_and_unknown_email_get_the_same_answer(client):
    await client.post(
        "/auth/register", json={"email": "same@example.test", "password": PASSWORD, "business_name": "A"}
    )

    wrong_password = await client.post("/auth/login", json={"email": "same@example.test", "password": "nope"})
    unknown_email = await client.post("/auth/login", json={"email": "ghost@example.test", "password": "nope"})

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()

@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": f"Bearer {create_access_token(999_999)}"},
    ],
    ids=["no_header", "bad_token", "wrong_scheme", "deleted_account"],
)
async def test_chat_without_a_valid_owner_token_is_refused_before_the_model(client, headers):
    response = await client.post("/chat", json={"message": "hi"}, headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert client.fake.calls == 0


async def test_new_chat_conversation_belongs_to_the_caller(client, session):
    await new_account(session, business_name="Someone else")  # so the caller is not the only account
    owner = await new_account(session)

    response = await client.post("/chat", json={"message": "hi"}, headers=auth_headers(owner))

    assert response.status_code == 200
    conversation = await session.get(Conversation, response.json()["conversation_id"])
    assert conversation.account_id == owner.id


async def test_owner_cannot_continue_another_owners_conversation(client, session):
    owner_a = await new_account(session, business_name="A")
    owner_b = await new_account(session, business_name="B")
    a_conversation = await new_conversation(session, owner_a)

    response = await client.post(
        "/chat",
        json={"conversation_id": a_conversation.id, "message": "show me your leads"},
        headers=auth_headers(owner_b),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}  # same as a missing conversation
    assert client.fake.calls == 0


async def test_database_failure_while_checking_the_token_returns_clean_503(client, session, monkeypatch):
    owner = await new_account(session)
    headers = auth_headers(owner)

    async def db_down(*args, **kwargs):
        raise OperationalError("SELECT accounts", {}, Exception("server at 10.9.8.7 closed the connection"))

    monkeypatch.setattr(session, "scalar", db_down)
    response = await client.post("/chat", json={"message": "hi"}, headers=headers)

    assert response.status_code == 503
    assert "10.9.8.7" not in response.text
    assert client.fake.calls == 0
