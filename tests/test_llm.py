import asyncio
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors, types

from app.core import llm
from app.core.config import get_settings
from app.core.llm import LLMError, LLMRateLimitError, Message, ToolCall, ToolSpec, chat, embed_documents, embed_query

LOOKUP_TOOL = ToolSpec(
    name="get_opening_hours",
    description="Opening hours for a day.",
    parameters={"type": "object", "properties": {"day": {"type": "string"}}, "required": ["day"]},
)


class FakeClient:
    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    async def _generate(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return await item()
        return item


def make_response(*parts: types.Part, in_tokens: int = 10, out_tokens: int = 5):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=in_tokens, candidates_token_count=out_tokens
        ),
    )


def api_error(code: int) -> errors.APIError:
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": "fake", "status": "FAKE"}})


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_DELAYS_SECONDS", (0.0, 0.0))


USER_MSG = [Message(role="user", text="Are you open Saturday?")]


async def test_text_reply_is_returned_with_token_counts():
    client = FakeClient([make_response(types.Part(text="Yes, 10 to 4."))])

    result = await chat(USER_MSG, [LOOKUP_TOOL], client=client)

    assert result.text == "Yes, 10 to 4."
    assert result.tool_calls == []
    assert (result.input_tokens, result.output_tokens) == (10, 5)


async def test_tool_call_is_parsed_and_signature_kept():
    call_part = types.Part(
        function_call=types.FunctionCall(id="c1", name="get_opening_hours", args={"day": "Saturday"}),
        thought_signature=b"opaque",
    )
    client = FakeClient([make_response(call_part)])

    result = await chat(USER_MSG, [LOOKUP_TOOL], client=client)

    assert result.text == ""
    assert result.tool_calls == [
        ToolCall(name="get_opening_hours", args={"day": "Saturday"}, id="c1", signature=b"opaque")
    ]


async def test_thinking_text_is_not_returned():
    client = FakeClient(
        [make_response(types.Part(text="let me think", thought=True), types.Part(text="Answer"))]
    )

    result = await chat(USER_MSG, [], client=client)

    assert result.text == "Answer"


async def test_request_has_tools_and_automatic_calling_disabled():
    client = FakeClient([make_response(types.Part(text="ok"))])

    await chat(USER_MSG, [LOOKUP_TOOL], system="Be brief.", client=client)

    config = client.calls[0]["config"]
    assert client.calls[0]["model"] == get_settings().gemini_model
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].name == "get_opening_hours"
    assert config.system_instruction == "Be brief."


async def test_history_sends_signature_back_and_groups_tool_results():
    history = [
        Message(role="user", text="Hours for Sat and Sun?"),
        Message(
            role="assistant",
            tool_calls=[
                ToolCall(name="get_opening_hours", args={"day": "Sat"}, id="a", signature=b"sig"),
                ToolCall(name="get_opening_hours", args={"day": "Sun"}, id="b"),
            ],
        ),
        Message(role="tool", tool_name="get_opening_hours", tool_result={"open": "10"}),
        Message(role="tool", tool_name="get_opening_hours", tool_result={"open": "12"}),
    ]
    client = FakeClient([make_response(types.Part(text="Sat 10, Sun 12"))])

    await chat(history, [LOOKUP_TOOL], client=client)

    contents = client.calls[0]["contents"]
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[0].thought_signature == b"sig"
    assert len(contents[2].parts) == 2
    assert contents[2].parts[1].function_response.response == {"open": "12"}


async def test_rate_limit_is_retried_then_succeeds():
    client = FakeClient([api_error(429), make_response(types.Part(text="ok"))])

    result = await chat(USER_MSG, [], client=client)

    assert result.text == "ok"
    assert len(client.calls) == 2


async def test_rate_limit_every_time_gives_clear_error_after_max_attempts():
    client = FakeClient([api_error(429)] * 5)

    with pytest.raises(LLMRateLimitError, match="rate limit"):
        await chat(USER_MSG, [], client=client)

    assert len(client.calls) == llm.MAX_ATTEMPTS


async def test_bad_request_is_not_retried():
    client = FakeClient([api_error(400), make_response(types.Part(text="never reached"))])

    with pytest.raises(LLMError, match="status 400"):
        await chat(USER_MSG, [], client=client)

    assert len(client.calls) == 1


async def test_server_error_after_retries_is_not_reported_as_rate_limit():
    client = FakeClient([api_error(503)] * 5)

    with pytest.raises(LLMError, match="status 503") as info:
        await chat(USER_MSG, [], client=client)

    assert not isinstance(info.value, LLMRateLimitError)


async def test_network_error_becomes_llm_error_without_retry():
    client = FakeClient([httpx.ConnectError("connection refused"), make_response(types.Part(text="no"))])

    with pytest.raises(LLMError, match="Could not reach the model"):
        await chat(USER_MSG, [], client=client)

    assert len(client.calls) == 1


async def test_timeout_gives_clear_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_timeout_seconds", 0.05)

    async def too_slow():
        await asyncio.sleep(1)

    client = FakeClient([too_slow])

    with pytest.raises(LLMError, match="did not answer"):
        await chat(USER_MSG, [], client=client)


async def test_empty_response_gives_clear_error():
    client = FakeClient([types.GenerateContentResponse(candidates=[])])

    with pytest.raises(LLMError, match="no content"):
        await chat(USER_MSG, [], client=client)


class FakeEmbedClient:
    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(embed_content=self._embed))

    async def _embed(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def embed_response(*vectors: list[float]) -> types.EmbedContentResponse:
    return types.EmbedContentResponse(
        embeddings=[types.ContentEmbedding(values=v) for v in vectors]
    )


def vec(value: float = 0.1) -> list[float]:
    return [value] * get_settings().embedding_dim


async def test_embed_query_sends_task_prefix_model_and_dimension():
    client = FakeEmbedClient([embed_response(vec())])

    result = await embed_query("Are you open?", client=client)

    assert result == vec()
    call = client.calls[0]
    settings = get_settings()
    assert call["model"] == settings.gemini_embedding_model
    assert call["config"].output_dimensionality == settings.embedding_dim
    assert [c.parts[0].text for c in call["contents"]] == ["task: search result | query: Are you open?"]


async def test_embed_documents_sends_one_content_per_document_in_one_call():
    client = FakeEmbedClient([embed_response(vec(0.1), vec(0.2))])

    result = await embed_documents([("Hours?", "9 to 6."), ("Tyres?", "Yes.")], client=client)

    assert result == [vec(0.1), vec(0.2)]
    assert len(client.calls) == 1
    assert [c.parts[0].text for c in client.calls[0]["contents"]] == [
        "title: Hours? | text: 9 to 6.",
        "title: Tyres? | text: Yes.",
    ]


async def test_embed_wrong_count_or_size_gives_clear_error():
    one_for_two = FakeEmbedClient([embed_response(vec())])
    with pytest.raises(LLMError, match="Expected 2 embeddings, got 1"):
        await embed_documents([("a", "b"), ("c", "d")], client=one_for_two)

    too_short = FakeEmbedClient([embed_response([0.1, 0.2])])
    with pytest.raises(LLMError, match="Embedding size"):
        await embed_query("hi", client=too_short)


async def test_embed_rate_limit_is_retried_then_succeeds():
    client = FakeEmbedClient([api_error(429), embed_response(vec())])

    assert await embed_query("hi", client=client) == vec()
    assert len(client.calls) == 2
