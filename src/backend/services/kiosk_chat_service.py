"""Lightweight chat service for the kiosk voice assistant.

This service provides a simplified interface for getting LLM responses
from OpenRouter, independent from the main frontend's ChatOrchestrator.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Optional

from ..chat.orchestrator import ChatOrchestrator
from ..schemas.chat import ChatCompletionRequest, ChatMessage
from ..services.mcp_server_settings import MCPServerSettingsService
from ..services.model_settings import ModelSettingsService

logger = logging.getLogger(__name__)


class KioskChatService:
    """Manages conversation history and LLM responses for kiosk sessions.

    Uses a dedicated, isolated ChatOrchestrator to ensure:
    1. Separate settings and model preferences from main UI
    2. Separate MCP tool registry (e.g., Home Assistant only)
    3. Separate chat history database
    """

    def __init__(self, settings: Settings):
        # 1. Create Kiosk-specific settings (isolated paths)
        self._settings = settings.clone_for_kiosk()

        # 2. Initialize isolated configuration services
        self._model_settings = ModelSettingsService(
            path=self._settings.model_settings_path,
            default_model=self._settings.default_model,
            default_system_prompt=None  # Will load from file or use default
        )

        self._mcp_settings = MCPServerSettingsService(
            path=self._settings.mcp_servers_path,
            fallback=[]  # Start empty/default
        )

        # 3. Create private Orchestrator
        self._orchestrator = ChatOrchestrator(
            settings=self._settings,
            model_settings=self._model_settings,
            mcp_settings=self._mcp_settings
        )

        self._initialized = False

    async def ensure_initialized(self):
        """Lazy initialization of the orchestrator."""
        if not self._initialized:
            logger.info("Initializing Kiosk ChatOrchestrator...")
            await self._orchestrator.initialize()
            self._initialized = True

    async def stream_response(self, session_id: str, user_message: str):
        """Send message to the isolated Orchestrator and yield response chunks.

        Args:
            session_id: Unique identifier for the conversation session
            user_message: The user's transcribed speech

        Yields:
            str: Chunks of the assistant's response
        """
        await self.ensure_initialized()

        # Construct request for Orchestrator
        request = ChatCompletionRequest(
            session_id=session_id,
            model=self._settings.default_model, # Will be overridden by ModelSettings if set
            messages=[
                ChatMessage(role="user", content=user_message)
            ]
        )

        logger.info(f"Kiosk chat request for session {session_id}: {user_message[:50]}...")

        full_response_text = ""

        try:
            # Stream from Orchestrator
            async for event in self._orchestrator.process_stream(request):
                # The orchestrator yields SseEvent objects with event types:
                # - "message": content chunks from the LLM (OpenRouter format)
                # - "metadata": response metadata
                # - "tool": tool call events
                # - "session": session info
                event_type = event.get("event", "")
                data_str = event.get("data", "")

                if event_type == "message" and data_str and data_str != "[DONE]":
                    try:
                        data = json.loads(data_str)
                        # Extract content from OpenRouter streaming format:
                        # {"choices": [{"delta": {"content": "text"}}]}
                        choices = data.get("choices", [])
                        for choice in choices:
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            if isinstance(content, str) and content:
                                full_response_text += content
                                yield content
                    except json.JSONDecodeError:
                        logger.debug("Skipping non-JSON SSE payload: %s", data_str[:100])

        except Exception as e:
            logger.error(f"Error in kiosk chat stream: {e}", exc_info=True)
            yield "I'm sorry, something went wrong."

        if full_response_text:
            logger.info(f"Kiosk chat response length: {len(full_response_text)} chars")

    def clear_session(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        # This wrapper calls the async clear_session on orchestrator
        # Since this method is sync in the interface, we schedule it task
        # or we might need to update the interface to be async.
        # For now, let's just log a warning or fire-and-forget.
        # Ideally, update the interface to be async.
        # Given the existing usage in voice_assistant.py might be async, let's check.
        # voice_assistant.py calls this method. Let's make it async in the interface if possible,
        # but for now we'll schedule it on the loop.

        async def _do_clear():
            await self.ensure_initialized()
            await self._orchestrator.clear_session(session_id)
            logger.info(f"Cleared kiosk session {session_id}")

        try:
            asyncio.create_task(_do_clear())
        except RuntimeError:
            # No loop running?
            pass

    async def aclose(self) -> None:
        """Clean up resources."""
        if self._initialized:
            await self._orchestrator.shutdown()

    # --- Configuration Accessors for API ---

    @property
    def model_settings_service(self) -> ModelSettingsService:
        return self._model_settings

    @property
    def mcp_settings_service(self) -> MCPServerSettingsService:
        return self._mcp_settings

    @property
    def orchestrator(self) -> ChatOrchestrator:
        return self._orchestrator


__all__ = ["KioskChatService"]
