import zlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.faq import get_embed_documents_fn
from app.core.config import EMBEDDING_DIM
from app.core.llm import LLMError, LLMRateLimitError
from app.db.models import FaqEntry
from app.db.session import get_session
from app.main import app
from app.services.faq import search_faq
from app.services.faq_upload import (
    EMBED_BATCH_SIZE,
    MAX_ANSWER_LENGTH,
    MAX_FILE_BYTES,
    MAX_ROWS,
    TEMPLATE_CSV,
    FaqFileTooLargeError,
    FaqUploadError,
    parse_faq_csv,
)
from tests.factories import auth_headers, new_account, new_faq

VALID_CSV = (
    "question,answer\n"
    "What are your opening hours?,9am to 6pm\n"
    "Do you deliver?,Yes within 5 km\n"
    "Where are you?,12 Example Street\n"
)


def vector_for(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[zlib.crc32(text.lower().encode()) % EMBEDDING_DIM] = 1.0
    return vector


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[tuple[str, str]]] = []
        self.error: Exception | None = None

    async def __call__(self, docs: list[tuple[str, str]]) -> list[list[float]]:
        self.calls.append(list(docs))
        if self.error is not None:
            raise self.error
        return [vector_for(question) for question, _ in docs]


@pytest_asyncio.fixture
async def shop_a(session):
    return await new_account(session, business_name="Fake Shop A")


@pytest_asyncio.fixture
async def shop_b(session):
    return await new_account(session, business_name="Fake Shop B")


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest_asyncio.fixture
async def client(session, embedder):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_embed_documents_fn] = lambda: embedder
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def upload(client, account, content: str | bytes, filename: str = "faq.csv"):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return await client.post(
        "/faq/upload", files={"file": (filename, data, "text/csv")}, headers=auth_headers(account)
    )


async def entries_of(session, account) -> dict[str, str]:
    rows = await session.execute(
        select(FaqEntry.question, FaqEntry.answer).where(FaqEntry.account_id == account.id)
    )
    return dict(rows.all())




def test_parse_valid_file_with_bom_odd_headers_extra_column_and_multiline_cell():
    data = (
        "﻿  Answer , QUESTION ,notes\r\n"
        "  9am to 6pm  ,  What are your opening hours?  ,ignored\r\n"
        '"Line one\nline two",Is it two lines?,\r\n'
        ",,\r\n"
        "Yes,Do you deliver?,\r\n"
        ",\r\n"
    ).encode("utf-8")

    rows = parse_faq_csv(data)

    assert [(r.row, r.question, r.answer) for r in rows] == [
        (2, "What are your opening hours?", "9am to 6pm"),
        (3, "Is it two lines?", "Line one\nline two"),
        (5, "Do you deliver?", "Yes"),
    ]


def test_missing_header_names_the_column_and_row_1():
    with pytest.raises(FaqUploadError) as caught:
        parse_faq_csv(b"question,reply\nHours?,9 to 6\n")

    assert "answer" in caught.value.message
    assert [(e.row, e.message) for e in caught.value.errors] == [(1, "missing column(s): answer")]


def test_empty_cell_is_a_row_error_and_all_errors_come_back_together():
    data = (
        "question,answer\n"
        "Hours?,9 to 6\n"
        "Delivery?,   \n"
        ",Orphan answer\n"
        f"Long?,{'x' * (MAX_ANSWER_LENGTH + 1)}\n"
    ).encode()

    with pytest.raises(FaqUploadError) as caught:
        parse_faq_csv(data)

    errors = [(e.row, e.field, e.message) for e in caught.value.errors]
    assert errors == [
        (3, "answer", "must not be empty"),
        (4, "question", "must not be empty"),
        (5, "answer", f"must be at most {MAX_ANSWER_LENGTH} characters (this one has {MAX_ANSWER_LENGTH + 1})"),
    ]
    assert "Nothing was saved" in caught.value.message


def test_over_long_answer_is_rejected():
    with pytest.raises(FaqUploadError) as caught:
        parse_faq_csv(f"question,answer\nHours?,{'a' * (MAX_ANSWER_LENGTH + 1)}\n".encode())

    [error] = caught.value.errors
    assert (error.row, error.field) == (2, "answer")
    assert error.message.startswith(f"must be at most {MAX_ANSWER_LENGTH} characters")


def test_answer_at_the_exact_limit_is_accepted():
    [row] = parse_faq_csv(f"question,answer\nHours?,{'a' * MAX_ANSWER_LENGTH}\n".encode())
    assert len(row.answer) == MAX_ANSWER_LENGTH


def test_duplicate_question_inside_the_file_is_case_insensitive():
    data = b"question,answer\nOpening hours?,9 to 6\nOther?,x\n  OPENING HOURS?  ,10 to 5\n"

    with pytest.raises(FaqUploadError) as caught:
        parse_faq_csv(data)

    assert [(e.row, e.field, e.message) for e in caught.value.errors] == [
        (4, "question", "same question as row 2")
    ]


def test_non_utf8_file_gets_a_clear_message():
    with pytest.raises(FaqUploadError) as caught:
        parse_faq_csv("question,answer\nCafé hours?,9 to 6\n".encode("cp1252"))

    assert "not UTF-8" in caught.value.message


def test_oversized_file_is_refused_by_the_parser_too():
    with pytest.raises(FaqFileTooLargeError):
        parse_faq_csv(b"question,answer\n" + b"x" * MAX_FILE_BYTES)


@pytest.mark.parametrize(
    "data, expected",
    [(b"", "empty"), (b"\xef\xbb\xbf", "empty"), (b"question,answer\n\n,\n", "no FAQ rows")],
    ids=["empty", "bom_only", "header_only"],
)
def test_file_without_rows(data, expected):
    with pytest.raises(FaqUploadError, match=expected):
        parse_faq_csv(data)


def test_more_than_max_rows_is_refused_and_blank_rows_do_not_count():
    body = "".join(f"Question {i}?,Answer {i}\n" for i in range(MAX_ROWS))
    assert len(parse_faq_csv(f"question,answer\n{body}\n\n,\n".encode())) == MAX_ROWS

    with pytest.raises(FaqUploadError, match=f"more than {MAX_ROWS} rows"):
        parse_faq_csv(f"question,answer\n{body}Extra?,x\n".encode())


def test_template_is_a_valid_upload():
    assert len(parse_faq_csv(TEMPLATE_CSV.encode())) == 2

async def test_valid_upload_saves_entries_for_the_owner(client, session, shop_a, embedder):
    response = await upload(client, shop_a, VALID_CSV)

    assert response.status_code == 200, response.text
    assert response.json() == {"inserted": 3, "updated": 0, "unchanged": 0}
    assert await entries_of(session, shop_a) == {
        "What are your opening hours?": "9am to 6pm",
        "Do you deliver?": "Yes within 5 km",
        "Where are you?": "12 Example Street",
    }
    assert len(embedder.calls) == 1 and len(embedder.calls[0]) == 3


async def test_reupload_of_the_same_file_changes_nothing_and_embeds_nothing(client, session, shop_a, embedder):
    await upload(client, shop_a, VALID_CSV)
    embedder.calls.clear()

    response = await upload(client, shop_a, VALID_CSV)

    assert response.json() == {"inserted": 0, "updated": 0, "unchanged": 3}
    count = await session.scalar(
        select(func.count()).select_from(FaqEntry).where(FaqEntry.account_id == shop_a.id)
    )
    assert count == 3
    assert embedder.calls == []


async def test_reupload_with_changes_updates_answers_without_duplicates(client, session, shop_a, embedder):
    await upload(client, shop_a, VALID_CSV)
    before = await session.scalar(
        select(FaqEntry).where(FaqEntry.question == "Do you deliver?", FaqEntry.account_id == shop_a.id)
    )
    before_id, before_updated = before.id, before.updated_at
    embedder.calls.clear()

    changed = (
        "question,answer\n"
        "What are your opening hours?,9am to 6pm\n"
        "  do you DELIVER?  ,Yes within 10 km\n"
        "Is parking free?,Yes\n"
    )
    response = await upload(client, shop_a, changed)

    assert response.json() == {"inserted": 1, "updated": 1, "unchanged": 1}
    entries = await entries_of(session, shop_a)
    assert entries["do you DELIVER?"] == "Yes within 10 km"
    assert "Do you deliver?" not in entries
    assert len(entries) == 4
    after = await session.scalar(
        select(FaqEntry).where(FaqEntry.question == "do you DELIVER?").execution_options(populate_existing=True)
    )
    assert after.id == before_id and after.updated_at >= before_updated
    assert [q for q, _ in embedder.calls[0]] == ["Is parking free?", "do you DELIVER?"]


async def test_invalid_file_saves_nothing_and_returns_every_row_error(client, session, shop_a, embedder):
    bad = "question,answer\nGood?,Fine\nNo answer?,\nGood?,Again\n"

    response = await upload(client, shop_a, bad)

    assert response.status_code == 422
    body = response.json()
    assert body["errors"] == [
        {"row": 3, "field": "answer", "message": "must not be empty"},
        {"row": 4, "field": "question", "message": "same question as row 2"},
    ]
    assert "Nothing was saved" in body["detail"]
    assert await entries_of(session, shop_a) == {}
    assert embedder.calls == []


async def test_missing_header_returns_422_with_row_1(client, shop_a):
    response = await upload(client, shop_a, "q,a\nHours?,9 to 6\n")

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"row": 1, "field": None, "message": "missing column(s): question, answer"}
    ]


async def test_non_utf8_upload_returns_422(client, shop_a):
    response = await upload(client, shop_a, "question,answer\nCafé?,Oui\n".encode("latin-1"))

    assert response.status_code == 422
    assert "not UTF-8" in response.json()["detail"]
    assert response.json()["errors"] == []


async def test_oversized_upload_is_refused_before_reading(client, session, shop_a, embedder):
    big = "question,answer\n" + "Q?," + "x" * MAX_FILE_BYTES + "\n"

    response = await upload(client, shop_a, big)

    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]
    assert embedder.calls == []


async def test_oversized_request_is_refused_without_parsing_the_form(client, shop_a, monkeypatch):

    async def must_not_read(request):
        raise AssertionError("the form was read")

    monkeypatch.setattr("app.api.faq._read_csv_file", must_not_read)

    response = await upload(client, shop_a, "x" * (MAX_FILE_BYTES + 1))

    assert response.status_code == 413


async def test_upload_without_content_length_is_refused(client, shop_a):
    async def chunks():
        yield b"--x\r\nContent-Disposition: form-data; name=\"file\"; filename=\"f.csv\"\r\n\r\n"
        yield b"question,answer\r\nHours?,9\r\n--x--\r\n"

    response = await client.post(
        "/faq/upload",
        content=chunks(),
        headers={**auth_headers(shop_a), "Content-Type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 411


async def test_upload_without_a_file_field_is_refused(client, shop_a):
    response = await client.post("/faq/upload", data={"other": "x"}, headers=auth_headers(shop_a))

    assert response.status_code == 422
    assert "field named 'file'" in response.json()["detail"]


async def test_upload_needs_an_owner_token(client, embedder):
    response = await client.post("/faq/upload", files={"file": ("f.csv", VALID_CSV.encode(), "text/csv")})

    assert response.status_code == 401
    assert embedder.calls == []


@pytest.mark.parametrize(
    "error, status, text",
    [
        (LLMRateLimitError("Model rate limit reached, please try again shortly"), 429, "rate limit"),
        (LLMError("Model request failed with status 500"), 503, "status 500"),
    ],
    ids=["rate_limited", "model_down"],
)
async def test_embedding_failure_saves_nothing(client, session, shop_a, embedder, error, status, text):
    embedder.error = error

    response = await upload(client, shop_a, VALID_CSV)

    assert response.status_code == status
    assert text in response.json()["detail"] and "Nothing was saved" in response.json()["detail"]
    assert await entries_of(session, shop_a) == {}


async def test_new_rows_are_embedded_in_batches(client, session, shop_a, embedder):
    total = EMBED_BATCH_SIZE * 2 + 7
    rows = "".join(f"Question {i}?,Answer {i}\n" for i in range(total))

    response = await upload(client, shop_a, "question,answer\n" + rows)

    assert response.json()["inserted"] == total
    assert [len(call) for call in embedder.calls] == [EMBED_BATCH_SIZE, EMBED_BATCH_SIZE, 7]


async def test_uploaded_entries_are_found_by_search_faq(client, session, shop_a, shop_b):
    await upload(client, shop_a, VALID_CSV)

    found = await search_faq(session, vector_for("Do you deliver?"), account_id=shop_a.id, min_similarity=0.99)
    other = await search_faq(session, vector_for("Do you deliver?"), account_id=shop_b.id)

    assert [(m.question, m.answer) for m in found] == [("Do you deliver?", "Yes within 5 km")]
    assert other == []

async def test_upload_and_list_for_a_never_touch_or_show_b(client, session, shop_a, shop_b):
    b_entry = await new_faq(
        session, shop_b.id, question="Do you deliver?", answer="B's answer", embedding=vector_for("b")
    )

    response = await upload(client, shop_a, VALID_CSV)

    assert response.json() == {"inserted": 3, "updated": 0, "unchanged": 0}
    await session.refresh(b_entry)
    assert (b_entry.account_id, b_entry.answer) == (shop_b.id, "B's answer")
    assert await entries_of(session, shop_b) == {"Do you deliver?": "B's answer"}

    a_list = (await client.get("/faq", headers=auth_headers(shop_a))).json()
    b_list = (await client.get("/faq", headers=auth_headers(shop_b))).json()
    assert a_list["total"] == 3 and b_entry.id not in [item["id"] for item in a_list["items"]]
    assert b_list["total"] == 1 and [item["answer"] for item in b_list["items"]] == ["B's answer"]


async def test_list_is_paginated(client, session, shop_a):
    for i in range(25):
        await new_faq(session, shop_a.id, question=f"Q{i:02}?", answer=f"A{i}", embedding=vector_for(str(i)))

    page_1 = (await client.get("/faq?page=1&page_size=10", headers=auth_headers(shop_a))).json()
    page_3 = (await client.get("/faq?page=3&page_size=10", headers=auth_headers(shop_a))).json()
    page_4 = (await client.get("/faq?page=4&page_size=10", headers=auth_headers(shop_a))).json()

    assert (page_1["total"], page_1["page"], page_1["page_size"]) == (25, 1, 10)
    assert [item["question"] for item in page_1["items"]] == [f"Q{i:02}?" for i in range(10)]
    assert [item["question"] for item in page_3["items"]] == [f"Q{i:02}?" for i in range(20, 25)]
    assert page_4["items"] == [] and page_4["total"] == 25
    assert set(page_1["items"][0]) == {"id", "question", "answer", "created_at", "updated_at"}


async def test_list_defaults_and_empty_account(client, shop_a):
    response = await client.get("/faq", headers=auth_headers(shop_a))

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101", "page=x"])
async def test_list_rejects_bad_paging(client, shop_a, query):
    response = await client.get(f"/faq?{query}", headers=auth_headers(shop_a))
    assert response.status_code == 422


async def test_list_needs_an_owner_token(client):
    assert (await client.get("/faq")).status_code == 401

async def test_template_download_needs_no_login(client):
    response = await client.get("/faq/template.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="faq-template.csv"' in response.headers["content-disposition"]
    assert response.text.startswith("question,answer")


async def test_database_refuses_the_same_question_twice_in_one_account(session, shop_a, shop_b):
    await new_faq(session, shop_a.id, question="Hours?", answer="9", embedding=vector_for("1"))
    await new_faq(session, shop_b.id, question="Hours?", answer="10", embedding=vector_for("2"))  # other account: fine

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await new_faq(session, shop_a.id, question="  HOURS?  ", answer="11", embedding=vector_for("3"))
