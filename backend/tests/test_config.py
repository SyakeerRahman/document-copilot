import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED = {
    "supabase_url": "https://ref.supabase.co",
    "supabase_anon_key": "anon",
    "supabase_service_role_key": "service",
    "database_url": "postgresql://u:p@h:5432/db",
    "chat_model_provider": "ollama",
    "chat_model": "qwen3:14b",
}


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        ("postgresql://u:p%40ss@h:5432/db", "postgresql+psycopg://u:p%40ss@h:5432/db"),
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql+psycopg://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
    ],
)
def test_sqlalchemy_database_url_uses_psycopg3(database_url, expected):
    assert make_settings(database_url=database_url).sqlalchemy_database_url == expected


def test_cors_origins_splits_and_trims():
    settings = make_settings(allowed_origins="http://localhost:5173, https://app.example.com ,")
    assert settings.cors_origins == ["http://localhost:5173", "https://app.example.com"]


def test_missing_required_value_fails_fast(monkeypatch):
    monkeypatch.delenv("CHAT_MODEL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{k: v for k, v in REQUIRED.items() if k != "chat_model"})


def test_ollama_chat_does_not_need_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert make_settings(openai_api_key="").openai_api_key is None


def test_openai_chat_without_key_fails_fast(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is required"):
        make_settings(chat_model_provider="openai", chat_model="gpt-test", openai_api_key="")


def test_unknown_provider_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(chat_model_provider="anthropic")
