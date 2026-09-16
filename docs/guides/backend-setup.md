# Backend setup

This project uses a separate Python + FastAPI backend because the server is responsible for AI and document-processing work, not just basic web CRUD. Python gives us the strongest ecosystem for ingestion, chunking, embeddings, retrieval, evaluation, and LLM workflows. Keeping this logic behind a dedicated API also keeps the frontend focused on the user experience while the backend owns data access, orchestration, and grounding.

## Init (from empty `backend/`)

```bash
cd backend
uv sync
uv add fastapi uvicorn pydantic pydantic-settings httpx structlog openai supabase pydantic-ai sqlalchemy alembic "psycopg[binary]" pgvector
uv add --dev pytest ruff
```

## Models (OpenRouter)

Chat and embeddings both go through OpenRouter, in every environment.

1. Create a key at https://openrouter.ai/keys and add a few dollars of credit.
2. Set `OPENROUTER_API_KEY` in `backend/.env`. Never commit it.
3. Keep `CHAT_MODEL` and `EMBEDDING_MODEL` from `.env.example` unless you are deliberately changing models.

The app refuses to start with a blank key. Live check, which costs a fraction of a cent:

```bash
uv run pytest -m integration tests/assistant/test_model.py tests/test_embeddings_integration.py
```

Changing `EMBEDDING_MODEL` means re-running ingestion. Its output dimensions must match `EMBEDDING_DIMENSIONS` and the database column (1024).

## Ingest the corpus

From the repo root, download the filings. `USER_AGENT` in `data/download.py` holds the contact email SEC requires:

```bash
uv run data/download.py
```

Then from `backend/`, with Supabase running, migrations applied, and `OPENROUTER_API_KEY` set:

```bash
uv run python -m ingest --dry-run   # parse and chunk only, about 8 seconds
uv run python -m ingest             # embed and store 7,515 chunks, about 3 million tokens
```

Filings already embedded with the current `EMBEDDING_MODEL` are skipped; filings embedded with a different model are re-embedded automatically. `--replace` re-ingests everything, and fails for any filing whose chunks are cited by a saved answer. `--ticker AAPL` limits the run to one company.

## Measure retrieval

```bash
uv run python -m evals.retrieval --misses
```

Prints hit@1, hit@3, hit@10 and MRR for semantic, keyword, and hybrid search at three filter scopes, over the questions in `evals/retrieval_questions.json`. It checks the answer key against the database first and refuses semantic or hybrid search while stored vectors come from a different embedding model.

## Database migrations

Alembic owns database schema changes for this project. SQLAlchemy models describe the app tables, and Alembic migrations apply those changes to Supabase Postgres.

Initialize Alembic once from `backend/`:

```bash
uv run alembic init alembic
```

Configure `alembic/env.py` to import the app's SQLAlchemy metadata and read the direct database URL from `app.config.settings`. Use the direct/session Supabase database connection, not the transaction pooler URL, for migrations.

Create a migration after changing SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "add document tables"
```

Always review the generated migration. Add explicit operations for Supabase/Postgres features that autogenerate cannot reliably infer:

- `create extension if not exists vector`
- `vector(1536)` columns
- generated `tsvector` columns
- HNSW and GIN indexes
- RLS enablement and policies

Apply migrations:

```bash
uv run alembic upgrade head
```

## Run

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Imports (`from app...`)

`backend/app` is installed as an editable package by `uv sync`, so `from app...` imports work from uvicorn, direct Python execution, tests, and Jupyter kernels that use the backend venv.

The `[build-system]` and `[tool.hatch.build.targets.wheel]` sections in `backend/pyproject.toml` tell uv how to install the local `app/` package. Without that package install, imports depend on the current working directory or a manually configured `PYTHONPATH`, which is fragile in notebooks and IDE run buttons.

Preferred API server command. On Windows `--reload` is required: without it uvicorn uses the ProactorEventLoop, which psycopg async does not support, and the app refuses to start.

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Direct file execution also works:

```bash
cd backend
uv run python app/main.py
```

For Jupyter, install and select the backend kernel:

```bash
cd backend
uv run python -m ipykernel install --user --name document-copilot-backend --display-name "Document Copilot Backend"
```

Then notebooks can import backend modules:

```python
from app.config import settings
```

## Sample SEC data

From the repo root (stdlib-only script, no backend env needed):

```bash
uv run data/download.py
```
