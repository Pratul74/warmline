import logging

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.integrations import router as integrations_router
from app.core.config import get_settings
from app.db.session import DB_ERRORS, get_session

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Warmline - A Sales and support Agent"
)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(integrations_router)

@app.get("/")
async def root():
    return {
        "Warmline": "A Sales and support Agent"
    }
@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected",
        }
    except DB_ERRORS:
        logger.exception("Health check could not reach the database")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "database": "disconnected"},
        )