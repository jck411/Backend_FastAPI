"""Streaming handler that coordinates OpenRouter responses and MCP tools."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Iterable, Protocol, Sequence
from urllib.parse import unquote_to_bytes

from ..openrouter import OpenRouterClient, OpenRouterError
from ..repository import ChatRepository, format_timestamp_for_client
from ..schemas.chat import ChatCompletionRequest
from ..services.attachments import AttachmentService
from ..services.model_settings import ModelSettingsService


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

    async def finalize(
        self,
        session_id: str,
        attachment_service: AttachmentService | None,
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
    ) -> None:
        self._client = client
        self._repo = repository
        self._tool_client = tool_client
        self._default_model = default_model
        self._tool_hop_limit = tool_hop_limit
        self._model_settings = model_settings
        self._attachment_service = attachment_service

    def set_attachment_service(self, service: AttachmentService | None) -> None:
        """Attach or replace the attachment service used for image persistence."""

        self._attachment_service = service

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
                (
                    model_override,
                    overrides,
                ) = await self._model_settings.get_openrouter_overrides()
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
                            content_builder.add_structured(delta_content)

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
                            content_builder.add_structured(message_content)

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
            assistant_content = await content_builder.finalize(
                session_id,
                self._attachment_service,
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
                                result_text = self._tool_client.format_tool_result(
                                    result
                                )
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


_TEXT_FRAGMENT_TYPES = {"text", "output_text"}


_MIME_EXTENSION_MAP = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
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
) -> tuple[dict[str, Any] | None, str | None]:
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

    if normalized_type in {"image_url", "image"} or "image_url" in fragment:
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
) -> tuple[dict[str, Any] | None, str | None]:
    logger.info("[IMG-GEN] === STARTING IMAGE PERSISTENCE ===")
    logger.debug("[IMG-GEN] Fragment keys: %s", list(fragment.keys()))

    image_payload = fragment.get("image_url")
    logger.debug(
        "[IMG-GEN] image_payload type: %s, is_dict: %s",
        type(image_payload).__name__,
        isinstance(image_payload, dict),
    )

    if not isinstance(image_payload, dict):
        logger.warning(
            "[IMG-GEN] image_payload is not a dict, returning fragment as-is"
        )
        return _deep_copy_jsonable(fragment), None

    data_bytes: bytes | None = None
    mime_type: str | None = image_payload.get("mime_type")
    filename_hint = image_payload.get("file_name") or image_payload.get("filename")

    logger.debug(
        "[IMG-GEN] Image payload structure: keys=%s, mime_type=%s, filename_hint=%s",
        list(image_payload.keys()),
        mime_type,
        filename_hint,
    )

    b64_value = image_payload.get("b64_json")
    logger.debug(
        "[IMG-GEN] b64_json field: exists=%s, type=%s",
        b64_value is not None,
        type(b64_value).__name__ if b64_value else "None",
    )
    if isinstance(b64_value, str) and b64_value:
        data_bytes = _safe_b64decode(b64_value)
        if data_bytes is None:
            logger.debug("Failed to decode image payload b64_json")

    if data_bytes is None:
        url_value = image_payload.get("url")
        logger.debug(
            "[IMG-GEN] url field: exists=%s, type=%s",
            url_value is not None,
            type(url_value).__name__ if url_value else "None",
        )
        if isinstance(url_value, str) and url_value:
            logger.debug(
                "[IMG-GEN] Attempting to decode url field (length: %d, starts_with: %s)",
                len(url_value),
                url_value[:50],
            )
            data_bytes, derived_mime = _decode_data_uri(url_value)
            if data_bytes is None:
                logger.debug(
                    "[IMG-GEN] url is not a data URI, trying direct base64 decode"
                )
                decoded_inline = _safe_b64decode(url_value)
                if decoded_inline is not None:
                    logger.info(
                        "[IMG-GEN] ✓ Successfully decoded url as inline base64: %d bytes",
                        len(decoded_inline),
                    )
                    data_bytes = decoded_inline
                else:
                    logger.warning("[IMG-GEN] Failed to decode url as base64")
            else:
                logger.info(
                    "[IMG-GEN] ✓ Successfully decoded data URI: %d bytes, mime=%s",
                    len(data_bytes),
                    derived_mime,
                )
            if data_bytes is not None and not mime_type:
                mime_type = derived_mime

    if data_bytes is None:
        return _deep_copy_jsonable(fragment), None

    if attachment_service is None:
        logger.error(
            "[IMG-GEN] ✗ FAILED: Generated image content received for session %s but no attachment service is configured",
            session_id,
        )
        return _deep_copy_jsonable(fragment), None

    normalized_mime = (mime_type or "image/png").lower()
    filename = filename_hint or _guess_filename_from_mime(normalized_mime)

    logger.info(
        "[IMG-GEN] Preparing to save image: size=%d bytes, mime=%s, filename=%s, session=%s",
        len(data_bytes),
        normalized_mime,
        filename,
        session_id,
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
    fragment_payload = {
        "type": "image_url",
        "image_url": {
            "url": record.get("delivery_url") or record.get("signed_url"),
        },
        "metadata": metadata,
    }
    attachment_id = record.get("attachment_id")
    return fragment_payload, attachment_id if isinstance(attachment_id, str) else None


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
