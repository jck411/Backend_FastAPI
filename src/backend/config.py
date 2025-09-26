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
            "REFERER",
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
    openrouter_system_prompt: Optional[str] = Field(
        default=(
            "You are a helpful assistant who follows OpenRouter best practices. "
            "Use the provided context from the server, call tools when they improve your answer, "
            "and if a tool is unavailable you should continue without it while complying with safety policies."
        ),
        validation_alias=AliasChoices(
            "OPENROUTER_SYSTEM_PROMPT",
            "system_prompt",
        ),
    )
    model_settings_path: Path = Field(
        default_factory=lambda: Path("data/model_settings.json"),
        validation_alias=AliasChoices("MODEL_SETTINGS_PATH", "model_settings_path"),
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

    # Deepgram (optional, only needed if using browser STT)
    deepgram_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("DEEPGRAM_API_KEY")
    )
    deepgram_token_ttl_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("DEEPGRAM_TOKEN_TTL", "deepgram_token_ttl"),
        ge=1,
        le=3600,
    )
    deepgram_allow_apikey_fallback: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DEEPGRAM_ALLOW_APIKEY_FALLBACK",
            "DEEPGRAM_DEV_APIKEY_FALLBACK",
        ),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached `Settings` instance."""

    return Settings()  # pyright: ignore[reportCallIssue]


__all__ = ["Settings", "get_settings"]
