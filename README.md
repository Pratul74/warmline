# Warmline

A sales and support chat agent for small businesses. A customer sends a
message; the agent answers questions from the business's FAQ, lists free
appointment slots, and, after the customer confirms, saves leads and books or
cancels slots. It records every tool it runs in an audit log.

A React web app (`frontend/`) gives business owners a dashboard for their
chat links, and gives visitors the hosted chat page that a link opens.

It uses Google Gemini with native function calling. The agent loop is
hand-written (no LangChain or other agent framework) and short enough to
read in one sitting.

All data in this repo (FAQ entries, slots, names, emails) is fake.

## How a request flows

```
POST /chat {message, conversation_id?}   Authorization: Bearer <owner token>
  ├─ get_current_account()              app/api/auth.py  (401 without a valid token)
  └─ handle_chat()                      app/services/chat.py
       ├─ load the conversation (404 if it belongs to another account)
       │  and its last 20 messages
       ├─ run_agent()                   app/agent/loop.py
       │    repeat up to AGENT_MAX_STEPS:
       │      chat(messages, tools) ──▶ Gemini         app/core/llm.py
       │      no tool call?  → final reply, stop
       │      tool call(s):  → allowlist check
       │                     → Pydantic validation of the arguments
       │                     → run the tool          app/agent/tools.py
       │                         search_faq  (embedding + pgvector search)
       │                         create_lead (proposes a save; nothing is written)
       │                         confirm_pending_action / decline_pending_action
       │                         check_availability (free slots for given days)
       │                         book_slot / cancel_booking (propose; nothing is written)
       │                     → send the result back to the model
       └─ save messages + one tool_calls audit row per tool call,
          in one database transaction
          (if a model call fails: roll back, then save only the audit rows
           and a failed request_logs row, and return 429/503)

POST /public/c/{public_id}/messages {message, conversation_token?}   (no login)
  └─ handle_public_chat()               app/services/public_chat.py
       ├─ look up the integration by public_id (404 unknown or rotated, 403 disabled)
       ├─ count the message for this link and commit (429 + Retry-After if over the limit)
       ├─ with a token: find the conversation by the token's hash AND this integration (404 otherwise)
       └─ handle_chat() as above, with the integration's owner as the account
```

| Path | Role |
|---|---|
| `app/core/llm.py` | The only module that imports the Gemini SDK: `chat()`, `embed_query()`, `embed_documents()`, with a timeout and limited retry on 429/503. |
| `app/agent/loop.py` | The agent loop, the tool allowlist, argument validation and the retry cap. |
| `app/agent/tools.py` | Tool definitions: a Pydantic input model + handler for each tool. |
| `app/agent/prompts.py` | The system prompt, with today's date added on each request. |
| `app/services/` | Business logic: chat orchestration, owner accounts and login, integrations (chat links), public chat through a link, the per-link rate limit, leads, FAQ search, slot availability, the audit log. |
| `app/api/` | Thin FastAPI routes (`/auth/*`, `/chat`, `/integrations`, `/public/c/*`) and request/response schemas. |
| `app/db/` | SQLAlchemy models and the database session. |
| `migrations/` | Alembic migrations. |
| `scripts/` | `seed_faq.py` (fake FAQ data), `seed_slots.py` (fake slots for the next 14 days), `smoke_gemini.py` (a one-off Gemini function-calling check). |

## Key design decisions

- **Hand-written agent loop with a step limit.** Every model call, tool call and stop condition is visible in about 150 lines, and `AGENT_MAX_STEPS` caps model calls per request, which matters on a free-tier quota.
- **One module talks to the LLM.** The rest of the app uses small dataclasses (`Message`, `ToolSpec`, `ChatResult`), so the SDK can change in one place and tests can pass in a fake.
- **Tool inputs are Pydantic models.** The same model generates the JSON schema sent to Gemini and validates what Gemini sends back. Invalid arguments go back to the model as an error. After the first mistake the model gets `AGENT_MAX_TOOL_RETRIES` (2) more tries per tool, then the agent stops with a fixed reply.
- **Semantic FAQ search.** `gemini-embedding-2` (configured by env) turns questions and FAQ entries into 1536-dimension vectors, and pgvector finds the closest ones. Matches below a cosine similarity of 0.70 are dropped, so the model gets "no matches" instead of a wrong answer.
- **Confirmation before writes, enforced in code.** A write tool (`create_lead`, `book_slot`, `cancel_booking`) only stores a pending action and returns the details for the customer to check. The real write runs when the model calls `confirm_pending_action` in a **later** request, after the customer replied. The code refuses a confirmation of an action proposed in the same request, so the model cannot propose and confirm on its own. The claim is a single `UPDATE ... WHERE status = 'pending' AND not expired`, so a second "yes" cannot save twice. Pending actions expire after 10 minutes; a newer proposal replaces an older one.
- **No double booking.** Booking is one `UPDATE slots SET booked_by_lead_id = ... WHERE id = ... AND booked_by_lead_id IS NULL AND start_at > now()`. If two customers confirm the same slot at once, Postgres makes the second `UPDATE` wait for the first one's row lock and then re-check the condition, so it changes nothing and the customer is told the slot is taken. A test runs this with two real database connections.
- **Slots are named by date and time, not id.** `book_slot` and `cancel_booking` take the slot's local date and start time, because the conversation history keeps only text and the model no longer has slot ids from an earlier turn.
- **Audit log in the same transaction.** Each tool call is stored with its arguments, status (`ok`, `validation_error`, `rejected`, `error`), result or error, and duration. It is saved together with the messages, so the log never disagrees with the data.
- **Cost and latency per request.** Every chat request (owner `/chat` and public link messages) writes one `request_logs` row: status (`ok`, `rate_limited`, `model_error`), model, steps, input and output tokens, latency and cost. Cost uses `Decimal` and the configured per-1M-token prices. The row shares its `request_id` with the request's `tool_calls` rows. A successful request is logged in the same transaction as its messages; a failed one is logged after the rollback, in its own transaction (with no conversation if the conversation was new). Each request also writes one INFO line to the server log.
- **Owner accounts with password login.** A business owner registers with email, password and business name (`POST /auth/register`) and logs in (`POST /auth/login`) to get a JWT access token. Passwords are stored as Argon2id hashes, hashed in a worker thread so the event loop keeps serving. Tokens are signed with `SECRET_KEY` (HS256, at least 32 characters, checked at startup) and expire after `ACCESS_TOKEN_EXPIRE_MINUTES`; the server only accepts its own algorithm. A wrong password and an unknown email get the same answer, and an unknown email still runs a password check so timing does not reveal which emails have accounts. `POST /chat` is owner-only: each conversation belongs to one account, and another account's conversation id gets the same 404 as a missing one. End customers do not log in: they chat through an integration link (see below).
- **Integrations (chat links).** An owner creates integrations with `POST /integrations` (a name and an optional greeting) and manages them with `GET /integrations`, `GET`/`PATCH /integrations/{id}` and `POST /integrations/{id}/rotate`. Each integration has a random `public_id` (`secrets.token_urlsafe(16)`, 128 bits): it goes in the link, is not a secret, and cannot be guessed from another one. The link is `PUBLIC_CHAT_BASE_URL/c/<public_id>`. Disabling (`PATCH` with `enabled: false`) keeps the row and its history; rotating gives the same integration a new `public_id`, so the old link stops working. There is no delete. The owner API uses the stable internal id, because `public_id` changes on rotation; another account's integration gets the same 404 as a missing one.
- **Public chat through a link (no login).** `GET /public/c/{public_id}` returns the integration's name, greeting and business name; `POST /public/c/{public_id}/messages` sends a visitor's message. The owner is found only by looking the `public_id` up in the `integrations` table, never from anything the visitor sends (extra fields such as `account_id` are refused). Unknown and rotated links answer 404, disabled links 403. The first message returns a `conversation_token` (`secrets.token_urlsafe(32)`), which the visitor sends with later messages. Only its SHA-256 hash is stored, and it only works on the link it was issued for. The response never contains internal ids. These are the API routes; the page at the link (`PUBLIC_CHAT_BASE_URL/c/<public_id>`) is built in Phase 4.
- **FAQ bulk upload (CSV).** An owner uploads a CSV with the columns `question` and `answer` to `POST /faq/upload` (multipart field `file`). The owner comes only from the login token, never from the file. The upload is **all or nothing**: the file is checked first (at most 1 MB, at most 500 rows, UTF-8 with or without a BOM, headers matched ignoring case and spaces, question up to 500 and answer up to 2,000 characters, no repeated question ignoring case). If anything is wrong, nothing is saved and a 422 lists every problem with its spreadsheet row number (the header is row 1; fully blank rows are skipped). Questions are unique per account, ignoring case and outer spaces (a unique index on `(account_id, lower(btrim(question)))`), and the save is one upsert in one transaction, so uploading the same file again changes nothing (`{"inserted": 0, "updated": 0, "unchanged": N}`) and a new answer for an existing question updates it. Only new and changed entries are embedded, in batches of 50, **before** anything is written, so if Gemini fails the upload returns 429/503 and the database is unchanged. `GET /faq?page=&page_size=` lists the owner's entries (at most 100 per page); `GET /faq/template.csv` downloads a sample file and needs no login. Uploaded entries are found by `search_faq` like seeded ones.
- **Rate limit per chat link.** Each integration accepts at most `PUBLIC_CHAT_RATE_LIMIT` messages per `PUBLIC_CHAT_RATE_WINDOW_SECONDS` (default 20 per 60 seconds), from all visitors together, so the owner's model spend has a ceiling. The count is a row per link per fixed window in the `rate_limit_counters` table, increased with one atomic `INSERT ... ON CONFLICT DO UPDATE ... RETURNING count`, so simultaneous requests and several app copies count correctly. The count is committed before the token check and before the model call, so wrong tokens and failed model calls use up the limit too. Over the limit, the route answers 429 with a `Retry-After` header and the model is not called. Unknown and disabled links are refused before counting; the profile `GET` is not limited.
- **Tests never call the API.** The model and the embedder are passed in as functions, and tests pass scripted fakes.

## Run it locally

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker, and a
Gemini API key from Google AI Studio.

```bash
cp .env.example .env                 # then set GEMINI_API_KEY and change the passwords
docker compose up -d db              # Postgres 16 + pgvector on 127.0.0.1:5433
uv sync                              # install dependencies from uv.lock
uv run alembic upgrade head          # create the tables
uv run uvicorn app.main:app --reload
```

Try it (`/chat` needs an owner token, so register and log in first). FAQ
entries and slots belong to one account, so seed them for the account you
registered, using the `id` from the register response:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/auth/register -H "Content-Type: application/json" \
     -d '{"email": "owner@example.test", "password": "a long fake password", "business_name": "Fake Bikes"}'
ACCOUNT_ID=...   # the id from the register response
uv run python -m scripts.seed_faq --account-id $ACCOUNT_ID    # 8 fake FAQ entries (one embedding API call)
uv run python -m scripts.seed_slots --account-id $ACCOUNT_ID  # fake slots, Mon-Sat 10:00/13:00/16:00, next 14 days
curl -X POST localhost:8000/auth/login -H "Content-Type: application/json" \
     -d '{"email": "owner@example.test", "password": "a long fake password"}'
TOKEN=...   # the access_token from the login response
curl -X POST localhost:8000/chat -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
     -d '{"message": "How much does a puncture repair cost?"}'
# continue the same conversation by sending the returned conversation_id:
curl -X POST localhost:8000/chat -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
     -d '{"conversation_id": 1, "message": "Please call me back. I am Sam Fake, sam@example.test"}'
# create a chat link (integration) and list your links:
curl -X POST localhost:8000/integrations -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN"      -d '{"name": "Website chat", "greeting": "Hi! Ask us about bike repairs."}'
curl localhost:8000/integrations -H "Authorization: Bearer $TOKEN"
# upload your own FAQ entries as CSV (columns question,answer), then list them:
curl -o faq-template.csv localhost:8000/faq/template.csv
curl -X POST localhost:8000/faq/upload -H "Authorization: Bearer $TOKEN" -F "file=@faq-template.csv"
curl "localhost:8000/faq?page=1&page_size=20" -H "Authorization: Bearer $TOKEN"
# chat through the link as a visitor (no login), using public_id from the create response:
PUBLIC_ID=...
curl localhost:8000/public/c/$PUBLIC_ID
curl -X POST localhost:8000/public/c/$PUBLIC_ID/messages -H "Content-Type: application/json"      -d '{"message": "Any free service slots this week?"}'
# continue with the conversation_token from the reply:
curl -X POST localhost:8000/public/c/$PUBLIC_ID/messages -H "Content-Type: application/json"      -d '{"message": "The earliest one, please", "conversation_token": "..."}'
```

## Run the frontend

The frontend is a Vite + React app in plain JavaScript, in `frontend/`, styled with
Tailwind CSS and shadcn/ui components (copied into the repo as JSX, built on Radix).
It needs Node.js 22.22 or newer (CI uses Node 24). Details, folder structure and the
production notes are in [`frontend/README.md`](frontend/README.md).

Start the backend first, as above, with these two values in `.env` (both are in
`.env.example`):
- `PUBLIC_CHAT_BASE_URL=http://localhost:5173`: chat links are built from it, so they
  must point at the frontend;
- `CORS_ALLOWED_ORIGINS=http://localhost:5173`: lets the frontend's page call the API.

Then, in a second terminal:

```bash
cd frontend
cp .env.example .env # VITE_API_BASE_URL and VITE_SITE_URL
npm install
npm run dev          # http://localhost:5173
npm test             # unit and component tests (Vitest, fake fetch, no backend needed)
```

| Route | Page |
|---|---|
| `/` | Landing page. |
| `/login`, `/register` | Owner log in and sign up. |
| `/app/integrations` | Chat links (login required): create, edit, disable/enable, rotate, copy, open. |
| `/app/faq` | FAQ (login required): upload a CSV (drag and drop or pick), see counts or the server's row errors, page through entries. |
| `/c/<public_id>` | Hosted chat that a link opens (no login). |

`uv run python -m scripts.seed_slots --account-id <id>` from the host (the scripts are not in the image).

## Tests, evals and CI

The tests need a test database whose name ends in `test_db` (the test setup
refuses any other). Create it once, using the user and database from your `.env`:

```bash
docker compose exec db psql -U warmline -d warmline -c "CREATE DATABASE warmline_test_db"
uv run pytest -q
```

- **303 tests** run against a real Postgres database, with a fake model and a fake embedder. They cover the LLM wrapper (with a fake SDK client), the agent loop, all seven tools, the confirmation flow, booking (including a two-connection double-booking test), request cost and latency logging, the audit log, the error responses, owner registration, login and tokens (including expired, tampered, wrong-key and `alg: none` tokens), isolation between accounts (one account cannot see or change another's leads, FAQ entries, slots or integrations), integration management (create, list, update, disable, rotate, refusals, a real commit), the public chat path (unknown, rotated and disabled links, tokens that only work on their own link, hashed storage, the link's owner deciding the FAQ), the per-link rate limit (exact limit, window reset, separate links, failed calls still counted, Retry-After, and twelve simultaneous requests counted exactly), the `/chat` API (owner-only, including the step limit and a crashing tool, end to end), and the FAQ CSV upload (BOM, odd headers, multi-line cells, blank rows, missing header, empty and over-long cells, in-file duplicates, non-UTF-8, the row and size limits checked before the form is read, all-or-nothing, idempotent re-upload, updates without duplicates, embedding in batches and embedding failure saving nothing, pagination, and one business never touching or seeing another's entries), and CORS (only the configured origins, allowed methods, no credentials, `Retry-After` exposed, origin setting validation).
- **17 evals** (`tests/test_evals.py`) are customer-level scenarios run through the real chat service: FAQ hit, FAQ miss, lead captured (with confirmation), lead over several messages, bad arguments then fixed, retry give-up, unknown tool rejected, embedding outage, availability lookup, confirmation in the same turn refused, customer declines, details corrected before confirming, booking confirmed, booking proposed again on "yes" then confirmed, book then cancel, another business's FAQ and slot staying hidden, and a lead captured through a public link landing with the link's owner. Each checks the audit-log rows, the reply and the database.
- **What the evals do not prove:** the model in them is scripted, so they test how this code handles each model behaviour, not whether Gemini chooses tools well. They don't test the system prompt or the 0.70 similarity threshold. There is no live evaluation against the real model.
- **CI:** `.github/workflows/tests.yml` runs on every push and on pull requests to `main`, with a pgvector Postgres service container and placeholder settings (the Gemini key is a dummy, because no test calls the API). It first applies every migration to a separate empty database and runs `alembic check`, which fails if a model changed without a migration, then runs `uv run pytest -q`.
- **Frontend CI:** `.github/workflows/frontend.yml` runs when `frontend/` changes: `npm ci`, lint, the Prettier check, `npm test` (48 tests) and a production build.

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
| `LLM_TIMEOUT_SECONDS` | Timeout for each model call (default 30). |
| `BUSINESS_TIMEZONE` | IANA time zone of the business, e.g. `Europe/London` (default `UTC`). Slot times and today's date use it. |
| `AGENT_MAX_STEPS` | Maximum model calls per request (default 6). |
| `AGENT_MAX_TOOL_RETRIES` | Retries after an invalid tool call, per tool (default 2, max 2). |
| `APP_ENV`, `LOG_LEVEL` | Environment name and log level (applied at startup). |
| `LLM_INPUT_PRICE_PER_1M_TOKENS`, `LLM_OUTPUT_PRICE_PER_1M_TOKENS` | USD prices used to compute `request_logs.cost_usd` (default 0, the free tier). |
| `SECRET_KEY` | Signs owner login tokens. At least 32 characters (the app refuses to start otherwise). Never commit it; changing it logs everyone out. |
| `ALGORITHM` | Token signing algorithm: `HS256` (default), `HS384` or `HS512`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Lifetime of a login token (default 30, 1 to 1440). |
| `PUBLIC_CHAT_BASE_URL` | Where the hosted chat page (the frontend) is served; integration links are built from it. Set it to `http://localhost:5173` for local development, as `.env.example` does. If it is not set, the code falls back to `http://localhost:8000`. Must be http or https with no query. |
| `PUBLIC_CHAT_RATE_LIMIT` | Messages one chat link accepts per window, from all visitors together (default 20). |
| `PUBLIC_CHAT_RATE_WINDOW_SECONDS` | Length of the rate limit window in seconds (default 60). |
| `CORS_ALLOWED_ORIGINS` | Comma-separated browser origins allowed to call the API, e.g. `http://localhost:5173` (scheme and host only, no path or wildcard). Empty (the default) = CORS off. |

## Not built yet

- No deployment: the frontend and backend run only locally, and the frontend is not in Docker Compose. No dashboard or endpoint for the request logs, no owner page for leads or bookings, and no live evaluation set.

## Known limitations

- FAQ upload: the whole request must be at most 1 MB (checked from `Content-Length` before the
  form is read, because larger uploads would be written to a temporary file), so a file just
  under 1 MB plus the multipart wrapper is refused; requests without `Content-Length` get 411.
  The request waits for all embedding calls (up to 10 batches of 50; each can take up to the
  model timeout and its retries), and a failure in a late batch wastes the earlier calls (the
  owner uploads again). An upload only adds or updates: entries missing from the file are not
  deleted, and there is no delete or edit route for one entry. Questions are compared with
  Python's `lower()` in the file and Postgres's `lower()` in the database; for unusual Unicode
  these can differ, and two such questions in one file would make the save fail with a 503
  instead of a row error. The inserted/updated counts come from a read before the save, so two
  uploads at the same moment can report slightly wrong counts (the data itself stays correct
  because of the upsert). Upload counts are not logged in `request_logs`, and embedding calls
  are not counted in cost logging.
- Frontend: see the "Known limitations" section of `frontend/README.md`. In short: no
  type checking (plain JavaScript, by choice), the owner token sits in `localStorage`
  (an `httpOnly` cookie would need backend changes), no refresh token, a reload of the
  hosted chat starts a new conversation, the agent does not know the business's name
  (backend prompt), and production hosting is not decided.
- Public chat rate limit: the limit is per link, for all visitors together; there is no
  per-visitor or per-IP limit. It caps the owner's cost, but one visitor or bot can use up a
  link's whole quota and block real customers until the window ends. A fixed window also
  allows up to twice the limit in a short burst around a window boundary. Old counter rows
  are never deleted (one small row per active link per window). Each message costs one extra
  database write and commit.
- Public chat: there is no route to read a conversation's earlier messages. Conversation tokens never expire. A token from before a
  rotation keeps working on the new link (the conversation belongs to the integration, not to
  one `public_id`); the old link itself answers 404. The owner can also continue a public
  conversation through `POST /chat`, because it belongs to their account.
- Integrations: rotating replaces the `public_id` at once, with no grace period for the old
  link. The owner API has no paging and no cap on how many integrations an owner creates; an
  owner with many integrations gets them all in one list. `PUBLIC_CHAT_BASE_URL` is only checked
  for its format, not that it really serves the chat. In the (practically impossible) case of
  two random `public_id`s colliding, the create or rotate request fails with 503 instead of
  trying again.
- Request logs: embedding calls (FAQ search) are not counted. Latency is measured inside
  the chat service, so it excludes HTTP and request parsing. Prices are set
  by hand in the environment. A database failure cannot be logged in the
  database; it only reaches the server log.
- At INFO level, the HTTP library also logs each Gemini request URL (the API
  key is sent in a header, not in the URL).
- `POST /chat` and the public messages route return 429 when Gemini's rate
  limit persists after retries, 503 for other model failures, and 503 with a
  generic message for database failures (details go to the server log only).
  That 429 has no `Retry-After` header (only the per-link limit's 429 has one). Timeouts and network errors are not retried, and the 429/503
  retry waits are fixed (no jitter).
- If the database fails while a tool is running, the tool reports an
  internal error to the model and the model makes one more call before the
  request fails with 503 when saving. That extra model call is wasted. This
  path follows from the code but has no end-to-end test.
- `check_availability` returns at most 10 slots, so a long range shows only
  the earliest ones. Slots are fake seed data (seeded per account), and there is no
  admin path to edit them. There is no rescheduling tool (cancel, then book).
- `cancel_booking` only cancels bookings of the lead linked to the current
  conversation.
- If a slot is taken between the proposal and the "yes", nothing is saved
  and the pending action stays pending; the model is told to offer another
  time.
- Conversation ids are sequential numbers. Only owners use them, through
  `POST /chat`, which checks that the conversation belongs to the caller's
  account. The public routes never return them; visitors get a random
  conversation token instead.
- Owner accounts: there is no rate limit on `/auth/login` or
  `/auth/register` (password guessing and sign-up spam are possible), no
  email verification, no password reset and no logout. A token stays valid
  until it expires, even after the account changes (there is no revocation
  list). `/auth/register` answers 409 for an email that is taken, which
  tells a caller that the email has an account. Tokens last 30 minutes, so
  they do not suit long-running server-to-server API use (that would need
  API keys). Conversations created before accounts existed belong to a
  "Legacy (pre-Phase 3)" account that has no password and cannot log in.
- Leads, FAQ entries and slots belong to one account. Every query filters
  by the account of the conversation's owner; the model never sends an
  account id, so a customer cannot ask for another business's data. The
  same email in two accounts is two separate leads. This is enforced in the
  service queries, not by database row-level security, so a new query that
  forgets the filter would leak data (the isolation tests cover the
  existing ones). Rows created before accounts existed belong to the
  "Legacy (pre-Phase 3)" account. A slot and its booking lead are checked to
  be in the same account when booking, but the database itself does not
  enforce that.
- FAQ search filters by account after the vector index lookup, so with many
  accounts sharing the index a search can return fewer than 3 matches even
  when the account has more. That is fine at this size.
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
  question costs one extra embedding API call. Editing an answer requires
  re-running the embedding for that entry.
- If the model sends invalid tool arguments three times for the same tool
  in one request, the agent stops with a generic "please check your
  details" reply. When that reply, or the step-limit reply, follows a
  confirmed write in the same request, the reply starts with one sentence
  saying what was saved, booked or cancelled. Tool errors that are not validation errors (for example,
  an email that fails the business check) are limited only by the overall
  step limit.
- Every tool call is written to the `tool_calls` audit table. If a model
  call fails later in the same request, the request is rolled back (so any
  write it confirmed is undone) and the audit rows are then saved on their
  own, linked to the failed `request_logs` row by `request_id`. So an audit
  row can say `confirm_pending_action ok` for a write that was rolled back:
  check the request's status in `request_logs`. For a first message the
  conversation itself is rolled back, so those audit rows have no
  `conversation_id`. The audit rows store the tool arguments, which can
  include customer contact details.
- If the model proposes exactly the same write again when the customer says
  "yes" (seen live with `book_slot`), the earlier proposal is kept so the
  confirmation works. A proposal with any changed detail replaces the old
  one and needs a new "yes".
- The embedding size (1536) is a constant in `app/core/config.py`, not a
  setting, because it is part of the database schema. Changing it needs a
  code change, a migration and re-embedding every FAQ entry.
- The Docker container runs database migrations every time it starts. That
  is fine for one container; with several copies they should run once as a
  separate task. The API container receives the whole `.env`, including
  settings it does not need (such as `TEST_DB_URL` and `POSTGRES_PASSWORD`).
- The evals and tests use a scripted model, so real Gemini behaviour (which
  tool it picks, whether it follows the system prompt) is only checked by
  hand with live runs.
