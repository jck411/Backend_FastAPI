"""Tests for the model settings service provider resolution logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from src.backend.openrouter import OpenRouterError
from src.backend.schemas.model_settings import ActiveModelSettingsPayload, ProviderPreferences
from src.backend.services.model_settings import ModelSettingsService


class DummyOpenRouterClient:
    def __init__(self, providers: list[Dict[str, Any]], endpoints: list[Dict[str, Any]]):
        self._providers = providers
        self._endpoints = endpoints
        self.last_filters: Dict[str, Any] | None = None

    async def list_providers(self) -> Dict[str, Any]:
        return {"data": self._providers}

    async def list_model_endpoints(
        self, model_id: str, *, filters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        # Capture filters so we can assert against them if needed later.
        self.last_filters = filters
        return {"data": self._endpoints}


class FailingProviderClient(DummyOpenRouterClient):
    async def list_providers(self) -> Dict[str, Any]:  # type: ignore[override]
        raise OpenRouterError(401, "unauthorized")


@pytest.fixture
def anyio_backend() -> str:
    """Limit AnyIO backend to asyncio for these tests."""
    return "asyncio"


@pytest.mark.anyio
async def test_get_active_provider_info_uses_sorted_endpoint(tmp_path: Path) -> None:
    service = ModelSettingsService(tmp_path / "settings.json", "meta-llama/llama-3-8b-instruct")

    await service.replace_settings(
        ActiveModelSettingsPayload(
            model="meta-llama/llama-3-8b-instruct",
            provider=ProviderPreferences(sort="price"),
        )
    )

    endpoints = [
        {
            "id": "together/us-west",
            "provider": {"name": "together", "display_name": "Together AI"},
            "region": "us-west",
            "pricing": {"completion": "0.95"},
            "throughput_tokens_per_second": 1500,
            "latency_ms": 120,
        },
        {
            "id": "openai/us-east",
            "provider": {"name": "openai", "display_name": "OpenAI"},
            "region": "us-east",
            "pricing": {"completion": "0.90"},
            "throughput_tokens_per_second": 900,
            "latency_ms": 90,
        },
    ]

    client = DummyOpenRouterClient(providers=[{"provider": {"name": "openai"}}], endpoints=endpoints)

    info = await service.get_active_provider_info(client)

    assert info["provider_type"] == "dynamic_sort"
    assert info["provider_slug"] == "openai"
    assert info["selected_endpoint"]["summary"].startswith("OpenAI")
    # Should surface the human readable summary back onto the main provider field for the UI.
    assert "OpenAI" in info["provider"]


@pytest.mark.anyio
async def test_get_active_provider_info_handles_explicit_order(tmp_path: Path) -> None:
    service = ModelSettingsService(tmp_path / "settings.json", "meta-llama/llama-3-8b-instruct")

    await service.replace_settings(
        ActiveModelSettingsPayload(
            model="meta-llama/llama-3-8b-instruct",
            provider=ProviderPreferences(order=["together", "openai"]),
        )
    )

    endpoints = [
        {
            "id": "together/us-west",
            "provider": {"name": "together", "display_name": "Together AI"},
            "region": "us-west",
            "pricing": {"completion": 0.95},
        },
        {
            "id": "openai/us-east",
            "provider": {"name": "openai", "display_name": "OpenAI"},
            "region": "us-east",
            "pricing": {"completion": 0.90},
        },
    ]

    client = DummyOpenRouterClient(providers=[{"provider": {"name": "openai"}}], endpoints=endpoints)

    info = await service.get_active_provider_info(client)

    assert info["provider_type"] == "explicit_order"
    assert info["provider_slug"] == "together"
    assert info["selected_endpoint"]["summary"].startswith("Together AI")


@pytest.mark.anyio
async def test_get_active_provider_info_handles_provider_api_failure(tmp_path: Path) -> None:
    service = ModelSettingsService(tmp_path / "settings.json", "meta-llama/llama-3-8b-instruct")

    await service.replace_settings(
        ActiveModelSettingsPayload(
            model="meta-llama/llama-3-8b-instruct",
            provider=ProviderPreferences(sort="price"),
        )
    )

    endpoints = [
        {
            "id": "anthropic/us-east",
            "provider": {"name": "anthropic", "display_name": "Anthropic"},
            "region": "us-east",
            "pricing": {"completion": "3.10"},
            "throughput_tokens_per_second": 1200,
        }
    ]

    client = FailingProviderClient(providers=[], endpoints=endpoints)

    info = await service.get_active_provider_info(client)

    assert info["provider_type"] == "dynamic_sort"
    assert info["provider_slug"] == "anthropic"
    assert info["selected_endpoint"]["summary"].startswith("Anthropic")


@pytest.mark.anyio
async def test_model_supports_tools_flag(tmp_path: Path) -> None:
    service = ModelSettingsService(tmp_path / "settings.json", "google/gemini-2.5-flash-image")

    # Default should assume tool support unless explicitly disabled.
    assert await service.model_supports_tools() is True

    await service.replace_settings(
        ActiveModelSettingsPayload(
            model="google/gemini-2.5-flash-image",
            supports_tools=False,
        )
    )
    assert await service.model_supports_tools() is False

    await service.replace_settings(
        ActiveModelSettingsPayload(
            model="meta-llama/llama-3-8b-instruct",
            supports_tools=True,
        )
    )
    assert await service.model_supports_tools() is True
