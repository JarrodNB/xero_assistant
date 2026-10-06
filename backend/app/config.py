"""Purpose: Load server settings from the environment.

Public API:
- Settings
- get_settings
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the one shared login, Xero, and the model."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_username: str
    app_password_hash: str
    session_secret: str
    database_path: str = "/app/data/app.db"
    xero_client_id: str = ""
    xero_client_secret: str = ""
    xero_redirect_uri: str = "http://localhost:3000/api/xero/callback"
    model: str = "openai:gpt-4.1-mini"
    typesafe_api_key: str = ""
    jev_model: str = "jev-latest"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    session_https_only: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return the process settings, loaded once."""
    return Settings()
