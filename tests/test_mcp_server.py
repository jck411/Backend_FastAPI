from backend.mcp_server import _merge_tool_calls


def test_merge_tool_calls_accumulates_arguments() -> None:
    accumulator: dict[str, dict[str, object]] = {}

    _merge_tool_calls(
        accumulator,
        [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "do_something", "arguments": "{"},
            },
            {
                "id": "call_1",
                "function": {"arguments": '"value": 42'},
            },
            {
                "id": "call_1",
                "function": {"arguments": "}"},
            },
        ],
    )

    assert "call_1" in accumulator
    entry = accumulator["call_1"]
    assert entry["function"]["name"] == "do_something"  # type: ignore[index]
    assert entry["function"]["arguments"] == '{"value": 42}'  # type: ignore[index]


def test_merge_tool_calls_assigns_default_identifier() -> None:
    accumulator: dict[str, dict[str, object]] = {}

    _merge_tool_calls(
        accumulator,
        [
            {
                "type": "function",
                "function": {"name": "fallback", "arguments": "{}"},
            }
        ],
    )

    assert len(accumulator) == 1
    entry = next(iter(accumulator.values()))
    assert entry["function"]["name"] == "fallback"  # type: ignore[index]
    assert entry["function"]["arguments"] == "{}"  # type: ignore[index]
