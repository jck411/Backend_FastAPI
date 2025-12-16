"""Kiosk chat service for OpenRouter LLM integration."""

import logging
from typing import Any

from backend.openrouter import OpenRouterClient
from backend.services.kiosk_llm_settings import get_kiosk_llm_settings_service

logger = logging.getLogger(__name__)


import httpx

class KioskChatService:
    """Simple chat service for kiosk voice interactions."""

    def __init__(self, openrouter_client: OpenRouterClient):
        # We keep the client reference only to get configuration
        self._config = openrouter_client._settings
        self._settings_service = get_kiosk_llm_settings_service()
        self._histories: dict[str, list[dict[str, Any]]] = {}

    def clear_history(self, client_id: str):
        """Clear conversation history for a client."""
        if client_id in self._histories:
            del self._histories[client_id]
            logger.info(f"Cleared conversation history for {client_id}")

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.openrouter_api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self._config.openrouter_app_url:
            referer = str(self._config.openrouter_app_url)
            headers["HTTP-Referer"] = referer
            headers["Referer"] = referer
        if self._config.openrouter_app_name:
            headers["X-Title"] = self._config.openrouter_app_name
        return headers

    async def generate_response(self, user_message: str, client_id: str = "default") -> str:
        """Generate LLM response for user's voice input.

        Uses a fresh HTTP client for every request to ensure stability and avoid
        connection pooling issues in the long-running process.
        """
        settings = self._settings_service.get_settings()

        # Initialize history if new
        if client_id not in self._histories:
            self._histories[client_id] = []

        history = self._histories[client_id]

        messages: list[dict[str, Any]] = []
        if settings.system_prompt:
            messages.append({"role": "system", "content": settings.system_prompt})

        # Add history
        messages.extend(history)

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": settings.model,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
            "stream": True,
        }

        # Use fresh client for every request
        base_url = str(self._config.openrouter_base_url).rstrip("/")
        url = f"{base_url}/chat/completions"

        logger.info(f"Kiosk LLM request: model={settings.model}, user_msg={user_message[:50]}...")
        logger.debug(f"Full payload: {payload}")

        full_response = ""

        try:
            # Short timeout for connect, generous for read (LLM generation)
            timeout = httpx.Timeout(60.0, connect=10.0)

            async with httpx.AsyncClient(timeout=timeout, http2=True) as client:
                logger.debug("Starting direct OpenRouter stream...")
                async with client.stream(
                    "POST",
                    url,
                    headers=self._get_headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        error_text = await response.aread()
                        logger.error(f"OpenRouter API error: {response.status_code} - {error_text}")
                        return "I'm sorry, I'm having trouble connecting to the AI service."

                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue

                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break

                            try:
                                import json
                                chunk = json.loads(data)
                                choices = chunk.get("choices") or []
                                for choice in choices:
                                    delta = choice.get("delta") or {}
                                    content = delta.get("content")
                                    if isinstance(content, str):
                                        full_response += content
                            except Exception:
                                continue

            logger.info(f"Stream complete. Total length: {len(full_response)}")

        except Exception as e:
            logger.error(f"Kiosk LLM error: {e}", exc_info=True)
            raise

        response_text = full_response.strip()
        logger.info(f"Kiosk LLM final response: {response_text[:100]}...")

        if response_text:
            # Update history
            history = self._histories[client_id]
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": response_text})
            # Keep only last 10 turns (20 messages)
            if len(history) > 20:
                self._histories[client_id] = history[-20:]

        return response_text if response_text else "I'm sorry, I couldn't generate a response."


__all__ = ["KioskChatService"]
