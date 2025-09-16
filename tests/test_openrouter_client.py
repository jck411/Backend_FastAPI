from backend.config import Settings
from backend.openrouter import OpenRouterClient


def make_client() -> OpenRouterClient:
    settings = Settings(
        openrouter_api_key="test",
        openrouter_base_url="https://example.com/api/v1",
    )
    return OpenRouterClient(settings)


def test_parse_event_supports_multiple_data_lines() -> None:
    client = make_client()

    event = client._parse_event(  # type: ignore[attr-defined]
        [
            "event: completion",
            "id: test-id",
            "data: part one",
            "data: part two",
        ]
    )

    assert event.event == "completion"
    assert event.event_id == "test-id"
    assert event.data == "part one\npart two"
    assert event.asdict() == {
        "event": "completion",
        "data": "part one\npart two",
        "id": "test-id",
    }
