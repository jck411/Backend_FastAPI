"""LLM-based context planning that simplifies tool selection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from .tool_context_planner import ToolContextPlan, merge_model_tool_plan
from .tool_utils import compact_tool_digest

if TYPE_CHECKING:
    from ..openrouter import OpenRouterClient
    from ..schemas.chat import ChatCompletionRequest

logger = logging.getLogger(__name__)


class LLMContextPlanner:
    """LLM-first context planner that simplifies tool selection logic."""

    def __init__(self, client: "OpenRouterClient"):
        self._client = client

    async def plan(
        self,
        request: "ChatCompletionRequest",
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
            )
            
            # Merge LLM response with fallback
            plan = merge_model_tool_plan(fallback_plan, planner_response)
            logger.debug(
                "LLM planner generated plan with %d stages and %d contexts",
                len(plan.stages),
                len(plan.ranked_contexts),
            )
            return plan
            
        except Exception as exc:
            # Log failure and return fallback
            logger.warning(
                "LLM planning failed, using fallback plan: %s",
                exc,
            )
            return fallback_plan

    def _create_fallback_plan(
        self,
        request: "ChatCompletionRequest",
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
        request: "ChatCompletionRequest",
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> ToolContextPlan:
        """Expose the fallback plan builder for callers that skip LLM planning."""

        return self._create_fallback_plan(request, capability_digest)

    def _is_explicit_tool_request(self, request: "ChatCompletionRequest") -> bool:
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


__all__ = ["LLMContextPlanner"]
