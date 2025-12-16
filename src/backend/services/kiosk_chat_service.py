"""Kiosk chat service for OpenRouter LLM integration."""

import logging
from typing import Any

from backend.openrouter import OpenRouterClient
from backend.services.kiosk_llm_settings import get_kiosk_llm_settings_service

logger = logging.getLogger(__name__)


class KioskChatService:
    """Simple chat service for kiosk voice interactions."""

    def __init__(self, openrouter_client: OpenRouterClient):
        self._client = openrouter_client
        self._settings_service = get_kiosk_llm_settings_service()

    async def generate_response(self, user_message: str) -> str:
        """Generate LLM response for user's voice input.

        Args:
            user_message: The transcribed user speech

        Returns:
            The assistant's text response
        """
        settings = self._settings_service.get_settings()

        messages: list[dict[str, Any]] = []
        if settings.system_prompt:
            messages.append({"role": "system", "content": settings.system_prompt})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": settings.model,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
            "stream": True,  # OpenRouter client streams by default
        }

        logger.info(f"Kiosk LLM request: model={settings.model}, user_msg={user_message[:50]}...")

        # Collect streamed response
        full_response = ""
        try:
            async for event in self._client.stream_chat_raw(payload):
                data = event.get("data")
                if not data or data == "[DONE]":
                    continue

                import json
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices") or []
                for choice in choices:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str):
                        full_response += content

        except Exception as e:
            logger.error(f"Kiosk LLM error: {e}")
            raise

        logger.info(f"Kiosk LLM response: {full_response[:100]}...")
        return full_response.strip() if full_response else "I'm sorry, I couldn't generate a response."


__all__ = ["KioskChatService"]
