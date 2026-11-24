import re
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import Account, Integration, IntegrationStatus
from app.db.session import get_session
from app.main import app
from app.services.integrations import (
    MAX_GREETING_LENGTH,
    MAX_NAME_LENGTH,
    IntegrationNotFoundError,
    InvalidIntegrationError,
    create_integration,
    embed_url,
    get_integration,
    list_integrations,
    rotate_public_id,
    update_integration,
)
from tests.factories import auth_headers, new_account

PUBLIC_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")


@pytest_asyncio.fixture
async def shop_a(session):
    return await new_account(session, business_name="Fake Shop A")


@pytest_asyncio.fixture
async def shop_b(session):
    return await new_account(session, business_name="Fake Shop B")

async def test_create_gives_an_active_integration_with_a_random_public_id(session, shop_a):
    integration = await create_integration(
        session, account_id=shop_a.id, name="  Website chat ", greeting="  Hi! How can we help? "
    )

    assert PUBLIC_ID.match(integration.public_id)
    assert (integration.name, integration.greeting) == ("Website chat", "Hi! How can we help?")
    assert integration.status is IntegrationStatus.ACTIVE
    assert integration.disabled_at is None
    assert integration.created_at is not None


async def test_public_ids_are_not_sequential_or_repeated(session, shop_a):
    ids = [
        (await create_integration(session, account_id=shop_a.id, name=f"Chat {i}")).public_id
        for i in range(20)
    ]

    assert len(set(ids)) == 20
    assert all(PUBLIC_ID.match(public_id) for public_id in ids)


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * (MAX_NAME_LENGTH + 1)},
        {"name": "Ok", "greeting": "x" * (MAX_GREETING_LENGTH + 1)},
    ],
    ids=["empty_name", "blank_name", "long_name", "long_greeting"],
)
async def test_create_rejects_bad_fields(session, shop_a, fields):
    with pytest.raises(InvalidIntegrationError):
        await create_integration(session, account_id=shop_a.id, **fields)


async def test_blank_greeting_is_stored_as_none(session, shop_a):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat", greeting="   ")

    assert integration.greeting is None


async def test_list_and_get_only_see_the_accounts_own_integrations(session, shop_a, shop_b):
    first = await create_integration(session, account_id=shop_a.id, name="First")
    second = await create_integration(session, account_id=shop_a.id, name="Second")
    theirs = await create_integration(session, account_id=shop_b.id, name="B's chat")

    assert [i.id for i in await list_integrations(session, account_id=shop_a.id)] == [first.id, second.id]
    assert [i.id for i in await list_integrations(session, account_id=shop_b.id)] == [theirs.id]
    with pytest.raises(IntegrationNotFoundError):
        await get_integration(session, account_id=shop_a.id, integration_id=theirs.id)


async def test_update_changes_only_the_fields_given(session, shop_a):
    integration = await create_integration(session, account_id=shop_a.id, name="Old", greeting="Hello")

    renamed = await update_integration(
        session, account_id=shop_a.id, integration_id=integration.id, name="New"
    )
    assert (renamed.name, renamed.greeting, renamed.status) == ("New", "Hello", IntegrationStatus.ACTIVE)

    cleared = await update_integration(
        session, account_id=shop_a.id, integration_id=integration.id, greeting=None
    )
    assert (cleared.name, cleared.greeting) == ("New", None)


async def test_disable_keeps_the_first_time_and_enable_clears_it(session, shop_a):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat")
    public_id = integration.public_id

    disabled = await update_integration(
        session, account_id=shop_a.id, integration_id=integration.id, enabled=False
    )
    assert disabled.status is IntegrationStatus.DISABLED
    assert disabled.disabled_at is not None

    first_disabled_at = datetime(2030, 1, 1, tzinfo=UTC)
    disabled.disabled_at = first_disabled_at
    await session.flush()
    again = await update_integration(
        session, account_id=shop_a.id, integration_id=integration.id, enabled=False
    )

    assert again.disabled_at == first_disabled_at
    assert again.public_id == public_id

    enabled = await update_integration(
        session, account_id=shop_a.id, integration_id=integration.id, enabled=True
    )
    assert (enabled.status, enabled.disabled_at) == (IntegrationStatus.ACTIVE, None)


@pytest.mark.parametrize("fields", [{"name": None}, {"name": "  "}, {"enabled": None}])
async def test_update_rejects_bad_fields(session, shop_a, fields):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat")

    with pytest.raises(InvalidIntegrationError):
        await update_integration(
            session, account_id=shop_a.id, integration_id=integration.id, **fields
        )


async def test_another_account_cannot_update_or_rotate(session, shop_a, shop_b):
    theirs = await create_integration(session, account_id=shop_b.id, name="B's chat")
    public_id = theirs.public_id

    with pytest.raises(IntegrationNotFoundError):
        await update_integration(
            session, account_id=shop_a.id, integration_id=theirs.id, name="Taken", enabled=False
        )
    with pytest.raises(IntegrationNotFoundError):
        await rotate_public_id(session, account_id=shop_a.id, integration_id=theirs.id)

    await session.refresh(theirs)
    assert (theirs.name, theirs.status, theirs.public_id) == (
        "B's chat",
        IntegrationStatus.ACTIVE,
        public_id,
    )


async def test_rotate_replaces_the_public_id_and_keeps_the_row(session, shop_a):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat", greeting="Hi")
    old_public_id = integration.public_id

    rotated = await rotate_public_id(session, account_id=shop_a.id, integration_id=integration.id)

    assert rotated.id == integration.id
    assert PUBLIC_ID.match(rotated.public_id)
    assert rotated.public_id != old_public_id
    assert (rotated.name, rotated.greeting) == ("Chat", "Hi")
    old_link_rows = await session.scalar(
        select(func.count()).select_from(Integration).where(Integration.public_id == old_public_id)
    )
    assert old_link_rows == 0


async def test_embed_url_is_built_from_the_configured_base_url(session, shop_a, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_chat_base_url", "https://chat.example.test")
    integration = await create_integration(session, account_id=shop_a.id, name="Chat")

    assert embed_url(integration) == f"https://chat.example.test/c/{integration.public_id}"


def test_base_url_setting_is_cleaned_and_checked():
    assert Settings(public_chat_base_url=" https://chat.example.test/ ").public_chat_base_url == (
        "https://chat.example.test"
    )
    for bad in ["chat.example.test", "ftp://chat.example.test", "https://x.test/?a=1"]:
        with pytest.raises(ValidationError, match="PUBLIC_CHAT_BASE_URL"):
            Settings(public_chat_base_url=bad)


# API


@pytest_asyncio.fixture
async def client(session):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/integrations"),
        ("GET", "/integrations"),
        ("GET", "/integrations/1"),
        ("PATCH", "/integrations/1"),
        ("POST", "/integrations/1/rotate"),
    ],
)
async def test_every_route_needs_an_owner_token(client, method, path):
    response = await client.request(method, path, json={"name": "Chat"})

    assert response.status_code == 401


async def test_owner_creates_lists_and_reads_an_integration(client, shop_a, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_chat_base_url", "https://chat.example.test")
    headers = auth_headers(shop_a)

    created = await client.post(
        "/integrations", json={"name": "Website chat", "greeting": "Hi!"}, headers=headers
    )
    body = created.json()
    listed = await client.get("/integrations", headers=headers)
    one = await client.get(f"/integrations/{body['id']}", headers=headers)

    assert created.status_code == 201
    assert PUBLIC_ID.match(body["public_id"])
    assert body["embed_url"] == f"https://chat.example.test/c/{body['public_id']}"
    assert (body["name"], body["greeting"], body["status"]) == ("Website chat", "Hi!", "active")
    assert body["disabled_at"] is None
    assert listed.status_code == 200 and listed.json() == [body]
    assert one.status_code == 200 and one.json() == body


async def test_another_owners_integration_looks_like_a_missing_one(client, session, shop_a, shop_b):
    theirs = await create_integration(session, account_id=shop_b.id, name="B's chat")
    headers = auth_headers(shop_a)

    responses = [
        await client.get(f"/integrations/{theirs.id}", headers=headers),
        await client.patch(f"/integrations/{theirs.id}", json={"enabled": False}, headers=headers),
        await client.post(f"/integrations/{theirs.id}/rotate", headers=headers),
        await client.get("/integrations/999999", headers=headers),
    ]
    listed = await client.get("/integrations", headers=headers)

    assert [r.status_code for r in responses] == [404, 404, 404, 404]
    assert len({r.text for r in responses}) == 1
    assert listed.json() == []


async def test_patch_disables_and_enables(client, session, shop_a):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat", greeting="Hi")
    headers = auth_headers(shop_a)
    path = f"/integrations/{integration.id}"

    disabled = await client.patch(path, json={"enabled": False}, headers=headers)
    enabled = await client.patch(path, json={"enabled": True}, headers=headers)

    assert disabled.status_code == 200
    assert (disabled.json()["status"], disabled.json()["greeting"]) == ("disabled", "Hi")
    assert disabled.json()["disabled_at"] is not None
    assert (enabled.json()["status"], enabled.json()["disabled_at"]) == ("active", None)


@pytest.mark.parametrize(
    "body",
    [{"name": None}, {"name": ""}, {"enabled": None}, {"enabled": "maybe"}, {"public_id": "mine"}],
    ids=["null_name", "empty_name", "null_enabled", "not_a_bool", "unknown_field"],
)
async def test_patch_rejects_bad_bodies(client, session, shop_a, body):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat")

    response = await client.patch(
        f"/integrations/{integration.id}", json=body, headers=auth_headers(shop_a)
    )

    assert response.status_code == 422
    await session.refresh(integration)
    assert (integration.name, integration.status) == ("Chat", IntegrationStatus.ACTIVE)


async def test_rotate_returns_a_new_link(client, session, shop_a):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat")
    old_public_id = integration.public_id

    response = await client.post(f"/integrations/{integration.id}/rotate", headers=auth_headers(shop_a))

    assert response.status_code == 200
    assert response.json()["id"] == integration.id
    assert response.json()["public_id"] != old_public_id
    assert response.json()["embed_url"].endswith(response.json()["public_id"])


async def test_there_is_no_delete_route(client, session, shop_a):
    integration = await create_integration(session, account_id=shop_a.id, name="Chat")

    response = await client.delete(f"/integrations/{integration.id}", headers=auth_headers(shop_a))

    assert response.status_code == 405


async def test_database_failure_returns_clean_503(client, session, shop_a, monkeypatch):
    headers = auth_headers(shop_a)

    async def db_down(*args, **kwargs):
        raise OperationalError("INSERT integrations", {}, Exception("server at 10.9.8.7 closed"))

    monkeypatch.setattr(session, "flush", db_down)
    response = await client.post("/integrations", json={"name": "Chat"}, headers=headers)

    assert response.status_code == 503
    assert "10.9.8.7" not in response.text


async def test_changes_are_committed_and_visible_to_other_connections(engine):
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        owner = await new_account(setup)
        await setup.commit()

    async def own_session():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = own_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/integrations", json={"name": "Committed"}, headers=auth_headers(owner)
            )
            integration_id = created.json()["id"]
            await client.patch(
                f"/integrations/{integration_id}", json={"enabled": False}, headers=auth_headers(owner)
            )
        async with AsyncSession(engine) as check:
            row = await check.get(Integration, integration_id)
        assert (row.name, row.status) == ("Committed", IntegrationStatus.DISABLED)
    finally:
        app.dependency_overrides.clear()
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(Integration).where(Integration.account_id == owner.id))
            await cleanup.execute(delete(Account).where(Account.id == owner.id))
            await cleanup.commit()
