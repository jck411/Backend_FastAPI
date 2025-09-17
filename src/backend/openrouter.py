"""OpenRouter streaming client utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional

import httpx
from fastapi import status

from .config import Settings
from .schemas.chat import ChatCompletionRequest


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

    def asdict(self) -> Dict[str, Optional[str]]:
        payload: Dict[str, Optional[str]] = {"event": self.event, "data": self.data}
        if self.event_id is not None:
            payload["id"] = self.event_id
        return payload


class OpenRouterClient:
    """Client responsible for streaming chat completions from OpenRouter."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def _headers(self) -> Dict[str, str]:
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
    ) -> AsyncGenerator[Dict[str, Optional[str]], None]:
        """Stream chat completions back as SSE payload dictionaries."""

        payload = request.to_openrouter_payload(self._settings.default_model)
        async for event in self.stream_chat_raw(payload):
            yield event

    async def stream_chat_raw(
        self, payload: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Optional[str]], None]:
        """Low-level streaming helper accepting a prebuilt payload."""

        url = f"{self._base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
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

                    async for event in self._iter_events(response):
                        yield event.asdict()
            except httpx.HTTPError as exc:
                raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    async def list_models(self) -> Dict[str, Any]:
        """Return the raw payload from OpenRouter's `/models` endpoint."""

        url = f"{self._base_url}/models"
        headers = dict(self._headers)
        headers["Accept"] = "application/json"

        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            try:
                response = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def list_providers(self) -> Dict[str, Any]:
        """Return the raw payload from OpenRouter's `/providers` endpoint."""

        url = f"{self._base_url}/providers"
        headers = dict(self._headers)
        headers["Accept"] = "application/json"

        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            try:
                response = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def list_model_endpoints(
        self, model_id: str, *, filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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

        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            try:
                response = await client.get(url, headers=headers, params=filters)
            except httpx.HTTPError as exc:
                raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def get_generation(self, generation_id: str) -> Dict[str, Any]:
        """Fetch detailed information for a completed generation."""

        if not generation_id:
            raise ValueError("generation_id must be provided")

        url = f"{self._base_url}/generation"
        headers = dict(self._headers)
        headers["Accept"] = "application/json"

        params = {"id": generation_id}

        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            try:
                response = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise OpenRouterError(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response.content)
            raise OpenRouterError(response.status_code, detail)

        return response.json()

    async def _iter_events(
        self, response: httpx.Response
    ) -> AsyncGenerator[ServerSentEvent, None]:
        buffer: List[str] = []
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
        data_lines: List[str] = []

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

    def _extract_routing_headers(self, headers: httpx.Headers) -> Dict[str, str]:
        """Return OpenRouter-specific routing headers for debugging/UI metadata."""

        interesting: Dict[str, str] = {}
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
