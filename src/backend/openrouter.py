"""OpenRouter streaming client utilities."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Iterable, Mapping, Optional, Sequence

import httpx
from fastapi import status

from .config import Settings
from .schemas.chat import ChatCompletionRequest

logger = logging.getLogger(__name__)


class OpenRouterError(Exception):
    """Wrap transport or API failures when communicating with OpenRouter."""

    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


@dataclass
class ServerSentEvent:
    """Represents a parsed Server-Sent Event."""

    data: str
    event: str = "message"
    event_id: Optional[str] = None

    def asdict(self) -> dict[str, Optional[str]]:
        payload: dict[str, Optional[str]] = {"event": self.event, "data": self.data}
        if self.event_id is not None:
            payload["id"] = self.event_id
        return payload


class OpenRouterClient:
    """Client responsible for streaming chat completions from OpenRouter."""

    _client_lock: asyncio.Lock = asyncio.Lock()
    _client_pool: dict[tuple[str, float], httpx.AsyncClient] = {}

    def __init__(self, settings: Settings):
        self._settings = settings

    def _client_key(self) -> tuple[str, float]:
        return (self._base_url, float(self._settings.request_timeout))

    async def _get_http_client(self) -> httpx.AsyncClient:
        key = self._client_key()
        client = self.__class__._client_pool.get(key)
        if client is not None:
            return client

        async with self.__class__._client_lock:
            client = self.__class__._client_pool.get(key)
            if client is None:
                timeout = httpx.Timeout(self._settings.request_timeout, connect=10.0)
                limits = httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                )
                client = httpx.AsyncClient(
                    timeout=timeout,
                    limits=limits,
                    http2=True,
                )
                self.__class__._client_pool[key] = client
        return client

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self._settings.openrouter_app_url:
            referer = str(self._settings.openrouter_app_url)
            headers["HTTP-Referer"] = referer
            headers["Referer"] = referer
        if self._settings.openrouter_app_name:
            headers["X-Title"] = self._settings.openrouter_app_name
        return headers

    @property
    def _base_url(self) -> str:
        """Return the OpenRouter API base URL without a trailing slash."""

        return str(self._settings.openrouter_base_url).rstrip("/")

    async def stream_chat(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[dict[str, Optional[str]], None]:
        """Stream chat completions back as SSE payload dictionaries."""

        payload = request.to_openrouter_payload(self._settings.default_model)
        async for event in self.stream_chat_raw(payload):
            yield event

    async def request_tool_plan(
        self,
        *,
        request: ChatCompletionRequest,
        conversation: Sequence[dict[str, Any]] | Iterable[dict[str, Any]],
        tool_digest: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Request a planning pass ahead of streaming."""

        payload = self._build_planner_payload(request, conversation, tool_digest)

        client = await self._get_http_client()
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=self._planner_headers(),
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        try:
            body = response.json()
        except ValueError as exc:  # pragma: no cover - unexpected payload
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        planner_text = self._extract_planner_text(body)
        try:
            return json.loads(planner_text)
        except json.JSONDecodeError as exc:
            detail = (
                "Failed to parse planner response as JSON: "
                f"{exc.msg} at line {exc.lineno} column {exc.colno}"
            )
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, detail) from exc

    def _planner_headers(self) -> dict[str, str]:
        headers = dict(self._headers)
        headers["Accept"] = "application/json"
        return headers

    def _build_planner_payload(
        self,
        request: ChatCompletionRequest,
        conversation: Sequence[dict[str, Any]] | Iterable[dict[str, Any]],
        tool_digest: Mapping[str, Any],
    ) -> dict[str, Any]:
        system_prompt = """
You are a planning specialist that prepares tool usage strategies for another chat assistant.
Review the conversation, user request metadata, and available tool contexts.
Return a strict JSON object describing the plan. The JSON must either be the plan itself
or contain a top-level "plan" object. The plan supports these keys:
- intent: short string summarizing the user's objective.
- stages: list of ordered stage arrays. Each stage is a list of context names drawn from the provided digest.
- ranked_contexts: list of context names ranked from most to least relevant.
- broad_search: boolean indicating whether all tools should be available when the assistant runs out of staged contexts.
- candidate_tools: mapping of context name to an array of tools. Each tool comes from the digest and can include name, description, parameters, server, and score.
- argument_hints: mapping of tool name to a list of argument suggestions (strings).
- privacy_note: optional short string with any privacy-related callouts.
- stop_conditions: list of strings explaining when the assistant should stop invoking tools.

CRITICAL PLANNING GUIDELINES:
1. Plan for COMPLETE workflows, not just prerequisites. Authentication/status checks are steps toward the user's goal, not endpoints.
2. When the user asks to read/view/get data (e.g., "what's on my calendar", "show my emails"), include BOTH prerequisite tools (auth checks) AND data-fetching tools (get_events, list_emails).
3. Use stages to sequence dependent operations, but ensure all necessary tools are available across stages.
4. Don't set stop_conditions for normal tool responses. Only use them for actual stopping scenarios (e.g., privacy blocks, explicit user cancellation).
5. Set broad_search=true if the query might need tools beyond what you explicitly staged.

Example: For "what's on my calendar today?":
- Include calendar_auth_status AND calendar_get_events in candidate_tools
- Stage 1: calendar context (for both auth and events)
- Don't stop after auth check - the user wants actual calendar data

Do not invent tools or contexts that are absent from the digest. Respond with JSON only, without markdown fences or commentary.
""".strip()

        def _safe_json(data: Any) -> str:
            return json.dumps(data, ensure_ascii=False, indent=2, default=repr)

        request_summary = request.model_dump(
            by_alias=True,
            exclude_none=True,
            exclude={
                "messages",
                "tools",
                "session_id",
                "plugins",
                "metadata",
                "usage",
            },
        )
        request_summary.setdefault(
            "model", request.model or self._settings.default_model
        )

        analysis_payload = {
            "request": request_summary,
            "conversation": list(conversation),
            "tool_digest": dict(tool_digest),
        }

        return {
            "model": request.model or self._settings.default_model,
            "stream": False,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        "Analyze the provided data and respond with the planning JSON.\n\n"
                        + _safe_json(analysis_payload)
                    ),
                },
            ],
        }

    @staticmethod
    def _extract_planner_text(payload: Mapping[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, Sequence) or not choices:
            raise OpenRouterError(
                status.HTTP_502_BAD_GATEWAY, "Planner response missing choices"
            )
        message_container = choices[0]
        if not isinstance(message_container, Mapping):
            raise OpenRouterError(
                status.HTTP_502_BAD_GATEWAY, "Planner response missing message"
            )
        message = message_container.get("message")
        if not isinstance(message, Mapping):
            raise OpenRouterError(
                status.HTTP_502_BAD_GATEWAY, "Planner response missing message"
            )
        content = message.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, Sequence):
            fragments: list[str] = []
            for item in content:
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    fragments.append(item["text"])
            text = "".join(fragments).strip()
        else:
            text = ""
        if not text:
            raise OpenRouterError(
                status.HTTP_502_BAD_GATEWAY, "Planner response missing content"
            )
        return text

    async def stream_chat_raw(
        self, payload: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Optional[str]], None]:
        """Low-level streaming helper accepting a prebuilt payload."""

        url = f"{self._base_url}/chat/completions"

        client = await self._get_http_client()
        try:
            async with client.stream(
                "POST",
                url,
                headers=self._headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = self._extract_error_detail(body)
                    raise OpenRouterError(response.status_code, detail)

                routing_headers = self._extract_routing_headers(response.headers)
                if routing_headers:
                    yield {
                        "event": "openrouter_headers",
                        "data": json.dumps(routing_headers),
                    }

                logger.debug("[IMG-GEN] Starting to read OpenRouter SSE stream")
                async for event in self._iter_events(response):
                    # Log if event contains structured content
                    if event.data and event.data != "[DONE]":
                        try:
                            chunk = json.loads(event.data)
                            if "choices" in chunk and chunk["choices"]:
                                choice = chunk["choices"][0]
                                delta = choice.get("delta", {})
                                if "content" in delta:
                                    content = delta["content"]
                                    if isinstance(content, list):
                                        logger.debug(
                                            "[IMG-GEN] OpenRouter delta with structured content array: %d items",
                                            len(content),
                                        )
                                        for i, item in enumerate(content):
                                            if isinstance(item, dict):
                                                logger.debug(
                                                    "[IMG-GEN]   Content item %d: type=%s, keys=%s",
                                                    i,
                                                    item.get("type"),
                                                    list(item.keys()),
                                                )
                                    elif isinstance(content, str) and len(content) > 0:
                                        logger.debug(
                                            "[IMG-GEN] OpenRouter delta with text content: %d chars",
                                            len(content),
                                        )
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass  # Skip logging errors for non-standard chunks
                    yield event.asdict()
        except httpx.HTTPError as exc:
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    async def list_models(
        self, *, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Return the raw payload from OpenRouter's `/models` endpoint."""

        url = f"{self._base_url}/models"
        headers = dict(self._headers)
        headers["Accept"] = "application/json"

        client = await self._get_http_client()
        try:
            response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def list_providers(self) -> dict[str, Any]:
        """Return the raw payload from OpenRouter's `/providers` endpoint."""

        url = f"{self._base_url}/providers"
        headers = dict(self._headers)
        headers["Accept"] = "application/json"

        client = await self._get_http_client()
        try:
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def list_model_endpoints(
        self, model_id: str, *, filters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Return the raw payload from OpenRouter's model endpoints endpoint."""

        # Parse model_id to extract author and slug
        if "/" not in model_id:
            raise ValueError(
                f"Invalid model_id format: {model_id}. Expected 'author/slug'."
            )

        author, slug = model_id.split("/", 1)
        url = f"{self._base_url}/models/{author}/{slug}/endpoints"
        headers = dict(self._headers)
        headers["Accept"] = "application/json"

        client = await self._get_http_client()
        try:
            response = await client.get(url, headers=headers, params=filters)
        except httpx.HTTPError as exc:
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def get_generation(self, generation_id: str) -> dict[str, Any]:
        """Fetch detailed information for a completed generation."""

        if not generation_id:
            raise ValueError("generation_id must be provided")

        url = f"{self._base_url}/generation"
        headers = dict(self._headers)
        headers["Accept"] = "application/json"

        params = {"id": generation_id}

        client = await self._get_http_client()
        try:
            response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def aclose(self) -> None:
        await self.__class__.aclose_shared()

    @classmethod
    async def aclose_shared(cls) -> None:
        async with cls._client_lock:
            clients = list(cls._client_pool.values())
            cls._client_pool.clear()
        for client in clients:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    async def _iter_events(
        self, response: httpx.Response
    ) -> AsyncGenerator[ServerSentEvent, None]:
        buffer: list[str] = []
        async for line in response.aiter_lines():
            if not line:
                if buffer:
                    yield self._parse_event(buffer)
                    buffer.clear()
                continue
            if line.startswith(":"):
                continue
            buffer.append(line)
        if buffer:
            yield self._parse_event(buffer)

    def _parse_event(self, lines: Iterable[str]) -> ServerSentEvent:
        event_name: Optional[str] = None
        event_id: Optional[str] = None
        data_lines: list[str] = []

        for line in lines:
            field, _, value = line.partition(":")
            value = value.lstrip(" ")
            if field == "event":
                event_name = value or None
            elif field == "data":
                data_lines.append(value)
            elif field == "id":
                event_id = value or None

        data = "\n".join(data_lines)
        return ServerSentEvent(
            data=data, event=event_name or "message", event_id=event_id
        )

    def _extract_routing_headers(self, headers: httpx.Headers) -> dict[str, str]:
        """Return OpenRouter-specific routing headers for debugging/UI metadata."""

        interesting: dict[str, str] = {}
        for key, value in headers.items():
            normalized = key.lower()
            if normalized.startswith("openrouter-") or normalized in {
                "x-request-id",
                "via",
            }:
                interesting[key] = value
        return interesting

    @staticmethod
    def _extract_error_detail(raw: bytes) -> Any:
        if not raw:
            return "OpenRouter returned an empty error response."
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="ignore")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(payload, dict):
            return payload.get("error") or payload
        return payload


__all__ = ["OpenRouterClient", "OpenRouterError", "ServerSentEvent"]
