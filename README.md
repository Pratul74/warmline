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
- `create_lead` saves a lead without asking the customer to confirm it,
  checks only the email's shape, and treats the same email as the same lead.
- `search_faq` uses a similarity threshold (0.70) chosen from a small live
  test with fake FAQ data. The gap between right and wrong matches was
  narrow (0.71 vs 0.68), so it needs checking against real FAQs. Each FAQ
  question costs one extra embedding API call. FAQ entries are shared by
  everyone (no per-business owner yet), and editing an answer requires
  re-running the embedding for that entry.
- If the model sends invalid tool arguments three times for the same tool
  in one request, the agent stops with a generic "please check your
  details" reply. Any write already made in that request (such as a saved
  lead) is kept. Tool errors that are not validation errors (for example,
  an email that fails the business check) are limited only by the overall
  step limit.
