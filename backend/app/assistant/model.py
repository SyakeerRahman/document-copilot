from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.config import Settings


def build_chat_model(settings: Settings) -> OpenAIChatModel:
    # The key is passed explicitly: OpenRouterProvider would otherwise read os.environ itself,
    # bypassing app.config.
    provider = OpenRouterProvider(api_key=settings.openrouter_api_key, app_title="Document Copilot")
    return OpenAIChatModel(settings.chat_model, provider=provider)
