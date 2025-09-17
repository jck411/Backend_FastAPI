"""Streaming handler that coordinates OpenRouter responses and MCP tools."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from ..openrouter import OpenRouterClient
from ..repository import ChatRepository
from ..services.model_settings import ModelSettingsService
from ..schemas.chat import ChatCompletionRequest
from .mcp_client import MCPToolClient

logger = logging.getLogger(__name__)

SseEvent = dict[str, str | None]


@dataclass
class AssistantTurn:
    content: str | None
    tool_calls: list[dict[str, Any]]
    finish_reason: str | None
    model: str | None
    usage: dict[str, Any] | None
    meta: dict[str, Any] | None

    def to_message_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
        }
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls:
            message["tool_calls"] = self.tool_calls
        return message


class StreamingHandler:
    """Stream chat responses, execute tools, and persist conversation state."""

    def __init__(
        self,
        client: OpenRouterClient,
        repository: ChatRepository,
        tool_client: MCPToolClient,
        *,
        default_model: str,
        tool_hop_limit: int = 3,
        model_settings: ModelSettingsService | None = None,
    ) -> None:
        self._client = client
        self._repo = repository
        self._tool_client = tool_client
        self._default_model = default_model
        self._tool_hop_limit = tool_hop_limit
        self._model_settings = model_settings

    async def stream_conversation(
        self,
        session_id: str,
        request: ChatCompletionRequest,
        conversation: list[dict[str, Any]],
        tools_payload: list[dict[str, Any]],
    ) -> AsyncGenerator[SseEvent, None]:
        """Yield SSE events while maintaining state and executing tools."""

        hop_count = 0
        conversation_state = list(conversation)

        while True:
            routing_headers: dict[str, Any] | None = None
            active_model = self._default_model
            overrides: dict[str, Any] = {}
            if self._model_settings is not None:
                model_override, overrides = await self._model_settings.get_openrouter_overrides()
                if model_override:
                    active_model = model_override
                overrides = dict(overrides) if overrides else {}

            payload = request.to_openrouter_payload(active_model)
            payload["messages"] = conversation_state

            if overrides:
                provider_overrides = overrides.get("provider")
                if isinstance(provider_overrides, dict):
                    existing_provider = payload.get("provider")
                    if isinstance(existing_provider, dict):
                        # Persisted provider preferences act as defaults.
                        merged_provider = dict(provider_overrides)
                        merged_provider.update(existing_provider)
                        payload["provider"] = merged_provider
                    else:
                        payload["provider"] = dict(provider_overrides)
                for key, value in overrides.items():
                    if key == "provider":
                        continue
                    payload.setdefault(key, value)

            if tools_payload:
                payload["tools"] = tools_payload
                payload.setdefault("tool_choice", request.tool_choice or "auto")

            accumulator = _AssistantAccumulator()
            async for event in self._client.stream_chat_raw(payload):
                data = event.get("data")
                if not data:
                    continue
                event_name = event.get("event") or "message"

                if event_name == "openrouter_headers":
                    try:
                        parsed_headers = json.loads(data)
                    except json.JSONDecodeError:
                        logger.debug("Skipping invalid routing metadata payload: %s", data)
                    else:
                        if isinstance(parsed_headers, dict):
                            routing_headers = parsed_headers
                    continue

                if event_name != "message":
                    yield event
                    continue

                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON SSE payload: %s", data)
                    continue

                accumulator.consume(chunk)
                yield event

            assistant_turn = accumulator.build()
            metadata: dict[str, Any] = {}
            if assistant_turn.finish_reason is not None:
                metadata["finish_reason"] = assistant_turn.finish_reason
            if assistant_turn.tool_calls:
                metadata["tool_calls"] = assistant_turn.tool_calls
            if assistant_turn.model is not None:
                metadata["model"] = assistant_turn.model
            if assistant_turn.usage is not None:
                metadata["usage"] = assistant_turn.usage
            if assistant_turn.meta is not None:
                metadata["meta"] = assistant_turn.meta
            if routing_headers:
                metadata["routing"] = routing_headers

            await self._repo.add_message(
                session_id,
                role="assistant",
                content=assistant_turn.content,
                metadata=metadata or None,
            )
            conversation_state.append(assistant_turn.to_message_dict())

            metadata_event_payload = {
                "role": "assistant",
                "finish_reason": assistant_turn.finish_reason,
                "model": assistant_turn.model,
                "usage": assistant_turn.usage,
                "routing": routing_headers,
                "meta": assistant_turn.meta,
            }
            yield {
                "event": "metadata",
                "data": json.dumps(metadata_event_payload),
            }
            routing_headers = None

            if not assistant_turn.tool_calls:
                break

            if hop_count >= self._tool_hop_limit:
                warning = "Tool execution stopped after hop limit"
                logger.warning("%s for session %s", warning, session_id)
                yield {
                    "event": "tool",
                    "data": json.dumps(
                        {
                            "status": "error",
                            "name": "system",
                            "message": warning,
                        }
                    ),
                }
                break

            for call_index, tool_call in enumerate(assistant_turn.tool_calls):
                function = tool_call.get("function") or {}
                tool_name = function.get("name")
                tool_id = tool_call.get("id") or f"call_{call_index}"

                if not tool_name:
                    warning_text = (
                        "Tool call missing function name; skipping execution."
                    )
                    logger.warning(warning_text)
                    await self._repo.add_message(
                        session_id,
                        role="tool",
                        content=warning_text,
                        tool_call_id=tool_id,
                        metadata={"tool_name": "unknown"},
                    )
                    conversation_state.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": warning_text,
                        }
                    )
                    yield {
                        "event": "tool",
                        "data": json.dumps(
                            {
                                "status": "error",
                                "name": "unknown",
                                "call_id": tool_id,
                                "result": warning_text,
                            }
                        ),
                    }
                    continue

                yield {
                    "event": "tool",
                    "data": json.dumps(
                        {
                            "status": "started",
                            "name": tool_name,
                            "call_id": tool_id,
                        }
                    ),
                }

                arguments_raw = function.get("arguments")
                status = "finished"
                if not arguments_raw or arguments_raw.strip() == "":
                    result_text = (
                        f"Tool {tool_name} requires arguments but none were provided."
                    )
                    status = "error"
                    logger.warning("Missing tool arguments for %s", tool_name)
                else:
                    try:
                        arguments = json.loads(arguments_raw)
                    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                        result_text = (
                            f"Invalid JSON arguments for tool {tool_name}: {exc}"
                        )
                        status = "error"
                        logger.warning(
                            "Tool argument parse failure for %s: %s", tool_name, exc
                        )
                    else:
                        try:
                            result = await self._tool_client.call_tool(
                                tool_name, arguments
                            )
                            result_text = self._tool_client.format_tool_result(result)
                            status = "error" if result.isError else "finished"
                        except Exception as exc:  # pragma: no cover - MCP errors
                            logger.exception("Tool '%s' raised an exception", tool_name)
                            result_text = f"Tool error: {exc}"
                            status = "error"

                await self._repo.add_message(
                    session_id,
                    role="tool",
                    content=result_text,
                    tool_call_id=tool_id,
                    metadata={"tool_name": tool_name},
                )

                conversation_state.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result_text,
                    }
                )

                yield {
                    "event": "tool",
                    "data": json.dumps(
                        {
                            "status": status,
                            "name": tool_name,
                            "call_id": tool_id,
                            "result": result_text,
                        }
                    ),
                }

            hop_count += 1

        yield {"event": "message", "data": "[DONE]"}


class _AssistantAccumulator:
    def __init__(self) -> None:
        self._role = "assistant"
        self._content_fragments: list[str] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._finish_reason: str | None = None
        self._model: str | None = None
        self._usage: dict[str, Any] | None = None
        self._meta: dict[str, Any] | None = None

    def consume(self, payload: dict[str, Any]) -> None:
        choices = payload.get("choices") or []
        for choice in choices:
            delta = choice.get("delta") or {}
            role = delta.get("role")
            if role:
                self._role = role

            text = delta.get("content")
            if isinstance(text, str):
                self._content_fragments.append(text)

            if tool_calls := delta.get("tool_calls"):
                _merge_tool_calls(self._tool_calls, tool_calls)

            finish_reason = choice.get("finish_reason")
            if finish_reason:
                self._finish_reason = finish_reason

        model = payload.get("model")
        if isinstance(model, str):
            self._model = model

        usage = payload.get("usage")
        if isinstance(usage, dict):
            self._usage = usage

        meta = payload.get("meta")
        if isinstance(meta, dict):
            self._meta = meta

    def build(self) -> AssistantTurn:
        content = "".join(self._content_fragments)
        tool_calls: list[dict[str, Any]] = []
        for index, call in enumerate(self._tool_calls):
            function = call.get("function") or {}
            name = function.get("name")
            arguments = function.get("arguments")
            if not (name and arguments is not None and arguments.strip()):
                continue

            # Ensure each tool call has an identifier for downstream persistence.
            if not call.get("id"):
                call = dict(call)
                call["id"] = f"call_{index}"
            tool_calls.append(call)

        return AssistantTurn(
            content=content if content else None,
            tool_calls=tool_calls,
            finish_reason=self._finish_reason,
            model=self._model,
            usage=self._usage,
            meta=self._meta,
        )


def _merge_tool_calls(
    accumulator: list[dict[str, Any]],
    deltas: Any,
) -> None:
    for delta in deltas or []:
        if not isinstance(delta, dict):
            continue

        index = delta.get("index")
        delta_id = delta.get("id")
        if not isinstance(index, int) or index < 0:
            index = None
            if isinstance(delta_id, str):
                for existing_index, existing in enumerate(accumulator):
                    if existing.get("id") == delta_id:
                        index = existing_index
                        break
            if index is None:
                index = len(accumulator)

        while len(accumulator) <= index:
            accumulator.append(
                {
                    "id": None,
                    "type": "function",
                    "function": {"name": None, "arguments": ""},
                }
            )

        entry = accumulator[index]

        if delta_id:
            entry["id"] = delta_id
        if delta_type := delta.get("type"):
            entry["type"] = delta_type

        function_delta = delta.get("function") or {}
        if (function_name := function_delta.get("name")):
            entry.setdefault("function", {"name": None, "arguments": ""})
            entry["function"]["name"] = function_name
        if (arguments_fragment := function_delta.get("arguments")):
            entry.setdefault("function", {"name": None, "arguments": ""})
            entry["function"]["arguments"] += arguments_fragment


__all__ = ["StreamingHandler", "SseEvent"]
