"""Streaming handler that coordinates OpenRouter responses and MCP tools."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Iterable, Mapping, Protocol, Sequence
from urllib.parse import unquote_to_bytes

import httpx
from ..config import get_settings
from ..openrouter import OpenRouterClient, OpenRouterError
from ..repository import ChatRepository, format_timestamp_for_client
from ..schemas.chat import ChatCompletionRequest
from ..services.attachments import AttachmentService
from ..services.conversation_logging import ConversationLogWriter
from ..services.model_settings import ModelCapabilities, ModelSettingsService
from .tool_context_planner import ToolContextPlan


class ToolExecutor(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any: ...

    def get_openai_tools(self) -> list[dict[str, Any]]: ...

    def get_openai_tools_for_contexts(
        self, contexts: Iterable[str]
    ) -> list[dict[str, Any]]: ...

    def format_tool_result(self, result: Any) -> str: ...


logger = logging.getLogger(__name__)

SseEvent = dict[str, str | None]

_SESSION_AWARE_TOOL_NAME = "chat_history"
_SESSION_AWARE_TOOL_SUFFIX = "__chat_history"


def _summarize_tool_parameters(parameters: Mapping[str, Any] | None) -> str:
    if not isinstance(parameters, Mapping):
        return "none"

    required_raw = parameters.get("required")
    required: set[str] = set()
    if isinstance(required_raw, Sequence):
        for item in required_raw:
            if isinstance(item, str) and item.strip():
                required.add(item.strip())

    props = parameters.get("properties")
    names: list[str] = []
    if isinstance(props, Mapping):
        for key in props.keys():
            if not isinstance(key, str):
                continue
            normalized = key.strip()
            if not normalized:
                continue
            if normalized in required:
                names.append(f"{normalized}*")
                required.discard(normalized)
            else:
                names.append(normalized)

    if not names and required:
        for item in sorted(required):
            names.append(f"{item}*")

    if not names:
        return "none"

    return ", ".join(names)


def _build_tool_digest_message(
    plan: ToolContextPlan | None,
    tools_payload: Sequence[dict[str, Any]] | None,
    active_contexts: Sequence[str] | None,
) -> dict[str, Any] | None:
    if plan is None or not tools_payload:
        return None

    candidate_map = plan.candidate_tools or {}
    if not candidate_map:
        return None

    tool_names: list[str] = []
    tool_specs: dict[str, Mapping[str, Any]] = {}
    for spec in tools_payload:
        if not isinstance(spec, Mapping):
            continue
        function = spec.get("function")
        if not isinstance(function, Mapping):
            continue
        raw_name = function.get("name")
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        if not name or name in tool_specs:
            continue
        tool_names.append(name)
        tool_specs[name] = function

    if not tool_names:
        return None

    ordered_contexts: list[str] = []
    seen_contexts: set[str] = set()
    if active_contexts:
        for context in active_contexts:
            if not isinstance(context, str):
                continue
            normalized = context.strip().lower()
            if not normalized or normalized in seen_contexts:
                continue
            if normalized in candidate_map:
                ordered_contexts.append(normalized)
                seen_contexts.add(normalized)
    if not ordered_contexts:
        for context in plan.ranked_contexts:
            normalized = context.strip().lower()
            if not normalized or normalized in seen_contexts:
                continue
            if normalized in candidate_map:
                ordered_contexts.append(normalized)
                seen_contexts.add(normalized)
    if not ordered_contexts:
        for context in candidate_map:
            if context not in seen_contexts:
                ordered_contexts.append(context)
                seen_contexts.add(context)

    if not ordered_contexts:
        return None

    candidate_lookup: dict[str, dict[str, Any]] = {}
    for context in ordered_contexts:
        for candidate in candidate_map.get(context, []):
            if isinstance(candidate, Mapping):
                name = candidate.get("name")
                description = candidate.get("description")
                parameters = candidate.get("parameters")
                server = candidate.get("server")
            else:
                name = getattr(candidate, "name", None)
                description = getattr(candidate, "description", None)
                parameters = getattr(candidate, "parameters", None)
                server = getattr(candidate, "server", None)
            if not isinstance(name, str) or not name:
                continue
            if name not in candidate_lookup:
                candidate_lookup[name] = {
                    "description": description,
                    "parameters": parameters,
                    "server": server,
                    "context": context,
                }

    summaries: list[str] = []
    for name in tool_names:
        candidate_info = candidate_lookup.get(name, {})
        description = candidate_info.get("description")
        if not isinstance(description, str) or not description.strip():
            description = None
        else:
            description = " ".join(description.strip().split())
        parameters = candidate_info.get("parameters")
        if not isinstance(parameters, Mapping):
            spec = tool_specs.get(name)
            parameters = spec.get("parameters") if isinstance(spec, Mapping) else None
        description = description or (
            tool_specs.get(name, {}).get("description")
            if isinstance(tool_specs.get(name), Mapping)
            else None
        )
        if not isinstance(description, str) or not description.strip():
            server = candidate_info.get("server")
            if isinstance(server, str) and server.strip():
                description = f"Provided by {server.strip()} server"
            else:
                description = "No description provided"
        params_summary = _summarize_tool_parameters(parameters)
        summaries.append(f"- {name} — {description} (params: {params_summary})")

    if not summaries:
        return None

    header_contexts: list[str] = []
    for context in ordered_contexts:
        if isinstance(context, str) and context:
            header_contexts.append(context)
    if header_contexts:
        header = "Tool digest for contexts: " + ", ".join(header_contexts)
    else:
        header = "Tool digest for active tools"

    message = "\n".join([header, *summaries])
    return {"role": "system", "content": message}


@dataclass
class AssistantTurn:
    content: str | list[dict[str, Any]] | None
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


@dataclass(frozen=True)
class ToolRationaleInfo:
    index: int
    call_id: str
    text: str | None


class _AssistantContentBuilder:
    """Accumulate assistant content fragments and persist generated images."""

    __slots__ = ("_segments", "_created_attachment_ids")

    def __init__(self) -> None:
        self._segments: list[tuple[str, Any]] = []
        self._created_attachment_ids: list[str] = []

    def add_text(self, text: str) -> None:
        if not isinstance(text, str) or not text:
            return

        logger.debug(
            "[IMG-GEN] add_text incoming segment len=%d preview=%r",
            len(text),
            text[:120],
        )

        # Merge consecutive text segments so data URIs split across chunks join correctly.
        if self._segments and self._segments[-1][0] == "text":
            _, previous_value = self._segments.pop()
            if isinstance(previous_value, str):
                logger.debug(
                    "[IMG-GEN] Merging consecutive text segments: prev_len=%d, new_len=%d",
                    len(previous_value),
                    len(text),
                )
                text = previous_value + text
            else:
                self._segments.append(("text", previous_value))

        segments = list(_split_text_and_inline_images(text))
        logger.debug(
            "[IMG-GEN] add_text received %d segments after split", len(segments)
        )
        if not segments:
            return

        if len(segments) == 1 and segments[0][0] == "text":
            text_segment = segments[0][1]
            logger.debug(
                "[IMG-GEN] add_text storing plain text segment len=%d preview=%r",
                len(text_segment),
                text_segment[:120],
            )
            self._segments.append(("text", text_segment))
            return

        for kind, value in segments:
            if kind == "text":
                if value:
                    logger.debug(
                        "[IMG-GEN] Adding text sub-segment len=%d preview=%r",
                        len(value),
                        value[:80],
                    )
                    self._segments.append(("text", value))
            elif kind == "image":
                logger.info(
                    "[IMG-GEN] Detected inline image data URI in text content, length=%d",
                    len(value),
                )
                self._segments.append(
                    (
                        "fragment",
                        {
                            "type": "image_url",
                            "image_url": {"url": value.strip()},
                        },
                    )
                )

    def add_structured(self, fragments: Sequence[Any]) -> None:
        if not fragments:
            return
        logger.debug(
            "[IMG-GEN] add_structured called with %d fragments", len(fragments)
        )
        for idx, fragment in enumerate(fragments):
            if isinstance(fragment, dict):
                fragment_type = fragment.get("type")
                logger.debug(
                    "[IMG-GEN] Fragment %d: type=%s, keys=%s",
                    idx,
                    fragment_type,
                    list(fragment.keys()),
                )
                self._segments.append(("fragment", fragment))
            elif isinstance(fragment, str):
                logger.debug(
                    "[IMG-GEN] Fragment %d: string with length %d", idx, len(fragment)
                )
                self.add_text(fragment)

    @property
    def created_attachment_ids(self) -> Sequence[str]:
        return tuple(self._created_attachment_ids)

    def register_attachment(self, attachment_id: str) -> None:
        if not attachment_id:
            return
        if attachment_id not in self._created_attachment_ids:
            self._created_attachment_ids.append(attachment_id)

    async def finalize(
        self,
        session_id: str,
        attachment_service: AttachmentService | None,
        http_client: httpx.AsyncClient | None = None,
    ) -> str | list[dict[str, Any]] | None:
        if not self._segments:
            return None

        structured_mode = False
        text_buffer: list[str] = []
        structured_parts: list[dict[str, Any]] = []

        for kind, payload in self._segments:
            if kind == "text":
                if isinstance(payload, str):
                    text_buffer.append(payload)
                continue

            if not isinstance(payload, dict):
                continue

            if text_buffer:
                structured_parts.append({"type": "text", "text": "".join(text_buffer)})
                text_buffer.clear()
            structured_mode = True

            processed, attachment_id = await _process_assistant_fragment(
                payload,
                session_id,
                attachment_service,
                http_client,
            )
            if attachment_id:
                self._created_attachment_ids.append(attachment_id)
            if processed is None:
                continue
            structured_parts.append(processed)

        if not structured_mode:
            return "".join(text_buffer)

        if text_buffer:
            structured_parts.append({"type": "text", "text": "".join(text_buffer)})

        return structured_parts if structured_parts else None


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
        attachment_service: AttachmentService | None = None,
        conversation_logger: ConversationLogWriter | None = None,
    ) -> None:
        self._client = client
        self._repo = repository
        self._tool_client = tool_client
        self._default_model = default_model
        self._tool_hop_limit = tool_hop_limit
        self._model_settings = model_settings
        self._attachment_service = attachment_service
        self._conversation_logger = conversation_logger

    def set_attachment_service(self, service: AttachmentService | None) -> None:
        """Attach or replace the attachment service used for image persistence."""

        self._attachment_service = service

    async def _log_conversation_snapshot(
        self,
        session_id: str,
        request: ChatCompletionRequest,
    ) -> None:
        """Persist the latest conversation state for debugging and replay."""

        if self._conversation_logger is None:
            return

        try:
            conversation = await self._repo.get_messages(session_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Failed to load conversation for session %s: %s", session_id, exc
            )
            return

        try:
            metadata = await self._repo.get_session_metadata(session_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Failed to load session metadata for session %s: %s", session_id, exc
            )
            metadata = None

        request_snapshot = request.model_dump(mode="json", exclude_none=True)
        request_snapshot.pop("session_id", None)

        try:
            await self._conversation_logger.write(
                session_id=session_id,
                session_created_at=(metadata or {}).get("created_at"),
                request_snapshot=request_snapshot,
                conversation=conversation,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Failed to write conversation log for session %s: %s", session_id, exc
            )

    async def stream_conversation(
        self,
        session_id: str,
        request: ChatCompletionRequest,
        conversation: list[dict[str, Any]],
        tools_payload: list[dict[str, Any]],
        assistant_parent_message_id: str | None,
        tool_context_plan: ToolContextPlan | None = None,
    ) -> AsyncGenerator[SseEvent, None]:
        """Yield SSE events while maintaining state and executing tools."""

        hop_count = 0
        conversation_state = list(conversation)
        assistant_client_message_id: str | None = None
        if isinstance(request.metadata, dict):
            candidate = request.metadata.get("client_assistant_message_id")
            if isinstance(candidate, str):
                assistant_client_message_id = candidate
        active_tools_payload = list(tools_payload)
        active_contexts: list[str] | None = None
        if (
            tool_context_plan is not None
            and not tool_context_plan.use_all_tools_for_attempt(0)
        ):
            active_contexts = tool_context_plan.contexts_for_attempt(0)
        stop_reasons = (
            set(tool_context_plan.stop_conditions)
            if tool_context_plan is not None
            else set()
        )
        privacy_note = (
            tool_context_plan.privacy_note if tool_context_plan is not None else None
        )
        if privacy_note:
            privacy_notice: dict[str, Any] = {
                "type": "privacy",
                "message": privacy_note,
                "contexts": list(tool_context_plan.ranked_contexts),
                "intent": tool_context_plan.intent,
            }
            if tool_context_plan.candidate_tools:
                privacy_notice["candidate_tools"] = {
                    context: [candidate.to_dict() for candidate in candidates]
                    for context, candidates in tool_context_plan.candidate_tools.items()
                }
            yield {
                "event": "notice",
                "data": json.dumps(privacy_notice),
            }
        tool_choice_value = request.tool_choice
        requested_tool_choice = (
            tool_choice_value if isinstance(tool_choice_value, str) else None
        )
        base_tools_disabled = requested_tool_choice == "none"
        has_structured_tool_choice = isinstance(tool_choice_value, dict)
        can_retry_without_tools = (
            requested_tool_choice in (None, "auto") and not has_structured_tool_choice
        )

        total_tool_calls = 0

        while True:
            stop_triggered_reason: str | None = None
            tools_available = bool(active_tools_payload)
            tools_disabled = base_tools_disabled or not tools_available
            routing_headers: dict[str, Any] | None = None
            active_model = self._default_model
            overrides: dict[str, Any] = {}
            capability: ModelCapabilities | None = None
            model_supports_tools = True
            if self._model_settings is not None:
                (
                    model_override,
                    overrides,
                ) = await self._model_settings.get_openrouter_overrides()
                if model_override:
                    active_model = model_override
                overrides = dict(overrides) if overrides else {}

            payload = request.to_openrouter_payload(active_model)
            payload_messages = list(conversation_state)
            digest_message = _build_tool_digest_message(
                tool_context_plan, active_tools_payload, active_contexts
            )
            if digest_message is not None:
                payload_messages.append(digest_message)
            payload["messages"] = payload_messages

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

            if self._model_settings is not None:
                if hasattr(self._model_settings, "sanitize_payload_for_model"):
                    capability = await self._model_settings.sanitize_payload_for_model(  # type: ignore[attr-defined]
                        active_model,
                        payload,
                        client=self._client,
                    )
                if capability and capability.supports_tools is not None:
                    model_supports_tools = capability.supports_tools
                else:
                    try:
                        model_supports_tools = await self._model_settings.model_supports_tools(  # type: ignore[misc]
                            client=self._client,  # type: ignore[arg-type]
                        )
                    except TypeError:
                        model_supports_tools = await self._model_settings.model_supports_tools()  # type: ignore[misc]

            if (
                not model_supports_tools
                and tools_available
                and not tools_disabled
            ):
                logger.debug(
                    "Skipping tool payload for session %s because active model does not support tool use",
                    session_id,
                )

            allow_tools = tools_available and not tools_disabled and model_supports_tools
            if allow_tools:
                payload["tools"] = active_tools_payload
                payload.setdefault("tool_choice", request.tool_choice or "auto")
            else:
                payload.pop("tools", None)
                payload.pop("tool_choice", None)

            content_builder = _AssistantContentBuilder()
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

                    chunk_modified = False
                    http_client_cache: httpx.AsyncClient | None = None

                    choices = chunk.get("choices") or []
                    for choice in choices:
                        delta = choice.get("delta") or {}

                        delta_content = delta.get("content")
                        if isinstance(delta_content, str):
                            logger.debug(
                                "[IMG-GEN] delta content str len=%d preview=%r",
                                len(delta_content),
                                delta_content[:120],
                            )
                            content_builder.add_text(delta_content)
                        elif isinstance(delta_content, list):
                            http_client: httpx.AsyncClient | None = None
                            if hasattr(self._client, "_get_http_client"):
                                if http_client_cache is None:
                                    http_client_cache = await self._client._get_http_client()
                                http_client = http_client_cache
                            new_fragments, attachment_ids, mutated = await _normalize_structured_fragments(
                                delta_content,
                                session_id,
                                self._attachment_service,
                                http_client,
                            )
                            if mutated:
                                delta["content"] = new_fragments
                                chunk_modified = True
                            content_builder.add_structured(new_fragments)
                            for attachment_id in attachment_ids:
                                content_builder.register_attachment(attachment_id)

                        delta_images = delta.get("images")
                        if isinstance(delta_images, list) and delta_images:
                            http_client: httpx.AsyncClient | None = None
                            if hasattr(self._client, "_get_http_client"):
                                if http_client_cache is None:
                                    http_client_cache = await self._client._get_http_client()
                                http_client = http_client_cache
                            normalized_images, image_attachment_ids, images_mutated = (
                                await _normalize_structured_fragments(
                                    delta_images,
                                    session_id,
                                    self._attachment_service,
                                    http_client,
                                )
                            )
                            if images_mutated:
                                delta["images"] = normalized_images
                                chunk_modified = True
                            content_builder.add_structured(normalized_images)
                            for attachment_id in image_attachment_ids:
                                content_builder.register_attachment(attachment_id)

                        if tool_deltas := delta.get("tool_calls"):
                            _merge_tool_calls(streamed_tool_calls, tool_deltas)

                        choice_finish = choice.get("finish_reason")
                        if choice_finish:
                            finish_reason = choice_finish

                        if "reasoning" in delta:
                            new_segments = _extract_reasoning_segments(
                                delta["reasoning"]
                            )
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

                    message_payload = chunk.get("message")
                    if isinstance(message_payload, dict):
                        message_content = message_payload.get("content")
                        if message_content is not None:
                            logger.debug(
                                "[IMG-GEN] message payload content type=%s",
                                type(message_content).__name__,
                            )
                        if isinstance(message_content, str):
                            logger.debug(
                                "[IMG-GEN] message content str len=%d preview=%r",
                                len(message_content),
                                message_content[:120],
                            )
                            content_builder.add_text(message_content)
                        elif isinstance(message_content, list):
                            http_client: httpx.AsyncClient | None = None
                            if hasattr(self._client, "_get_http_client"):
                                if http_client_cache is None:
                                    http_client_cache = await self._client._get_http_client()
                                http_client = http_client_cache
                            new_fragments, attachment_ids, mutated = await _normalize_structured_fragments(
                                message_content,
                                session_id,
                                self._attachment_service,
                                http_client,
                            )
                            if mutated:
                                message_payload["content"] = new_fragments
                                chunk_modified = True
                            content_builder.add_structured(new_fragments)
                            for attachment_id in attachment_ids:
                                content_builder.register_attachment(attachment_id)

                        message_images = message_payload.get("images")
                        if isinstance(message_images, list) and message_images:
                            http_client: httpx.AsyncClient | None = None
                            if hasattr(self._client, "_get_http_client"):
                                if http_client_cache is None:
                                    http_client_cache = await self._client._get_http_client()
                                http_client = http_client_cache
                            normalized_images, image_attachment_ids, images_mutated = (
                                await _normalize_structured_fragments(
                                    message_images,
                                    session_id,
                                    self._attachment_service,
                                    http_client,
                                )
                            )
                            if images_mutated:
                                message_payload["images"] = normalized_images
                                chunk_modified = True
                            content_builder.add_structured(normalized_images)
                            for attachment_id in image_attachment_ids:
                                content_builder.register_attachment(attachment_id)

                    if chunk_modified:
                        event["data"] = json.dumps(chunk)

                    yield event
            except OpenRouterError as exc:
                if (
                    allow_tools
                    and can_retry_without_tools
                    and _is_tool_support_error(exc)
                ):
                    logger.info(
                        "Retrying without tools for session %s: %s",
                        session_id,
                        exc.detail,
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
            if streamed_tool_calls:
                fallback_calls: list[dict[str, Any]] = []
                for index, raw_call in enumerate(streamed_tool_calls):
                    if not isinstance(raw_call, dict):
                        continue
                    raw_function = raw_call.get("function")
                    if not isinstance(raw_function, dict):
                        continue
                    name_value = raw_function.get("name")
                    arguments_value = raw_function.get("arguments")
                    if not (isinstance(name_value, str) and name_value.strip()):
                        continue
                    arguments_str = (
                        arguments_value if isinstance(arguments_value, str) else ""
                    )
                    if arguments_str.strip():
                        continue
                    fallback_calls.append(
                        {
                            "id": raw_call.get("id")
                            or f"call_{len(tool_calls) + index}",
                            "type": raw_call.get("type") or "function",
                            "function": {
                                "name": name_value.strip(),
                                "arguments": arguments_str,
                            },
                        }
                    )
                if fallback_calls:
                    tool_calls.extend(fallback_calls)
            assistant_content = await content_builder.finalize(
                session_id,
                self._attachment_service,
                # Reuse the OpenRouter HTTP client pool for image downloads (if available)
                (await self._client._get_http_client())
                if hasattr(self._client, "_get_http_client")
                else None,
            )
            new_attachment_ids = list(content_builder.created_attachment_ids)

            assistant_turn = AssistantTurn(
                content=assistant_content if assistant_content else None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                model=model_name,
                usage=usage_details,
                meta=meta_details,
                generation_id=generation_id,
                reasoning=reasoning_segments if reasoning_segments else None,
            )
            assistant_rationales = _extract_tool_rationale(assistant_turn.content)
            tool_rationales = _pair_tool_rationales(
                assistant_turn.tool_calls,
                assistant_rationales,
                start_index=total_tool_calls + 1,
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
            if assistant_turn.tool_calls:
                metadata["tool_rationales"] = [
                    {
                        "index": info.index,
                        "call_id": info.call_id,
                        "text": info.text,
                    }
                    for info in tool_rationales
                ]

            assistant_result = await self._repo.add_message(
                session_id,
                role="assistant",
                content=assistant_turn.content,
                metadata=metadata or None,
                client_message_id=assistant_client_message_id,
                parent_client_message_id=assistant_parent_message_id,
            )
            if isinstance(assistant_result, tuple):
                assistant_record_id, assistant_created_at = assistant_result
            else:
                assistant_record_id = int(assistant_result)
                assistant_created_at = None
            edt_iso, utc_iso = format_timestamp_for_client(assistant_created_at)
            assistant_turn.created_at = edt_iso or assistant_created_at
            assistant_turn.created_at_utc = utc_iso or assistant_created_at
            conversation_state.append(assistant_turn.to_message_dict())
            if new_attachment_ids:
                await self._repo.mark_attachments_used(session_id, new_attachment_ids)

            metadata_event_payload = {
                "role": "assistant",
                "finish_reason": assistant_turn.finish_reason,
                "model": assistant_turn.model,
                "usage": assistant_turn.usage,
                "routing": routing_headers,
                "meta": assistant_turn.meta,
                "generation_id": assistant_turn.generation_id,
                "reasoning": assistant_turn.reasoning,
                "tool_calls": assistant_turn.tool_calls
                if assistant_turn.tool_calls
                else None,
            }
            if assistant_client_message_id is not None:
                metadata_event_payload["client_message_id"] = (
                    assistant_client_message_id
                )
            metadata_event_payload["message_id"] = assistant_record_id
            if assistant_turn.created_at is not None:
                metadata_event_payload["created_at"] = assistant_turn.created_at
            if assistant_turn.created_at_utc is not None:
                metadata_event_payload["created_at_utc"] = assistant_turn.created_at_utc
            if assistant_turn.tool_calls:
                metadata_event_payload["tool_rationales"] = [
                    {
                        "index": info.index,
                        "call_id": info.call_id,
                        "text": info.text,
                    }
                    for info in tool_rationales
                ]
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

            expand_contexts = False

            missing_rationale_detected = False
            processed_tool_calls = 0

            for call_index, tool_call in enumerate(assistant_turn.tool_calls):
                function = tool_call.get("function") or {}
                tool_name = function.get("name")
                rationale_info = (
                    tool_rationales[call_index]
                    if call_index < len(tool_rationales)
                    else None
                )
                rationale_index = (
                    rationale_info.index
                    if rationale_info is not None
                    else total_tool_calls + call_index + 1
                )
                tool_id = (
                    rationale_info.call_id
                    if rationale_info is not None
                    else tool_call.get("id") or f"call_{call_index}"
                )
                rationale_text = (
                    rationale_info.text if rationale_info is not None else None
                )
                skip_execution = False
                missing_rationale_flag = False

                if not tool_name:
                    warning_text = (
                        "Tool call missing function name; skipping execution."
                    )
                    logger.warning(warning_text)
                    tool_result = await self._repo.add_message(
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
                    if isinstance(tool_result, tuple):
                        tool_record_id, tool_created_at = tool_result
                    else:
                        tool_record_id = int(tool_result)
                        tool_created_at = None
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

                if rationale_text:
                    yield {
                        "event": "notice",
                        "data": json.dumps(
                            {
                                "type": "tool_rationale",
                                "tool": tool_name,
                                "call_id": tool_id,
                                "message": rationale_text,
                                "index": rationale_index,
                            }
                        ),
                    }
                else:
                    missing_rationale_flag = True
                    skip_execution = True
                    missing_message = (
                        "Tool execution paused: provide Rationale "
                        f"{rationale_index} before calling '{tool_name}'."
                    )
                    yield {
                        "event": "notice",
                        "data": json.dumps(
                            {
                                "type": "tool_rationale_missing",
                                "tool": tool_name,
                                "call_id": tool_id,
                                "message": missing_message,
                                "confirmation_required": True,
                                "index": rationale_index,
                            }
                        ),
                    }

                if not skip_execution:
                    yield {
                        "event": "tool",
                        "data": json.dumps(
                            {
                                "status": "started",
                                "name": tool_name,
                                "call_id": tool_id,
                                "rationale": rationale_text,
                                "rationale_index": rationale_index,
                            }
                        ),
                    }

                arguments_raw = function.get("arguments")
                status = "finished"
                result_text = ""
                result_obj: Any | None = None
                missing_arguments = False
                tool_error_flag = False
                if skip_execution:
                    result_text = (
                        "Tool call blocked: missing rationale describing why the tool is"
                        " being used and the expected outcome."
                        f" (expected Rationale {rationale_index})."
                    )
                    status = "error"
                    tool_error_flag = True
                elif not arguments_raw or arguments_raw.strip() == "":
                    result_text = (
                        f"Tool {tool_name} requires arguments but none were provided."
                    )
                    status = "error"
                    missing_arguments = True
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
                                result_obj = await self._tool_client.call_tool(
                                    tool_name, working_arguments
                                )
                                result_text = self._tool_client.format_tool_result(
                                    result_obj
                                )
                                tool_error_flag = getattr(result_obj, "isError", False)
                                status = "error" if tool_error_flag else "finished"
                            except Exception as exc:  # pragma: no cover - MCP errors
                                logger.exception(
                                    "Tool '%s' raised an exception", tool_name
                                )
                                result_text = f"Tool error: {exc}"
                                status = "error"
                                tool_error_flag = True

                tool_metadata = {
                    "tool_name": tool_name,
                    "parent_client_message_id": assistant_client_message_id,
                }
                if rationale_text is not None:
                    tool_metadata["tool_rationale"] = rationale_text
                tool_metadata["tool_rationale_index"] = rationale_index

                tool_record_id, tool_created_at = await self._repo.add_message(
                    session_id,
                    role="tool",
                    content=result_text,
                    tool_call_id=tool_id,
                    metadata=tool_metadata,
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
                            "rationale": rationale_text,
                            "rationale_index": rationale_index,
                        }
                    ),
                }

                notice_reason = (
                    "missing_rationale"
                    if missing_rationale_flag
                    else _classify_tool_followup(
                        status,
                        result_text,
                        tool_error_flag=tool_error_flag,
                        missing_arguments=missing_arguments,
                    )
                )
                if notice_reason is not None:
                    next_contexts: list[str] = []
                    will_use_all_tools = False
                    if tool_context_plan is not None:
                        if notice_reason in {"no_results", "empty_result", "tool_error"}:
                            next_contexts = (
                                tool_context_plan.additional_contexts_for_attempt(hop_count)
                            )
                            will_use_all_tools = (
                                tool_context_plan.use_all_tools_for_attempt(hop_count + 1)
                            )
                    if notice_reason in {"no_results", "empty_result", "tool_error"}:
                        expand_contexts = True
                    notice_payload = {
                        "type": "tool_followup_required",
                        "tool": tool_name or "unknown",
                        "reason": notice_reason,
                        "message": result_text,
                        "attempt": hop_count,
                        "next_contexts": next_contexts,
                        "will_use_all_tools": will_use_all_tools,
                        "confirmation_required": True,
                        "rationale_index": rationale_index,
                    }
                    if rationale_text is not None:
                        notice_payload["rationale"] = rationale_text
                    if (
                        tool_context_plan is not None
                        and notice_reason == "missing_arguments"
                    ):
                        hints = tool_context_plan.argument_hints.get(tool_name or "")
                        if hints:
                            notice_payload["argument_hints"] = list(hints)
                    if (
                        stop_reasons
                        and notice_reason in stop_reasons
                        and stop_triggered_reason is None
                    ):
                        stop_triggered_reason = notice_reason
                        expand_contexts = False
                    yield {
                        "event": "notice",
                        "data": json.dumps(notice_payload),
                    }

                processed_tool_calls += 1

                if missing_rationale_flag:
                    missing_rationale_detected = True
                    break

            total_tool_calls += processed_tool_calls

            if missing_rationale_detected:
                break

            hop_count += 1

            if stop_triggered_reason is not None:
                logger.info(
                    "Stop condition '%s' triggered for session %s",
                    stop_triggered_reason,
                    session_id,
                )
                yield {
                    "event": "notice",
                    "data": json.dumps(
                        {
                            "type": "plan_stop",
                            "reason": stop_triggered_reason,
                            "message": "Tool plan stop condition reached.",
                        }
                    ),
                }
                break

            if (
                tool_context_plan is not None
                and expand_contexts
            ):
                next_contexts = tool_context_plan.contexts_for_attempt(hop_count)
                contexts_changed = False
                if tool_context_plan.use_all_tools_for_attempt(hop_count):
                    if active_contexts is not None:
                        contexts_changed = True
                    active_tools_payload = self._tool_client.get_openai_tools()
                    active_contexts = None
                else:
                    if next_contexts != (active_contexts or []):
                        active_tools_payload = (
                            self._tool_client.get_openai_tools_for_contexts(
                                next_contexts
                            )
                        )
                        active_contexts = next_contexts
                        contexts_changed = True
                if contexts_changed:
                    continue

        if self._conversation_logger is not None:
            await self._log_conversation_snapshot(session_id, request)

        yield {"event": "message", "data": "[DONE]"}


def _looks_like_no_result(result_text: str) -> bool:
    if not isinstance(result_text, str):
        return False
    lowered = result_text.strip().lower()
    if not lowered:
        return False
    phrases = (
        "not found",
        "no results",
        "no result",
        "could not find",
        "can't find",
        "cannot find",
        "wasn't found",
        "nothing found",
        "no matching",
        "no events found",
    )
    return any(phrase in lowered for phrase in phrases)


def _classify_tool_followup(
    status: str,
    result_text: str | None,
    *,
    tool_error_flag: bool,
    missing_arguments: bool,
) -> str | None:
    """Classify tool results that require follow-up guidance for the assistant."""

    text = result_text if isinstance(result_text, str) else ""
    normalized = text.strip().lower()

    if missing_arguments:
        return "missing_arguments"

    if status == "error":
        if _looks_like_no_result(text):
            return "no_results"
        if tool_error_flag or not normalized:
            return "tool_error"
        if "invalid" in normalized and "argument" in normalized:
            return "tool_error"
        return "tool_error"

    if not normalized:
        return "empty_result"

    if _looks_like_no_result(text):
        return "no_results"

    return None


def _is_tool_support_error(error: OpenRouterError) -> bool:
    detail = error.detail
    message = ""
    if isinstance(detail, dict):
        message = " ".join(
            str(value) for value in detail.values() if isinstance(value, str)
        )
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
    return tool_name == _SESSION_AWARE_TOOL_NAME or tool_name.endswith(
        _SESSION_AWARE_TOOL_SUFFIX
    )


_RATIONALE_SENTENCE_PATTERN = re.compile(
    r"Rationale\s+(?P<index>\d+):\s*(?P<body>.+?(?:(?<=\S)[.!?]|$))(?=\s*(?:Rationale\s+\d+:)|\s*$)",
    re.IGNORECASE | re.DOTALL,
)

_RATIONALE_INDEX_PATTERN = re.compile(r"^\s*Rationale\s+(\d+):", re.IGNORECASE)


def _extract_tool_rationale(
    content: str | list[dict[str, Any]] | None,
) -> list[str]:
    """Return ordered rationale sentences extracted from assistant content."""

    segments = list(_iterate_rationale_segments(content))
    rationales: dict[int, str] = {}

    for segment in segments:
        if not isinstance(segment, str):
            continue
        for match in _RATIONALE_SENTENCE_PATTERN.finditer(segment):
            index_raw = match.group("index")
            body_text = match.group("body")
            if not index_raw:
                continue
            try:
                index = int(index_raw)
            except (TypeError, ValueError):
                continue
            sentence = _first_sentence(body_text)
            if not sentence:
                continue
            normalized = f"Rationale {index}: {sentence}"
            rationales.setdefault(index, normalized)

    if rationales:
        return [rationales[key] for key in sorted(rationales)]

    return []


def _match_rationale_index(text: str | None) -> int | None:
    if not isinstance(text, str):
        return None
    match = _RATIONALE_INDEX_PATTERN.match(text.strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _pair_tool_rationales(
    tool_calls: Sequence[dict[str, Any]],
    rationales: Sequence[str],
    *,
    start_index: int = 1,
) -> list[ToolRationaleInfo]:
    if not tool_calls:
        return []

    indexed_rationales: dict[int, str] = {}
    fallback_queue: list[tuple[int | None, str]] = []

    for text in rationales:
        normalized = text.strip()
        if not normalized:
            continue
        index = _match_rationale_index(normalized)
        if index is not None and index not in indexed_rationales:
            indexed_rationales[index] = normalized
            continue
        fallback_queue.append((index, normalized))

    paired: list[ToolRationaleInfo] = []
    for offset, tool_call in enumerate(tool_calls):
        expected_index = start_index + offset
        call_id = tool_call.get("id")
        if not isinstance(call_id, str) or not call_id.strip():
            call_id = f"call_{expected_index - 1}"

        text = indexed_rationales.pop(expected_index, None)
        actual_index = expected_index

        if text is None and fallback_queue:
            fallback_index, fallback_text = fallback_queue.pop(0)
            text = fallback_text
            if fallback_index is not None:
                actual_index = fallback_index

        if text is not None:
            parsed_index = _match_rationale_index(text)
            if parsed_index is not None:
                actual_index = parsed_index

        paired.append(
            ToolRationaleInfo(index=actual_index, call_id=call_id, text=text)
        )

    return paired


def _iterate_rationale_segments(
    content: str | list[dict[str, Any]] | None,
) -> Iterable[str]:
    if isinstance(content, str):
        yield content
        return

    if not isinstance(content, list):
        return

    for fragment in content:
        if isinstance(fragment, str):
            yield fragment
            continue
        if isinstance(fragment, dict):
            for key in ("text", "content", "value"):
                value = fragment.get(key)
                if isinstance(value, str) and value.strip():
                    yield value
                    break


def _first_sentence(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None

    normalized = " ".join(text.strip().split())
    if not normalized:
        return None

    match = re.search(r"(.+?[.!?])(?=\s|$)", normalized)
    if match:
        return match.group(1).strip()
    return normalized


_TEXT_FRAGMENT_TYPES = {"text", "output_text"}


_MIME_EXTENSION_MAP = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/heic": "heic",
    "image/heif": "heif",
}

_INLINE_DATA_URI_PATTERN = re.compile(
    r"data:image/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+",
    re.IGNORECASE,
)


def _split_text_and_inline_images(text: str) -> list[tuple[str, str]]:
    """Split text into tuples of (kind, value) for text and inline images."""

    if not text:
        return []

    segments: list[tuple[str, str]] = []
    cursor = 0
    for match in _INLINE_DATA_URI_PATTERN.finditer(text):
        start, end = match.span()
        if start > cursor:
            segments.append(("text", text[cursor:start]))
        data_uri = match.group(0).strip()
        logger.debug(
            "[IMG-GEN] Inline image data URI match span=(%d,%d) preview=%r",
            start,
            end,
            data_uri[:40],
        )

        if segments and segments[-1][0] == "text":
            prefix_text = segments[-1][1]
            md_match = re.search(r"!\[([^\]]*)\]\($", prefix_text)
            if md_match:
                segments.pop()
                before_prefix = prefix_text[: md_match.start()]
                if before_prefix:
                    segments.append(("text", before_prefix))
                alt_text = md_match.group(1).strip()
                if alt_text:
                    segments.append(("text", f"{alt_text}: "))

        segments.append(("image", data_uri))
        cursor = end

    if cursor < len(text):
        segments.append(("text", text[cursor:]))
    logger.debug(
        "[IMG-GEN] _split_text_and_inline_images produced %d segments", len(segments)
    )

    return segments


async def _process_assistant_fragment(
    fragment: dict[str, Any],
    session_id: str,
    attachment_service: AttachmentService | None,
    http_client: httpx.AsyncClient | None,
) -> tuple[dict[str, Any] | None, str | None]:
    # If already persisted (has attachment metadata), return as-is to avoid duplicates
    meta = fragment.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("attachment_id"), str):
        return _deep_copy_jsonable(fragment), None
    fragment_type = fragment.get("type")
    normalized_type = (
        fragment_type.lower().strip() if isinstance(fragment_type, str) else ""
    )

    logger.debug(
        "[IMG-GEN] _process_assistant_fragment: type=%s, normalized=%s, has_image_url=%s, all_keys=%s",
        fragment_type,
        normalized_type,
        "image_url" in fragment,
        list(fragment.keys()),
    )

    if normalized_type in _TEXT_FRAGMENT_TYPES:
        logger.debug("[IMG-GEN] Detected text fragment type: %s", normalized_type)
        text_value = fragment.get("text")
        if isinstance(text_value, str):
            return {"type": "text", "text": text_value}, None
        return None, None

    fallback_text = fragment.get("text")
    if not normalized_type and isinstance(fallback_text, str):
        return {"type": "text", "text": fallback_text}, None

    has_explicit_image_payload = any(
        key in fragment
        for key in ("image_url", "image", "b64_json", "image_base64", "image_b64")
    )

    if (
        normalized_type in {"image_url", "image"}
        or normalized_type.startswith("image")
        or has_explicit_image_payload
    ):
        logger.info(
            "[IMG-GEN] IMAGE FRAGMENT DETECTED! session=%s, type=%s, has_image_url_key=%s",
            session_id,
            normalized_type,
            "image_url" in fragment,
        )
        processed, attachment_id = await _persist_image_fragment(
            fragment,
            session_id,
            attachment_service,
            http_client,
        )
        logger.info(
            "[IMG-GEN] Image fragment processing complete: attachment_id=%s, processed=%s",
            attachment_id,
            "success" if processed else "failed",
        )
        return processed, attachment_id

    return _deep_copy_jsonable(fragment), None


async def _persist_image_fragment(
    fragment: dict[str, Any],
    session_id: str,
    attachment_service: AttachmentService | None,
    http_client: httpx.AsyncClient | None,
) -> tuple[dict[str, Any] | None, str | None]:
    logger.info("[IMG-GEN] === STARTING IMAGE PERSISTENCE ===")
    logger.debug("[IMG-GEN] Fragment keys: %s", list(fragment.keys()))

    (
        image_payload,
        payload_source,
        data_bytes,
        mime_type,
        filename_hint,
    ) = _extract_image_payload(fragment)

    if image_payload is not None:
        logger.debug(
            "[IMG-GEN] Selected image payload source=%s keys=%s",
            payload_source or "unknown",
            list(image_payload.keys()),
        )

    if data_bytes is None:
        logger.debug(
            "[IMG-GEN] No decodable inline bytes found in fragment (source=%s)",
            payload_source,
        )
        # Attempt remote fetch if a URL is present and allowed
        url_value: str | None = None
        if isinstance(image_payload, dict):
            candidate_url = image_payload.get("url")
            if isinstance(candidate_url, str) and candidate_url.strip():
                url_value = candidate_url.strip()
        if not url_value:
            # Some providers nest the URL one level higher
            candidate_url = fragment.get("url")
            if isinstance(candidate_url, str) and candidate_url.strip():
                url_value = candidate_url.strip()

        if url_value and _is_http_url(url_value):
            settings = get_settings()
            if _is_allowed_host(url_value, settings.image_download_allowed_hosts):
                if http_client is None:
                    logger.warning(
                        "[IMG-GEN] Cannot fetch image URL; no HTTP client available"
                    )
                else:
                    logger.info(
                        "[IMG-GEN] Fetching image from URL: %s (session=%s)",
                        _redact_url(url_value),
                        session_id,
                    )
                    try:
                        fetched_bytes, fetched_mime = await _download_image(
                            http_client,
                            url_value,
                            timeout_seconds=float(
                                settings.image_download_timeout_seconds
                            ),
                            max_bytes=int(settings.image_download_max_bytes),
                        )
                        if fetched_bytes:
                            data_bytes = fetched_bytes
                            # Prefer decoded/guessed mime over fragment hint
                            mime_type = fetched_mime or mime_type
                            logger.info(
                                "[IMG-GEN] ✓ Downloaded %d bytes from provider URL",
                                len(data_bytes),
                            )
                        else:
                            logger.warning(
                                "[IMG-GEN] Failed to download image bytes from URL"
                            )
                    except Exception as exc:  # pragma: no cover - transport issues
                        logger.warning(
                            "[IMG-GEN] Error downloading image from %s: %s",
                            _redact_url(url_value),
                            exc,
                        )
        if data_bytes is None:
            return _deep_copy_jsonable(fragment), None

    if attachment_service is None:
        logger.error(
            "[IMG-GEN] ✗ FAILED: Generated image content received for session %s but no attachment service is configured",
            session_id,
        )
        return _deep_copy_jsonable(fragment), None

    normalized_mime = (mime_type or _sniff_mime_from_bytes(data_bytes) or "image/png").lower()
    filename = filename_hint or _guess_filename_from_mime(normalized_mime)

    logger.info(
        "[IMG-GEN] Preparing to save image: size=%d bytes, mime=%s, filename=%s, session=%s, payload_source=%s",
        len(data_bytes),
        normalized_mime,
        filename,
        session_id,
        payload_source or "unknown",
    )

    try:
        logger.debug("[IMG-GEN] Calling attachment_service.save_model_image_bytes...")
        record = await attachment_service.save_model_image_bytes(
            session_id=session_id,
            data=data_bytes,
            mime_type=normalized_mime,
            filename_hint=filename,
        )
        logger.info(
            "[IMG-GEN] ✓ SUCCESS: Image saved with attachment_id=%s, url=%s",
            record.get("attachment_id"),
            record.get("url"),
        )
    except Exception as e:  # pragma: no cover - defensive persistence handling
        logger.error(
            "[IMG-GEN] ✗ FAILED: Exception while persisting image for session %s: %s",
            session_id,
            str(e),
            exc_info=True,
        )
        return _deep_copy_jsonable(fragment), None

    metadata = _build_attachment_metadata(record)
    original_type = fragment.get("type")
    if isinstance(original_type, str) and original_type:
        metadata.setdefault("source_fragment_type", original_type)
    fragment_payload = {
        "type": "image_url",
        "image_url": {
            "url": record.get("delivery_url") or record.get("signed_url"),
        },
        "metadata": metadata,
    }
    attachment_id = record.get("attachment_id")
    return fragment_payload, attachment_id if isinstance(attachment_id, str) else None


async def _normalize_structured_fragments(
    fragments: Sequence[Any],
    session_id: str,
    attachment_service: AttachmentService | None,
    http_client: httpx.AsyncClient | None,
) -> tuple[list[Any], list[str], bool]:
    """Persist image fragments and return updated fragments, attachment IDs, and mutation flag."""

    normalized: list[Any] = []
    created_ids: list[str] = []
    mutated = False

    for index, fragment in enumerate(fragments):
        if isinstance(fragment, dict):
            processed, attachment_id = await _process_assistant_fragment(
                fragment,
                session_id,
                attachment_service,
                http_client,
            )
            if processed is not None:
                normalized.append(processed)
                if processed is not fragment:
                    mutated = True
            else:
                normalized.append(fragment)
            if attachment_id:
                created_ids.append(attachment_id)
        else:
            normalized.append(fragment)

    return normalized, created_ids, mutated


def _decode_data_uri(value: str) -> tuple[bytes | None, str | None]:
    if not isinstance(value, str) or not value.startswith("data:"):
        return None, None

    header, _, data_part = value.partition(",")
    if not data_part:
        return None, None

    meta = header[5:]
    if ";" in meta:
        mime, *params = meta.split(";")
    else:
        mime, params = meta, []

    mime_type = mime or "application/octet-stream"
    params_lower = {param.lower() for param in params}
    is_base64 = "base64" in params_lower

    if is_base64:
        cleaned = data_part.strip().replace("\n", "").replace("\r", "")
        data_bytes = _safe_b64decode(cleaned)
    else:
        data_bytes = unquote_to_bytes(data_part)

    return data_bytes, mime_type


def _safe_b64decode(value: str) -> bytes | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("\n", "").replace("\r", "")
    padding = len(cleaned) % 4
    if padding:
        cleaned += "=" * (4 - padding)
    try:
        return base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError):
        return None


def _is_http_url(value: str) -> bool:
    return value.lower().startswith("http://") or value.lower().startswith("https://")


def _is_allowed_host(url: str, allowlist: list[str] | None) -> bool:
    """Return True if URL hostname matches the allowlist. Empty allowlist allows all."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except Exception:
        return False
    if not allowlist:
        return True
    for allowed in allowlist:
        candidate = allowed.strip().lower()
        if not candidate:
            continue
        if host == candidate or host.endswith("." + candidate):
            return True
    return False


def _redact_url(url: str) -> str:
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        # Drop query/fragment when logging
        return urlunparse(parsed._replace(query="", fragment=""))
    except Exception:
        return url


async def _download_image(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
) -> tuple[bytes | None, str | None]:
    """Fetch image bytes with size limit and basic content-type checks."""

    timeout = httpx.Timeout(timeout_seconds, connect=10.0)
    headers = {"Accept": "image/*"}
    async with client.stream("GET", url, timeout=timeout, headers=headers) as resp:
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type and not content_type.lower().startswith("image/"):
            # Continue, but we will sniff after download
            logger.debug(
                "[IMG-GEN] Non-image content-type '%s' from %s",
                content_type,
                _redact_url(url),
            )

        chunks: list[bytes] = []
        total = 0
        async for chunk in resp.aiter_bytes():
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(
                    f"Downloaded image exceeds maximum size of {max_bytes} bytes"
                )
            chunks.append(chunk)

        data = b"".join(chunks)
        mime = content_type or _sniff_mime_from_bytes(data)
        if not mime or not mime.lower().startswith("image/"):
            raise ValueError("Fetched content is not a valid image")
        return data, mime


def _sniff_mime_from_bytes(data: bytes) -> str | None:
    """Guess image mime type from magic bytes for common formats."""

    if not data or len(data) < 12:
        return None
    # PNG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    # JPEG
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    # GIF
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    # WEBP: RIFF....WEBP
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    # BMP
    if data.startswith(b"BM"):
        return "image/bmp"
    # HEIC/HEIF (rough check for 'ftypheic'/'ftypheif')
    if b"ftypheic" in data[:64] or b"ftypheif" in data[:64]:
        return "image/heic"
    return None


_IMAGE_DATA_KEYS: tuple[str, ...] = (
    "b64_json",
    "image_base64",
    "image_b64",
    "base64",
    "image_bytes",
    "image_data",
)


def _extract_image_payload(
    fragment: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, bytes | None, str | None, str | None]:
    """Locate and decode inline image bytes within a fragment."""

    candidates: list[tuple[str, dict[str, Any]] | tuple[str, None]] = [
        ("image_url", fragment.get("image_url")),
        ("image", fragment.get("image")),
    ]

    data_field = fragment.get("data")
    if isinstance(data_field, dict):
        candidates.append(("data", data_field))

    candidates.append(("fragment", fragment))

    fragment_mime = _coalesce_str(
        fragment.get("mime_type"),
        fragment.get("mimeType"),
    )
    fragment_filename = _coalesce_str(
        fragment.get("file_name"),
        fragment.get("filename"),
        fragment.get("name"),
    )

    for source, payload in candidates:
        if not isinstance(payload, dict):
            continue

        mime_type = _coalesce_str(
            payload.get("mime_type"),
            payload.get("mimeType"),
            fragment_mime,
        )
        filename_hint = _coalesce_str(
            payload.get("file_name"),
            payload.get("filename"),
            payload.get("name"),
            fragment_filename,
        )

        data_bytes = _decode_payload_bytes(payload)
        if data_bytes is not None:
            return payload, source, data_bytes, mime_type, filename_hint

    return None, "", None, fragment_mime, fragment_filename


def _decode_payload_bytes(payload: dict[str, Any], *, _depth: int = 0) -> bytes | None:
    """Attempt to decode inline bytes from a payload mapping.

    Uses a conservative recursion depth limit to avoid pathological inputs.
    """

    if _depth > 5:
        logger.debug("[IMG-GEN] Max decode depth reached; aborting nested decode")
        return None

    for key in _IMAGE_DATA_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate:
            logger.debug(
                "[IMG-GEN] Attempting base64 decode from key=%s (length=%d)",
                key,
                len(candidate),
            )
            decoded = _safe_b64decode(candidate)
            if decoded is not None:
                logger.info(
                    "[IMG-GEN] ✓ Successfully decoded base64 field '%s': %d bytes",
                    key,
                    len(decoded),
                )
                return decoded
            logger.debug("[IMG-GEN] Failed to decode base64 from key=%s", key)

    data_field = payload.get("data")
    if isinstance(data_field, dict):
        nested = _decode_payload_bytes(data_field, _depth=_depth + 1)
        if nested is not None:
            return nested
    elif isinstance(data_field, str) and data_field:
        logger.debug(
            "[IMG-GEN] Attempting to decode data field string (length=%d)",
            len(data_field),
        )
        decoded, _ = _decode_data_uri(data_field)
        if decoded is not None:
            return decoded
        inline = _safe_b64decode(data_field)
        if inline is not None:
            logger.info(
                "[IMG-GEN] ✓ Successfully decoded inline base64 from data field: %d bytes",
                len(inline),
            )
            return inline

    url_value = payload.get("url")
    if isinstance(url_value, str) and url_value:
        logger.debug(
            "[IMG-GEN] Attempting to decode url field (length=%d)",
            len(url_value),
        )
        data_bytes, _ = _decode_data_uri(url_value)
        if data_bytes is not None:
            return data_bytes
        inline = _safe_b64decode(url_value)
        if inline is not None:
            logger.info(
                "[IMG-GEN] ✓ Successfully decoded inline base64 from url: %d bytes",
                len(inline),
            )
            return inline

    return None


def _coalesce_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
    return None


def _guess_filename_from_mime(mime_type: str) -> str:
    extension = _MIME_EXTENSION_MAP.get(mime_type.lower())
    if not extension:
        return "generated.bin"
    return f"image.{extension}"


def _build_attachment_metadata(record: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "attachment_id": record.get("attachment_id"),
        "display_url": record.get("display_url") or record.get("signed_url"),
        "delivery_url": record.get("delivery_url") or record.get("signed_url"),
        "mime_type": record.get("mime_type"),
        "size_bytes": record.get("size_bytes"),
        "session_id": record.get("session_id"),
        "uploaded_at": record.get("created_at"),
        "expires_at": record.get("expires_at"),
        "signed_url_expires_at": record.get("signed_url_expires_at"),
    }

    extra_metadata = record.get("metadata")
    if isinstance(extra_metadata, dict):
        filename = extra_metadata.get("filename")
        if isinstance(filename, str):
            metadata["filename"] = filename

    # Remove keys with None values for cleaner payloads
    return {key: value for key, value in metadata.items() if value is not None}


def _deep_copy_jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(payload))
    except (TypeError, ValueError):
        return dict(payload)


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
        if function_name := function_delta.get("name"):
            entry.setdefault("function", {"name": None, "arguments": ""})
            entry["function"]["name"] = function_name
        if arguments_fragment := function_delta.get("arguments"):
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
            for key in (
                "text",
                "output",
                "content",
                "reasoning",
                "message",
                "details",
                "explanation",
            ):
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
