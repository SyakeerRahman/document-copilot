import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED = {
    "supabase_url": "https://ref.supabase.co",
    "supabase_anon_key": "anon",
    "supabase_service_role_key": "service",
    "database_url": "postgresql://u:p@h:5432/db",
    "openrouter_api_key": "sk-or-test",
    "chat_model": "deepseek/deepseek-v4-flash-0731",
    "embedding_model": "baai/bge-m3",
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


@pytest.mark.parametrize("field", ["openrouter_api_key", "chat_model", "embedding_model"])
def test_missing_model_setting_fails_fast(monkeypatch, field):
    monkeypatch.delenv(field.upper(), raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{k: v for k, v in REQUIRED.items() if k != field})


def test_blank_api_key_fails_fast_instead_of_on_first_request():
    with pytest.raises(ValidationError, match="openrouter_api_key"):
        make_settings(openrouter_api_key="")
