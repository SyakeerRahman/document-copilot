from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    database_url: str

    # Chat and embeddings both go through OpenRouter, in every environment.
    # min_length: `OPENROUTER_API_KEY=` left blank in .env must fail at startup, not on the first request.
    openrouter_api_key: str = Field(min_length=1)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    chat_model: str = Field(min_length=1)

    # Changing the embedding model means re-ingesting, and the dimensions must match the
    # `document_chunks.embedding` column.
    embedding_model: str = Field(min_length=1)
    embedding_dimensions: int = 1024
    # Checked before sending, because the API does not promise to reject over-long input rather than
    # truncate it. Keep below the model's context window (bge-m3: 8192).
    embedding_max_input_tokens: int = 8000
    # Some models (qwen3-embedding) want questions, but not passages, prefixed with a task instruction.
    embedding_query_instruction: str = ""

    # Comma-separated; kept as a string because pydantic-settings expects JSON for list fields.
    allowed_origins: str = "http://localhost:5173"

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
