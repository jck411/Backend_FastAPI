"""Heuristic planner for selecting tool contexts prior to streaming."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..schemas.chat import ChatCompletionRequest


@dataclass(slots=True)
class ToolContextPlan:
    """Represents an ordered plan of tool contexts to attempt."""

    stages: list[list[str]] = field(default_factory=list)
    broad_search: bool = False

    def contexts_for_attempt(self, attempt: int) -> list[str]:
        """Return the merged context list for the given attempt index."""

        if not self.stages:
            return []

        limit = min(max(attempt, 0) + 1, len(self.stages))
        merged: list[str] = []
        seen: set[str] = set()
        for stage in self.stages[:limit]:
            for context in stage:
                normalized = context.strip().lower()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                merged.append(normalized)
        return merged

    def additional_contexts_for_attempt(self, attempt: int) -> list[str]:
        """Return new contexts that would be introduced on the next attempt."""

        if not self.stages:
            return []

        if attempt < 0:
            attempt = 0

        if attempt + 1 >= len(self.stages):
            return []

        seen: set[str] = set()
        for stage in self.stages[: attempt + 1]:
            for context in stage:
                normalized = context.strip().lower()
                if normalized:
                    seen.add(normalized)

        additions: list[str] = []
        for context in self.stages[attempt + 1]:
            normalized = context.strip().lower()
            if not normalized or normalized in seen or normalized in additions:
                continue
            additions.append(normalized)
        return additions

    def use_all_tools_for_attempt(self, attempt: int) -> bool:
        """Return True when the attempt should fall back to every tool."""

        if not self.stages:
            return self.broad_search
        if attempt >= len(self.stages):
            return self.broad_search
        return False


class ToolContextPlanner:
    """Very small keyword-based planner for MCP tool contexts."""

    _KEYWORD_RULES: Sequence[tuple[tuple[str, ...], list[list[str]]]] = (
        (
            (
                "schedule",
                "scheduling",
                "calendar",
                "availability",
                "appointment",
                "event",
                "events",
            ),
            [["calendar"]],
        ),
        (("habit", "habits", "routine", "routines"), [["calendar"], ["tasks"], ["notes"]]),
        (
            ("task", "tasks", "todo", "to-do", "reminder", "reminders", "chore"),
            [["tasks"]],
        ),
        (
            (
                "doc",
                "docs",
                "document",
                "documents",
                "file",
                "files",
                "drive",
                "gdrive",
            ),
            [["gdrive"]],
        ),
        (("note", "notes", "journal", "log"), [["notes"]]),
        (("gmail", "email", "emails", "inbox", "mail", "message"), [["gmail"]]),
        (("notion",), [["notion"]]),
        (("contact", "contacts", "people"), [["contacts"]]),
    )

    _EXPLICIT_TOOL_MARKERS: tuple[str, ...] = (
        "tool:",
        "tool=",
        "use tool",
        "call tool",
        "use the tool",
        "mcp",
    )

    def plan(
        self,
        request: ChatCompletionRequest,
        conversation: Sequence[dict[str, Any]] | None,
    ) -> ToolContextPlan:
        """Return a ranked context plan for the incoming request."""

        if self._explicit_tool_request(request):
            return ToolContextPlan([], broad_search=True)

        text = self._extract_recent_user_text(request, conversation)
        if not text:
            return ToolContextPlan([], broad_search=True)

        lowered = text.lower()
        if any(marker in lowered for marker in self._EXPLICIT_TOOL_MARKERS):
            return ToolContextPlan([], broad_search=True)

        matched_stages: list[list[str]] = []
        for keywords, stages in self._KEYWORD_RULES:
            if any(keyword in lowered for keyword in keywords):
                matched_stages.extend(stages)

        if matched_stages:
            return ToolContextPlan(stages=matched_stages, broad_search=True)

        return ToolContextPlan([], broad_search=True)

    def _explicit_tool_request(self, request: ChatCompletionRequest) -> bool:
        tool_choice = request.tool_choice
        if isinstance(tool_choice, str) and tool_choice not in {"auto", "none"}:
            return True
        if isinstance(tool_choice, dict):
            return True
        tools = request.tools
        if isinstance(tools, Iterable) and any(tools):
            return True
        return False

    def _extract_recent_user_text(
        self,
        request: ChatCompletionRequest,
        conversation: Sequence[dict[str, Any]] | None,
    ) -> str:
        for message in reversed(request.messages):
            if message.role == "user":
                text = _stringify_content(message.content)
                if text:
                    return text

        if not conversation:
            return ""
        for entry in reversed(conversation):
            if entry.get("role") == "user":
                text = _stringify_content(entry.get("content"))
                if text:
                    return text
        return ""


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_stringify_content(item) for item in content]
        return " ".join(part for part in parts if part)
    if isinstance(content, dict):
        parts = [_stringify_content(value) for value in content.values()]
        return " ".join(part for part in parts if part)
    return ""


__all__ = ["ToolContextPlan", "ToolContextPlanner"]
