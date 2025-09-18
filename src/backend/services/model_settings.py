"""Service for persisting and exposing active model settings."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from ..schemas.model_settings import (
    ActiveModelSettingsPayload,
    ActiveModelSettingsResponse,
)
from ..openrouter import OpenRouterError

logger = logging.getLogger(__name__)


def _coerce_float(value: Any) -> float | None:
    """Best-effort conversion of mixed numeric inputs to float."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _format_price(value: float | None, kind: str) -> str | None:
    if value is None:
        return None

    if value >= 1:
        formatted = f"${value:,.2f}"
    elif value >= 0.01:
        formatted = f"${value:,.3f}"
    else:
        formatted = f"${value:,.4f}"

    suffix = {
        "completion": "/m completion",
        "prompt": "/m prompt",
        "request": "/request",
        "image": "/image",
    }.get(kind, "")
    return f"{formatted}{suffix}"


def _build_provider_details(provider_entry: Dict[str, Any]) -> Dict[str, Any]:
    provider_info = provider_entry.get("provider")
    if not isinstance(provider_info, dict):
        provider_info = {}

    slug = provider_info.get("name") or provider_info.get("id") or provider_entry.get("slug")
    display_name = (
        provider_info.get("display_name")
        or provider_entry.get("display_name")
        or provider_info.get("name")
        or provider_info.get("id")
        or slug
    )

    endpoint_id = provider_entry.get("id") or provider_entry.get("endpoint")
    region = provider_entry.get("region") or provider_entry.get("location")

    pricing_raw = provider_entry.get("pricing")
    pricing: Dict[str, float | None] = {}
    if isinstance(pricing_raw, dict):
        for key in ("prompt", "completion", "request", "image"):
            pricing[key] = _coerce_float(pricing_raw.get(key))

    throughput = _coerce_float(provider_entry.get("throughput_tokens_per_second"))
    latency = _coerce_float(provider_entry.get("latency_ms"))

    details: Dict[str, Any] = {
        "display_name": display_name,
        "slug": slug,
        "provider_id": provider_info.get("id") or slug,
        "endpoint_id": endpoint_id,
        "region": region,
        "pricing": pricing,
        "throughput_tokens_per_second": throughput,
        "latency_ms": latency,
    }

    # Build a short human-readable summary
    label_parts = []
    if display_name and slug and display_name.lower() != slug.lower():
        label_parts.append(f"{display_name} ({slug})")
    elif display_name:
        label_parts.append(display_name)
    elif slug:
        label_parts.append(slug)
    else:
        label_parts.append("Unknown provider")

    if region:
        label_parts.append(str(region))

    price_label = None
    if pricing:
        for price_key in ("completion", "prompt", "request", "image"):
            price_label = _format_price(pricing.get(price_key), price_key)
            if price_label:
                break
    if price_label:
        label_parts.append(price_label)

    if throughput:
        label_parts.append(f"{throughput:,.0f} tok/s")

    if latency:
        label_parts.append(f"{latency:,.0f} ms latency")

    details["summary"] = " · ".join(label_parts)

    return details


def _provider_price_sort_key(provider_entry: Dict[str, Any]) -> float:
    pricing = provider_entry.get("pricing")
    if isinstance(pricing, dict):
        value = _coerce_float(pricing.get("completion"))
        if value is not None:
            return value
    return float("inf")


def _provider_throughput_sort_key(provider_entry: Dict[str, Any]) -> float:
    value = _coerce_float(provider_entry.get("throughput_tokens_per_second"))
    if value is not None:
        return value
    return 0.0


def _provider_latency_sort_key(provider_entry: Dict[str, Any]) -> float:
    value = _coerce_float(provider_entry.get("latency_ms"))
    if value is not None:
        return value
    return float("inf")


class ModelSettingsService:
    """Manage the active model, provider routing, and hyperparameters."""

    def __init__(self, path: Path, default_model: str) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._settings = ActiveModelSettingsResponse(model=default_model)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read model settings file %s: %s", self._path, exc)
            return

        try:
            loaded = ActiveModelSettingsResponse.model_validate(data)
        except ValidationError:
            try:
                payload = ActiveModelSettingsPayload.model_validate(data)
            except (
                ValidationError
            ) as exc:  # pragma: no cover - corrupted persisted state
                logger.warning(
                    "Invalid model settings payload in %s: %s", self._path, exc
                )
                return
            loaded = ActiveModelSettingsResponse(
                **payload.model_dump(exclude_none=False),
                updated_at=datetime.now(timezone.utc),
            )

        self._settings = loaded

    def _save_to_disk(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = self._settings.model_dump(exclude_none=True)
        data["updated_at"] = self._settings.updated_at.isoformat()
        serialized = json.dumps(data, indent=2, sort_keys=True)
        self._path.write_text(serialized + "\n", encoding="utf-8")

    async def get_settings(self) -> ActiveModelSettingsResponse:
        async with self._lock:
            return self._settings.model_copy(deep=True)

    async def replace_settings(
        self, payload: ActiveModelSettingsPayload
    ) -> ActiveModelSettingsResponse:
        async with self._lock:
            self._settings = ActiveModelSettingsResponse(
                **payload.model_dump(exclude_none=False),
                updated_at=datetime.now(timezone.utc),
            )
            self._save_to_disk()
            return self._settings.model_copy(deep=True)

    async def get_openrouter_overrides(self) -> Tuple[str, Dict[str, Any]]:
        """Return the active model id and OpenRouter payload overrides."""

        settings = await self.get_settings()
        overrides = settings.as_openrouter_overrides()
        return settings.model, overrides

    async def get_active_provider_info(self, openrouter_client) -> Dict[str, Any]:
        """Get the active service provider information for the current model based on provider preferences."""

        settings = await self.get_settings()
        model_id = settings.model

        try:
            # Get available service providers for general context
            try:
                providers_response = await openrouter_client.list_providers()
            except OpenRouterError as exc:
                logger.info(
                    "Unable to list providers for %s: %s", model_id, exc.detail
                )
                providers_response = {"data": []}
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Unexpected provider list failure for %s: %s", model_id, exc
                )
                providers_response = {"data": []}

            all_providers = providers_response.get("data", [])

            # For models with explicit endpoints, get the model-specific endpoints
            model_endpoints = []
            if "/" in model_id and model_id != "openrouter/auto":
                try:
                    endpoints_response = await openrouter_client.list_model_endpoints(
                        model_id
                    )
                except OpenRouterError as exc:
                    logger.info(
                        "Unable to list endpoints for %s: %s", model_id, exc.detail
                    )
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(
                        "Unexpected endpoint list failure for %s: %s", model_id, e
                    )
                else:
                    model_endpoints = endpoints_response.get("data", [])
                    logger.info(
                        "Got %d endpoints for model %s", len(model_endpoints), model_id
                    )

            provider_prefs = settings.provider

            if provider_prefs:
                # Start with model endpoints if available, otherwise use all providers
                available_providers = (
                    model_endpoints if model_endpoints else all_providers.copy()
                )

                # Apply filters to get count of available providers
                if provider_prefs.data_collection == "deny":
                    available_providers = [
                        p
                        for p in available_providers
                        if p.get("zero_data_retention", False)
                    ]

                if provider_prefs.only:
                    available_providers = [
                        p
                        for p in available_providers
                        if p.get("provider", {}).get("name") in provider_prefs.only
                    ]

                if provider_prefs.ignore:
                    available_providers = [
                        p
                        for p in available_providers
                        if p.get("provider", {}).get("name")
                        not in provider_prefs.ignore
                    ]

                # Build response based on active preferences
                response = {
                    "model_id": model_id,
                    "total_providers": len(all_providers),
                    "available_providers": len(available_providers),
                    "routing_strategy": "dynamic",
                }

                # Apply sorting and get the selected provider
                selected_provider = None
                if provider_prefs.order and len(provider_prefs.order) > 0:
                    # Explicit order specified
                    for preferred_provider in provider_prefs.order:
                        for provider in available_providers:
                            provider_name = provider.get("provider", {}).get("name", "")
                            if provider_name == preferred_provider:
                                selected_provider = provider
                                break
                        if selected_provider:
                            break

                    if selected_provider:
                        details = _build_provider_details(selected_provider)
                        response["provider"] = details.get("summary") or details.get("display_name")
                        response["provider_id"] = details.get("provider_id")
                        response["provider_slug"] = details.get("slug")
                        response["selected_endpoint"] = details
                    else:
                        response["provider"] = provider_prefs.order[0]
                    response["provider_type"] = "explicit_order"
                    response["provider_order"] = provider_prefs.order
                elif provider_prefs.sort and available_providers:
                    # Apply sorting strategy to find the actual selected provider
                    if provider_prefs.sort == "price":
                        # Sort by price (lowest first)
                        sorted_providers = sorted(
                            available_providers,
                            key=_provider_price_sort_key,
                        )
                    elif provider_prefs.sort == "throughput":
                        # Sort by throughput (highest first)
                        sorted_providers = sorted(
                            available_providers,
                            key=_provider_throughput_sort_key,
                            reverse=True,
                        )
                    elif provider_prefs.sort == "latency":
                        # Sort by latency (lowest first)
                        sorted_providers = sorted(
                            available_providers,
                            key=_provider_latency_sort_key,
                        )
                    else:
                        sorted_providers = available_providers

                    selected_provider = (
                        sorted_providers[0] if sorted_providers else None
                    )

                    if selected_provider:
                        details = _build_provider_details(selected_provider)
                        response["provider"] = (
                            details.get("summary")
                            or details.get("display_name")
                            or details.get("slug")
                        )
                        response["provider_type"] = "dynamic_sort"
                        response["sort_strategy"] = provider_prefs.sort
                        response["selected_endpoint"] = details
                        response["provider_id"] = details.get("provider_id")
                        response["provider_slug"] = details.get("slug")
                    else:
                        # Fallback if no providers found
                        sort_descriptions = {
                            "price": "lowest cost provider",
                            "throughput": "highest throughput provider",
                            "latency": "lowest latency provider",
                        }
                        response["provider"] = (
                            f"Dynamic ({sort_descriptions.get(provider_prefs.sort, provider_prefs.sort)})"
                        )
                        response["provider_type"] = "dynamic_sort"
                        response["sort_strategy"] = provider_prefs.sort
                else:
                    response["provider"] = "OpenRouter default routing"
                    response["provider_type"] = "default"

                # Add filter information
                filters_applied = []
                if provider_prefs.data_collection == "deny":
                    filters_applied.append("zero-data retention only")
                if provider_prefs.only:
                    filters_applied.append(f"only: {', '.join(provider_prefs.only)}")
                if provider_prefs.ignore:
                    filters_applied.append(
                        f"ignoring: {', '.join(provider_prefs.ignore)}"
                    )

                response["filters_applied"] = filters_applied
                response["allow_fallbacks"] = provider_prefs.allow_fallbacks
                response["require_parameters"] = provider_prefs.require_parameters
                response["has_model_endpoints"] = len(model_endpoints) > 0

                return response
            else:
                # No provider preferences - using OpenRouter default routing
                return {
                    "provider": "OpenRouter default routing",
                    "provider_type": "default",
                    "model_id": model_id,
                    "total_providers": len(all_providers),
                    "available_providers": len(all_providers),
                    "routing_strategy": "default",
                    "note": "No provider preferences set",
                    "has_model_endpoints": len(model_endpoints) > 0,
                }

        except Exception as e:
            logger.warning(
                "Failed to get active provider info for model %s: %s",
                model_id,
                e,
                exc_info=True,
            )
            # Fallback to extracting provider from model ID
            provider_name = model_id.split("/")[0] if "/" in model_id else "unknown"
            return {
                "provider": provider_name,
                "provider_id": provider_name,
                "error": str(e),
                "fallback": True,
            }


__all__ = ["ModelSettingsService"]
