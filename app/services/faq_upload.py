from __future__ import annotations

import csv
import io
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import BaseModel, StringConstraints, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FaqEntry

MAX_FILE_BYTES = 1024 * 1024
MAX_ROWS = 500
MAX_QUESTION_LENGTH = 500
MAX_ANSWER_LENGTH = 2000
EMBED_BATCH_SIZE = 50
REQUIRED_COLUMNS = ("question", "answer")

TEMPLATE_CSV = (
    "question,answer\r\n"
    "What are your opening hours?,\"We are open Monday to Saturday, 9am to 6pm.\"\r\n"
    "Do you offer home delivery?,Yes. Delivery within 5 km is free for orders over 30 dollars.\r\n"
)

EmbedDocumentsFn = Callable[[list[tuple[str, str]]], Awaitable[list[list[float]]]]


@dataclass(frozen=True, slots=True)
class RowError:
    row: int | None
    field: str | None
    message: str


class FaqUploadError(Exception):

    def __init__(self, message: str, errors: list[RowError] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.errors = errors or []


class FaqFileTooLargeError(Exception):
    """The file is bigger than MAX_FILE_BYTES."""


class FaqRow(BaseModel):

    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH)
    ]
    answer: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_ANSWER_LENGTH)
    ]


@dataclass(frozen=True, slots=True)
class ParsedRow:
    row: int
    question: str
    answer: str


@dataclass(frozen=True, slots=True)
class FaqUploadResult:
    inserted: int
    updated: int
    unchanged: int


@dataclass(slots=True)
class _Plan:
    new: list[ParsedRow] = field(default_factory=list)
    changed: list[ParsedRow] = field(default_factory=list)
    unchanged: int = 0


def question_key(question: str) -> str:
    return question.strip().lower()


def _friendly(error: dict) -> str:
    kind = error["type"]
    if kind == "string_too_short":
        return "must not be empty"
    if kind == "string_too_long":
        return f"must be at most {error['ctx']['max_length']} characters (this one has {len(error['input'].strip())})"
    return error["msg"]


def _cell(cells: list[str], index: int) -> str:
    return cells[index] if index < len(cells) else ""


def _column_indexes(header: list[str]) -> tuple[int, int]:
    names = [name.strip().lower() for name in header]
    missing = [column for column in REQUIRED_COLUMNS if column not in names]
    if missing:
        raise FaqUploadError(
            f"Missing column(s): {', '.join(missing)}. "
            "The first row must be a header with the columns 'question' and 'answer'.",
            [RowError(1, None, f"missing column(s): {', '.join(missing)}")],
        )
    repeated = [column for column in REQUIRED_COLUMNS if names.count(column) > 1]
    if repeated:
        raise FaqUploadError(
            f"Column(s) appear more than once in the header: {', '.join(repeated)}.",
            [RowError(1, None, f"repeated column(s): {', '.join(repeated)}")],
        )
    return names.index("question"), names.index("answer")


def parse_faq_csv(data: bytes) -> list[ParsedRow]:
    if len(data) > MAX_FILE_BYTES:
        raise FaqFileTooLargeError
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FaqUploadError(
            "The file is not UTF-8 text. In your spreadsheet, save it as 'CSV UTF-8' and upload again."
        ) from None

    reader = csv.reader(io.StringIO(text, newline=""))
    rows: list[ParsedRow] = []
    errors: list[RowError] = []
    first_row_of: dict[str, int] = {}
    data_rows = 0
    try:
        header = next(reader, None)
        if header is None or not any(cell.strip() for cell in header):
            raise FaqUploadError("The file is empty. The first row must be the header 'question,answer'.")
        question_at, answer_at = _column_indexes(header)

        for row_number, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue
            data_rows += 1
            if data_rows > MAX_ROWS:
                raise FaqUploadError(f"The file has more than {MAX_ROWS} rows. Split it into smaller files.")
            try:
                parsed = FaqRow(question=_cell(cells, question_at), answer=_cell(cells, answer_at))
            except ValidationError as exc:
                errors.extend(
                    RowError(row_number, str(err["loc"][0]), _friendly(err)) for err in exc.errors()
                )
                continue
            key = question_key(parsed.question)
            if key in first_row_of:
                errors.append(
                    RowError(row_number, "question", f"same question as row {first_row_of[key]}")
                )
                continue
            first_row_of[key] = row_number
            rows.append(ParsedRow(row_number, parsed.question, parsed.answer))
    except csv.Error as exc:
        raise FaqUploadError(f"The file is not valid CSV: {exc}.") from None

    if errors:
        raise FaqUploadError(
            f"{len(errors)} problem(s) found. Nothing was saved; fix the rows and upload again.", errors
        )
    if not rows:
        raise FaqUploadError("The file has a header but no FAQ rows.")
    return rows


async def _plan(session: AsyncSession, account_id: int, rows: list[ParsedRow]) -> _Plan:
    key = func.lower(func.btrim(FaqEntry.question))
    result = await session.execute(
        select(key.label("key"), FaqEntry.question, FaqEntry.answer).where(
            FaqEntry.account_id == account_id
        )
    )
    existing = {row.key: (row.question, row.answer) for row in result}
    plan = _Plan()
    for row in rows:
        current = existing.get(question_key(row.question))
        if current is None:
            plan.new.append(row)
        elif current != (row.question, row.answer):
            plan.changed.append(row)
        else:
            plan.unchanged += 1
    return plan


async def import_faq_rows(
    session: AsyncSession,
    *,
    account_id: int,
    rows: list[ParsedRow],
    embed_documents_fn: EmbedDocumentsFn,
) -> FaqUploadResult:
    plan = await _plan(session, account_id, rows)
    to_save = plan.new + plan.changed

    vectors: list[list[float]] = []
    for start in range(0, len(to_save), EMBED_BATCH_SIZE):
        batch = to_save[start : start + EMBED_BATCH_SIZE]
        vectors.extend(await embed_documents_fn([(row.question, row.answer) for row in batch]))

    if to_save:
        stmt = insert(FaqEntry).values(
            [
                {"account_id": account_id, "question": row.question, "answer": row.answer, "embedding": vector}
                for row, vector in zip(to_save, vectors, strict=True)
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[FaqEntry.account_id, func.lower(func.btrim(FaqEntry.question))],
            set_={
                "question": stmt.excluded.question,
                "answer": stmt.excluded.answer,
                "embedding": stmt.excluded.embedding,
                "updated_at": func.now(),
            },
        )
        await session.execute(stmt)

    return FaqUploadResult(inserted=len(plan.new), updated=len(plan.changed), unchanged=plan.unchanged)
