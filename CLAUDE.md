# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read these first

The build rules for this repo live in the `AGENTS.md` tree, not here. This file is the map; those files are the law.

- [AGENTS.md](AGENTS.md) - universal rules: locked stack, dependency policy, config policy, code style
- [backend/AGENTS.md](backend/AGENTS.md) - Python/FastAPI conventions, test policy, rejected anti-patterns
- [frontend/AGENTS.md](frontend/AGENTS.md) - React/Vite conventions, pnpm-only rule, **no frontend tests**
- [docs/architecture.md](docs/architecture.md) - the target design: request flow, module layout, retrieval strategy, streaming contract, data model, 13-step implementation sequence
- [docs/client-brief.md](docs/client-brief.md) - the (fictional) client and what they actually need

## Current state

Architecture steps 1-7 are done. A user can sign up, start a chat, and get a streamed reply that is saved and reloads with the page. The reply is a placeholder from `backend/app/assistant/stub.py`; retrieval, the agent, and grounding (steps 8-13) do not exist yet.

Development runs fully local: Supabase in Docker, chat on Ollama. No hosted Supabase project exists yet. Embeddings need `OPENAI_API_KEY`, which is unset until the ingestion step. Rationale: `brain/decisions/2026-09-16-the-chat-model-is-local-the-embeddings-are-not.md` in the workspace root.

Continue from step 8 of the implementation sequence at the end of [docs/architecture.md](docs/architecture.md) unless told otherwise.

## Commands

Local services (from repo root, once per machine session):

```bash
supabase start                                            # Docker; `supabase status -o env` prints keys
ollama create qwen3-14b-16k -f backend/ollama/Modelfile   # once per machine
```

Backend (from `backend/`):

```bash
uv sync                                    # install deps; also installs app/ as an editable package
uv run uvicorn app.main:app --reload       # dev server. --reload is REQUIRED on Windows (see below)
uv run alembic revision --autogenerate -m "<change>"
uv run alembic upgrade head                # apply migrations
uv run pytest -m "not integration"         # fast suite: no network, no DB
uv run pytest -m integration               # live: needs Ollama running (and later Supabase/OpenAI)
uv run pytest tests/retrieval/test_retriever.py::test_name   # single test
uv run ruff check . && uv run ruff format --check .
```

Frontend (from `frontend/`):

```bash
pnpm install
pnpm dev
pnpm typecheck             # tsc -b. Not `tsc --noEmit`: with project references it checks zero files
pnpm lint                  # oxlint, not eslint
pnpm dlx shadcn@latest add <name>   # add a UI primitive
```

Corpus download (from repo root, stdlib-only, no backend env needed):

```bash
uv run data/download.py    # edit params at the top of the file first, especially USER_AGENT
```

First-time init commands for each service are in [docs/guides/backend-setup.md](docs/guides/backend-setup.md) and [docs/guides/frontend-setup.md](docs/guides/frontend-setup.md).

## Architecture in one pass

Two paths through the system:

1. **Chat path.** Browser signs in with Supabase Auth (email only), sends `Authorization: Bearer <supabase JWT>` to FastAPI. FastAPI verifies the token, runs hybrid retrieval, calls a PydanticAI agent, streams AI SDK-compatible message parts back, then persists the turn.
2. **Ingestion path.** `data/download.py` pulls SEC 10-Ks locally, backend `ingest/` scripts extract Markdown, chunk, embed via OpenAI, and write `source_documents` + `document_chunks` to Supabase Postgres.

Rules that shape most decisions:

- **The backend is authoritative.** Retrieval, prompts, LLM calls, citation validation, and privileged writes all live in FastAPI. The browser never calls OpenAI, never holds the service-role key, never runs retrieval.
- **Hybrid retrieval is two bounded queries plus Python fusion.** A `pgvector` semantic query and a Postgres full-text query run separately; results fuse with Reciprocal Rank Fusion in Python. The agent gets bounded tools (`search_filings`, `read_chunk`, `read_surrounding_chunks`), never generated SQL.
- **Grounding is an architectural invariant, not a prompt preference.** Every citation must map to a passage retrieved for *this* request. If validation fails, return a controlled failure instead of a polished unsupported answer. This is the product; treat it as such in tests.
- **Retrieval and grounding stay independent of PydanticAI** so they are testable without invoking an LLM.
- **Alembic is the source of truth for schema**, not the Supabase dashboard. Migrations need the direct/session `DATABASE_URL` (`db.<ref>.supabase.co`), never the transaction pooler URL. pgvector extension, generated `tsvector` columns, HNSW/GIN indexes, and RLS policies are written explicitly in migrations - autogenerate cannot infer them.

## Constraints worth restating

- Stack is locked. No Next.js, SSR, or server components. No separate vector database. No direct OpenAI calls from the browser.
- Config goes through `app/config.py` (backend) and `src/lib/env.ts` (frontend). Never `os.getenv`, never `load_dotenv`, never `import.meta.env.X` outside `env.ts`.
- Frontend is **pnpm only**, with a 7-day minimum release age enforced by `.npmrc`. A `package-lock.json` or `yarn.lock` appearing is a bug.
- **No frontend tests.** Do not add vitest, Playwright, or Cypress. Verification is `pnpm typecheck`, `pnpm lint`, `pnpm build`, and the browser.
- Default to writing it yourself. Justify any new runtime dependency in the commit message per the checklist in [AGENTS.md](AGENTS.md).
- No em-dashes or en-dashes in new writing, including commit messages and code comments. Plain hyphen only.

## Non-obvious details

- `backend/pyproject.toml` sets `exclude-newer = "7 days"` and `add-bounds = "exact"` - the uv-side mirror of the frontend release-age defence.
- `from app...` imports work everywhere (uvicorn, pytest, direct execution, Jupyter) because `uv sync` installs `app/` as an editable package. If imports break, check `[build-system]` and `[tool.hatch.build.targets.wheel]` in `backend/pyproject.toml`.
- Downloaded filings under `data/downloads/` are gitignored; the folder stays in git for the script and notes.
- `app.config` builds `Settings` at import time, so anything importing `app.*` (including Alembic) needs all required env vars. `tests/conftest.py` sets placeholders for the fast suite.
- `auth.users` is declared as a stub table in `models.py` only so the `profiles` FK resolves. `alembic/env.py` excludes the `auth` schema from autogenerate. Without that, every future autogenerate tries to drop the FK.
- The `vector` extension lives in the `extensions` schema (Supabase convention). The unqualified `vector` type resolves because Supabase puts `extensions` on the search_path.
- `alembic/versions/` is excluded from ruff so migrations keep Alembic's generated style.
- `supabase/config.toml` disables Supabase's own migrations and seeding. Never add files under `supabase/migrations/`; schema changes go through Alembic only.
- Chat provider is `CHAT_MODEL_PROVIDER=ollama|openai`. Embeddings are always OpenAI, never Ollama: vectors from different models are not comparable, and production cannot host the local model.
- The Ollama context window is set in `backend/ollama/Modelfile` (16k), not per request, because Ollama's OpenAI-compatible endpoint ignores `num_ctx`. Past the window, Ollama drops the start of the prompt with no error. When the agent is built, compare `usage.prompt_tokens` to the window and fail loudly.
- **On Windows the API must run with `--reload`.** Plain `uvicorn` uses the ProactorEventLoop, which psycopg async rejects; `--reload` uses the selector loop. `app/main.py` fails at startup with that message. Tests get the selector loop from the `anyio_backend` fixture in `tests/conftest.py`. Production (Linux) is unaffected.
- The backend reads and writes Postgres through SQLAlchemy async (`app/database/`), as the `postgres` role, so RLS does not apply to it. Ownership is enforced in code: `get_owned_thread` in `app/api/threads.py` returns 404 or 403. The RLS policies protect direct browser access through Supabase's REST API.
- Chat wire types come from `pydantic_ai.ui.vercel_ai` (request and response models for the AI SDK stream protocol). The frontend is AI SDK v7; `app/chat/streaming.py` pins `SDK_VERSION = 7`.
- `POST /chat/stream` takes `{threadId, message}`: only the new user message. History is loaded from the database, never taken from the client.
- `app/chat/orchestrator.py` sends `finish` only after the turn is saved. A client disconnect cancels the generator, and nothing is saved.
- `backend/tests/conftest.py` only sets placeholder env vars when `backend/.env` is missing, because env vars override `.env` and would break integration tests.
- `MAX_MESSAGE_CHARS` in `frontend/src/lib/api.ts` must match `MAX_USER_MESSAGE_CHARS` in `backend/app/chat/messages.py`.
- To test RLS for real: sign up users via `$API_URL/auth/v1/signup` with the anon key, then query `$API_URL/rest/v1/<table>` with each user's `access_token`.
- The migration can be tested without Supabase: run `pgvector/pgvector:pg17` in Docker, create roles `anon`/`authenticated`, schema `auth` with `auth.users(id uuid)` and an `auth.uid()` function, add `extensions` to the search_path, then `upgrade head`, `alembic check`, `downgrade base`.
