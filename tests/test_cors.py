import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import configure_cors

FRONTEND = "http://localhost:5173"


def make_app(origins: list[str]) -> FastAPI:
    app = FastAPI()

    @app.get("/limited")
    async def limited():
        return JSONResponse({"detail": "slow down"}, status_code=429, headers={"Retry-After": "7"})

    @app.post("/thing")
    async def thing():
        return {"ok": True}

    configure_cors(app, origins)
    return app


async def call(app: FastAPI, method: str, path: str, headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, headers=headers)


async def test_preflight_from_the_allowed_origin_is_accepted():
    response = await call(
        make_app([FRONTEND]),
        "OPTIONS",
        "/thing",
        {
            "Origin": FRONTEND,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and "content-type" in allowed
    assert "access-control-allow-credentials" not in response.headers


async def test_preflight_from_another_origin_is_refused():
    response = await call(
        make_app([FRONTEND]),
        "OPTIONS",
        "/thing",
        {"Origin": "http://evil.example.test", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


async def test_preflight_for_a_method_we_do_not_allow_is_refused():
    response = await call(
        make_app([FRONTEND]),
        "OPTIONS",
        "/thing",
        {"Origin": FRONTEND, "Access-Control-Request-Method": "DELETE"},
    )

    assert response.status_code == 400


async def test_allowed_origin_can_read_retry_after():
    response = await call(make_app([FRONTEND]), "GET", "/limited", {"Origin": FRONTEND})

    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert "retry-after" in response.headers["access-control-expose-headers"].lower()


async def test_other_origin_gets_no_cors_headers():
    response = await call(make_app([FRONTEND]), "GET", "/limited", {"Origin": "http://evil.example.test"})

    assert "access-control-allow-origin" not in response.headers


async def test_no_origins_configured_means_no_cors():
    response = await call(make_app([]), "GET", "/limited", {"Origin": FRONTEND})

    assert "access-control-allow-origin" not in response.headers


def test_origins_setting_is_split_and_cleaned():
    settings = Settings(cors_allowed_origins=" http://localhost:5173/ , https://app.example.test ")
    assert settings.cors_origins == ["http://localhost:5173", "https://app.example.test"]
    assert Settings(cors_allowed_origins="").cors_origins == []


@pytest.mark.parametrize(
    "bad", ["localhost:5173", "ftp://x.test", "http://x.test/path", "*", "http://*.example.test"]
)
def test_origins_setting_rejects_non_origins(bad):
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings(cors_allowed_origins=bad)
