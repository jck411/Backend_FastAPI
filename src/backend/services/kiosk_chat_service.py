"""Kiosk chat service for OpenRouter LLM integration via ChatOrchestrator."""

import json
import logging
from typing import Any

from backend.chat.orchestrator import ChatOrchestrator
from backend.schemas.chat import ChatCompletionRequest, ChatMessage
from backend.services.kiosk_llm_settings import get_kiosk_llm_settings_service

logger = logging.getLogger(__name__)


class KioskChatService:
    """Chat service for kiosk voice interactions using the main orchestrator."""

    def __init__(self, orchestrator: ChatOrchestrator):
        self._orchestrator = orchestrator
        self._settings_service = get_kiosk_llm_settings_service()

    def clear_history(self, client_id: str):
        """Clear conversation history for a client by clearing session."""
        # The orchestrator manages sessions via repository
        # We'll clear by session_id which is now f"kiosk_{client_id}"
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._orchestrator.clear_session(f"kiosk_{client_id}"))
        except RuntimeError:
            # No running loop - can't clear asynchronously
            pass
        logger.info(f"Cleared conversation history for kiosk_{client_id}")

    async def generate_response(self, user_message: str, client_id: str = "default") -> str:
        """Generate LLM response using the main orchestrator.

        This routes through the same code path as the main frontend,
        ensuring tool execution works correctly.
        """
        settings = self._settings_service.get_settings()
        session_id = f"kiosk_{client_id}"

        logger.info(f"Kiosk LLM request: session={session_id}, model={settings.model}, msg_len={len(user_message)}")

        # Build messages list
        messages = [
            ChatMessage(role="user", content=user_message)
        ]

        # If there's a system prompt in kiosk settings, prepend it
        # Note: The orchestrator may also add its own system prompt from model settings
        # For kiosk, we want to use the kiosk-specific system prompt
        if settings.system_prompt:
            messages.insert(0, ChatMessage(role="system", content=settings.system_prompt))

        # Build the request
        request = ChatCompletionRequest(
            session_id=session_id,
            messages=messages,
            model=settings.model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

        # Process through orchestrator - this handles tools correctly
        full_response = ""

        try:
            async for event in self._orchestrator.process_stream(request):
                event_type = event.get("event")
                data = event.get("data")

                if event_type == "message" and data and data != "[DONE]":
                    try:
                        chunk = json.loads(data)
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            content = delta.get("content")
                            if isinstance(content, str):
                                full_response += content
                    except (json.JSONDecodeError, TypeError):
                        continue

                elif event_type == "tool":
                    # Log tool execution for debugging
                    try:
                        tool_data = json.loads(data) if data else {}
                        status = tool_data.get("status")
                        name = tool_data.get("name")
                        if status == "started":
                            logger.info(f"Tool started: {name}")
                        elif status == "finished":
                            logger.info(f"Tool finished: {name}")
                        elif status == "error":
                            logger.warning(f"Tool error: {name} - {tool_data.get('result')}")
                    except (json.JSONDecodeError, TypeError):
                        pass

        except Exception as e:
            logger.error(f"Kiosk LLM error: {e}", exc_info=True)
            return "I'm sorry, I encountered an error processing your request."

        result = full_response.strip()
        logger.info(f"Kiosk LLM response: {result[:100]}..." if len(result) > 100 else f"Kiosk LLM response: {result}")

        return result if result else "Action completed."


__all__ = ["KioskChatService"]
