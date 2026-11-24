"""Settings from environment variables (and `.env` for local development)."""

from functools import lru_cache

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
    # Model ID for the agent. Set in `.env`; never hard-coded elsewhere.
    model: str = ""
    seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
