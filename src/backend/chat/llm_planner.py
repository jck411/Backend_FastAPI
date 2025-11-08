"""LLM-based context planning that simplifies tool selection."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from .tool_context_planner import ToolContextPlan, merge_model_tool_plan
from .tool_dependencies import expand_tool_plan_with_dependencies
from .tool_utils import compact_tool_digest

if TYPE_CHECKING:
    from ..openrouter import OpenRouterClient

from ..schemas.chat import ChatCompletionRequest

logger = logging.getLogger(__name__)


class LLMContextPlanner:
    """LLM-first context planner that simplifies tool selection logic."""

    PLANNER_SYSTEM_PROMPT = """
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
2. When the user asks to read/view/get data (e.g., "what's on my calendar", "show my emails", "my tasks"), include BOTH prerequisite tools (auth checks) AND data-fetching tools (get_events, list_tasks, list_emails).
3. Use stages to sequence dependent operations, but ensure all necessary tools are available across stages.
4. Don't set stop_conditions for normal tool responses. Only use them for actual stopping scenarios (e.g., privacy blocks, explicit user cancellation).
5. Set broad_search=true if the query might need tools beyond what you explicitly staged.

Examples:
- "what's on my calendar today?" → Include calendar_auth_status AND calendar_get_events
- "show my scheduled tasks" / "my tasks" → Include calendar_auth_status AND list_tasks
- "show my emails" → Include gmail_auth_status AND gmail_list_messages
Don't stop after auth checks - the user wants the actual data, not just confirmation they're authorized.

Do not invent tools or contexts that are absent from the digest. Respond with JSON only, without markdown fences or commentary.
""".strip()

    def __init__(self, client: "OpenRouterClient"):
        self._client = client

    async def plan(
        self,
        request: ChatCompletionRequest,
        conversation: Sequence[dict[str, Any]],
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> ToolContextPlan:
        """
        Generate a tool context plan using the LLM directly.

        This simplifies the planning logic by:
        1. Calling the LLM planner with full tool context
        2. Using a minimal fallback only if LLM planning fails
        3. Eliminating keyword-based pre-planning
        """
        # Create minimal fallback plan in case LLM planning fails
        fallback_plan = self._create_fallback_plan(request, capability_digest)

        # Prepare tool digest for LLM planner
        compact_digest = compact_tool_digest(capability_digest)

        # Try to get plan from LLM
        try:
            planner_response = await self._client.request_tool_plan(
                request=request,
                conversation=conversation,
                tool_digest=compact_digest,
                system_prompt=self.PLANNER_SYSTEM_PROMPT,
            )

            # Merge LLM response with fallback
            plan = merge_model_tool_plan(fallback_plan, planner_response)

            # Realign any tool-named contexts with their canonical capability contexts
            plan = self._align_plan_with_capabilities(plan, capability_digest)

            # Auto-expand to include auth dependencies
            plan = expand_tool_plan_with_dependencies(plan)

            logger.debug(
                "LLM planner generated plan with %d stages and %d contexts",
                len(plan.stages),
                len(plan.ranked_contexts),
            )
            return plan

        except Exception as exc:
            # Log failure and return fallback with reason
            reason = str(exc) if exc else "Unknown error"
            logger.warning(
                "LLM planning failed, using fallback plan: %s",
                reason,
            )
            fallback_plan.fallback_reason = reason
            return fallback_plan

    def _create_fallback_plan(
        self,
        request: ChatCompletionRequest,
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> ToolContextPlan:
        """
        Create a simple fallback plan when LLM planning is unavailable.

        This is much simpler than the keyword-based planner - it just
        provides all tools with broad search enabled.
        """
        # Check if user explicitly requested specific tools
        explicit_tool_request = self._is_explicit_tool_request(request)

        if explicit_tool_request:
            # User specified tools, use them directly
            return ToolContextPlan(
                stages=[],
                broad_search=True,
                intent="Use specified tools",
                used_fallback=True,
            )

        # Default fallback: provide all available tools
        return ToolContextPlan(
            stages=[],
            broad_search=True,
            intent="General assistance with all available tools",
            used_fallback=True,
        )

    def fallback_plan(
        self,
        request: ChatCompletionRequest,
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> ToolContextPlan:
        """Expose the fallback plan builder for callers that skip LLM planning."""

        return self._create_fallback_plan(request, capability_digest)

    def _is_explicit_tool_request(self, request: ChatCompletionRequest) -> bool:
        """Check if the request explicitly specifies tool requirements."""
        tool_choice = request.tool_choice
        if isinstance(tool_choice, str) and tool_choice not in {"auto", "none"}:
            return True
        if isinstance(tool_choice, dict):
            return True
        tools = request.tools
        if tools and len(tools) > 0:
            return True
        return False

    def _align_plan_with_capabilities(
        self,
        plan: ToolContextPlan,
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    ) -> ToolContextPlan:
        """Normalize plan contexts so auth/tool steps don't stall the main task."""

        if not capability_digest:
            return plan

        valid_contexts: set[str] = set()
        tool_to_contexts: dict[str, set[str]] = defaultdict(set)

        for context_name, entries in capability_digest.items():
            if not isinstance(context_name, str):
                continue
            normalized_context = context_name.strip().lower()
            if not normalized_context:
                continue
            valid_contexts.add(normalized_context)
            if not isinstance(entries, Sequence):
                continue
            for entry in entries:
                tool_name: str | None
                if isinstance(entry, Mapping):
                    name_value = entry.get("name")
                    tool_name = name_value if isinstance(name_value, str) else None
                elif isinstance(entry, str):
                    tool_name = entry
                else:
                    tool_name = None
                if not tool_name:
                    continue
                normalized_tool = tool_name.strip().lower()
                if not normalized_tool:
                    continue
                tool_to_contexts[normalized_tool].add(normalized_context)

        if not tool_to_contexts:
            return plan

        def _resolve_context(identifier: str) -> list[str]:
            normalized = identifier.strip().lower()
            if not normalized:
                return []
            if normalized in valid_contexts or normalized == "__all__":
                return [normalized]
            mapped = sorted(tool_to_contexts.get(normalized, set()))
            if mapped:
                return mapped
            return [normalized]

        if plan.stages:
            aligned_stages: list[list[str]] = []
            for stage in plan.stages:
                seen_in_stage: set[str] = set()
                aligned_stage: list[str] = []
                for context in stage:
                    for resolved in _resolve_context(context):
                        if not resolved or resolved in seen_in_stage:
                            continue
                        seen_in_stage.add(resolved)
                        aligned_stage.append(resolved)
                if aligned_stage:
                    aligned_stages.append(aligned_stage)
            plan.stages = aligned_stages

        if plan.ranked_contexts:
            aligned_ranked: list[str] = []
            seen_ranked: set[str] = set()
            for context in plan.ranked_contexts:
                for resolved in _resolve_context(context):
                    if not resolved or resolved in seen_ranked:
                        continue
                    seen_ranked.add(resolved)
                    aligned_ranked.append(resolved)
            plan.ranked_contexts = aligned_ranked

        if plan.candidate_tools:
            aligned_candidates: dict[str, list["ToolCandidate"]] = {}
            seen_per_context: dict[str, set[str]] = {}
            for context, candidates in plan.candidate_tools.items():
                for resolved in _resolve_context(context):
                    bucket = aligned_candidates.setdefault(resolved, [])
                    seen = seen_per_context.setdefault(
                        resolved, {candidate.name.strip().lower() for candidate in bucket if isinstance(candidate.name, str)}
                    )
                    for candidate in candidates:
                        name = candidate.name.strip().lower()
                        if not name or name in seen:
                            continue
                        bucket.append(candidate)
                        seen.add(name)
            plan.candidate_tools = aligned_candidates

        return plan


__all__ = ["LLMContextPlanner"]
