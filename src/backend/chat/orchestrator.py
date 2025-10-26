"""Chat orchestrator coordinating repository, streaming handler, and MCP tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Iterable, Sequence

from dotenv import dotenv_values

from ..config import Settings
from ..openrouter import OpenRouterClient
from ..repository import ChatRepository
from ..schemas.chat import ChatCompletionRequest
from ..services.attachment_urls import refresh_message_attachments
from ..logging_settings import parse_logging_settings
from ..services.conversation_logging import ConversationLogWriter
from ..services.mcp_server_settings import MCPServerSettingsService
from ..services.model_settings import ModelSettingsService
from .image_reflection import reflect_assistant_images
from .mcp_registry import MCPServerConfig, MCPToolAggregator
from .streaming import SseEvent, StreamingHandler

if TYPE_CHECKING:
    from ..services.attachments import AttachmentService

logger = logging.getLogger(__name__)


def _iter_attachment_ids(content: Any) -> Iterable[str]:
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                candidate = metadata.get("attachment_id")
                if isinstance(candidate, str):
                    yield candidate


def _build_mcp_base_env(project_root: Path) -> dict[str, str]:
    """Return the environment passed to launched MCP servers."""

    env = os.environ.copy()
    dotenv_path = project_root / ".env"
    if dotenv_path.exists():
        for key, value in dotenv_values(dotenv_path).items():
            if not key or value is None:
                continue
            env.setdefault(key, value)
    return env


class ChatOrchestrator:
    """High-level coordination for chat sessions."""

    def __init__(
        self,
        settings: Settings,
        model_settings: ModelSettingsService,
        mcp_settings: MCPServerSettingsService,
    ):
        src_dir = Path(__file__).resolve().parents[2]
        project_root = src_dir.parent

        db_path = settings.chat_database_path
        if not db_path.is_absolute():
            db_path = project_root / db_path

        env = _build_mcp_base_env(project_root)
        pythonpath = env.get("PYTHONPATH", "")
        src_str = str(src_dir)
        if src_str not in pythonpath.split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [pythonpath, src_str]))

        self._repo = ChatRepository(db_path)
        self._client = OpenRouterClient(settings)
        self._mcp_client = MCPToolAggregator(
            [],
            base_env=env,
            default_cwd=project_root,
        )
        conversation_log_dir = settings.conversation_log_dir
        if not conversation_log_dir.is_absolute():
            conversation_log_dir = project_root / conversation_log_dir
        logging_settings = parse_logging_settings(project_root / "logging_settings.conf")
        self._conversation_logger = ConversationLogWriter(
            conversation_log_dir,
            min_level=logging_settings.conversations_level,
        )
        self._model_settings = model_settings
        self._mcp_settings = mcp_settings
        self._streaming = StreamingHandler(
            self._client,
            self._repo,
            self._mcp_client,
            default_model=settings.default_model,
            model_settings=model_settings,
            conversation_logger=self._conversation_logger,
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
            configs = await self._mcp_settings.get_configs()
            await self._mcp_client.apply_configs(configs)
            await self._mcp_client.connect()
            self._ready.set()
            logger.info(
                "Chat orchestrator ready: %d tool(s) available",
                len(self._mcp_client.tools),
            )

    async def shutdown(self) -> None:
        """Clean up held resources."""

        try:
            await asyncio.wait_for(self._client.aclose(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Error closing OpenRouter client: %s", exc)

        try:
            await asyncio.wait_for(self._mcp_client.close(), timeout=5.0)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Error closing MCP client: %s", exc)

        try:
            await asyncio.wait_for(self._repo.close(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Error closing repository: %s", exc)

        self._ready.clear()

    async def wait_until_ready(self) -> None:
        """Block until initialization has completed."""

        await self._ready.wait()

    @property
    def repository(self) -> ChatRepository:
        """Expose the underlying repository for shared services."""

        return self._repo

    def set_attachment_service(self, service: "AttachmentService | None") -> None:
        """Inject the attachment service after application startup wiring."""

        self._streaming.set_attachment_service(service)

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

        assistant_parent_message_id: str | None = None
        if isinstance(request.metadata, dict):
            parent_candidate = request.metadata.get("client_parent_message_id")
            if isinstance(parent_candidate, str):
                assistant_parent_message_id = parent_candidate
        stored_messages = await self._repo.get_messages(session_id)
        has_system_message = any(msg.get("role") == "system" for msg in stored_messages)
        incoming_has_system = any(
            message.role == "system" for message in incoming_messages
        )
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
            extra = message.model_dump(
                exclude={
                    "role",
                    "content",
                    "tool_call_id",
                    "name",
                    "client_message_id",
                },
                exclude_none=True,
            )
            if extra:
                metadata.update(extra)
            await self._repo.add_message(
                session_id,
                role=message.role,
                content=content,
                tool_call_id=message.tool_call_id,
                metadata=metadata or None,
                client_message_id=message.client_message_id,
            )
            attachment_ids = list(dict.fromkeys(_iter_attachment_ids(content)))
            if attachment_ids:
                await self._repo.mark_attachments_used(session_id, attachment_ids)

        conversation = await self._repo.get_messages(session_id)
        conversation = await refresh_message_attachments(
            conversation,
            self._repo,
            ttl=self._settings.attachment_signed_url_ttl,
        )
        conversation = reflect_assistant_images(conversation)
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
            assistant_parent_message_id,
        ):
            yield event

    async def clear_session(self, session_id: str) -> None:
        """Remove stored state for a session."""

        await self._repo.clear_session(session_id)

    async def delete_message(self, session_id: str, client_message_id: str) -> bool:
        """Delete a specific message within a session."""

        await self._ready.wait()
        deleted = await self._repo.delete_message(session_id, client_message_id)
        return deleted > 0

    def get_openrouter_client(self) -> OpenRouterClient:
        """Expose the underlying OpenRouter client."""

        return self._client

    async def apply_mcp_configs(self, configs: Sequence[MCPServerConfig]) -> None:
        """Apply MCP configuration updates to the running aggregator."""

        await self._mcp_client.apply_configs(configs)

    def describe_mcp_servers(self) -> list[dict[str, Any]]:
        """Return runtime snapshot of MCP servers."""

        return self._mcp_client.describe_servers()

    async def refresh_mcp_tools(self) -> None:
        """Trigger a manual refresh of tool catalogs."""

        await self._mcp_client.refresh()


__all__ = ["ChatOrchestrator"]
