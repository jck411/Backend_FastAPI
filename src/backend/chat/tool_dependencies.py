"""Tool dependency rules for automatic expansion of tool plans."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tool_context_planner import ToolContextPlan

logger = logging.getLogger(__name__)


# Tool dependency mapping: data_tool -> auth_tool
# When a data-fetching tool is in the plan, ensure its auth tool is included
TOOL_AUTH_DEPENDENCIES: dict[str, str] = {
    # Calendar tools
    "calendar_get_events": "calendar_auth_status",
    "list_tasks": "calendar_auth_status",
    "calendar_list_tasks": "calendar_auth_status",
    "create_event": "calendar_auth_status",
    "update_event": "calendar_auth_status",
    "delete_event": "calendar_auth_status",
    "create_task": "calendar_auth_status",
    "update_task": "calendar_auth_status",
    "delete_task": "calendar_auth_status",
    # Gmail tools
    "gmail_list_messages": "gmail_auth_status",
    "gmail_get_message": "gmail_auth_status",
    "gmail_send_message": "gmail_auth_status",
    "gmail_search": "gmail_auth_status",
    # Google Drive tools
    "gdrive_list_files": "gdrive_auth_status",
    "gdrive_get_file": "gdrive_auth_status",
    "gdrive_upload_file": "gdrive_auth_status",
    "gdrive_delete_file": "gdrive_auth_status",
    # Notion tools
    "notion_search": "notion_auth_status",
    "notion_get_page": "notion_auth_status",
    "notion_create_page": "notion_auth_status",
}


def expand_tool_plan_with_dependencies(plan: ToolContextPlan) -> ToolContextPlan:
    """
    Automatically expand the tool plan to include auth prerequisites.

    Examines candidate_tools and ensures that for every data-fetching tool,
    its required auth tool is also included.

    Args:
        plan: The original tool plan from the LLM planner

    Returns:
        The expanded plan with auth tools added where needed
    """
    if not plan.candidate_tools:
        return plan

    added_tools: list[tuple[str, str]] = []  # (context, tool_name) pairs

    # Scan all contexts and their tools
    for context, candidates in plan.candidate_tools.items():
        existing_tool_names = {candidate.name for candidate in candidates}
        tools_to_add: set[str] = set()

        # Check each tool for dependencies
        for candidate in candidates:
            tool_name = candidate.name

            # If this tool requires auth, ensure auth tool is present
            auth_tool = TOOL_AUTH_DEPENDENCIES.get(tool_name)
            if auth_tool and auth_tool not in existing_tool_names:
                tools_to_add.add(auth_tool)
                added_tools.append((context, auth_tool))

        # Add missing auth tools to this context
        if tools_to_add:
            from .tool_context_planner import ToolCandidate

            for auth_tool in tools_to_add:
                # Create a minimal ToolCandidate for the auth tool
                auth_candidate = ToolCandidate(
                    name=auth_tool,
                    description="Authentication prerequisite (auto-added)",
                    score=1.0,  # High score since it's required
                )
                # Insert at the beginning so auth runs first
                plan.candidate_tools[context].insert(0, auth_candidate)

    if added_tools:
        logger.info(
            "Auto-expanded tool plan with %d auth dependencies: %s",
            len(added_tools),
            ", ".join(f"{tool} to {ctx}" for ctx, tool in added_tools),
        )

    return plan


__all__ = ["expand_tool_plan_with_dependencies", "TOOL_AUTH_DEPENDENCIES"]
