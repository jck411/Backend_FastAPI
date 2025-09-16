"""Application configuration using environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load configuration from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: SecretStr = Field(
        ..., validation_alias=AliasChoices("OPENROUTER_API_KEY")
    )
    openrouter_base_url: AnyHttpUrl = Field(
        default_factory=lambda: AnyHttpUrl("https://openrouter.ai/api/v1"),
        validation_alias=AliasChoices("OPENROUTER_BASE_URL", "base_url"),
    )
    openrouter_app_url: Optional[AnyHttpUrl] = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPENROUTER_APP_URL",
            "HTTP_REFERER",
            "http_referer",
        ),
    )
    openrouter_app_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPENROUTER_APP_TITLE",
            "X_TITLE",
            "x_title",
        ),
    )
    default_model: str = Field(
        default="openrouter/auto",
        validation_alias=AliasChoices(
            "OPENROUTER_DEFAULT_MODEL",
            "default_model",
        ),
    )
    request_timeout: float = Field(
        default=120.0,
        validation_alias=AliasChoices("OPENROUTER_TIMEOUT", "timeout"),
        ge=1,
    )
    chat_database_path: Path = Field(
        default_factory=lambda: Path("data/chat_sessions.db"),
        validation_alias=AliasChoices("CHAT_DATABASE_PATH", "chat_db"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached `Settings` instance."""

    return Settings()  # pyright: ignore[reportCallIssue]


__all__ = ["Settings", "get_settings"]
