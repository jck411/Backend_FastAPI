import pytest
from pathlib import Path
from backend.schemas.kiosk_llm_settings import KioskLlmSettings, KioskLlmSettingsUpdate
from backend.services.kiosk_llm_settings import KioskLlmSettingsService

@pytest.fixture
def temp_settings_file(tmp_path):
    return tmp_path / "test_kiosk_llm_settings.json"

def test_defaults(temp_settings_file):
    service = KioskLlmSettingsService(temp_settings_file)
    settings = service.get_settings()
    assert settings.model == "openai/gpt-4o-mini"
    assert "helpful voice assistant" in settings.system_prompt
    assert settings.temperature == 0.7

def test_update_settings(temp_settings_file):
    service = KioskLlmSettingsService(temp_settings_file)

    update = KioskLlmSettingsUpdate(model="anthropic/claude-3-haiku")
    new_settings = service.update_settings(update)

    assert new_settings.model == "anthropic/claude-3-haiku"
    assert new_settings.temperature == 0.7  # Unchanged

    # Verify persistence
    service2 = KioskLlmSettingsService(temp_settings_file)
    loaded = service2.get_settings()
    assert loaded.model == "anthropic/claude-3-haiku"

def test_reset(temp_settings_file):
    service = KioskLlmSettingsService(temp_settings_file)
    service.update_settings(KioskLlmSettingsUpdate(temperature=0.9))

    service.reset_to_defaults()
    assert service.get_settings().temperature == 0.7
