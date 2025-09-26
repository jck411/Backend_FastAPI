"""Chat orchestrator coordinating repository, streaming handler, and MCP tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from ..config import Settings
from ..openrouter import OpenRouterClient
from ..services.model_settings import ModelSettingsService
from ..repository import ChatRepository
from ..schemas.chat import ChatCompletionRequest
from .mcp_client import MCPToolClient
from .streaming import SseEvent, StreamingHandler

logger = logging.getLogger(__name__)


class ChatOrchestrator:
    """High-level coordination for chat sessions."""

    def __init__(self, settings: Settings, model_settings: ModelSettingsService):
        src_dir = Path(__file__).resolve().parents[2]
        project_root = src_dir.parent

        db_path = settings.chat_database_path
        if not db_path.is_absolute():
            db_path = project_root / db_path

        env = os.environ.copy()
        pythonpath = env.get("PYTHONPATH", "")
        src_str = str(src_dir)
        if src_str not in pythonpath.split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [pythonpath, src_str]))

        self._repo = ChatRepository(db_path)
        self._client = OpenRouterClient(settings)
        self._mcp_client = MCPToolClient(
            "backend.mcp_server",
            cwd=project_root,
            env=env,
        )
        self._model_settings = model_settings
        self._streaming = StreamingHandler(
            self._client,
            self._repo,
            self._mcp_client,
            default_model=settings.default_model,
            model_settings=model_settings,
        )
        self._settings = settings
        self._init_lock = asyncio.Lock()
        self._ready = asyncio.Event()

    async def initialize(self) -> None:
        """Initialize database and MCP client once."""

        async with self._init_lock:
            if self._ready.is_set():
                return

            await self._repo.initialize()
            await self._mcp_client.connect()
            self._ready.set()
            logger.info("Chat orchestrator ready: %d tool(s) available", len(self._mcp_client.tools))

    async def shutdown(self) -> None:
        """Clean up held resources."""

        await self._mcp_client.close()
        await self._repo.close()
        self._ready.clear()

    async def process_stream(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncGenerator[SseEvent, None]:
        """Process a chat request and yield SSE events."""

        await self._ready.wait()

        if not request.messages:
            raise ValueError("At least one message is required to start a turn")
        incoming_messages = request.messages

        session_id = request.session_id or uuid.uuid4().hex
        existing = await self._repo.session_exists(session_id)
        await self._repo.ensure_session(session_id)

        stored_messages = await self._repo.get_messages(session_id)
        has_system_message = any(msg.get("role") == "system" for msg in stored_messages)
        incoming_has_system = any(message.role == "system" for message in incoming_messages)
        system_prompt = await self._model_settings.get_system_prompt()

        if (
            system_prompt
            and not stored_messages
            and not has_system_message
            and not incoming_has_system
        ):
            await self._repo.add_message(
                session_id,
                role="system",
                content=system_prompt,
            )

        for message in incoming_messages:
            if message.role == "assistant":
                logger.debug(
                    "Ignoring assistant-authored message provided by client for session %s",
                    session_id,
                )
                continue
            content = message.content
            metadata: dict[str, Any] = {}
            if message.name:
                metadata["name"] = message.name
            extra = message.model_dump(exclude={"role", "content", "tool_call_id", "name"}, exclude_none=True)
            if extra:
                metadata.update(extra)
            await self._repo.add_message(
                session_id,
                role=message.role,
                content=content,
                tool_call_id=message.tool_call_id,
                metadata=metadata or None,
            )

        conversation = await self._repo.get_messages(session_id)
        tools_payload = self._mcp_client.get_openai_tools()

        if not existing:
            yield {
                "event": "session",
                "data": json.dumps({"session_id": session_id}),
            }

        async for event in self._streaming.stream_conversation(
            session_id,
            request,
            conversation,
            tools_payload,
        ):
            yield event

    async def clear_session(self, session_id: str) -> None:
        """Remove stored state for a session."""

        await self._repo.clear_session(session_id)

    def get_openrouter_client(self) -> OpenRouterClient:
        """Expose the underlying OpenRouter client."""

        return self._client

__all__ = ["ChatOrchestrator"]
