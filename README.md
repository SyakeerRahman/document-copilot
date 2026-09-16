# Document Copilot

Document Copilot is an internal chatbot for investment analysts. An analyst asks a question in plain English about a set of SEC filings. The system finds the passages that answer the question and gives an answer that cites the filing and the page.

## The client

**Driftwood Capital** is a fictional independent investment research firm. Its analysts spend about half of each week on reading 10-K and 10-Q filings before they can start original analysis. Document Copilot does that intake work, so the analysts can go straight to the analysis.

The full brief is in [docs/client-brief.md](docs/client-brief.md).

## Project status

The build follows the 13-step sequence at the end of [docs/architecture.md](docs/architecture.md).

| Step | What it adds | Status |
| ---- | ------------ | ------ |
| 1-3 | Backend and frontend scaffold, database models, first migration | Done |
| 4-7 | Sign-in, protected API, chat UI, streamed replies saved to the database | Done |
| 8 | Ingestion: parse, chunk, embed, and store the SEC filings | Done |
| 9-10 | Hybrid search (vector and keyword) with a retrieval eval | Done |
| 11 | Agent that answers from retrieved passages, with citations | Done |
| 12 | Citation validation and grounding checks | Not started |
| 13 | UI for citations, source passages, empty states, and errors | Not started |

**What works today:** you can sign in, ask a question about the 25 filings, and get a streamed answer with citations. Each citation opens the source passage. The answer and its sources stay after a reload. The system detects a citation that points to no retrieved passage, but it does not reject the answer yet (step 12). The chat shows Markdown tables as plain text until step 13.

## How it works

The system has two paths.

1. **Ingestion path (offline).** A script downloads 10-K filings from SEC EDGAR. The ingestion pipeline splits each filing into pages and chunks, embeds each chunk, and stores the chunks in Postgres.
2. **Chat path (online).** The browser signs in with Supabase Auth and sends each question to the FastAPI backend. The backend checks the user's token, finds relevant passages, generates an answer, and streams it back. Then the backend saves the conversation.

```text
SEC EDGAR --> data/download.py --> backend/ingest --> OpenRouter (embeddings)
                                         |
                                         v
Browser <--> FastAPI backend <--> Postgres + pgvector (Supabase)
                   |
                   v
             OpenRouter (chat model)
```

## Stack

| Layer | Choice |
| ----- | ------ |
| Backend | Python 3.12, FastAPI, SQLAlchemy async, PydanticAI |
| Frontend | Vite, React, TypeScript, Tailwind CSS, shadcn/ui, AI SDK |
| Database | Supabase Postgres with `pgvector` and full-text search |
| Migrations | SQLAlchemy models and Alembic |
| Auth | Supabase Auth (email and password) |
| Chat model | OpenRouter, `deepseek/deepseek-v4-flash-0731` (set by `CHAT_MODEL`) |
| Embeddings | OpenRouter, `baai/bge-m3` (1024 dimensions) |
| Hosting (planned) | Railway |

## Repository layout

```text
document-copilot/
├── AGENTS.md              # Rules for coding agents: stack, dependencies, style
├── CLAUDE.md              # Map of the repo for Claude Code
├── data/
│   ├── download.py        # Downloads 10-K filings from SEC EDGAR
│   └── downloads/         # Downloaded filings (not in git)
├── docs/
│   ├── architecture.md    # Target design and the 13-step build sequence
│   ├── client-brief.md    # The client and what they need
│   └── guides/            # Setup guides for Supabase, backend, frontend
├── supabase/
│   └── config.toml        # Local Supabase stack configuration
├── backend/
│   ├── app/               # FastAPI app: API, auth, chat, retrieval, database
│   ├── ingest/            # Filing parser, chunker, ingestion command
│   ├── evals/             # Retrieval and answer evals, and their questions
│   ├── alembic/           # Database migrations
│   └── tests/             # Unit and integration tests
└── frontend/
    └── src/               # React app: pages, components, API client
```

## Before you start

Install these tools.

| Tool | Version | Used for | Install |
| ---- | ------- | -------- | ------- |
| [Python](https://www.python.org/downloads/) | 3.12 or later | Backend runtime | python.org or your OS package manager |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | latest | Backend packages and scripts | See the uv install page |
| [Node.js](https://nodejs.org/) | 20 or later | Frontend toolchain | nodejs.org |
| [pnpm](https://pnpm.io/installation) | latest | Frontend packages | See the pnpm install page |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | latest | Runs the local Supabase stack | docker.com |
| [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) | 2.x | Starts and stops local Supabase | See the Supabase CLI page |

You also need an **OpenRouter account and API key**. The chat model and the embedding model both use it.

1. Create a key at https://openrouter.ai/keys.
2. Add credit to the account. A few dollars is enough: one full ingestion costs about $0.03.

You do **not** need a hosted Supabase project for local development.

## Set up and run, step by step

Run the commands from the repository root unless a step says otherwise. The commands use bash syntax. On Windows, Git Bash runs them without changes.

### Step 1. Check the tools

**What this step does:** It confirms that each tool is installed and on your `PATH`.

**Why:** A missing tool causes an error in a later step, and that error often names a different cause.

```bash
uv --version
pnpm --version
docker info --format "{{.ServerVersion}}"
supabase --version
```

**Example output:**

```text
uv 0.12.15
12.4.2
29.6.2
2.117.0
```

If `docker info` fails, start Docker Desktop and wait until it reports that the engine is running.

### Step 2. Start local Supabase

**What this step does:** It starts Postgres, Supabase Auth, the Supabase Studio dashboard, and Mailpit in Docker.

**Why:** The backend stores users, chats, filings, and chunks in Postgres. The app uses Supabase Auth for sign-in. A local stack needs no account and no internet connection.

`supabase/config.toml` turns off the services that this app does not use: realtime, storage, edge functions, and analytics. This makes the first start faster. The config also turns off Supabase migrations, because Alembic owns the database schema.

```bash
supabase start
supabase status -o env
```

The first start downloads several GB of Docker images. Later starts take less than a minute.

**Example output** of `supabase status -o env` (keys replaced here):

```text
API_URL="http://127.0.0.1:54321"
DB_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
STUDIO_URL="http://127.0.0.1:54323"
MAILPIT_URL="http://127.0.0.1:54324"
ANON_KEY="<anon key>"
SERVICE_ROLE_KEY="<service role key>"
```

Keep this output open. Step 3 and step 10 use these values.

### Step 3. Configure the backend

**What this step does:** It creates `backend/.env` with the database address, the Supabase keys, and your OpenRouter key.

**Why:** `backend/app/config.py` reads all settings from this file and stops at startup if a required value is missing or empty. A configuration error then shows immediately, not in the middle of a request.

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

1. Set `SUPABASE_ANON_KEY` to `ANON_KEY` from step 2.
2. Set `SUPABASE_SERVICE_ROLE_KEY` to `SERVICE_ROLE_KEY` from step 2.
3. Set `OPENROUTER_API_KEY` to your OpenRouter key.
4. Keep the other values as they are.

Never commit `backend/.env`. Git ignores it.

**Example result** (keys replaced here):

```text
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
OPENROUTER_API_KEY=<your OpenRouter key>
CHAT_MODEL=deepseek/deepseek-v4-flash-0731
EMBEDDING_MODEL=baai/bge-m3
EMBEDDING_DIMENSIONS=1024
```

### Step 4. Install the backend and apply migrations

**What this step does:** It installs the Python packages and creates the database tables.

**Why:** Alembic migrations are the only source of truth for the schema. The migrations also create things that a plain table definition cannot create:

- the `vector` extension
- a generated full-text column
- the vector and text indexes
- row-level security policies

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run alembic current
```

**Example output** of `uv run alembic current`:

```text
c3b7c46fbef0 (head)
```

`uv sync` refuses any package version that is less than 7 days old. This protects the project from a compromised release. The frontend `.npmrc` applies the same rule.

### Step 5. Download the SEC filings

**What this step does:** It downloads the 5 most recent 10-K filings for Apple, Microsoft, NVIDIA, Amazon, and Alphabet. It also writes `data/downloads/manifest.json`.

**Why:** These 25 filings are the corpus that the analysts ask about. The ingestion step reads the manifest to find each file and its filing details.

SEC EDGAR requires a contact email in the `User-Agent` header of every request. Set `USER_AGENT` at the top of `data/download.py` to your own contact before you run the script.

```bash
uv run data/download.py
```

**Example output:**

```text
Downloading AAPL filings...
Downloading MSFT filings...
Downloading NVDA filings...
Downloading AMZN filings...
Downloading GOOGL filings...
Downloaded 25 filing(s) to C:\Users\User\Project\document-copilot\data\downloads
Manifest: C:\Users\User\Project\document-copilot\data\downloads\manifest.json
```

Git ignores the downloaded files.

### Step 6. Ingest the filings

**What this step does:** For each filing, the pipeline does 4 things:

1. It parses the HTML into pages. The page number printed in the footer becomes the page label.
2. It finds the Item sections, for example "Item 7. Management's Discussion and Analysis".
3. It splits each page into chunks. A chunk never crosses a page or a section.
4. It embeds each chunk through OpenRouter and stores the filing and its chunks in one database transaction.

**Why:** The page is the unit that an analyst cites, so each chunk must belong to exactly one page. Each stored chunk is an exact slice of the stored filing text, so a citation can always point to the original words.

Run a dry run first. It parses and chunks every filing but makes no API calls and no database writes.

```bash
uv run python -m ingest --dry-run
```

**Example output:**

```text
25 filing(s) from C:\Users\User\Project\document-copilot\data\downloads\manifest.json
AAPL FY2025 0000320193-25-000079: 60 pages, 212 chunks
AAPL FY2024 0000320193-24-000123: 59 pages, 201 chunks
...
done in 7s, 0 failure(s)
```

Then run the real ingestion:

```bash
uv run python -m ingest
```

**Example output** (the full run takes about 6 minutes):

```text
25 filing(s) from C:\Users\User\Project\document-copilot\data\downloads\manifest.json
AAPL FY2025 0000320193-25-000079: 60 pages, 212 chunks, replaced (qwen3-embedding:0.6b -> baai/bge-m3) 212 chunks (embedding 14.7s)
AAPL FY2024 0000320193-24-000123: 59 pages, 201 chunks, replaced (qwen3-embedding:0.6b -> baai/bge-m3) 201 chunks (embedding 12.3s)
...
GOOGL FY2021 0001652044-22-000019: 95 pages, 358 chunks, replaced (qwen3-embedding:0.6b -> baai/bge-m3) 358 chunks (embedding 16.6s)
done in 372s, 0 failure(s)
```

This output comes from a database that held vectors from an earlier embedding model, so each line says `replaced`. On an empty database, each line says `stored 212 chunks` instead.

The corpus has 7,515 chunks after ingestion. When you run the command again, it skips filings that the current `EMBEDDING_MODEL` already embedded:

```text
AAPL FY2025 0000320193-25-000079: 60 pages, 212 chunks, skipped (already ingested with this model; use --replace to re-ingest)
```

Other options:

- `--ticker AAPL` ingests one company. You can repeat the option.
- `--replace` embeds and stores filings again, even with the same model.

If you change `EMBEDDING_MODEL`, the next run embeds every filing again automatically. Vectors from two different models cannot be compared.

### Step 7. Measure retrieval

**What this step does:** It runs 20 questions from the client brief through the search and reports how high the correct passage ranks.

**Why:** A chatbot can only cite what the search finds. This eval shows whether a change to chunking or ranking makes search better or worse. Without the eval, a regression is invisible until an analyst gets a wrong answer.

Each question in `backend/evals/retrieval_questions.json` names one filing and the text that an answer passage must contain. The answers were found by a direct text search of the chunks, not by the search under test. The runner first checks that every expected passage exists in the database. It stops if an expected passage is missing or too common.

```bash
uv run python -m evals.retrieval --misses
```

**Example output:**

```text
20 questions, embedding model baai/bge-m3, top 10

scope        mode       hit@1  hit@3  hit@10    MRR
ticker+year  semantic    0.60   0.75    0.95   0.71
ticker+year  keyword     0.40   0.70    0.90   0.57
ticker+year  hybrid      0.55   0.80    1.00   0.69

ticker       semantic    0.20   0.25    0.70   0.30
ticker       keyword     0.10   0.20    0.60   0.21
ticker       hybrid      0.15   0.30    0.80   0.31

all filings  semantic    0.20   0.25    0.70   0.30
all filings  keyword     0.10   0.20    0.55   0.20
all filings  hybrid      0.15   0.35    0.65   0.29

Hybrid misses with ticker+year filters:
  none
```

**How to read the table:**

- **scope** is the filter on the search. `ticker+year` searches one filing. `ticker` searches all 5 filings of one company. `all filings` searches all 25.
- **mode** is the search method. `semantic` compares embeddings. `keyword` uses Postgres full-text search. `hybrid` combines both with Reciprocal Rank Fusion. The app uses `hybrid`.
- **hit@k** is the share of questions with a correct passage in the top k results.
- **MRR** (mean reciprocal rank) is 1.0 when the first result is always correct.

**What the results show:**

- With the correct company and year, hybrid search puts a correct passage in the top 10 for all 20 questions.
- Without a year filter, results drop sharply. Each company's 5 filings contain very similar passages. The agent therefore passes the fiscal year to the search whenever a question implies one.
- One question is worth 0.05 in this table. Treat a difference of 0.05 as noise.

### Step 8. Measure answer quality

**What this step does:** It runs the real agent on the 20 eval questions and on 3 questions that it must decline. For each answer, it checks the citations.

**Why:** Good search does not guarantee a good answer. The model can ignore a passage, cite the wrong passage, or invent a citation. This eval shows whether the chat model follows the citation rules before analysts rely on it. Use it again before you change `CHAT_MODEL`.

The eval asks each question with the company and the fiscal year, as an analyst would. It checks 3 things for each answer:

- **cited:** the answer has at least one citation.
- **valid:** every citation points to a passage that a tool showed the model in this turn.
- **expected:** at least one cited passage is a correct answer passage from the answer key.

```bash
cd backend
uv run python -m evals.answers
```

The run takes about 2 minutes and costs about $0.02.

**Example output** (the middle rows are removed here):

```text
model deepseek/deepseek-v4-flash-0731, 20 answerable questions, 3 decline questions

question                               cited valid expected cites  secs  tokens in/out
aapl-2025-category-mix                   yes   yes      yes     2  20.7       9045/848
amzn-2025-segment-operating-income       yes   yes      yes     3  10.2       5823/364
nvda-2024-china-export-rules             yes   yes      yes     8  28.7       8315/929
...
googl-2025-revenue-by-type               yes   yes      yes     6   8.0      14014/876

cited 1.00   valid 1.00   expected 1.00   median 20.2s   max 51.1s   tokens 193038 in / 14170 out   errors 0
```

The eval then prints the answers to the 3 decline questions for a person to read:

- "Should I buy NVIDIA stock based on its fiscal 2025 results?" The model must refuse to give investment advice.
- "What was Tesla's total revenue in fiscal 2024?" The model must say that Tesla is not in the corpus, with no citations.
- "Do Microsoft's 10-K filings prove that generative AI improved its operating margins?" The model must not state a conclusion that the filings do not state.

Add `--show-answers` to print every answer with its citations. Add `--model <OpenRouter model id>` to test a different chat model.

### Step 9. Start the backend API

**What this step does:** It starts the FastAPI server on port 8000.

**Why:** The frontend sends all requests to this server. The server checks the sign-in token, reads and writes chats, and streams replies.

```bash
uv run uvicorn app.main:app --reload
```

On Windows, `--reload` is required, not optional. Without it, uvicorn uses an event loop that the Postgres driver cannot use, and the app stops at startup with an explanation.

In a second terminal, check the server:

```bash
curl http://127.0.0.1:8000/health
```

**Example output:**

```text
{"status":"ok"}
```

### Step 10. Configure and start the frontend

**What this step does:** It creates `frontend/.env`, installs the frontend packages, and starts the Vite dev server.

**Why:** The browser needs the backend address and the public Supabase key. `frontend/src/lib/env.ts` checks these values when the app loads.

```bash
cd frontend
cp .env.example .env
```

Edit `frontend/.env` and set `VITE_SUPABASE_ANON_KEY` to `ANON_KEY` from step 2. Keep the other values. Never put the service role key in this file, because the browser can read every value in it.

```bash
pnpm install
pnpm dev
```

**Example output:**

```text
  VITE v8.3.0  ready in 499 ms

  ➜  Local:   http://localhost:5173/
```

### Step 11. Sign in and ask a question

**What this step does:** It tests the full chat path in the browser.

**Why:** The tests cover each part on its own. This step proves that the parts work together.

1. Open http://localhost:5173. The app sends you to the sign-in page.
2. Select **No account yet? Create one**.
3. Enter any email address and a password of at least 6 characters.
4. Select **Start a chat**.
5. Type a question, for example "How did AWS operating income compare with North America and International in fiscal 2025?", and press Enter.

**Example result:**

- After about 15 seconds, the answer appears word by word while the **Stop** button shows. The agent first searches the filings, so the first words take longer than the rest.
- The answer starts like this: `AWS was the most profitable of Amazon's three segments in fiscal 2025, with operating income of $45,606 million, versus $29,619 million for North America and $4,750 million for International [P4][P7].`
- A **Sources** list follows the answer. Each source names the filing, the page, and the section, for example `[P7] AMAZON.COM, INC. 10-K, fiscal 2025, page 68, Item 8. Financial Statements and Supplementary Data > Note 10`.
- Select a source to see the passage text and a link to the filing on SEC.gov.
- When you reload the page, the question, the answer, and the sources are still there.
- The chat list shows the chat, with the first question as its title.

A follow-up question can depend on the chat. For example, after the question above, "And in fiscal 2024?" gets the same comparison for 2024.

Local Supabase does not send confirmation emails for sign-up. Mailpit at http://127.0.0.1:54324 shows any emails that Supabase sends.

### Step 12. Run the tests

**What this step does:** It runs the backend test suites and the frontend checks.

**Why:** The fast suite runs in seconds and needs no network, so you can run it after every change. The integration suite proves that the code works with the real database and the real OpenRouter models.

Backend, from `backend/`:

```bash
uv run pytest -m "not integration"
uv run pytest -m integration
uv run ruff check . && uv run ruff format --check .
```

**Example output:**

```text
72 passed, 12 deselected, 1 warning in 4.22s
12 passed, 72 deselected, 1 warning in 102.55s (0:01:42)
All checks passed!
```

The integration suite needs local Supabase, the ingested corpus, and a real `OPENROUTER_API_KEY`. It runs the real agent, takes about 2 minutes, and costs less than one cent.

Frontend, from `frontend/`:

```bash
pnpm typecheck
pnpm lint
pnpm build
```

The frontend has no automated tests by design. Step 11 is the frontend check.

## Configuration reference

### Backend (`backend/.env`)

| Variable | Required | Example | Purpose |
| -------- | -------- | ------- | ------- |
| `SUPABASE_URL` | Yes | `http://127.0.0.1:54321` | Supabase API, used to verify sign-in tokens |
| `SUPABASE_ANON_KEY` | Yes | from `supabase status` | Public key sent with token checks |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | from `supabase status` | Privileged key, backend only |
| `DATABASE_URL` | Yes | `postgresql://postgres:postgres@127.0.0.1:54322/postgres` | Direct Postgres connection for the app and Alembic |
| `OPENROUTER_API_KEY` | Yes | `sk-or-...` | Key for chat and embeddings |
| `CHAT_MODEL` | Yes | `deepseek/deepseek-v4-flash-0731` | OpenRouter chat model id |
| `EMBEDDING_MODEL` | Yes | `baai/bge-m3` | OpenRouter embedding model id |
| `EMBEDDING_DIMENSIONS` | No | `1024` | Must match the database column |
| `EMBEDDING_MAX_INPUT_TOKENS` | No | `8000` | Longer input stops with an error instead of a silent truncation |
| `EMBEDDING_QUERY_INSTRUCTION` | No | empty | Prefix for questions, only for models that need one |
| `ALLOWED_ORIGINS` | No | `http://localhost:5173` | Browser origins that can call the API |

### Frontend (`frontend/.env`)

| Variable | Example | Purpose |
| -------- | ------- | ------- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend address |
| `VITE_SUPABASE_URL` | `http://127.0.0.1:54321` | Supabase address for sign-in |
| `VITE_SUPABASE_ANON_KEY` | from `supabase status` | Public Supabase key |

## Design decisions

Each decision below has a reason. A change to one of them needs a new reason.

| Decision | Reason |
| -------- | ------ |
| A chunk never crosses a page or an Item section. | Analysts cite a page. A chunk that spans two pages cannot have one correct citation. |
| A chunk is an exact slice of the stored filing text. | A citation must show the words that the filing contains, not a rewritten version. |
| The chat endpoint accepts only the new message. The backend loads earlier messages from the database. | A browser cannot then insert false assistant messages or false citations into the history. |
| The backend sends `finish` only after it saves the turn. | The browser never shows a completed answer that is missing after a reload. |
| Keyword search uses length-normalized ranking (`ts_rank` with normalization 1). | Without normalization, long chunks won on word count, and hybrid search ranked below vector search alone (MRR 0.55 against 0.71). |
| The embedding client refuses input that is too long. | Some embedding APIs cut long input without an error. The end of that passage then becomes impossible to find. |
| Ingestion records the embedding model and embeds again after a model change. | A comparison between vectors from two different models gives wrong results without an error. |
| Each API route checks that the user owns the chat. | The backend connects as the database owner, so row-level security does not protect it. |
| The model cites a short handle, for example `[P3]`, and code maps the handle to the stored passage. | The model cannot cite a passage that it did not see. An invented handle maps to no passage, so the system can detect it. |
| Earlier answers go back to the model without their citation handles. | Each turn numbers its handles again. An old `[P3]` would otherwise point to a different passage in the new turn. |
| The backend holds back the first 300 characters of each model response before it streams them. | Some models write a short note, for example "Let me search", before they call a tool. That note must not become part of the answer. |
| The chat model is pinned to a dated version and checked with the answer eval. | An alias such as `~latest` can change the model without a warning, and an unchecked model can cite passages incorrectly. |

The full reasoning is in [docs/architecture.md](docs/architecture.md) and [CLAUDE.md](CLAUDE.md).

## Troubleshooting

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| Docker Desktop shows `Not enough memory resources are available to complete this operation` | The computer has too little free RAM for the Docker VM. | Close memory-heavy programs. Check for runaway processes, for example many `node` processes from another dev server. Then restart Docker Desktop. |
| The API stops at startup with `On Windows, start the API with uv run uvicorn app.main:app --reload` | uvicorn started without `--reload` on Windows. | Start it with `--reload`. |
| Any backend command stops with `openrouter_api_key String should have at least 1 character` | `OPENROUTER_API_KEY` in `backend/.env` is empty. | Add your key. |
| The eval prints `Stored vectors come from [...], but EMBEDDING_MODEL is ...` | The database holds vectors from a different embedding model. | Run `uv run python -m ingest`. It embeds the stale filings again. |
| The eval prints `Answer key does not match the database` | A change to chunking changed the stored chunk text. | Update the expected text in `backend/evals/retrieval_questions.json` from the real chunk text. |
| Filing text prints with `�` characters in a Windows terminal | The terminal uses the wrong encoding. The files are valid UTF-8. | Set `PYTHONIOENCODING=utf-8` before the command. |

## Further reading

- [docs/architecture.md](docs/architecture.md): target design, data model, and the 13-step sequence
- [docs/guides/supabase-setup.md](docs/guides/supabase-setup.md): local and hosted Supabase
- [docs/guides/backend-setup.md](docs/guides/backend-setup.md): backend details, ingestion, and the eval
- [docs/guides/frontend-setup.md](docs/guides/frontend-setup.md): frontend setup and checks
- [AGENTS.md](AGENTS.md): rules for anyone, human or agent, who changes the code
