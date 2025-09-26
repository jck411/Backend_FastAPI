from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.chat import get_openrouter_client, router


class DummyOpenRouterClient:
    def __init__(
        self,
        payload: dict[str, Any],
        category_payloads: dict[str, Any] | None = None,
    ) -> None:
        self._payload = payload
        self._category_payloads = category_payloads or {}

    async def list_models(
        self, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if params and "category" in params:
            slug = params["category"]
            return self._category_payloads.get(slug, {"data": []})
        return self._payload


def make_client(
    payload: dict[str, Any],
    category_payloads: dict[str, Any] | None = None,
) -> TestClient:
    app = FastAPI()

    def _override_client() -> DummyOpenRouterClient:
        return DummyOpenRouterClient(payload, category_payloads=category_payloads)

    app.dependency_overrides[get_openrouter_client] = _override_client
    app.include_router(router)

    return TestClient(app)


def test_models_endpoint_marks_tool_support() -> None:
    payload = {
        "data": [
            {
                "id": "a",
                "capabilities": {"tools": True},
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "pricing": {"prompt": "0.0000001"},
                "categories": ["programming", "science"],
            },
            {"id": "b", "capabilities": {"tools": False}},
            {"id": "c", "capabilities": {"function_calling": "enabled"}},
            {"id": "d"},
            {
                "id": "e",
                "supported_parameters": ["temperature", "tools"],
                "architecture": {
                    "input_modalities": ["image", "text"],
                    "output_modalities": ["text"],
                },
                "pricing": {"prompt": "0"},
            },
        ]
    }

    client = make_client(payload)
    response = client.get("/api/models")

    assert response.status_code == 200
    body = response.json()
    supports_tools = {item["id"]: item.get("supports_tools") for item in body["data"]}
    assert supports_tools == {
        "a": True,
        "b": False,
        "c": True,
        "d": False,
        "e": True,
    }

    enriched = {item["id"]: item for item in body["data"]}
    assert enriched["a"]["input_modalities"] == ["text"]
    assert enriched["e"]["input_modalities"] == ["image", "text"]
    assert enriched["a"]["prompt_price_per_million"] == pytest.approx(0.1)
    assert "Other" in enriched["d"].get("series", [])
    assert enriched["a"].get("categories", []) == ["Programming", "Science"]
    assert enriched["a"].get("categories_normalized", []) == [
        "programming",
        "science",
    ]

    metadata = body.get("metadata")
    assert metadata is not None
    paths = {entry["path"] for entry in metadata["properties"]}
    assert "id" in paths
    assert "capabilities.tools" in paths
    facets = metadata["facets"]
    assert "text" in facets["input_modalities"]
    assert facets["prompt_price_per_million"]["min"] == 0.0
    assert "Programming" in facets["categories"]


def test_models_endpoint_backfills_categories_from_api_queries() -> None:
    payload = {
        "data": [
            {"id": "model-a", "name": "Model A"},
            {"id": "model-b", "name": "Model B"},
        ]
    }

    category_payloads = {
        "programming": {"data": [{"id": "model-a"}]},
        "roleplay": {"data": [{"id": "model-b"}]},
    }

    client = make_client(payload, category_payloads=category_payloads)
    response = client.get("/api/models")

    assert response.status_code == 200
    body = response.json()

    categories = {item["id"]: item.get("categories", []) for item in body["data"]}
    assert categories["model-a"] == ["Programming"]
    assert categories["model-b"] == ["Roleplay"]

    facets = body["metadata"]["facets"]
    assert set(facets["categories"]) >= {"Programming", "Roleplay"}


def test_models_endpoint_filters_for_tool_support() -> None:
    payload = {
        "data": [
            {"id": "a", "capabilities": {"tools": True}},
            {"id": "b", "supports_tools": False},
            {"id": "c", "tools": ["something"]},
        ]
    }

    client = make_client(payload)
    response = client.get("/api/models", params={"tools_only": "true"})

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["a", "c"]

    metadata = body["metadata"]
    assert metadata["base_count"] == 2
    assert metadata["count"] == 2


def test_models_endpoint_supports_search_query() -> None:
    payload = {
        "data": [
            {"id": "model-a", "name": "Fast Model", "description": "Great for coding"},
            {
                "id": "model-b",
                "name": "Accurate Model",
                "description": "Great for math",
            },
        ]
    }

    client = make_client(payload)
    response = client.get("/api/models", params={"search": "math"})

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["model-b"]


def test_models_endpoint_series_aliases_allow_search() -> None:
    payload = {
        "data": [
            {"id": "google/text-bison@001", "name": "Text Bison"},
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
        ]
    }

    client = make_client(payload)
    response = client.get("/api/models", params={"search": "pam"})

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["data"]}
    assert "google/text-bison@001" in ids
    # Ensure normalized series are included on the enriched model.
    item = next(
        model for model in body["data"] if model["id"] == "google/text-bison@001"
    )
    assert "palm" in item.get("series_normalized", [])


def test_models_endpoint_series_aliases_allow_filtering() -> None:
    payload = {
        "data": [
            {"id": "google/text-bison@001", "name": "Text Bison"},
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
        ]
    }

    client = make_client(payload)
    response = client.get(
        "/api/models",
        params={"filters": json.dumps({"series": ["pam"]})},
    )

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["google/text-bison@001"]


def test_models_endpoint_classifies_palm_series() -> None:
    payload = {
        "data": [
            {"id": "google/text-bison@001", "name": "Text Bison"},
            {"id": "google/codey-codechat-bison", "name": "Codey for Bison"},
        ]
    }

    client = make_client(payload)
    response = client.get("/api/models")

    assert response.status_code == 200
    body = response.json()
    series_map = {item["id"]: item.get("series", []) for item in body["data"]}
    assert "PaLM" in series_map["google/text-bison@001"]
    assert "PaLM" in series_map["google/codey-codechat-bison"]


def test_models_endpoint_applies_advanced_filters() -> None:
    payload = {
        "data": [
            {
                "id": "model-a",
                "pricing": {"prompt": 0.001, "completion": 0.002},
                "capabilities": {"tools": True},
            },
            {
                "id": "model-b",
                "pricing": {"prompt": 0.01, "completion": 0.02},
                "capabilities": {"tools": False},
            },
        ]
    }

    client = make_client(payload)
    response = client.get(
        "/api/models",
        params={
            "filters": json.dumps(
                {
                    "pricing.prompt": {"max": 0.005},
                    "capabilities.tools": True,
                }
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["model-a"]
