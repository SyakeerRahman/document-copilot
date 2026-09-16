import os

import pytest
from pydantic_ai import Agent

from app.assistant.model import build_chat_model
from app.config import Settings

BASE = {
    "supabase_url": "https://ref.supabase.co",
    "supabase_anon_key": "anon",
    "supabase_service_role_key": "service",
    "database_url": "postgresql://u:p@h:5432/db",
}


def test_ollama_provider_points_at_configured_base_url():
    settings = Settings(
        _env_file=None,
        **BASE,
        chat_model_provider="ollama",
        chat_model="qwen3-14b-16k",
        ollama_base_url="http://ollama.test:11434/v1",
    )
    model = build_chat_model(settings)
    assert model.model_name == "qwen3-14b-16k"
    assert model.system == "ollama"
    assert model.base_url.rstrip("/") == "http://ollama.test:11434/v1"


def test_openai_provider_uses_openai():
    settings = Settings(
        _env_file=None, **BASE, chat_model_provider="openai", chat_model="gpt-test", openai_api_key="sk-test"
    )
    model = build_chat_model(settings)
    assert model.model_name == "gpt-test"
    assert model.system == "openai"


@pytest.mark.integration
@pytest.mark.anyio
async def test_ollama_round_trip():
    # Needs a running Ollama with the model from backend/ollama/Modelfile created.
    settings = Settings(
        _env_file=None,
        **BASE,
        chat_model_provider="ollama",
        chat_model=os.environ.get("INTEGRATION_OLLAMA_MODEL", "qwen3-14b-16k"),
    )
    agent = Agent(build_chat_model(settings))
    result = await agent.run("Reply with exactly the word: pong /no_think")
    assert "pong" in result.output.lower()
