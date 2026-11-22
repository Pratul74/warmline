# Warmline

## Known limitations

- `app/core/llm.py` turns timeouts and HTTP errors from Gemini into a clear
  `LLMError`, but other network failures (DNS failure, connection refused)
  are not caught yet. Timeouts are not retried, and the 429 retry waits are
  fixed (no jitter).
