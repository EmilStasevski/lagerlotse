"""Settings from environment variables (and `.env` for local development)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LAGERLOTSE_", extra="ignore")

    # Owner connection: used only by the seed script and the report job.
    database_url: str = "postgresql+psycopg://lagerlotse:lagerlotse@localhost:5432/lagerlotse"
    # Read-only connection: used by the agent tools and the web app.
    reader_database_url: str = (
        "postgresql+psycopg://lagerlotse_reader:lagerlotse_reader@localhost:5432/lagerlotse"
    )
    reader_password: str = "lagerlotse_reader"
    # Claude API key; read from ANTHROPIC_API_KEY (environment or `.env`).
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="ANTHROPIC_API_KEY"
    )
    # Model ID for the agent. Set in `.env`; never hard-coded elsewhere.
    model: str = ""
    # Thinking depth for the agent: low | medium | high | xhigh | max.
    effort: str = "medium"
    # Server-side refusal fallback; set false for models without it (e.g. Haiku).
    refusal_fallback: bool = True
    # Model prices in USD per million tokens, only for cost reporting in `task eval`.
    price_input_per_mtok: float = 0.0
    price_output_per_mtok: float = 0.0
    # Upper bound for tool-call rounds per question.
    max_tool_rounds: int = 6
    seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
