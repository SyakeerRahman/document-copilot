import asyncio
import os
import sys
from pathlib import Path

import pytest

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# app.config builds Settings at import time and fails fast on missing or blank values. The fast suite
# never calls real services, so placeholders fill whatever is not configured. Environment variables beat
# .env in pydantic-settings, so a placeholder is only set when .env has no value of its own; otherwise it
# would override a real key the integration tests need.
PLACEHOLDERS = {
    "SUPABASE_URL": "http://127.0.0.1:54321",
    "SUPABASE_ANON_KEY": "test-placeholder",
    "SUPABASE_SERVICE_ROLE_KEY": "test-placeholder",
    "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    "OPENROUTER_API_KEY": "test-placeholder",
    "CHAT_MODEL": "test/placeholder",
    "EMBEDDING_MODEL": "test/placeholder",
}


def _configured_in_env_file() -> set[str]:
    if not ENV_FILE.exists():
        return set()
    names = set()
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and not name.lstrip().startswith("#") and value.strip():
            names.add(name.strip())
    return names


for _name in PLACEHOLDERS.keys() - _configured_in_env_file():
    os.environ.setdefault(_name, PLACEHOLDERS[_name])


@pytest.fixture
def anyio_backend():
    # psycopg async cannot run on Windows' default ProactorEventLoop.
    if sys.platform == "win32":
        return "asyncio", {"loop_factory": asyncio.SelectorEventLoop}
    return "asyncio"
