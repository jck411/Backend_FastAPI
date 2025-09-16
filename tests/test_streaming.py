"""Tests for streaming handler functionality."""

from typing import Any

from src.backend.chat.streaming import _AssistantAccumulator, _merge_tool_calls


class TestAssistantAccumulator:
    """Test the streaming accumulator logic."""

    def test_build_filters_empty_arguments(self):
        """Tool calls with empty arguments should be filtered out."""
        accumulator = _AssistantAccumulator()

        # Simulate streaming chunks with empty arguments
        accumulator.consume(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator_evaluate",
                                        "arguments": "",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

        result = accumulator.build()

        # Tool call with empty arguments should be filtered out
        assert result.tool_calls == []

    def test_build_includes_valid_arguments(self):
        """Tool calls with valid arguments should be included."""
        accumulator = _AssistantAccumulator()

        # Simulate streaming chunks with valid arguments
        accumulator.consume(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator_evaluate",
                                        "arguments": '{"operation": "add", "a": 2, "b": 3}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

        result = accumulator.build()

        # Tool call with valid arguments should be included
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["function"]["name"] == "calculator_evaluate"
        assert (
            result.tool_calls[0]["function"]["arguments"]
            == '{"operation": "add", "a": 2, "b": 3}'
        )

    def test_build_filters_whitespace_only_arguments(self):
        """Tool calls with whitespace-only arguments should be filtered out."""
        accumulator = _AssistantAccumulator()

        # Simulate streaming chunks with whitespace-only arguments
        accumulator.consume(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator_evaluate",
                                        "arguments": "   \n\t  ",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

        result = accumulator.build()

        # Tool call with whitespace-only arguments should be filtered out
        assert result.tool_calls == []


class TestMergeToolCalls:
    """Test the tool call delta merging logic."""

    def test_merge_accumulates_arguments(self):
        """Arguments should be accumulated across multiple deltas."""
        accumulator: list[dict[str, Any]] = []

        # First delta with partial arguments
        _merge_tool_calls(
            accumulator,
            [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator_evaluate",
                        "arguments": '{"operation":',
                    },
                }
            ],
        )

        # Second delta with more arguments
        _merge_tool_calls(
            accumulator, [{"id": "call_1", "function": {"arguments": '"add","a":2,'}}]
        )

        # Third delta completing arguments
        _merge_tool_calls(
            accumulator, [{"id": "call_1", "function": {"arguments": '"b":3}'}}]
        )

        # Check that arguments were properly accumulated
        call = accumulator[0]
        assert call["function"]["arguments"] == '{"operation":"add","a":2,"b":3}'

    def test_merge_handles_missing_id(self):
        """Tool calls without IDs should be handled gracefully."""
        accumulator: list[dict[str, Any]] = []

        _merge_tool_calls(
            accumulator,
            [
                {
                    "type": "function",
                    "function": {
                        "name": "calculator_evaluate",
                        "arguments": '{"operation":"add"}',
                    },
                }
            ],
        )

        # Should create entry with function details populated
        assert accumulator
        assert (
            accumulator[0]["function"]["name"] == "calculator_evaluate"
        )
