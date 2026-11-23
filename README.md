# Warmline

A sales and support chat agent for small businesses. A customer sends a
message; the agent answers questions from the business's FAQ, lists free
appointment slots, saves interested customers as leads after they confirm, and
records every tool it runs in an audit log.

It uses Google Gemini with native function calling. The agent loop is
hand-written (no LangChain or other agent framework) and short enough to
read in one sitting.

All data in this repo (FAQ entries, slots, names, emails) is fake.

## How a request flows

```
POST /chat {message, conversation_id?}
  └─ handle_chat()                      app/services/chat.py
       ├─ load the last 20 messages of the conversation
       ├─ run_agent()                   app/agent/loop.py
       │    repeat up to AGENT_MAX_STEPS:
       │      chat(messages, tools) ──▶ Gemini         app/core/llm.py
       │      no tool call?  → final reply, stop
       │      tool call(s):  → allowlist check
       │                     → Pydantic validation of the arguments
       │                     → run the tool          app/agent/tools.py
       │                         search_faq  (embedding + pgvector search)
       │                         create_lead (proposes a save; nothing is written)
       │                         confirm_pending_action / cancel_pending_action
       │                         check_availability (free slots for given days)
       │                     → send the result back to the model
       └─ save messages + one tool_calls audit row per tool call,
          in one database transaction
```

| Path | Role |
|---|---|
| `app/core/llm.py` | The only module that imports the Gemini SDK: `chat()`, `embed_query()`, `embed_documents()`, with a timeout and limited retry on 429/503. |
| `app/agent/loop.py` | The agent loop, the tool allowlist, argument validation and the retry cap. |
| `app/agent/tools.py` | Tool definitions: a Pydantic input model + handler for each tool. |
| `app/agent/prompts.py` | The system prompt, with today's date added on each request. |
| `app/services/` | Business logic: chat orchestration, leads, FAQ search, slot availability, the audit log. |
| `app/api/` | The thin FastAPI route and request/response schemas. |
| `app/db/` | SQLAlchemy models and the database session. |
| `migrations/` | Alembic migrations. |
| `scripts/` | `seed_faq.py` (fake FAQ data), `seed_slots.py` (fake slots for the next 14 days), `smoke_gemini.py` (a one-off Gemini function-calling check). |

## Key design decisions

- **Hand-written agent loop with a step limit.** Every model call, tool call and stop condition is visible in about 150 lines, and `AGENT_MAX_STEPS` caps model calls per request, which matters on a free-tier quota.
- **One module talks to the LLM.** The rest of the app uses small dataclasses (`Message`, `ToolSpec`, `ChatResult`), so the SDK can change in one place and tests can pass in a fake.
- **Tool inputs are Pydantic models.** The same model generates the JSON schema sent to Gemini and validates what Gemini sends back. Invalid arguments go back to the model as an error. After the first mistake the model gets `AGENT_MAX_TOOL_RETRIES` (2) more tries per tool, then the agent stops with a fixed reply.
- **Semantic FAQ search.** `gemini-embedding-2` (configured by env) turns questions and FAQ entries into 1536-dimension vectors, and pgvector finds the closest ones. Matches below a cosine similarity of 0.70 are dropped, so the model gets "no matches" instead of a wrong answer.
- **Confirmation before writes, enforced in code.** A write tool (`create_lead`) only stores a pending action and returns the details for the customer to check. The real write runs when the model calls `confirm_pending_action` in a **later** request, after the customer replied. The code refuses a confirmation of an action proposed in the same request, so the model cannot propose and confirm on its own. The claim is a single `UPDATE ... WHERE status = 'pending' AND not expired`, so a second "yes" cannot save twice. Pending actions expire after 10 minutes; a newer proposal replaces an older one.
- **Audit log in the same transaction.** Each tool call is stored with its arguments, status (`ok`, `validation_error`, `rejected`, `error`), result or error, and duration. It is saved together with the messages, so the log never disagrees with the data.
- **Tests never call the API.** The model and the embedder are passed in as functions, and tests pass scripted fakes.

## Run it locally

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker, and a
Gemini API key from Google AI Studio.

```bash
cp .env.example .env                 # then set GEMINI_API_KEY and change the passwords
docker compose up -d db              # Postgres 16 + pgvector on 127.0.0.1:5433
uv sync                              # install dependencies from uv.lock
uv run alembic upgrade head          # create the tables
uv run python -m scripts.seed_faq    # 8 fake FAQ entries (one embedding API call)
uv run python -m scripts.seed_slots  # fake slots, Mon-Sat 10:00/13:00/16:00, next 14 days
uv run uvicorn app.main:app --reload
```

Try it:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
     -d '{"message": "How much does a puncture repair cost?"}'
# continue the same conversation by sending the returned conversation_id:
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
     -d '{"conversation_id": 1, "message": "Please call me back. I am Sam Fake, sam@example.test"}'
```

## Run it with Docker Compose

```bash
docker compose up --build
```

This builds the API image and starts it next to Postgres on
`127.0.0.1:8000`. The container runs `alembic upgrade head` before starting
the server. The API key reaches the container at run time through
`env_file: .env`; `.env` is excluded from the image by `.dockerignore`. To
load the fake FAQ entries and slots, run `uv run python -m scripts.seed_faq` and
`uv run python -m scripts.seed_slots` from the host (the scripts are not in the image).

## Tests, evals and CI

The tests need a test database whose name ends in `test_db` (the test setup
refuses any other). Create it once, using the user and database from your `.env`:

```bash
docker compose exec db psql -U warmline -d warmline -c "CREATE DATABASE warmline_test_db"
uv run pytest -q
```

- **105 tests** run against a real Postgres database, with a fake model and a fake embedder. They cover the LLM wrapper (with a fake SDK client), the agent loop, all five tools, the confirmation flow, the audit log, the error responses and the `/chat` API.
- **12 evals** (`tests/test_evals.py`) are customer-level scenarios run through the real chat service: FAQ hit, FAQ miss, lead captured (with confirmation), lead over several messages, bad arguments then fixed, retry give-up, unknown tool rejected, embedding outage, availability lookup, confirmation in the same turn refused, customer declines, and details corrected before confirming. Each checks the audit-log rows, the reply and the database.
- **What the evals do not prove:** the model in them is scripted, so they test how this code handles each model behaviour, not whether Gemini chooses tools well. They don't test the system prompt or the 0.70 similarity threshold. There is no live evaluation against the real model.
- **CI:** `.github/workflows/tests.yml` runs `uv run pytest -q` on every push and on pull requests to `main`, with a pgvector Postgres service container and placeholder settings (the Gemini key is a dummy, because no test calls the API).

## Configuration

All settings come from environment variables (or `.env`). See `.env.example`.

| Variable | Purpose |
|---|---|
| `DB_URL` | Database for the app (`postgresql+asyncpg://...`). |
| `TEST_DB_URL` | Database for tests; its name must end in `test_db`. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Used by docker compose to create the database. |
| `GEMINI_API_KEY` | Google AI Studio key. Never commit it. |
| `GEMINI_MODEL` | Chat model with function calling. |
| `GEMINI_EMBEDDING_MODEL` | Embedding model for FAQ search. |
| `EMBEDDING_DIM` | Embedding size; must match the `faq_entries` column (1536). |
| `LLM_TIMEOUT_SECONDS` | Timeout for each model call (default 30). |
| `BUSINESS_TIMEZONE` | IANA time zone of the business, e.g. `Europe/London` (default `UTC`). Slot times and today's date use it. |
| `AGENT_MAX_STEPS` | Maximum model calls per request (default 6). |
| `AGENT_MAX_TOOL_RETRIES` | Retries after an invalid tool call, per tool (default 2, max 2). |
| `APP_ENV`, `LOG_LEVEL` | Environment name and log level. |
| `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `LLM_*_PRICE_PER_1M_TOKENS` | Reserved for later features; not used yet. |

## Not built yet

- **Present but not connected:** booking and cancelling in `app/services/booking.py` (only availability is used) and `app/services/request_logs.py` (empty), plus the `request_logs` table. They are not used by the agent, booking has known bugs, and both are planned for the next phase.
- No authentication or per-business accounts, no frontend, no deployment, no cost or latency logging, and no live evaluation set.

## Known limitations

- `POST /chat` returns 429 when Gemini's rate limit persists after retries,
  503 for other model failures, and 503 with a generic message for database
  failures (details go to the server log only). The 429 has no `Retry-After`
  header. Timeouts and network errors are not retried, and the 429/503
  retry waits are fixed (no jitter).
- If the database fails while a tool is running, the tool reports an
  internal error to the model and the model makes one more call before the
  request fails with 503 when saving. That extra model call is wasted. This
  path follows from the code but has no end-to-end test.
- `check_availability` can only list slots; nothing books them yet. The
  prompt tells the model to call a chosen time a request, not a booking, but
  that is an instruction, not a guarantee. It returns at most 10 slots, so a
  long range shows only the earliest ones. Slots are fake seed data with no
  owner, and there is no admin path to edit them.
- `POST /chat` uses sequential conversation ids with no ownership check, so
  anyone who guesses an id can continue that conversation. This is
  acceptable only for local demos with fake data.
- A database connection is held while waiting for the model, so many slow
  model calls at once can exhaust the connection pool.
- Only user and assistant text is stored as conversation history. Tool
  calls are not replayed on later turns.
- `create_lead` checks only the email's shape and treats the same email as
  the same lead.
- Confirmation: the model decides whether the customer's reply means "yes".
  The code guarantees a later request, the same conversation, not expired and
  used once, but not that the customer really agreed to exactly what was
  read back. Expired or abandoned actions keep `status = pending` (there is no
  cleanup job); `expires_at` is what makes them unusable. Saving a lead now
  takes one extra customer message.
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
- Every tool call is written to the `tool_calls` audit table in the same
  transaction as the chat messages. If the model fails later in the same
  request, everything is rolled back, including the audit rows, so that
  failed request leaves no trace. The audit rows store the tool arguments,
  which can include customer contact details.
- The Docker container runs database migrations every time it starts. That
  is fine for one container; with several copies they should run once as a
  separate task. The API container receives the whole `.env`, including
  settings it does not need (such as `TEST_DB_URL` and `POSTGRES_PASSWORD`).
- The evals and tests use a scripted model, so real Gemini behaviour (which
  tool it picks, whether it follows the system prompt) is only checked by
  hand with live runs.
