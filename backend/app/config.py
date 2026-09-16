from pathlib import Path
from typing import Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    database_url: str

    # Chat generation. "ollama" is for local development; production uses a hosted provider.
    chat_model_provider: Literal["openai", "ollama"]
    chat_model: str
    ollama_base_url: str = "http://127.0.0.1:11434/v1"

    # Embeddings always come from OpenAI so dev and prod vectors stay comparable.
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    # Comma-separated; kept as a string because pydantic-settings expects JSON for list fields.
    allowed_origins: str = "http://localhost:5173"

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def blank_is_unset(cls, value: object) -> object:
        # `OPENAI_API_KEY=` in .env arrives as "", which should mean "not configured".
        return None if value == "" else value

    @model_validator(mode="after")
    def openai_chat_needs_key(self) -> Self:
        if self.chat_model_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when CHAT_MODEL_PROVIDER=openai")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        # Supabase hands out plain postgresql:// URLs; SQLAlchemy would pick psycopg2, which we don't install.
        scheme, _, rest = self.database_url.partition("://")
        if scheme in ("postgres", "postgresql"):
            return f"postgresql+psycopg://{rest}"
        return self.database_url


settings = Settings()
