import asyncio
import os
import sys
from pathlib import Path

import pytest

# app.config builds Settings at import time and fails fast on missing values. Without a local
# backend/.env the fast suite still needs something to import against. Environment variables
# beat .env in pydantic-settings, so placeholders are only set when there is no .env to read.
if not (Path(__file__).resolve().parent.parent / ".env").exists():
    PLACEHOLDERS = {
        "SUPABASE_URL": "http://127.0.0.1:54321",
        "SUPABASE_ANON_KEY": "test-placeholder",
        "SUPABASE_SERVICE_ROLE_KEY": "test-placeholder",
        "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        "CHAT_MODEL_PROVIDER": "ollama",
        "CHAT_MODEL": "test-placeholder",
    }
    for name, value in PLACEHOLDERS.items():
        os.environ.setdefault(name, value)


@pytest.fixture
def anyio_backend():
    # psycopg async cannot run on Windows' default ProactorEventLoop.
    if sys.platform == "win32":
        return "asyncio", {"loop_factory": asyncio.SelectorEventLoop}
    return "asyncio"
