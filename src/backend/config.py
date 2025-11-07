"""Application configuration using environment variables."""

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the project root once so that `.env` is discovered regardless of CWD
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Load configuration from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base URL for the frontend (for redirects)
    frontend_url: AnyHttpUrl = Field(
        default_factory=lambda: AnyHttpUrl("http://localhost:5173"),
        validation_alias=AliasChoices("FRONTEND_URL", "frontend_url"),
    )

    # Google OAuth settings
    google_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/api/google-auth/callback",
        validation_alias=AliasChoices(
            "GOOGLE_OAUTH_REDIRECT_URI", "google_oauth_redirect_uri"
        ),
    )

    openrouter_api_key: SecretStr = Field(
        ...,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key"),
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
    mcp_servers_path: Path = Field(
        default_factory=lambda: Path("data/mcp_servers.json"),
        validation_alias=AliasChoices("MCP_SERVERS_PATH", "mcp_servers_path"),
    )
    presets_path: Path = Field(
        default_factory=lambda: Path("data/presets.json"),
        validation_alias=AliasChoices("PRESETS_PATH", "presets_path"),
    )
    suggestions_path: Path = Field(
        default_factory=lambda: Path("data/suggestions.json"),
        validation_alias=AliasChoices("SUGGESTIONS_PATH", "suggestions_path"),
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
    conversation_log_dir: Path = Field(
        default_factory=lambda: Path("logs/conversations"),
        validation_alias=AliasChoices(
            "CONVERSATION_LOG_DIR",
            "conversation_log_dir",
        ),
    )

    attachments_max_size_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        validation_alias=AliasChoices(
            "ATTACHMENTS_MAX_SIZE_BYTES",
            "attachments_max_size_bytes",
        ),
    )
    attachments_retention_days: int = Field(
        default=7,
        ge=0,
        validation_alias=AliasChoices(
            "ATTACHMENTS_RETENTION_DAYS",
            "attachments_retention_days",
        ),
    )
    legacy_attachments_dir: Path = Field(
        default_factory=lambda: Path("data/uploads"),
        validation_alias=AliasChoices("LEGACY_ATTACHMENTS_DIR"),
    )
    gcs_bucket_name: str = Field(
        default="openrouter-chat",
        validation_alias=AliasChoices("GCS_BUCKET_NAME", "gcs_bucket_name"),
    )
    gcp_project_id: str = Field(
        default="pihome123",
        validation_alias=AliasChoices("GCP_PROJECT_ID", "gcp_project_id"),
    )
    google_application_credentials: Path = Field(
        default_factory=lambda: Path("credentials/googlecloud/sa.json"),
        validation_alias=AliasChoices(
            "GOOGLE_APPLICATION_CREDENTIALS",
            "google_application_credentials",
        ),
    )

    # Image download (for model-generated image_url fetch)
    image_download_allowed_hosts: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "IMAGE_DOWNLOAD_ALLOWED_HOSTS",
            "image_download_allowed_hosts",
        ),
        description=("List of hostnames allowed for server-side image downloads."),
    )
    image_download_timeout_seconds: int = Field(
        default=15,
        ge=1,
        validation_alias=AliasChoices(
            "IMAGE_DOWNLOAD_TIMEOUT_SECONDS",
            "image_download_timeout_seconds",
        ),
    )
    image_download_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        validation_alias=AliasChoices(
            "IMAGE_DOWNLOAD_MAX_BYTES",
            "image_download_max_bytes",
        ),
    )

    enable_llm_planner: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "ENABLE_LLM_PLANNER",
            "enable_llm_planner",
        ),
    )

    @property
    def attachment_signed_url_ttl(self) -> timedelta:
        return timedelta(days=self.attachments_retention_days)

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
