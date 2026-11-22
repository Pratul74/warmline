import pytest

from app.agent.loop import FALLBACK_REPLY, Tool, run_agent
from app.core.llm import ChatResult, LLMError, Message, ToolCall, ToolSpec


class ScriptedChat:
    def __init__(self, script: list):
        self.script = list(script)
        self.seen: list[list[Message]] = []

    async def __call__(self, messages, tools, *, system=None):
        self.seen.append(list(messages))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def text(reply: str) -> ChatResult:
    return ChatResult(text=reply, tool_calls=[], input_tokens=10, output_tokens=5)


def calls(*tool_calls: ToolCall) -> ChatResult:
    return ChatResult(text="", tool_calls=list(tool_calls), input_tokens=10, output_tokens=5)


async def get_hours(args: dict) -> dict:
    return {"day": args["day"], "open": "10:00", "close": "16:00"}


async def broken(args: dict) -> dict:
    raise RuntimeError("database password is hunter2")


def spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=name, parameters={"type": "object", "properties": {}})


TOOLS = {
    "get_hours": Tool(spec("get_hours"), get_hours),
    "broken": Tool(spec("broken"), broken),
}
USER = [Message(role="user", text="Are you open Saturday?")]


async def test_plain_answer_finishes_in_one_step():
    fake = ScriptedChat([text("Hello!")])

    result = await run_agent(USER, TOOLS, chat_fn=fake)

    assert result.reply == "Hello!"
    assert result.steps == 1
    assert result.tool_runs == []
    assert result.messages[-1] == Message(role="assistant", text="Hello!")
    assert len(USER) == 1


async def test_tool_call_then_answer():
    fake = ScriptedChat(
        [calls(ToolCall(name="get_hours", args={"day": "Saturday"})), text("Open 10 to 4.")]
    )

    result = await run_agent(USER, TOOLS, chat_fn=fake)

    assert result.reply == "Open 10 to 4."
    assert result.steps == 2
    assert [(r.name, r.ok) for r in result.tool_runs] == [("get_hours", True)]
    last_seen = fake.seen[1][-1]
    assert last_seen.role == "tool"
    assert last_seen.tool_result == {"day": "Saturday", "open": "10:00", "close": "16:00"}
    assert (result.input_tokens, result.output_tokens) == (20, 10)


async def test_two_tools_in_one_turn_both_run():
    fake = ScriptedChat(
        [
            calls(
                ToolCall(name="get_hours", args={"day": "Sat"}),
                ToolCall(name="get_hours", args={"day": "Sun"}),
            ),
            text("Both days 10 to 4."),
        ]
    )

    result = await run_agent(USER, TOOLS, chat_fn=fake)

    assert [r.args["day"] for r in result.tool_runs] == ["Sat", "Sun"]
    assert all(r.step == 1 for r in result.tool_runs)


async def test_unknown_tool_is_not_run_and_model_is_told():
    fake = ScriptedChat(
        [calls(ToolCall(name="delete_all_leads", args={})), text("Sorry, I can't do that.")]
    )

    result = await run_agent(USER, TOOLS, chat_fn=fake)

    run = result.tool_runs[0]
    assert run.ok is False
    assert "Unknown tool 'delete_all_leads'" in run.result["error"]
    assert result.reply == "Sorry, I can't do that."


async def test_crashing_tool_reports_generic_error_without_leaking_details():
    fake = ScriptedChat([calls(ToolCall(name="broken", args={})), text("Something went wrong.")])

    result = await run_agent(USER, TOOLS, chat_fn=fake)

    run = result.tool_runs[0]
    assert run.ok is False
    assert run.result == {"error": "Tool 'broken' failed with an internal error."}
    assert "hunter2" not in str(fake.seen[1])


async def test_step_limit_stops_a_model_that_never_answers():
    endless = [calls(ToolCall(name="get_hours", args={"day": "Sat"}))] * 10
    fake = ScriptedChat(endless)

    result = await run_agent(USER, TOOLS, chat_fn=fake, max_steps=3)

    assert result.hit_step_limit is True
    assert result.steps == 3
    assert len(fake.seen) == 3
    assert result.reply == FALLBACK_REPLY


async def test_empty_model_text_gets_fallback_reply():
    fake = ScriptedChat([text("")])

    result = await run_agent(USER, TOOLS, chat_fn=fake)

    assert result.reply == FALLBACK_REPLY


async def test_llm_error_propagates_to_caller():
    fake = ScriptedChat([LLMError("Model rate limit reached")])

    with pytest.raises(LLMError, match="rate limit"):
        await run_agent(USER, TOOLS, chat_fn=fake)
