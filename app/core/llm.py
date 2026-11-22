from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from google import genai
from google.genai import errors, types

from app.core.config import get_settings

MAX_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (1.0, 2.0)
RETRYABLE_STATUS_CODES = {429, 503}


class LLMError(Exception):
    """The model call failed. The message is safe to show to API callers."""


@dataclass
class ToolSpec:

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str | None = None
    signature: bytes | None = None


@dataclass
class Message:

    role: Literal["user", "assistant", "tool"]
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int


@lru_cache
def _default_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key.get_secret_value())


def _to_contents(messages: list[Message]) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in messages:
        if msg.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=msg.text or "")]))

        elif msg.role == "assistant":
            parts: list[types.Part] = []
            if msg.text:
                parts.append(types.Part(text=msg.text))
            for call in msg.tool_calls:
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(id=call.id, name=call.name, args=call.args),
                        thought_signature=call.signature,
                    )
                )
            contents.append(types.Content(role="model", parts=parts))

        else: 
            part = types.Part.from_function_response(
                name=msg.tool_name or "", response=msg.tool_result or {}
            )
            last = contents[-1] if contents else None
            if last is not None and last.parts and last.parts[0].function_response is not None:
                last.parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    return contents


def _to_config(tools: list[ToolSpec], system: str | None) -> types.GenerateContentConfig:
    declarations = [
        types.FunctionDeclaration(
            name=t.name, description=t.description, parameters_json_schema=t.parameters
        )
        for t in tools
    ]
    return types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=declarations)] if declarations else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _from_response(response: types.GenerateContentResponse) -> ChatResult:
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None or candidate.content is None:
        reason = candidate.finish_reason if candidate else "no candidates"
        raise LLMError(f"Model returned no content (reason: {reason})")

    texts: list[str] = []
    calls: list[ToolCall] = []
    for part in candidate.content.parts or []:
        if part.function_call is not None:
            calls.append(
                ToolCall(
                    name=part.function_call.name or "",
                    args=dict(part.function_call.args or {}),
                    id=part.function_call.id,
                    signature=part.thought_signature,
                )
            )
        elif part.text and not part.thought:
            texts.append(part.text)

    usage = response.usage_metadata
    return ChatResult(
        text="".join(texts),
        tool_calls=calls,
        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
        output_tokens=(usage.candidates_token_count or 0) if usage else 0,
    )


async def chat(
    messages: list[Message],
    tools: list[ToolSpec],
    *,
    system: str | None = None,
    client: Any = None,
) -> ChatResult:
    settings = get_settings()
    client = client or _default_client()
    contents = _to_contents(messages)
    config = _to_config(tools, system)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with asyncio.timeout(settings.llm_timeout_seconds):
                response = await client.aio.models.generate_content(
                    model=settings.gemini_model, contents=contents, config=config
                )
            return _from_response(response)

        except TimeoutError as exc:
            raise LLMError(f"Model did not answer within {settings.llm_timeout_seconds}s") from exc

        except errors.APIError as exc:
            if exc.code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue
            if exc.code == 429:
                raise LLMError("Model rate limit reached, please try again shortly") from exc
            raise LLMError(f"Model request failed with status {exc.code}") from exc

    raise AssertionError("unreachable")
