from google import genai
from google.genai import types

from app.core.config import get_settings

GET_OPENING_HOURS = types.FunctionDeclaration(
    name="get_opening_hours",
    description="Return the shop's opening hours for a given day of the week.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "day": {"type": "string", "description": "Day of the week, e.g. 'Saturday'"},
        },
        "required": ["day"],
    },
)


def get_opening_hours(day: str) -> dict:
    return {"day": day, "open": "10:00", "close": "16:00"}


def main() -> None:
    settings = get_settings()
    client = genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=int(settings.llm_timeout_seconds * 1000)),
    )
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[GET_OPENING_HOURS])],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text="Are you open on Saturday? What hours?")])
    ]

    print(f"model: {settings.gemini_model}\n")
    first = client.models.generate_content(
        model=settings.gemini_model, contents=contents, config=config
    )

    if not first.function_calls:
        print("No function_call returned. Model text was:")
        print(first.text)
        return

    call = first.function_calls[0]
    print("=== 1. raw function_call from the model ===")
    print(call.model_dump(exclude_none=True))

    result = get_opening_hours(**call.args)
    print("\n=== 2. our local tool result ===")
    print(result)

    contents.append(first.candidates[0].content)
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_function_response(name=call.name, response=result)],
        )
    )
    final = client.models.generate_content(
        model=settings.gemini_model, contents=contents, config=config
    )
    print("\n=== 3. final text from the model ===")
    print(final.text)

    usage = final.usage_metadata
    if usage is not None:
        print(f"\n(tokens, 2nd call: in={usage.prompt_token_count} out={usage.candidates_token_count})")


if __name__ == "__main__":
    main()
