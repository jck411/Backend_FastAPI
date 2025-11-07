"""Chat orchestrator coordinating repository, streaming handler, and MCP tools."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import uuid
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Callable,
    Iterable,
    Sequence,
    cast,
)

from dotenv import dotenv_values

from ..logging_settings import parse_logging_settings
from ..openrouter import OpenRouterClient
from ..repository import ChatRepository
from ..schemas.chat import ChatCompletionRequest
from ..services.attachment_urls import refresh_message_attachments
from ..services.conversation_logging import ConversationLogWriter
from ..services.mcp_server_settings import MCPServerSettingsService
from ..services.model_settings import ModelSettingsService
from ..services.time_context import create_time_snapshot
from .image_reflection import reflect_assistant_images
from .llm_planner import LLMContextPlanner
from .mcp_registry import MCPServerConfig, MCPToolAggregator
from .streaming import SseEvent, StreamingHandler

if TYPE_CHECKING:
    from ..config import Settings
    from ..services.attachments import AttachmentService

logger = logging.getLogger(__name__)


_MAX_RANKED_TOOLS = 5

CapDigest = dict[str, list[dict[str, Any]]]
ToolPayload = list[dict[str, Any]]
DigestProvider = Callable[..., CapDigest]
ToolLookup = Callable[[Iterable[str]], ToolPayload]


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


def _build_enhanced_system_prompt(base_prompt: str | None) -> str:
    """Prepend the current time context to the configured system prompt."""

    snapshot = create_time_snapshot()
    context_lines = [
        "# Current Date & Time Context",
        (
            "- Today's date: "
            f"{snapshot.date.isoformat()} ({snapshot.now_local.strftime('%A')})"
        ),
        f"- Current time: {snapshot.format_time()}",
        f"- Timezone: {snapshot.timezone_display()}",
        f"- ISO timestamp (UTC): {snapshot.iso_utc}",
        "",
        (
            "Use this context when interpreting relative dates like "
            "'last month', 'next week', etc."
        ),
    ]
    context_block = "\n".join(context_lines)
    base = (base_prompt or "").strip()
    if base:
        return f"{context_block}\n\n{base}"
    return context_block


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
        logging_settings = parse_logging_settings(
            project_root / "logging_settings.conf"
        )
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
        self._llm_planner = LLMContextPlanner(self._client)

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
        system_messages = [
            message for message in stored_messages if message.get("role") == "system"
        ]
        incoming_has_system = any(
            message.role == "system" for message in incoming_messages
        )
        (
            system_prompt_value,
            planner_enabled,
        ) = await self._model_settings.get_orchestrator_settings()
        system_prompt = _build_enhanced_system_prompt(system_prompt_value)
        has_system_message = bool(system_messages)

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
        capability_digest: CapDigest = {}
        digest_provider = cast(
            DigestProvider | None,
            getattr(self._mcp_client, "get_capability_digest", None),
        )
        if digest_provider is not None:
            try:
                candidate_digest = digest_provider()
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.debug("Capability digest unavailable: %s", exc)
                capability_digest = {}
            else:
                if isinstance(candidate_digest, dict):
                    capability_digest = candidate_digest
                else:  # pragma: no cover - defensive fallback
                    logger.debug(
                        "Capability digest returned unexpected type: %s",
                        type(candidate_digest),
                    )
                    capability_digest = {}

        if planner_enabled:
            plan = await self._llm_planner.plan(
                request,
                conversation,
                capability_digest=capability_digest,
            )
        else:
            plan = self._llm_planner.fallback_plan(
                request,
                capability_digest=capability_digest,
            )

        # Get contexts and ranked tools from the plan
        contexts = plan.contexts_for_attempt(0)
        ranked_tool_names: list[str] = []
        ranked_digest: CapDigest | None = None

        if contexts and digest_provider is not None:
            try:
                candidate_ranked = digest_provider(
                    contexts,
                    limit=_MAX_RANKED_TOOLS,
                    include_global=False,
                )
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.debug(
                    "Failed to obtain ranked capability digest for contexts %s: %s",
                    contexts,
                    exc,
                )
                ranked_digest = {}
            else:
                if isinstance(candidate_ranked, dict):
                    ranked_digest = candidate_ranked
                else:  # pragma: no cover - defensive fallback
                    logger.debug(
                        "Ranked capability digest returned unexpected type: %s",
                        type(candidate_ranked),
                    )
                    ranked_digest = {}
        else:
            ranked_digest = {}

        if plan.candidate_tools:
            seen_names: set[str] = set()
            ordered_contexts = list(contexts)
            if "__all__" in plan.candidate_tools and "__all__" not in ordered_contexts:
                ordered_contexts.append("__all__")
            for context in ordered_contexts:
                candidates = plan.candidate_tools.get(context) or []
                for candidate in candidates:
                    name = candidate.name.strip()
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    ranked_tool_names.append(name)

        if ranked_digest:
            seen_names = set(ranked_tool_names)
            for context in contexts:
                entries = ranked_digest.get(context) or []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name")
                    if not isinstance(name, str) or not name:
                        continue
                    if name in seen_names:
                        continue
                    seen_names.add(name)
                    ranked_tool_names.append(name)

        plan_payload = plan.to_dict()
        request_event_id: str | None = None
        if isinstance(request.metadata, dict):
            candidate = request.metadata.get("client_request_id")
            if isinstance(candidate, str):
                request_event_id = candidate
        repo_add_event = getattr(self._repo, "add_event", None)
        if repo_add_event is not None:
            try:
                maybe_coro = repo_add_event(
                    session_id,
                    "tool_plan",
                    {"plan": plan_payload},
                    request_id=request_event_id,
                )
                if inspect.isawaitable(maybe_coro):
                    await maybe_coro
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.debug("Failed to persist tool plan: %s", exc)
        tools_payload: ToolPayload
        if plan.use_all_tools_for_attempt(0):
            tools_payload = self._mcp_client.get_openai_tools()
        else:
            ranked_tools_payload: ToolPayload = []
            if ranked_tool_names:
                lookup = cast(
                    ToolLookup | None,
                    getattr(
                        self._mcp_client, "get_openai_tools_by_qualified_names", None
                    ),
                )
                if lookup is not None:
                    try:
                        candidate_tools = lookup(ranked_tool_names)
                    except Exception as exc:  # pragma: no cover - defensive fallback
                        logger.debug(
                            "Failed to resolve ranked tool specs for %s: %s",
                            ranked_tool_names,
                            exc,
                        )
                        ranked_tools_payload = []
                    else:
                        if isinstance(candidate_tools, list):
                            ranked_tools_payload = [
                                tool
                                for tool in candidate_tools
                                if isinstance(tool, dict)
                            ]
                        else:  # pragma: no cover - defensive fallback
                            logger.debug(
                                "Ranked tool lookup returned unexpected type: %s",
                                type(candidate_tools),
                            )
                            ranked_tools_payload = []
            if ranked_tools_payload:
                tools_payload = ranked_tools_payload
            else:
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
            plan,
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
