from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.llm import ChatResult, Message, ToolCall, ToolSpec, chat

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I couldn't finish that request. Could you try rephrasing it?"
INVALID_ARGS_REPLY = (
    "Sorry, I couldn't process those details. Could you check them and send them again?"
)


ToolHandler = Callable[[Any], Awaitable[dict[str, Any]]]
ChatFn = Callable[..., Awaitable[ChatResult]]


@dataclass
class Tool:

    spec: ToolSpec
    args_model: type[BaseModel]
    handler: ToolHandler


@dataclass
class ToolRun:

    step: int
    name: str
    args: dict[str, Any]
    result: dict[str, Any]
    ok: bool


@dataclass
class AgentResult:
    reply: str
    messages: list[Message]
    steps: int = 0
    tool_runs: list[ToolRun] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    hit_step_limit: bool = False
    gave_up_on_tool: str | None = None


ToolStatus = Literal["ok", "error", "invalid_args"]


def describe_validation_error(exc: ValidationError) -> str:
    problems = [
        f"{'.'.join(str(part) for part in err['loc']) or 'input'}: {err['msg']}"
        for err in exc.errors(include_url=False)
    ]
    return "Invalid arguments. " + "; ".join(problems)


async def run_tool(call: ToolCall, tools: dict[str, Tool]) -> tuple[dict[str, Any], ToolStatus]:
    """Check the call against the allowlist and the tool's args_model, then run it."""
    tool = tools.get(call.name)
    if tool is None:
        return {"error": f"Unknown tool '{call.name}'. Available tools: {sorted(tools)}"}, "error"
    try:
        args = tool.args_model.model_validate(call.args)
    except ValidationError as exc:
        return {"error": describe_validation_error(exc)}, "invalid_args"
    try:
        output = await tool.handler(args)
    except Exception:
        logger.exception("Tool %s crashed", call.name)
        return {"error": f"Tool '{call.name}' failed with an internal error."}, "error"
    return output, "error" if "error" in output else "ok"


async def run_agent(
    history: list[Message],
    tools: dict[str, Tool],
    *,
    system: str | None = None,
    chat_fn: ChatFn = chat,
    max_steps: int | None = None,
    max_tool_retries: int | None = None,
) -> AgentResult:
    settings = get_settings()
    max_steps = max_steps or settings.agent_max_steps
    if max_tool_retries is None:
        max_tool_retries = settings.agent_max_tool_retries
    invalid_calls: dict[str, int] = {}
    messages = list(history)
    specs = [tool.spec for tool in tools.values()]
    result = AgentResult(reply="", messages=messages)

    for step in range(1, max_steps + 1):
        reply = await chat_fn(messages, specs, system=system)
        result.steps = step
        result.input_tokens += reply.input_tokens
        result.output_tokens += reply.output_tokens

        if not reply.tool_calls:
            result.reply = reply.text or FALLBACK_REPLY
            messages.append(Message(role="assistant", text=result.reply))
            return result

        messages.append(
            Message(role="assistant", text=reply.text or None, tool_calls=reply.tool_calls)
        )
        for call in reply.tool_calls:
            output, status = await run_tool(call, tools)
            messages.append(Message(role="tool", tool_name=call.name, tool_result=output))
            result.tool_runs.append(
                ToolRun(step=step, name=call.name, args=call.args, result=output, ok=status == "ok")
            )
            if status != "invalid_args":
                continue
            
            invalid_calls[call.name] = invalid_calls.get(call.name, 0) + 1
            if invalid_calls[call.name] > max_tool_retries:
                logger.warning(
                    "Giving up: %s got invalid arguments %d times",
                    call.name,
                    invalid_calls[call.name],
                )
                result.reply = INVALID_ARGS_REPLY
                result.gave_up_on_tool = call.name
                messages.append(Message(role="assistant", text=INVALID_ARGS_REPLY))
                return result

    logger.warning("Agent hit the step limit (%d)", max_steps)
    result.reply = FALLBACK_REPLY
    result.hit_step_limit = True
    messages.append(Message(role="assistant", text=FALLBACK_REPLY))
    return result
