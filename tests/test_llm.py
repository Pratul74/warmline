import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors, types

from app.core import llm
from app.core.config import get_settings
from app.core.llm import LLMError, Message, ToolCall, ToolSpec, chat

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

    with pytest.raises(LLMError, match="rate limit"):
        await chat(USER_MSG, [], client=client)

    assert len(client.calls) == llm.MAX_ATTEMPTS


async def test_bad_request_is_not_retried():
    client = FakeClient([api_error(400), make_response(types.Part(text="never reached"))])

    with pytest.raises(LLMError, match="status 400"):
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
