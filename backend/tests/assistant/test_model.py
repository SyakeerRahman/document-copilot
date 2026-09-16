import pytest
from pydantic_ai import Agent

from app.assistant.model import build_chat_model
from app.config import Settings, settings


def test_chat_model_goes_through_openrouter_with_the_configured_key():
    configured = Settings(
        _env_file=None,
        supabase_url="https://ref.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        database_url="postgresql://u:p@h:5432/db",
        openrouter_api_key="sk-or-test",
        chat_model="deepseek/deepseek-v4-flash-0731",
        embedding_model="baai/bge-m3",
    )
    model = build_chat_model(configured)
    assert model.model_name == "deepseek/deepseek-v4-flash-0731"
    assert model.system == "openrouter"
    assert model.base_url.rstrip("/") == "https://openrouter.ai/api/v1"


@pytest.mark.integration
@pytest.mark.anyio
async def test_openrouter_round_trip():
    # Needs a real OPENROUTER_API_KEY in backend/.env. Costs a fraction of a cent.
    agent = Agent(build_chat_model(settings))
    result = await agent.run("Reply with exactly the word: pong")
    assert "pong" in result.output.lower()
