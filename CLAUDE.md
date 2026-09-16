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

Architecture steps 1-10 are done. A user can sign up, start a chat, and get a streamed reply that is saved and reloads with the page. The reply is still a placeholder from `backend/app/assistant/stub.py`. The 25-filing corpus is ingested into `source_documents` and `document_chunks`. Hybrid search (`backend/app/retrieval/`) is built and measured with `backend/evals/retrieval.py`. Nothing calls it yet: the agent and grounding (steps 11-13) do not exist.

Chat and embeddings go through **OpenRouter** in every environment (`OPENROUTER_API_KEY` in `backend/.env`). Supabase runs locally in Docker. No hosted Supabase project exists yet. Rationale: `brain/decisions/2026-09-16-models-go-through-openrouter.md` in the workspace root, which supersedes the two earlier Ollama decisions.

If the stored vectors come from a different model than `EMBEDDING_MODEL` (check `select distinct metadata->>'embedding_model' from source_documents`), run `uv run python -m ingest` before any semantic or hybrid search: it re-embeds stale filings automatically.

## Commands

Local services (from repo root, once per machine session):

```bash
supabase start             # Docker; `supabase status -o env` prints keys
```

Backend (from `backend/`):

```bash
uv sync                                    # install deps; also installs app/ and ingest/ as editable packages
uv run uvicorn app.main:app --reload       # dev server. --reload is REQUIRED on Windows (see below)
uv run alembic revision --autogenerate -m "<change>"
uv run alembic upgrade head                # apply migrations
uv run pytest -m "not integration"         # fast suite: no network, no DB, no key needed
uv run pytest -m integration               # live: local Supabase + real OPENROUTER_API_KEY (costs cents)
uv run pytest tests/retrieval/test_fusion.py::test_name   # single test
uv run ruff check . && uv run ruff format --check .
uv run python -m ingest --dry-run          # parse + chunk all filings, no API/DB calls (~8s)
uv run python -m ingest                    # embed + store; skips filings already embedded with EMBEDDING_MODEL
uv run python -m ingest --ticker AAPL --replace   # re-ingest one company
uv run python -m evals.retrieval --misses  # retrieval eval: all scopes x semantic/keyword/hybrid
uv run python -m evals.retrieval --modes keyword  # no embedding calls
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
uv run data/download.py    # 25 10-Ks into data/downloads/ + manifest.json. USER_AGENT holds the SEC contact email
```

First-time init commands for each service are in [docs/guides/backend-setup.md](docs/guides/backend-setup.md) and [docs/guides/frontend-setup.md](docs/guides/frontend-setup.md).

## Architecture in one pass

Two paths through the system:

1. **Chat path.** Browser signs in with Supabase Auth (email only), sends `Authorization: Bearer <supabase JWT>` to FastAPI. FastAPI verifies the token, runs hybrid retrieval, calls a PydanticAI agent, streams AI SDK-compatible message parts back, then persists the turn.
2. **Ingestion path.** `data/download.py` pulls SEC 10-Ks locally. `backend/ingest/` parses each HTML filing into pages (`filing_html.py`), builds Markdown and chunks (`chunking.py`), embeds through OpenRouter (`app/embeddings.py`), and writes `source_documents` + `document_chunks` in one transaction per filing (`pipeline.py`).

Rules that shape most decisions:

- **The backend is authoritative.** Retrieval, prompts, LLM calls, citation validation, and privileged writes all live in FastAPI. The browser never calls a model API, never holds the service-role key, never runs retrieval.
- **Hybrid retrieval is two bounded queries plus Python fusion.** `app/retrieval/queries.py` runs a `pgvector` query and a Postgres full-text query separately; `fusion.py` merges them with Reciprocal Rank Fusion; `retriever.py:search_filings` is the single entry point (modes `hybrid`, `semantic`, `keyword`, used by the eval). The agent gets bounded tools (`search_filings`, `read_chunk`, `read_surrounding_chunks`), never generated SQL.
- **Grounding is an architectural invariant, not a prompt preference.** Every citation must map to a passage retrieved for *this* request. If validation fails, return a controlled failure instead of a polished unsupported answer. This is the product; treat it as such in tests.
- **Retrieval and grounding stay independent of PydanticAI** so they are testable without invoking an LLM.
- **Alembic is the source of truth for schema**, not the Supabase dashboard. Migrations need the direct/session `DATABASE_URL` (`db.<ref>.supabase.co`), never the transaction pooler URL. pgvector extension, generated `tsvector` columns, HNSW/GIN indexes, and RLS policies are written explicitly in migrations - autogenerate cannot infer them.

## Constraints worth restating

- Stack is locked. No Next.js, SSR, or server components. No separate vector database. No model API calls from the browser.
- Config goes through `app/config.py` (backend) and `src/lib/env.ts` (frontend). Never `os.getenv`, never `load_dotenv`, never `import.meta.env.X` outside `env.ts`.
- Frontend is **pnpm only**, with a 7-day minimum release age enforced by `.npmrc`. A `package-lock.json` or `yarn.lock` appearing is a bug.
- **No frontend tests.** Do not add vitest, Playwright, or Cypress. Verification is `pnpm typecheck`, `pnpm lint`, `pnpm build`, and the browser.
- Default to writing it yourself. Justify any new runtime dependency in the commit message per the checklist in [AGENTS.md](AGENTS.md).
- No em-dashes or en-dashes in new writing, including commit messages and code comments. Plain hyphen only.

## Non-obvious details

### Models (OpenRouter)

- `OPENROUTER_API_KEY`, `CHAT_MODEL`, and `EMBEDDING_MODEL` are required and must be non-empty: a blank `OPENROUTER_API_KEY=` fails at startup. Anything importing `app.*` (Alembic, ingest, evals) needs them. For keyword-only runs without a key, export a placeholder `OPENROUTER_API_KEY`.
- `CHAT_MODEL=deepseek/deepseek-v4-flash-0731` is a working choice, not a decision; step 11 picks the model with an answer-quality eval. Pin dated model ids, never `~...-latest` aliases, which change underneath you.
- `EMBEDDING_MODEL=baai/bge-m3` (1024 dims, matches the column, no instruction prefix). `qwen/qwen3-embedding-0.6b` appears in OpenRouter docs but not in its live model list. Larger qwen3-embedding models return more than 2000 dimensions, which the pgvector HNSW index cannot hold.
- Changing the embedding model means re-embedding everything. `ingest` stores `embedding_model` in document and chunk metadata and re-embeds any filing whose model differs. `evals.retrieval` refuses semantic/hybrid modes while stored vectors come from another model, because mixed-model similarity returns confident nonsense, not an error.
- `app/embeddings.py` refuses over-long input client-side (`EMBEDDING_MAX_INPUT_TOKENS`, estimated at 2.8 chars/token) because the API does not promise to error instead of truncating. It retries 429/5xx, and treats `{"error": ...}` inside a 200 response as a failure.
- `OpenRouterProvider` falls back to `os.environ` for its key; `app/assistant/model.py` passes the key from settings explicitly.

### Ingestion and chunks

- **Page is the citation unit.** Every filing splits pages with `<hr style="page-break-after:always">`; the printed footer number becomes `metadata.page_label` (what analysts cite), and `page` is the 1-based position. Chunks never cross a page or an Item section.
- Chunk `content` is always `source_documents.content_markdown[char_start:char_end]` (offsets in chunk metadata). Tests and a SQL check enforce it; keep it true when changing chunking.
- Embedded text is `company, form, fiscal year, section > subsection` plus the chunk (`ingest/pipeline.py:embedding_input`); the stored `content` is the chunk alone.
- Section detection: Amazon writes Item headings as single-row two-cell tables; Microsoft repeats "PART II / Item 7" at the top of every page; Alphabet repeats a one-row table "Table of Contents | Alphabet Inc.". All are handled in `filing_html.py:_strip_running_headers`. Every table of contents in the corpus is a multi-row table, so several Item headings on one page are real, not a TOC. NVIDIA's financial statements sit under Item 15, which is correct.
- The Windows console mangles curly quotes when printing filing text (`�`). The files are valid UTF-8; set `PYTHONIOENCODING=utf-8` when printing chunks.

### Retrieval and eval

- Keyword search ORs the question's words (`queries.py:keyword_tsquery`) and ranks with `ts_rank(..., 1)` (length-normalized); words are reduced to letters and digits first, so user text can never become tsquery syntax. Do not switch back to un-normalized `ts_rank_cd`: long chunks win on word count and hybrid falls below semantic-only (MRR 0.55 vs 0.71). AND queries (`websearch_to_tsquery`) find almost nothing for natural-language questions.
- Semantic search sets `hnsw.iterative_scan = strict_order` (pgvector 0.8+) so ticker/year filters do not return short result lists.
- `evals/retrieval_questions.json` answers were located by searching chunk text, never by running the retriever. The runner checks every expected substring against the database first (0 matches or more than 6 is an error), so fix the key when chunking changes rather than trusting the numbers. Table rows are separate lines: match `"AWS\nNet sales"`, not `"AWS Net sales"`.
- Current results, `baai/bge-m3`, 20 questions, top 10 (re-run `uv run python -m evals.retrieval --misses` after any retrieval or chunking change):

  | Filters | Mode | hit@1 | hit@3 | hit@10 | MRR |
  | --- | --- | --- | --- | --- | --- |
  | ticker + year | semantic | 0.60 | 0.75 | 0.95 | 0.71 |
  | ticker + year | keyword | 0.40 | 0.70 | 0.90 | 0.57 |
  | ticker + year | **hybrid** | 0.55 | 0.80 | 1.00 | 0.69 |
  | ticker only | hybrid | 0.15 | 0.30 | 0.80 | 0.31 |
  | none | hybrid | 0.15 | 0.35 | 0.65 | 0.29 |

  One question is 0.05, so single-question differences are noise. The ranking choice was picked from 6 variants on these same questions, so treat the numbers as slightly optimistic. The drop without a year filter is the important signal for step 11: the agent must pass `fiscal_years` whenever the question or the conversation implies one, because every company's 5 filings contain near-identical passages.

### Database, API, and platform

- `backend/pyproject.toml` sets `exclude-newer = "7 days"` and `add-bounds = "exact"` - the uv-side mirror of the frontend release-age defence.
- `from app...` and `from ingest...` imports work everywhere because `uv sync` installs both as editable packages (`[tool.hatch.build.targets.wheel]`).
- Downloaded filings under `data/downloads/` are gitignored; the folder stays in git for the script and notes.
- `auth.users` is declared as a stub table in `models.py` only so the `profiles` FK resolves. `alembic/env.py` excludes the `auth` schema from autogenerate. Without that, every future autogenerate tries to drop the FK.
- The `vector` extension lives in the `extensions` schema (Supabase convention). The unqualified `vector` type resolves because Supabase puts `extensions` on the search_path.
- `alembic/versions/` is excluded from ruff so migrations keep Alembic's generated style. The `embedding_dimensions_1024_for_ollama` migration name is historical; the 1024 column now serves bge-m3.
- `supabase/config.toml` disables Supabase's own migrations and seeding. Never add files under `supabase/migrations/`; schema changes go through Alembic only.
- **On Windows the API must run with `--reload`.** Plain `uvicorn` uses the ProactorEventLoop, which psycopg async rejects; `--reload` uses the selector loop. `app/main.py` fails at startup with that message. CLIs (`ingest`, `evals`) pass `loop_factory=asyncio.SelectorEventLoop`, and tests get it from the `anyio_backend` fixture. Production (Linux) is unaffected.
- Docker Desktop fails to start its VM ("Not enough memory resources", `0x8007000e`) when RAM is exhausted. Check for runaway processes before blaming Docker: on 2026-09-16 a Next.js dev server in another project had spawned 1,496 node workers holding 43 GB of commit.
- The backend reads and writes Postgres through SQLAlchemy async (`app/database/`), as the `postgres` role, so RLS does not apply to it. Ownership is enforced in code: `get_owned_thread` in `app/api/threads.py` returns 404 or 403. The RLS policies protect direct browser access through Supabase's REST API.
- Chat wire types come from `pydantic_ai.ui.vercel_ai` (request and response models for the AI SDK stream protocol). The frontend is AI SDK v7; `app/chat/streaming.py` pins `SDK_VERSION = 7`.
- `POST /chat/stream` takes `{threadId, message}`: only the new user message. History is loaded from the database, never taken from the client.
- `app/chat/orchestrator.py` sends `finish` only after the turn is saved. A client disconnect cancels the generator, and nothing is saved.
- `backend/tests/conftest.py` sets a placeholder only for settings that have no value in the environment or in `backend/.env`, because env vars override `.env` and would replace a real key the integration tests need.
- `MAX_MESSAGE_CHARS` in `frontend/src/lib/api.ts` must match `MAX_USER_MESSAGE_CHARS` in `backend/app/chat/messages.py`.
- To test RLS for real: sign up users via `$API_URL/auth/v1/signup` with the anon key, then query `$API_URL/rest/v1/<table>` with each user's `access_token`.
- The migration can be tested without Supabase: run `pgvector/pgvector:pg17` in Docker, create roles `anon`/`authenticated`, schema `auth` with `auth.users(id uuid)` and an `auth.uid()` function, add `extensions` to the search_path, then `upgrade head`, `alembic check`, `downgrade base`.
