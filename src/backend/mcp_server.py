"""Model Context Protocol server exposing OpenRouter chat completions."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from .config import get_settings
from .openrouter import OpenRouterClient, OpenRouterError
from .schemas.chat import ChatCompletionRequest

mcp = FastMCP("openrouter-backend")
_settings = get_settings()
_client = OpenRouterClient(_settings)


@mcp.tool("chat.completions")
async def chat_completions(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Proxy chat completions through OpenRouter.

    The payload mirrors OpenRouter's `/chat/completions` schema.
    """

    request = ChatCompletionRequest(**payload)

    try:
        return await _collect_response(request)
    except OpenRouterError as exc:
        # MCP tools should raise exceptions to signal failure
        raise RuntimeError(
            json.dumps(
                {
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )
        ) from exc


async def _collect_response(request: ChatCompletionRequest) -> Dict[str, Any]:
    aggregated_content: list[str] = []
    role: Optional[str] = None
    finish_reason: Optional[str] = None
    response_id: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    tool_calls: Dict[str, Dict[str, Any]] = {}

    async for event in _client.stream_chat(request):
        data = event.get("data") if event else None
        if not data:
            continue
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue

        response_id = payload.get("id", response_id)
        usage = payload.get("usage") or usage
        for choice in payload.get("choices", []):
            delta = choice.get("delta") or {}
            role = delta.get("role", role)

            text = delta.get("content")
            if text:
                aggregated_content.append(text)

            if tool_chunks := delta.get("tool_calls"):
                _merge_tool_calls(tool_calls, tool_chunks)

            finish = choice.get("finish_reason")
            if finish:
                finish_reason = finish

    response: Dict[str, Any] = {
        "id": response_id,
        "role": role or "assistant",
        "content": "".join(aggregated_content),
        "finish_reason": finish_reason,
        "usage": usage,
    }

    calls = list(tool_calls.values())
    if calls:
        response["tool_calls"] = calls

    return {key: value for key, value in response.items() if value is not None}


def _merge_tool_calls(
    tool_calls: Dict[str, Dict[str, Any]],
    deltas: Any,
) -> None:
    for delta in deltas or []:
        identifier = delta.get("id")
        function_info = delta.get("function") or {}
        function_name = function_info.get("name")
        arguments_fragment = function_info.get("arguments")

        if identifier is None:
            identifier = str(function_name or len(tool_calls))

        entry = tool_calls.setdefault(
            identifier,
            {
                "id": identifier,
                "type": delta.get("type", "function"),
                "function": {
                    "name": function_name,
                    "arguments": "",
                },
            },
        )

        if function_name:
            entry["function"]["name"] = function_name
        if arguments_fragment:
            entry["function"]["arguments"] += arguments_fragment


def run() -> None:  # pragma: no cover - integration entrypoint
    """Run the MCP server using the default FastMCP runner."""

    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = ["mcp", "run", "chat_completions"]
