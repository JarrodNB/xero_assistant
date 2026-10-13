"""Purpose: Load server settings from the environment.

Public API:
- Settings
- get_settings
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the one shared login, Xero, and the model."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_parse_none_str="null")

    app_username: str
    app_password_hash: str
    session_secret: str
    database_path: str = "/app/data/app.db"
    xero_client_id: str = ""
    xero_client_secret: str = ""
    xero_redirect_uri: str = "http://localhost:3001/api/xero/callback"
    model: str = "openai:gpt-4.1-mini"
    chat_summary_every: int = Field(default=10, ge=0, le=50)
    chat_timeout_seconds: float = Field(default=60, gt=0, le=180)
    chat_request_limit: int = Field(default=12, ge=1, le=40)
    chat_tool_limit: int = Field(default=12, ge=1, le=50)
    chat_token_limit: int = Field(default=20000, ge=256, le=100000)
    chat_output_limit: int = Field(default=2048, ge=64, le=8192)
    chat_prompt_character_limit: int = Field(default=4000, ge=256, le=16000)
    chat_temperature: float | None = Field(default=0, ge=0, le=2)
    ai_request_timeout_seconds: float = Field(default=20, gt=0, le=60)
    ai_provider_retries: Literal[0] = 0
    ai_validation_retries: int = Field(default=1, ge=0, le=2)
    summary_timeout_seconds: float = Field(default=10, gt=0, le=30)
    summary_request_limit: int = Field(default=2, ge=1, le=4)
    summary_token_limit: int = Field(default=4000, ge=256, le=10000)
    summary_output_limit: int = Field(default=768, ge=64, le=2048)
    summary_max_blocks: int = Field(default=1, ge=1, le=3)
    history_message_limit: int = Field(default=20, ge=2, le=50)
    history_character_limit: int = Field(default=12000, ge=256, le=30000)
    jev_timeout_seconds: float = Field(default=5, gt=0, le=15)
    trace_sample_ratio: float = Field(default=0.1, ge=0, le=1)
    environment: Literal["development", "test", "production"] = "development"
    typesafe_api_key: str = ""
    jev_model: str = "jev-latest"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    session_https_only: bool = False
    action_execution_timeout_seconds: float = Field(default=120, gt=0, le=240)


@lru_cache
def get_settings() -> Settings:
    """Return the process settings, loaded once."""
    return Settings()
