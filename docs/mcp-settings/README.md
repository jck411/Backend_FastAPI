# MCP Server Settings Implementation Guide

## Goals
- Allow operators to toggle MCP servers and individual tools at runtime without redeploying the backend.
- Surface the same controls in the web UI so non-technical users can enable/disable integrations.
- Keep the aggregator, orchestrator, and persisted JSON (`data/mcp_servers.json`) in sync.

## Prerequisites
- Review the current loader and aggregator in `src/backend/chat/mcp_registry.py` and how `ChatOrchestrator` wires it up (`src/backend/chat/orchestrator.py`).
- Understand the existing model settings flow (`src/backend/services/model_settings.py`) and `/api/settings` routes (`src/backend/routers/settings.py`) since we will mirror that pattern.
- Frontend uses Svelte with API helpers in `frontend/src/lib/api/client.ts` and state stores in `frontend/src/lib/stores`.

## Backend Roadmap

### 1. Persistent server settings service
- Create `src/backend/services/mcp_server_settings.py` that mirrors the locking + JSON persistence pattern from `ModelSettingsService`.
- Use `load_server_configs` to hydrate `MCPServerConfig` objects and keep the raw JSON payload for round-tripping custom fields.
- Track `updated_at`, preserve unknown future fields, and surface helpers like `get_configs()`, `replace_configs()`, and `toggle_tool(server_id, tool_name, enabled)`.
- Extend `src/backend/config.py` with an optional default servers fallback path if you want to override defaults in tests.

### 2. REST endpoints
- Add a new router (e.g. `src/backend/routers/mcp_servers.py`) mounted at `/api/mcp/servers`.
- Endpoints:
  - `GET /` → return current configs plus runtime info (active flag, connected status, tool counts).
  - `PUT /` → accept an ordered list of server definitions and persist via the service.
  - `PATCH /{server_id}` → minimal toggle payload for quick enable/disable updates (optional but handy for the UI).
  - `POST /refresh` → trigger `MCPToolAggregator.refresh()` to reconcile tool lists if external changes occur.
- Wire dependencies to pull both the orchestrator and the new service from `app.state` (add them in `src/backend/app.py`).

### 3. Aggregator runtime updates
- Update `MCPToolAggregator` to keep *all* configs (including disabled) so we can modify the enabled set after initialization.
- Add an `apply_configs(new_configs: Sequence[MCPServerConfig])` coroutine that:
  1. Differs the incoming configs against `self._configs`.
  2. Stops clients for servers that are now disabled or removed (await `client.close()`).
  3. Launches new/reenabled servers via `MCPToolClient`.
  4. Calls `_refresh_locked()` to rebuild bindings and OpenAI payloads.
- Expose lightweight getters like `describe_servers()` that return `{id, enabled, connected, tool_count}` for the API layer.

### 4. Tool-level toggles (optional but recommended)
- Extend `MCPServerConfig` with a field such as `disabled_tools: set[str] | None`.
- Modify `_refresh_locked()` to skip bindings whose `original_name` is listed as disabled.
- Provide service + API helpers to toggle individual tools without stopping the whole server.

### 5. Orchestrator integration
- Inject the new service into `ChatOrchestrator` and call `apply_configs()` after settings changes so the running aggregator stays in sync.
- Ensure `initialize()` still loads fallback configs for first run but respects persisted overrides.
- Consider emitting structured log lines whenever server or tool states change.

### 6. Tests
- Add unit coverage for the service (loading, dedupe, persistence) alongside existing registry tests in `tests/test_mcp_registry.py`.
- Add router tests using FastAPI's test client to validate serialization and integration with the orchestrator double.
- If practical, add an async integration test that toggles a sample server and asserts the tool list shrinks/expands.

## Frontend Roadmap

### 1. API client
- Add `fetchMcpServers()` and `updateMcpServers()` (or `patchMcpServer`) to `frontend/src/lib/api/client.ts` with supporting types in `frontend/src/lib/api/types.ts`.
- Decide on the response schema (e.g. include `connected`, `tool_count`, and `tools` arrays). Keep types aligned with backend responses.

### 2. Store
- Create `frontend/src/lib/stores/mcpServers.ts` mirroring `createModelSettingsStore()` to manage loading, optimistic toggles, and error handling.
- Support debounce for bulk edits or call-through saves for single toggle interactions.

### 3. UI
- Build a settings view (either new route or panel) that lists servers with:
  - Enable/disable switches.
  - Collapsible tool lists with per-tool toggles (if implemented).
  - Status badges driven by runtime metadata.
- Provide feedback when changes are saving or if the backend reports failures.

### 4. Real-time feedback (optional)
- After saving, refetch the server list to pick up any name-prefix changes applied by the aggregator.
- Consider streaming updates via existing SSE infrastructure if you need live status changes (stretch goal).

## Implementation Sequence
1. Backend service + router scaffolding.
2. Aggregator refactor (`src/backend/chat/mcp_registry.py`).
3. Orchestrator wiring and state exposure (`src/backend/chat/orchestrator.py`).
4. Automated tests (service + router + aggregator adjustments).
5. Frontend API helpers and store.
6. UI layer and polish (loading states, error surfaces).
7. Manual validation and end-to-end test run.

## Validation Checklist
- `uv run pytest tests/test_mcp_registry.py tests/test_mcp_server.py` (existing coverage) plus new tests.
- Manual toggle of sample server confirms tools appear/disappear in the chat UI.
- API endpoints return stable ordering and idempotent responses.
- Frontend build (`npm run build` in `frontend/`) succeeds with new types and store.

## Stretch Ideas
- Add rate-limit or concurrency guardrails per server.
- Persist last-known health status and surface in the UI.
- Allow ordering tools for display by storing a user-defined weight.

