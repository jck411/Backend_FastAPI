from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.settings import router as settings_router
from backend.services.model_settings import ModelSettingsService


def make_app(
    tmp_path: Path,
    default_prompt: str | None = None,
    planner_enabled: bool = True,
) -> TestClient:
    app = FastAPI()
    service = ModelSettingsService(
        tmp_path / "model-settings.json",
        "openrouter/auto",
        default_system_prompt=default_prompt,
        default_llm_planner_enabled=planner_enabled,
    )
    app.state.model_settings_service = service
    app.include_router(settings_router)
    return TestClient(app)


def test_get_system_prompt_returns_default(tmp_path: Path) -> None:
    client = make_app(tmp_path, default_prompt="Default prompt")

    response = client.get("/api/settings/system-prompt")

    assert response.status_code == 200
    assert response.json() == {
        "system_prompt": "Default prompt",
        "llm_planner_enabled": True,
    }


def test_update_system_prompt_persists_value(tmp_path: Path) -> None:
    client = make_app(tmp_path, default_prompt=None)

    response = client.put(
        "/api/settings/system-prompt",
        json={"system_prompt": "  Use tools wisely.  "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "system_prompt": "Use tools wisely.",
        "llm_planner_enabled": True,
    }

    retrieved = client.get("/api/settings/system-prompt")
    assert retrieved.json() == {
        "system_prompt": "Use tools wisely.",
        "llm_planner_enabled": True,
    }


def test_clearing_system_prompt_returns_null(tmp_path: Path) -> None:
    client = make_app(tmp_path, default_prompt="Existing")

    response = client.put(
        "/api/settings/system-prompt",
        json={"system_prompt": None},
    )

    assert response.status_code == 200
    assert response.json() == {
        "system_prompt": None,
        "llm_planner_enabled": True,
    }

    retrieved = client.get("/api/settings/system-prompt")
    assert retrieved.json() == {
        "system_prompt": None,
        "llm_planner_enabled": True,
    }


def test_toggle_llm_planner_setting(tmp_path: Path) -> None:
    client = make_app(tmp_path, planner_enabled=False)

    response = client.get("/api/settings/system-prompt")
    assert response.status_code == 200
    assert response.json() == {
        "system_prompt": None,
        "llm_planner_enabled": False,
    }

    update = client.put(
        "/api/settings/system-prompt",
        json={"llm_planner_enabled": True},
    )
    assert update.status_code == 200
    assert update.json() == {
        "system_prompt": None,
        "llm_planner_enabled": True,
    }

    retrieved = client.get("/api/settings/system-prompt")
    assert retrieved.json() == {
        "system_prompt": None,
        "llm_planner_enabled": True,
    }
