"""Streaming handler that coordinates OpenRouter responses and MCP tools."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Iterable, List, Protocol

from ..openrouter import OpenRouterClient, OpenRouterError
from ..repository import ChatRepository, format_timestamp_for_client
from ..services.model_settings import ModelSettingsService
from ..schemas.chat import ChatCompletionRequest


class ToolExecutor(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any: ...

    def get_openai_tools(self) -> list[dict[str, Any]]: ...

    def format_tool_result(self, result: Any) -> str: ...

logger = logging.getLogger(__name__)

SseEvent = dict[str, str | None]

_SESSION_AWARE_TOOL_NAME = "chat_history"
_SESSION_AWARE_TOOL_SUFFIX = "__chat_history"


@dataclass
class AssistantTurn:
    content: str | List[dict[str, Any]] | None
    tool_calls: list[dict[str, Any]]
    finish_reason: str | None
    model: str | None
    usage: dict[str, Any] | None
    meta: dict[str, Any] | None
    generation_id: str | None
    reasoning: list[dict[str, Any]] | None
    created_at: str | None = None
    created_at_utc: str | None = None

    def to_message_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
        }
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls:
            message["tool_calls"] = self.tool_calls
        if self.created_at is not None:
            message["created_at"] = self.created_at
        if self.created_at_utc is not None:
            message["created_at_utc"] = self.created_at_utc
        return message


class StreamingHandler:
    """Stream chat responses, execute tools, and persist conversation state."""

    def __init__(
        self,
        client: OpenRouterClient,
        repository: ChatRepository,
        tool_client: ToolExecutor,
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
        assistant_parent_message_id: str | None,
    ) -> AsyncGenerator[SseEvent, None]:
        """Yield SSE events while maintaining state and executing tools."""

        hop_count = 0
        conversation_state = list(conversation)
        assistant_client_message_id: str | None = None
        if isinstance(request.metadata, dict):
            candidate = request.metadata.get("client_assistant_message_id")
            if isinstance(candidate, str):
                assistant_client_message_id = candidate
        tools_available = bool(tools_payload)
        tool_choice_value = request.tool_choice
        requested_tool_choice = (
            tool_choice_value if isinstance(tool_choice_value, str) else None
        )
        tools_disabled = requested_tool_choice == "none" or not tools_available
        has_structured_tool_choice = isinstance(tool_choice_value, dict)
        can_retry_without_tools = (
            requested_tool_choice in (None, "auto") and not has_structured_tool_choice
        )

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

            allow_tools = tools_available and not tools_disabled
            if allow_tools:
                payload["tools"] = tools_payload
                payload.setdefault("tool_choice", request.tool_choice or "auto")
            else:
                payload.pop("tools", None)
                payload.pop("tool_choice", None)

            content_fragments: list[str] = []
            structured_segments: list[dict[str, Any]] = []
            streamed_tool_calls: list[dict[str, Any]] = []
            finish_reason: str | None = None
            model_name: str | None = None
            usage_details: dict[str, Any] | None = None
            meta_details: dict[str, Any] | None = None
            generation_id: str | None = None
            reasoning_segments: list[dict[str, Any]] = []
            seen_reasoning: set[tuple[str, str]] = set()
            try:
                async for event in self._client.stream_chat_raw(payload):
                    data = event.get("data")
                    if not data:
                        continue
                    event_name = event.get("event") or "message"

                    if event_name == "openrouter_headers":
                        try:
                            parsed_headers = json.loads(data)
                        except json.JSONDecodeError:
                            logger.debug(
                                "Skipping invalid routing metadata payload: %s", data
                            )
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

                    choices = chunk.get("choices") or []
                    for choice in choices:
                        delta = choice.get("delta") or {}

                        delta_content = delta.get("content")
                        if isinstance(delta_content, str):
                            _append_structured_segment(
                                structured_segments,
                                {"type": "text", "text": delta_content},
                                content_fragments,
                            )
                        elif isinstance(delta_content, list):
                            for segment in delta_content:
                                if isinstance(segment, dict):
                                    _append_structured_segment(
                                        structured_segments, segment, content_fragments
                                    )

                        if tool_deltas := delta.get("tool_calls"):
                            _merge_tool_calls(streamed_tool_calls, tool_deltas)

                        choice_finish = choice.get("finish_reason")
                        if choice_finish:
                            finish_reason = choice_finish

                        if "reasoning" in delta:
                            new_segments = _extract_reasoning_segments(delta["reasoning"])
                            _extend_reasoning_segments(
                                reasoning_segments, new_segments, seen_reasoning
                            )

                    model_value = chunk.get("model")
                    if isinstance(model_value, str):
                        model_name = model_value

                    usage_value = chunk.get("usage")
                    if isinstance(usage_value, dict):
                        usage_details = usage_value

                    meta_value = chunk.get("meta")
                    if isinstance(meta_value, dict):
                        meta_details = meta_value

                    chunk_id = chunk.get("id")
                    if isinstance(chunk_id, str) and chunk_id:
                        generation_id = chunk_id

                    for key in ("reasoning", "message"):
                        if key not in chunk:
                            continue
                        payload_value = chunk[key]
                        if key == "message" and isinstance(payload_value, dict):
                            reasoning_value = payload_value.get("reasoning")
                        else:
                            reasoning_value = payload_value
                        if reasoning_value is not None:
                            new_segments = _extract_reasoning_segments(reasoning_value)
                            _extend_reasoning_segments(
                                reasoning_segments, new_segments, seen_reasoning
                            )

                    yield event
            except OpenRouterError as exc:
                if allow_tools and can_retry_without_tools and _is_tool_support_error(exc):
                    logger.info(
                        "Retrying without tools for session %s: %s", session_id, exc.detail
                    )
                    tools_disabled = True
                    warning_text = (
                        "Tools unavailable for this model; continuing without them."
                    )
                    yield {
                        "event": "tool",
                        "data": json.dumps(
                            {
                                "status": "notice",
                                "name": "system",
                                "message": warning_text,
                            }
                        ),
                    }
                    continue
                raise

            tool_calls = _finalize_tool_calls(streamed_tool_calls)
            if structured_segments:
                if _contains_non_text_segments(structured_segments):
                    content_value: str | List[dict[str, Any]] | None = structured_segments
                else:
                    combined_text = "".join(
                        segment.get("text", "")
                        for segment in structured_segments
                        if isinstance(segment, dict) and segment.get("type") == "text"
                    )
                    content_value = combined_text or None
            else:
                combined_text = "".join(content_fragments)
                content_value = combined_text or None

            assistant_turn = AssistantTurn(
                content=content_value,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                model=model_name,
                usage=usage_details,
                meta=meta_details,
                generation_id=generation_id,
                reasoning=reasoning_segments if reasoning_segments else None,
            )
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
            if assistant_turn.generation_id is not None:
                metadata["generation_id"] = assistant_turn.generation_id
            if assistant_turn.reasoning is not None:
                metadata["reasoning"] = assistant_turn.reasoning
            if routing_headers:
                metadata["routing"] = routing_headers
            if assistant_client_message_id is not None:
                metadata.setdefault("client_message_id", assistant_client_message_id)

            assistant_record_id, assistant_created_at = await self._repo.add_message(
                session_id,
                role="assistant",
                content=assistant_turn.content,
                metadata=metadata or None,
                client_message_id=assistant_client_message_id,
                parent_client_message_id=assistant_parent_message_id,
            )
            edt_iso, utc_iso = format_timestamp_for_client(assistant_created_at)
            assistant_turn.created_at = edt_iso or assistant_created_at
            assistant_turn.created_at_utc = utc_iso or assistant_created_at
            conversation_state.append(assistant_turn.to_message_dict())

            metadata_event_payload = {
                "role": "assistant",
                "finish_reason": assistant_turn.finish_reason,
                "model": assistant_turn.model,
                "usage": assistant_turn.usage,
                "routing": routing_headers,
                "meta": assistant_turn.meta,
                "generation_id": assistant_turn.generation_id,
                "reasoning": assistant_turn.reasoning,
                "tool_calls": assistant_turn.tool_calls if assistant_turn.tool_calls else None,
            }
            if assistant_turn.content is not None:
                metadata_event_payload["content"] = assistant_turn.content
            if assistant_client_message_id is not None:
                metadata_event_payload["client_message_id"] = assistant_client_message_id
            metadata_event_payload["message_id"] = assistant_record_id
            if assistant_turn.created_at is not None:
                metadata_event_payload["created_at"] = assistant_turn.created_at
            if assistant_turn.created_at_utc is not None:
                metadata_event_payload["created_at_utc"] = assistant_turn.created_at_utc
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
                    tool_record_id, tool_created_at = await self._repo.add_message(
                        session_id,
                        role="tool",
                        content=warning_text,
                        tool_call_id=tool_id,
                        metadata={
                            "tool_name": "unknown",
                            "parent_client_message_id": assistant_client_message_id,
                        },
                        parent_client_message_id=assistant_client_message_id,
                    )
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": warning_text,
                    }
                    edt_iso, utc_iso = format_timestamp_for_client(tool_created_at)
                    if edt_iso is not None:
                        tool_message["created_at"] = edt_iso
                    if utc_iso is not None:
                        tool_message["created_at_utc"] = utc_iso
                    conversation_state.append(tool_message)
                    yield {
                        "event": "tool",
                        "data": json.dumps(
                            {
                                "status": "error",
                                "name": "unknown",
                                "call_id": tool_id,
                                "result": warning_text,
                                "message_id": tool_record_id,
                                "created_at": edt_iso or tool_created_at,
                                "created_at_utc": utc_iso or tool_created_at,
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
                        if not isinstance(arguments, dict):
                            result_text = (
                                f"Tool {tool_name} expected a JSON object for arguments but "
                                f"received {type(arguments).__name__}."
                            )
                            status = "error"
                            logger.warning(
                                "Unexpected tool argument type for %s: %s",
                                tool_name,
                                type(arguments).__name__,
                            )
                        else:
                            working_arguments = dict(arguments)
                            if session_id and _tool_requires_session_id(tool_name):
                                working_arguments.setdefault("session_id", session_id)
                            try:
                                result = await self._tool_client.call_tool(
                                    tool_name, working_arguments
                                )
                                result_text = self._tool_client.format_tool_result(result)
                                status = "error" if result.isError else "finished"
                            except Exception as exc:  # pragma: no cover - MCP errors
                                logger.exception(
                                    "Tool '%s' raised an exception", tool_name
                                )
                                result_text = f"Tool error: {exc}"
                                status = "error"

                tool_record_id, tool_created_at = await self._repo.add_message(
                    session_id,
                    role="tool",
                    content=result_text,
                    tool_call_id=tool_id,
                    metadata={
                        "tool_name": tool_name,
                        "parent_client_message_id": assistant_client_message_id,
                    },
                    parent_client_message_id=assistant_client_message_id,
                )

                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result_text,
                }
                edt_iso, utc_iso = format_timestamp_for_client(tool_created_at)
                if edt_iso is not None:
                    tool_message["created_at"] = edt_iso
                if utc_iso is not None:
                    tool_message["created_at_utc"] = utc_iso
                conversation_state.append(tool_message)

                yield {
                    "event": "tool",
                    "data": json.dumps(
                        {
                            "status": status,
                            "name": tool_name,
                            "call_id": tool_id,
                            "result": result_text,
                            "message_id": tool_record_id,
                            "created_at": edt_iso or tool_created_at,
                            "created_at_utc": utc_iso or tool_created_at,
                        }
                    ),
                }

            hop_count += 1

        yield {"event": "message", "data": "[DONE]"}


def _is_tool_support_error(error: OpenRouterError) -> bool:
    detail = error.detail
    message = ""
    if isinstance(detail, dict):
        message = " ".join(str(value) for value in detail.values() if isinstance(value, str))
    elif detail is not None:
        message = str(detail)

    message = message.lower()
    return (
        error.status_code == 404
        and "tool" in message
        and "support" in message
        and "tool use" in message
    )


def _tool_requires_session_id(tool_name: str) -> bool:
    return tool_name == _SESSION_AWARE_TOOL_NAME or tool_name.endswith(_SESSION_AWARE_TOOL_SUFFIX)


def _contains_non_text_segments(segments: Iterable[dict[str, Any]]) -> bool:
    for segment in segments:
        if not isinstance(segment, dict):
            return True
        if segment.get("type") != "text":
            return True
    return False


def _append_structured_segment(
    segments: list[dict[str, Any]],
    segment: dict[str, Any],
    text_fragments: list[str],
) -> None:
    if not isinstance(segment, dict):
        return

    segment_type = segment.get("type") or "text"
    if segment_type == "text":
        text_value = segment.get("text")
        if not isinstance(text_value, str) or not text_value:
            return
        if segments and isinstance(segments[-1], dict) and segments[-1].get("type") == "text":
            previous = segments[-1].get("text", "")
            segments[-1] = {"type": "text", "text": previous + text_value}
        else:
            segments.append({"type": "text", "text": text_value})
        text_fragments.append(text_value)
    else:
        segments.append(dict(segment))


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


def _finalize_tool_calls(
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    for index, call in enumerate(tool_calls):
        if not isinstance(call, dict):
            continue

        function = call.get("function") or {}
        if not isinstance(function, dict):
            function = {}

        name = function.get("name")
        arguments = function.get("arguments")
        if not (isinstance(name, str) and name.strip()):
            continue
        if not (isinstance(arguments, str) and arguments.strip()):
            continue

        entry = dict(call)
        entry_function = dict(function)
        entry_function["name"] = name
        entry_function["arguments"] = arguments
        entry["function"] = entry_function
        if not entry.get("id"):
            entry["id"] = f"call_{index}"
        finalized.append(entry)

    return finalized


def _extend_reasoning_segments(
    accumulator: list[dict[str, Any]],
    new_segments: Iterable[dict[str, Any]],
    seen: set[tuple[str, str]],
) -> None:
    """Merge new reasoning segments into the accumulator without duplicates."""

    for segment in new_segments:
        if not isinstance(segment, dict):
            continue
        text = segment.get("text")
        if not isinstance(text, str):
            continue
        normalized_text = text.strip()
        if not normalized_text:
            continue
        segment_type = segment.get("type")
        normalized_type = segment_type.strip() if isinstance(segment_type, str) else ""
        key = (normalized_type, normalized_text)
        if key in seen:
            continue
        seen.add(key)
        normalized_segment: dict[str, Any] = {"text": normalized_text}
        if normalized_type:
            normalized_segment["type"] = normalized_type
        accumulator.append(normalized_segment)


def _extract_reasoning_segments(payload: Any) -> list[dict[str, Any]]:
    """Normalize varied reasoning payload formats into labeled text segments."""

    segments: list[dict[str, Any]] = []

    def _walk(node: Any, current_type: str | None = None) -> None:
        if node is None:
            return

        if isinstance(node, str):
            text = node.strip()
            if text:
                segment: dict[str, Any] = {"text": text}
                if current_type:
                    segment["type"] = current_type
                segments.append(segment)
            return

        if isinstance(node, (int, float, bool)):
            text = str(node)
            segment: dict[str, Any] = {"text": text}
            if current_type:
                segment["type"] = current_type
            segments.append(segment)
            return

        if isinstance(node, list):
            for item in node:
                _walk(item, current_type)
            return

        if isinstance(node, dict):
            next_type = node.get("type")
            if isinstance(next_type, str) and next_type.strip():
                normalized_type = next_type.strip()
            else:
                normalized_type = current_type

            extracted = False
            for key in ("text", "output", "content", "reasoning", "message", "details", "explanation"):
                if key not in node:
                    continue
                value = node[key]
                if isinstance(value, (str, list, dict, int, float, bool)):
                    _walk(value, normalized_type)
                    extracted = True

            if not extracted:
                remaining = {
                    key: value
                    for key, value in node.items()
                    if key not in {"type", "id", "index"}
                }
                if remaining:
                    try:
                        serialized = json.dumps(remaining, ensure_ascii=False)
                    except TypeError:
                        serialized = str(remaining)
                    if serialized:
                        segment: dict[str, Any] = {"text": serialized}
                        if normalized_type:
                            segment["type"] = normalized_type
                        segments.append(segment)
            return

        # Fallback for other data types
        text = str(node)
        segment = {"text": text}
        if current_type:
            segment["type"] = current_type
        segments.append(segment)

    _walk(payload)
    return segments


__all__ = ["StreamingHandler", "SseEvent"]
