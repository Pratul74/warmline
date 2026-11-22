from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.llm import ChatResult, Message, ToolCall, ToolSpec, chat

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I couldn't finish that request. Could you try rephrasing it?"

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
ChatFn = Callable[..., Awaitable[ChatResult]]


@dataclass
class Tool:

    spec: ToolSpec
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


async def _run_tool(call: ToolCall, tools: dict[str, Tool]) -> tuple[dict[str, Any], bool]:
    tool = tools.get(call.name)
    if tool is None:
        return {"error": f"Unknown tool '{call.name}'. Available tools: {sorted(tools)}"}, False
    try:
        return await tool.handler(call.args), True
    except Exception:
        logger.exception("Tool %s crashed", call.name)
        return {"error": f"Tool '{call.name}' failed with an internal error."}, False


async def run_agent(
    history: list[Message],
    tools: dict[str, Tool],
    *,
    system: str | None = None,
    chat_fn: ChatFn = chat,
    max_steps: int | None = None,
) -> AgentResult:
    max_steps = max_steps or get_settings().agent_max_steps
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
            output, ok = await _run_tool(call, tools)
            messages.append(Message(role="tool", tool_name=call.name, tool_result=output))
            result.tool_runs.append(
                ToolRun(step=step, name=call.name, args=call.args, result=output, ok=ok)
            )

    logger.warning("Agent hit the step limit (%d)", max_steps)
    result.reply = FALLBACK_REPLY
    result.hit_step_limit = True
    messages.append(Message(role="assistant", text=FALLBACK_REPLY))
    return result
