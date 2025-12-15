"""Lightweight chat service for the kiosk voice assistant.

This service provides a simplified interface for getting LLM responses
from OpenRouter, independent from the main frontend's ChatOrchestrator.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Optional

from ..config import Settings
from ..openrouter import OpenRouterClient, OpenRouterError

logger = logging.getLogger(__name__)


class KioskChatService:
    """Manages conversation history and LLM responses for kiosk sessions.

    This is a simplified alternative to the full ChatOrchestrator,
    designed specifically for voice assistant interactions without
    MCP tools or complex session management.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = OpenRouterClient(settings)
        # In-memory conversation history: session_id -> list of messages
        self._conversations: dict[str, list[dict[str, Any]]] = defaultdict(list)

        # Build system prompt
        system_prompt = settings.openrouter_system_prompt
        if system_prompt:
            self._system_message = {"role": "system", "content": system_prompt}
        else:
            self._system_message = {
                "role": "system",
                "content": "You are a helpful voice assistant. Keep responses concise and natural for spoken conversation."
            }

    async def stream_response(self, session_id: str, user_message: str):
        """Send message to OpenRouter and yield response chunks.

        Args:
            session_id: Unique identifier for the conversation session
            user_message: The user's transcribed speech

        Yields:
            str: Chunks of the assistant's response
        """
        # Add user message to history
        self._conversations[session_id].append({
            "role": "user",
            "content": user_message
        })

        # Build messages for API call
        messages = [self._system_message] + self._conversations[session_id]

        # Create payload for OpenRouter
        payload = {
            "model": self._settings.default_model,
            "messages": messages,
            "stream": True,
        }

        logger.info(f"Kiosk chat request for session {session_id}: {user_message[:50]}...")

        # Collect streamed response for history
        full_response_text = ""

        try:
            async for event in self._client.stream_chat_raw(payload):
                data = event.get("data")
                if data and data != "[DONE]":
                    try:
                        chunk = json.loads(data) if isinstance(data, str) else data
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response_text += content
                                yield content
                    except (json.JSONDecodeError, KeyError, IndexError) as e:
                        logger.debug(f"Skipping malformed chunk: {e}")
                        continue
        except OpenRouterError as e:
            logger.error(f"OpenRouter error for session {session_id}: {e}")
            error_msg = "I'm sorry, I couldn't process that request."
            full_response_text = error_msg
            yield error_msg
        except Exception as e:
            logger.error(f"Unexpected error in kiosk chat for session {session_id}: {e}")
            error_msg = "Something went wrong."
            full_response_text = error_msg
            yield error_msg

        # Add assistant response to history
        if full_response_text:
            self._conversations[session_id].append({
                "role": "assistant",
                "content": full_response_text
            })
            logger.info(f"Kiosk chat response for session {session_id}: {full_response_text[:50]}...")

    def clear_session(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        if session_id in self._conversations:
            del self._conversations[session_id]
            logger.info(f"Cleared kiosk chat session: {session_id}")

    def get_conversation_length(self, session_id: str) -> int:
        """Get the number of messages in a session's history."""
        return len(self._conversations.get(session_id, []))

    async def aclose(self) -> None:
        """Clean up resources."""
        await self._client.aclose()


__all__ = ["KioskChatService"]
