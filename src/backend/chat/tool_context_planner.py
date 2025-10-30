"""Heuristic planner for selecting tool contexts prior to streaming."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..schemas.chat import ChatCompletionRequest


@dataclass(slots=True)
class ToolContextPlan:
    """Represents an ordered plan of tool contexts to attempt."""

    stages: list[list[str]] = field(default_factory=list)
    broad_search: bool = False
    intent: str | None = None
    ranked_contexts: list[str] = field(default_factory=list)
    candidate_tools: dict[str, list["ToolCandidate"]] = field(default_factory=dict)
    argument_hints: dict[str, list[str]] = field(default_factory=dict)
    privacy_note: str | None = None
    stop_conditions: list[str] = field(default_factory=list)

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the plan for persistence or client payloads."""

        return {
            "stages": [list(stage) for stage in self.stages],
            "broad_search": self.broad_search,
            "intent": self.intent,
            "ranked_contexts": list(self.ranked_contexts),
            "candidate_tools": {
                context: [candidate.to_dict() for candidate in candidates]
                for context, candidates in self.candidate_tools.items()
            },
            "argument_hints": {
                name: list(hints) for name, hints in self.argument_hints.items()
            },
            "privacy_note": self.privacy_note,
            "stop_conditions": list(self.stop_conditions),
        }


def _normalize_context(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _clone_candidate(candidate: "ToolCandidate") -> "ToolCandidate":
    parameters = None
    if candidate.parameters is not None:
        parameters = dict(candidate.parameters)
    return ToolCandidate(
        name=candidate.name,
        description=candidate.description,
        parameters=parameters,
        server=candidate.server,
        score=candidate.score,
    )


def _parse_candidate_tools(
    payload: Mapping[str, Any]
) -> dict[str, list["ToolCandidate"]]:
    candidates: dict[str, list[ToolCandidate]] = {}
    for context, entries in payload.items():
        normalized_context = _normalize_context(context)
        if not normalized_context:
            continue
        parsed_entries: list[ToolCandidate] = []
        if not isinstance(entries, Sequence):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            description = entry.get("description")
            if description is not None and not isinstance(description, str):
                description = None
            parameters = entry.get("parameters")
            if parameters is not None and not isinstance(parameters, Mapping):
                parameters = None
            server = entry.get("server")
            if server is not None and not isinstance(server, str):
                server = None
            score_value = entry.get("score")
            score: float | None
            if isinstance(score_value, (int, float)):
                score = float(score_value)
            else:
                score = None
            parsed_entries.append(
                ToolCandidate(
                    name=name.strip(),
                    description=description,
                    parameters=dict(parameters) if isinstance(parameters, Mapping) else None,
                    server=server.strip() if isinstance(server, str) and server.strip() else None,
                    score=score,
                )
            )
        if parsed_entries:
            candidates[normalized_context] = parsed_entries
    return candidates


def _parse_argument_hints(payload: Mapping[str, Any]) -> dict[str, list[str]]:
    hints: dict[str, list[str]] = {}
    for key, value in payload.items():
        normalized_key = _normalize_context(key)
        if not normalized_key:
            continue
        if not isinstance(value, Sequence):
            continue
        collected: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            hint = item.strip()
            if not hint:
                continue
            collected.append(hint)
        if collected:
            hints[normalized_key] = collected
    return hints


def _parse_stop_conditions(payload: Sequence[Any]) -> list[str]:
    conditions: list[str] = []
    for entry in payload:
        if not isinstance(entry, str):
            continue
        normalized = entry.strip()
        if not normalized:
            continue
        if normalized not in conditions:
            conditions.append(normalized)
    return conditions


def merge_model_tool_plan(
    fallback: ToolContextPlan, payload: Mapping[str, Any] | None
) -> ToolContextPlan:
    """Return a plan merged with model guidance while preserving fallbacks."""

    if payload is None:
        return fallback

    plan_payload: Mapping[str, Any] | None
    if isinstance(payload, Mapping) and "plan" in payload:
        plan_candidate = payload.get("plan")
        if isinstance(plan_candidate, Mapping):
            plan_payload = plan_candidate
        else:
            plan_payload = None
    elif isinstance(payload, Mapping):
        plan_payload = payload
    else:
        plan_payload = None

    if plan_payload is None:
        return fallback

    stages_source = plan_payload.get("stages") or plan_payload.get("attempts")
    parsed_stages: list[list[str]] = []
    source_had_stage_data = False
    if isinstance(stages_source, Sequence):
        source_had_stage_data = True
        for stage in stages_source:
            if not isinstance(stage, Sequence):
                continue
            stage_contexts: list[str] = []
            for context in stage:
                normalized = _normalize_context(context)
                if not normalized:
                    continue
                if normalized not in stage_contexts:
                    stage_contexts.append(normalized)
            if stage_contexts:
                parsed_stages.append(stage_contexts)

    ranked_contexts = []
    ranked_source = plan_payload.get("ranked_contexts")
    if isinstance(ranked_source, Sequence):
        for context in ranked_source:
            normalized = _normalize_context(context)
            if not normalized:
                continue
            if normalized not in ranked_contexts:
                ranked_contexts.append(normalized)

    if not parsed_stages and ranked_contexts:
        parsed_stages = [list(ranked_contexts)]

    if not parsed_stages and source_had_stage_data:
        # Model returned unusable stage data; treat as invalid response.
        return fallback

    broad_search_value = plan_payload.get("broad_search")
    broad_search_specified = isinstance(broad_search_value, bool)
    if broad_search_specified:
        broad_search = bool(broad_search_value)
    else:
        broad_search = fallback.broad_search

    intent_value = plan_payload.get("intent")
    if isinstance(intent_value, str):
        intent = intent_value.strip() or None
    else:
        intent = fallback.intent

    candidate_tools_value = plan_payload.get("candidate_tools")
    if isinstance(candidate_tools_value, Mapping):
        candidate_tools = _parse_candidate_tools(candidate_tools_value)
    else:
        candidate_tools = {}
    if not candidate_tools:
        candidate_tools = {
            key: [_clone_candidate(candidate) for candidate in value]
            for key, value in fallback.candidate_tools.items()
        }
    else:
        # Merge fallback contexts not returned by the model.
        for key, value in fallback.candidate_tools.items():
            if key in candidate_tools:
                continue
            candidate_tools[key] = [_clone_candidate(candidate) for candidate in value]

    argument_hints_value = plan_payload.get("argument_hints")
    if isinstance(argument_hints_value, Mapping):
        argument_hints = _parse_argument_hints(argument_hints_value)
    else:
        argument_hints = {
            key: list(value) for key, value in fallback.argument_hints.items()
        }

    privacy_note_value = plan_payload.get("privacy_note")
    if isinstance(privacy_note_value, str) and privacy_note_value.strip():
        privacy_note = privacy_note_value.strip()
    else:
        privacy_note = fallback.privacy_note

    stop_conditions_value = plan_payload.get("stop_conditions")
    if isinstance(stop_conditions_value, Sequence):
        stop_conditions = _parse_stop_conditions(stop_conditions_value)
    else:
        stop_conditions = list(fallback.stop_conditions)

    if not parsed_stages and not broad_search_specified:
        stages = [list(stage) for stage in fallback.stages]
        broad_search = fallback.broad_search
    else:
        stages = [list(stage) for stage in parsed_stages] if parsed_stages else []

    return ToolContextPlan(
        stages=stages,
        broad_search=broad_search,
        intent=intent,
        ranked_contexts=(ranked_contexts or list(fallback.ranked_contexts)),
        candidate_tools=candidate_tools,
        argument_hints=argument_hints,
        privacy_note=privacy_note,
        stop_conditions=stop_conditions,
    )


@dataclass(slots=True)
class ToolCandidate:
    """Lightweight summary of a tool ranked for a given context."""

    name: str
    description: str | None = None
    parameters: Mapping[str, Any] | None = None
    server: str | None = None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "server": self.server,
        }
        if self.parameters is not None:
            payload["parameters"] = dict(self.parameters)
        if self.score is not None:
            payload["score"] = self.score
        return payload


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

    _TEXT_INTENT_RULES: Sequence[tuple[tuple[str, ...], str]] = (
        (
            (
                "schedule",
                "calendar",
                "availability",
                "meeting",
                "appointment",
            ),
            "Review or update calendar availability",
        ),
        (("task", "todo", "reminder", "chore"), "Track or update tasks"),
        (("email", "inbox", "gmail", "message"), "Read or draft email"),
        (("note", "notes", "journal"), "Review or edit notes"),
        (("doc", "document", "drive"), "Open or modify drive documents"),
        (("contact", "people", "phone"), "Lookup contact details"),
    )

    _CONTEXT_INTENT_MAP: dict[str, str] = {
        "calendar": "Review or update calendar availability",
        "tasks": "Track or update tasks",
        "notes": "Review or edit notes",
        "gdrive": "Open or modify drive documents",
        "gmail": "Read or draft email",
        "notion": "Work with Notion workspace content",
        "contacts": "Lookup contact details",
    }

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
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> ToolContextPlan:
        """Return a ranked context plan for the incoming request."""

        normalized_digest = self._normalize_capability_digest(capability_digest)

        if self._explicit_tool_request(request):
            return self._finalize_plan([], True, "", normalized_digest)

        text = self._extract_recent_user_text(request, conversation)
        if not text:
            return self._finalize_plan([], True, "", normalized_digest)

        lowered = text.lower()
        if any(marker in lowered for marker in self._EXPLICIT_TOOL_MARKERS):
            return self._finalize_plan([], True, lowered, normalized_digest)

        matched_stages: list[list[str]] = []
        for keywords, stages in self._KEYWORD_RULES:
            if any(keyword in lowered for keyword in keywords):
                matched_stages.extend(stages)

        if matched_stages:
            return self._finalize_plan(matched_stages, True, lowered, normalized_digest)

        return self._finalize_plan([], True, lowered, normalized_digest)

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

    def _normalize_capability_digest(
        self,
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    ) -> dict[str, list[Mapping[str, Any]]]:
        if not capability_digest:
            return {}
        normalized: dict[str, list[Mapping[str, Any]]] = {}
        for key, entries in capability_digest.items():
            if not isinstance(entries, Sequence):
                continue
            normalized_key = self._normalize_context_key(key)
            normalized[normalized_key] = [
                entry for entry in entries if isinstance(entry, Mapping)
            ]
        return normalized

    @staticmethod
    def _normalize_context_key(key: str) -> str:
        if not isinstance(key, str):
            return ""
        normalized = key.strip().lower()
        if not normalized:
            return ""
        return normalized

    def _finalize_plan(
        self,
        stages: Sequence[Sequence[str]],
        broad_search: bool,
        lowered_text: str,
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> ToolContextPlan:
        normalized_stages = [
            [ctx for ctx in (self._normalize_context_key(item) for item in stage) if ctx]
            for stage in stages
        ]
        ranked_contexts = self._build_ranked_contexts(normalized_stages, capability_digest)
        candidate_map = self._select_candidates(ranked_contexts, capability_digest)
        argument_hints = self._build_argument_hints(candidate_map)
        privacy_note = self._derive_privacy_note(ranked_contexts)
        stop_conditions = self._derive_stop_conditions(ranked_contexts)
        intent = self._infer_intent(lowered_text, ranked_contexts)
        return ToolContextPlan(
            stages=[list(stage) for stage in normalized_stages],
            broad_search=broad_search,
            intent=intent,
            ranked_contexts=ranked_contexts,
            candidate_tools=candidate_map,
            argument_hints=argument_hints,
            privacy_note=privacy_note,
            stop_conditions=stop_conditions,
        )

    def _build_ranked_contexts(
        self,
        stages: Sequence[Sequence[str]],
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> list[str]:
        ranked: list[str] = []
        seen: set[str] = set()
        for stage in stages:
            for context in stage:
                if context and context not in seen:
                    seen.add(context)
                    ranked.append(context)
        if not ranked and capability_digest:
            fallback = [
                key for key in capability_digest if key and key != "__all__"
            ]
            fallback.sort()
            ranked.extend(fallback[:5])
        return ranked

    def _select_candidates(
        self,
        contexts: Sequence[str],
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> dict[str, list[ToolCandidate]]:
        candidates: dict[str, list[ToolCandidate]] = {}
        fallback = capability_digest.get("__all__", [])
        for context in contexts:
            entries = capability_digest.get(context) or fallback
            if not entries:
                continue
            context_candidates: list[ToolCandidate] = []
            for entry in entries:
                name = entry.get("name") if isinstance(entry, Mapping) else None
                if not isinstance(name, str) or not name:
                    continue
                description = entry.get("description")
                if not isinstance(description, str):
                    description = None
                parameters = entry.get("parameters")
                if not isinstance(parameters, Mapping):
                    parameters = None
                server = entry.get("server")
                if not isinstance(server, str):
                    server = None
                score_value = entry.get("score")
                score = float(score_value) if isinstance(score_value, (int, float)) else None
                context_candidates.append(
                    ToolCandidate(
                        name=name,
                        description=description,
                        parameters=parameters,
                        server=server,
                        score=score,
                    )
                )
            if context_candidates:
                candidates[context] = context_candidates
        return candidates

    def _build_argument_hints(
        self, candidate_map: Mapping[str, Sequence[ToolCandidate]]
    ) -> dict[str, list[str]]:
        hints: dict[str, list[str]] = {}
        for candidates in candidate_map.values():
            for candidate in candidates:
                if not candidate.parameters:
                    continue
                extracted = self._extract_parameter_hints(candidate.parameters)
                if not extracted:
                    continue
                existing = hints.setdefault(candidate.name, [])
                for item in extracted:
                    if item not in existing:
                        existing.append(item)
        return hints

    def _extract_parameter_hints(self, parameters: Mapping[str, Any]) -> list[str]:
        hints: list[str] = []
        required = parameters.get("required") if isinstance(parameters, Mapping) else None
        if isinstance(required, Sequence):
            for item in required:
                if isinstance(item, str) and item and item not in hints:
                    hints.append(item)
        if hints:
            return hints[:5]
        properties = parameters.get("properties") if isinstance(parameters, Mapping) else None
        if isinstance(properties, Mapping):
            for name in properties.keys():
                if isinstance(name, str) and name and name not in hints:
                    hints.append(name)
                if len(hints) >= 5:
                    break
        return hints

    def _derive_privacy_note(self, contexts: Sequence[str]) -> str | None:
        sensitive = {"gmail", "contacts"}
        matched = [context for context in contexts if context in sensitive]
        if not matched:
            return None
        unique = sorted(set(matched))
        joined = ", ".join(unique)
        return (
            "Tool access may read or modify sensitive "
            f"{joined} data. Confirm before proceeding."
        )

    def _derive_stop_conditions(self, contexts: Sequence[str]) -> list[str]:
        if not contexts:
            return []
        conditions = ["tool_error"]
        if any(context in {"gmail", "contacts"} for context in contexts):
            conditions.append("missing_arguments")
        return conditions

    def _infer_intent(
        self, lowered_text: str, contexts: Sequence[str]
    ) -> str | None:
        for context in contexts:
            intent = self._CONTEXT_INTENT_MAP.get(context)
            if intent:
                return intent
        if not lowered_text:
            return None
        for keywords, label in self._TEXT_INTENT_RULES:
            if any(keyword in lowered_text for keyword in keywords):
                return label
        return None


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


__all__ = [
    "ToolCandidate",
    "ToolContextPlan",
    "ToolContextPlanner",
    "merge_model_tool_plan",
]
