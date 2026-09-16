# Supabase setup

We use Supabase for **Postgres** (users, chats, source documents, chunks, embeddings, and citations) and **Auth** (email sign-in only).

- **Local development:** run the Supabase stack in Docker. No account needed. See section 0.
- **Production:** one hosted Supabase project. See sections 1-5.

## 0. Local development (no account)

Needs Docker Desktop running and the Supabase CLI on your PATH.

From the repo root:

```bash
supabase start           # first run downloads several GB of images
supabase status -o env   # prints the local URL, anon key, service_role key, and DB URL
```

`supabase/config.toml` is checked in. It turns off realtime, storage, edge functions, and analytics, which this app does not use. It also turns off Supabase's own migrations: **Alembic owns the schema, so never add files under `supabase/migrations/`.**

| Local service | URL |
| ------------- | --- |
| API (use as `SUPABASE_URL`) | `http://127.0.0.1:54321` |
| Postgres (use as `DATABASE_URL`) | `postgresql://postgres:postgres@127.0.0.1:54322/postgres` |
| Studio (dashboard) | `http://127.0.0.1:54323` |
| Mailpit (catches sign-up and login emails) | `http://127.0.0.1:54324` |

Copy the keys into `backend/.env` and `frontend/.env`, then apply the schema from `backend/`:

```bash
uv run alembic upgrade head
```

`supabase stop` keeps your data. `supabase stop --no-backup` deletes it.

## 1. Create an account

1. Go to [supabase.com](https://supabase.com) and sign up (GitHub or email).
2. Confirm your email if prompted.
3. You land in the [dashboard](https://supabase.com/dashboard). The free tier is enough for local development.

## 2. Create a project

1. Open [New project](https://supabase.com/dashboard/new).
2. Pick your organization (a personal org is created automatically on first signup).
3. Set a **project name** (e.g. `Document Copilot`).
4. Choose a **database password** — save it somewhere safe; you need it for direct DB access and `supabase link`.
5. Pick a **region** close to you.
6. Click **Create new project** and wait until status is healthy (~1–2 minutes).

## 3. Collect credentials

You need these values in backend and frontend env config (exact variable names will live in each service's settings module once the app is built).

| Value | Where to find it | Used by |
| ----- | ---------------- | ------- |
| **Project URL** | Dashboard → **Project Settings** → **API** → Project URL | Frontend + backend |
| **anon (public) key** | Same page → `anon` `public` key | Frontend (browser-safe) |
| **service_role (secret) key** | Same page → `service_role` `secret` key | Backend only — never expose to the browser |
| **Project ref** | Dashboard URL `supabase.com/dashboard/project/<ref>` or `supabase projects list` | CLI commands |
| **Direct database connection string** | Dashboard → **Project Settings** → **Database** → Connection string | Alembic migrations and backend DB access |
| **Database password** | What you set at project creation | Direct Postgres connection |

From the CLI you can also print API keys:

```bash
supabase projects api-keys --project-ref <your-project-ref>
```

Keep `service_role` out of git, client bundles, and frontend env files.

## 4. Auth settings (email only)

This app uses email auth only — no Google/SSO.

1. Dashboard → **Authentication** → **Providers**.
2. Leave **Email** enabled.
3. For local dev, you may want **Authentication** → **Email** → disable "Confirm email" so sign-up works without inbox access (re-enable for production).

## 5. Database schema management

Document Copilot uses Alembic from the Python backend to manage database schema. Do not create production tables manually in the Supabase dashboard.

Alembic migrations create and update:

- the `vector` extension for `pgvector`
- source document and chunk tables
- embedding columns
- generated full-text search columns
- HNSW and GIN indexes
- chat and citation tables
- row-level security policies

Use the direct/session database connection string for Alembic. Do not use the transaction pooler connection string for migrations.

From `backend/`:

```bash
uv run alembic upgrade head
```

See [Backend setup](backend-setup.md) for the Alembic workflow.

## Next steps

- [Backend setup](backend-setup.md) — Python service + Supabase client
- [Frontend setup](frontend-setup.md) — React app + `@supabase/supabase-js`
