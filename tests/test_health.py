from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_session
from app.main import app


import pytest


class BrokenSession:
    def __init__(self, error: Exception):
        self.error = error

    async def execute(self, *args, **kwargs):
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, Exception("could not connect to server at 10.9.8.7")),
        ConnectionRefusedError("connect to 10.9.8.7 refused"),
    ],
)
async def test_health_reports_db_down_without_leaking_the_error(error):
    async def broken_session():
        yield BrokenSession(error)

    app.dependency_overrides[get_session] = broken_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "unhealthy", "database": "disconnected"}}
    assert "10.9.8.7" not in response.text
