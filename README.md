# Warmline

## Known limitations

- `app/core/llm.py` turns timeouts and HTTP errors from Gemini into a clear
  `LLMError`, but other network failures (DNS failure, connection refused)
  are not caught yet. Timeouts are not retried, and the 429 retry waits are
  fixed (no jitter).
- `POST /chat` uses sequential conversation ids with no ownership check, so
  anyone who guesses an id can continue that conversation. This is
  acceptable only for local demos with fake data.
- A database connection is held while waiting for the model, so many slow
  model calls at once can exhaust the connection pool.
- Only user and assistant text is stored as conversation history. Tool
  calls are not replayed on later turns.
- `GET /health` includes the raw database error text in its 503 response.
