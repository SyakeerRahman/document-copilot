from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import Settings


def build_chat_model(settings: Settings) -> OpenAIChatModel:
    # Ollama speaks the OpenAI chat API, so both paths share one model class. The Ollama
    # provider is still used for its per-family model profiles (tool calling, JSON output).
    if settings.chat_model_provider == "ollama":
        provider = OllamaProvider(base_url=settings.ollama_base_url)
    else:
        provider = OpenAIProvider(api_key=settings.openai_api_key)
    return OpenAIChatModel(settings.chat_model, provider=provider)
