"""Pydantic models for persisted model and provider settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

PriceValue = Union[float, str]


class ProviderMaxPrice(BaseModel):
    """Maximum price caps per modality in USD per million tokens."""

    prompt: Optional[PriceValue] = None
    completion: Optional[PriceValue] = None
    image: Optional[PriceValue] = None
    audio: Optional[PriceValue] = None
    request: Optional[PriceValue] = None

    model_config = ConfigDict(extra="forbid")


class ProviderPreferences(BaseModel):
    """OpenRouter provider routing preferences."""

    allow_fallbacks: Optional[bool] = None
    require_parameters: Optional[bool] = None
    data_collection: Optional[Literal["allow", "deny"]] = None
    zdr: Optional[bool] = None
    order: Optional[List[str]] = None
    only: Optional[List[str]] = None
    ignore: Optional[List[str]] = None
    quantizations: Optional[List[str]] = None
    sort: Optional[Literal["price", "throughput", "latency"]] = None
    max_price: Optional[ProviderMaxPrice] = None
    experimental: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")


class ModelHyperparameters(BaseModel):
    """Hyperparameter overrides applied to the active model."""

    # Basic generation parameters
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(default=None, ge=0)
    min_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    top_a: Optional[float] = Field(default=None, ge=0.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)

    # Penalty parameters
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    repetition_penalty: Optional[float] = Field(default=None, ge=0.0)

    # Advanced parameters
    seed: Optional[int] = None
    logit_bias: Optional[Dict[str, float]] = None
    stop: Optional[Union[str, List[str]]] = None
    top_logprobs: Optional[int] = Field(default=None, ge=0)

    # Tool calling
    parallel_tool_calls: Optional[bool] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

    # Response formatting
    response_format: Optional[Dict[str, Any]] = None
    structured_outputs: Optional[bool] = None

    # Reasoning parameters
    reasoning: Optional[Dict[str, Any]] = None

    # Safety and moderation
    safe_prompt: Optional[bool] = None
    raw_mode: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class ActiveModelSettingsPayload(BaseModel):
    """Wire payload for updating model settings via the API."""

    model: str
    provider: Optional[ProviderPreferences] = None
    parameters: Optional[ModelHyperparameters] = None
    supports_tools: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class ActiveModelSettingsResponse(ActiveModelSettingsPayload):
    """Response payload including bookkeeping metadata."""

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="forbid")

    def as_openrouter_overrides(self) -> Dict[str, Any]:
        """Return a mapping of settings suitable for an OpenRouter request payload."""

        payload: Dict[str, Any] = {}
        if self.provider is not None:
            provider_dict = self.provider.model_dump(exclude_none=True)
            if provider_dict:
                payload["provider"] = provider_dict
        if self.parameters is not None:
            for key, value in self.parameters.model_dump(exclude_none=True).items():
                payload[key] = value
        return payload


class SystemPromptPayload(BaseModel):
    """Request payload for updating the orchestrator system prompt."""

    system_prompt: Optional[str] = None
    llm_planner_enabled: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class SystemPromptResponse(SystemPromptPayload):
    """Response wrapper returning the active system prompt."""

    llm_planner_enabled: bool

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ActiveModelSettingsPayload",
    "ActiveModelSettingsResponse",
    "ModelHyperparameters",
    "ProviderMaxPrice",
    "ProviderPreferences",
    "SystemPromptPayload",
    "SystemPromptResponse",
]
