from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import router as chat_router
from app.db.session import get_session

app = FastAPI(
    title="Warmline - A Sales and support Agent"
)
app.include_router(chat_router)

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
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
            },
        )