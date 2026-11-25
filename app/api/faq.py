import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.api.auth import get_current_account
from app.api.schemas import (
    FaqEntryResponse,
    FaqPageResponse,
    FaqRowErrorResponse,
    FaqUploadErrorResponse,
    FaqUploadResponse,
)
from app.core.llm import LLMError, LLMRateLimitError, embed_documents
from app.db.models import Account
from app.db.session import DB_ERRORS, get_session
from app.services.faq import MAX_PAGE_SIZE, list_faq_entries
from app.services.faq_upload import (
    MAX_FILE_BYTES,
    TEMPLATE_CSV,
    EmbedDocumentsFn,
    FaqFileTooLargeError,
    FaqUploadError,
    import_faq_rows,
    parse_faq_csv,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/faq", tags=["faq"])

UNAVAILABLE = "Service temporarily unavailable, please try again"
TOO_LARGE = f"The upload is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB."


def get_embed_documents_fn() -> EmbedDocumentsFn:
    return embed_documents


def _check_request_size(request: Request) -> None:
    length = request.headers.get("content-length")
    if length is None:
        raise HTTPException(status.HTTP_411_LENGTH_REQUIRED, detail="Content-Length header is required")
    if not length.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length header")
    if int(length) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=TOO_LARGE)


async def _read_csv_file(request: Request) -> bytes:
    async with request.form(max_files=1, max_fields=1) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(
                status_code=422, detail="Send the CSV as a multipart form field named 'file'."
            )
        return await upload.read()


def _upload_error(exc: FaqUploadError) -> JSONResponse:
    body = FaqUploadErrorResponse(
        detail=exc.message,
        errors=[FaqRowErrorResponse(row=e.row, field=e.field, message=e.message) for e in exc.errors],
    )
    return JSONResponse(status_code=422, content=body.model_dump())


@router.post(
    "/upload",
    response_model=FaqUploadResponse,
    responses={422: {"model": FaqUploadErrorResponse}, 413: {}, 411: {}},
)
async def upload(
    request: Request,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
    embed_documents_fn: EmbedDocumentsFn = Depends(get_embed_documents_fn),
):
    _check_request_size(request)
    data = await _read_csv_file(request)
    try:
        rows = parse_faq_csv(data)
    except FaqFileTooLargeError:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=TOO_LARGE)
    except FaqUploadError as exc:
        return _upload_error(exc)

    try:
        result = await import_faq_rows(
            session, account_id=account.id, rows=rows, embed_documents_fn=embed_documents_fn
        )
        await session.commit()
    except LLMRateLimitError as exc:
        await session.rollback()
        raise HTTPException(status_code=429, detail=f"{exc} Nothing was saved.")
    except LLMError as exc:
        await session.rollback()
        raise HTTPException(status_code=503, detail=f"{exc}. Nothing was saved.")
    except DB_ERRORS:
        logger.exception("Database error while saving an FAQ upload")
        await session.rollback()
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return FaqUploadResponse(inserted=result.inserted, updated=result.updated, unchanged=result.unchanged)


@router.get("", response_model=FaqPageResponse)
async def list_entries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> FaqPageResponse:
    try:
        entries, total = await list_faq_entries(
            session, account_id=account.id, page=page, page_size=page_size
        )
    except DB_ERRORS:
        logger.exception("Database error while listing FAQ entries")
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return FaqPageResponse(
        items=[
            FaqEntryResponse(
                id=e.id, question=e.question, answer=e.answer, created_at=e.created_at, updated_at=e.updated_at
            )
            for e in entries
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/template.csv", response_class=Response)
async def template() -> Response:
    return Response(
        content=TEMPLATE_CSV.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="faq-template.csv"'},
    )
