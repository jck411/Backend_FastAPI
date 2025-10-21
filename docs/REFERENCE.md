# Operations Reference

This document condenses the working notes that previously lived across several files.
Use it as a quick refresher on how the major subsystems hang together.

## Model settings and presets

- **Services**: `backend.services.model_settings.ModelSettingsService`,
  `backend.services.presets.PresetService`.
- **Storage**: `data/model_settings.json`, `data/presets.json`.
- **Key endpoints**:
  - `GET /api/settings/model`, `PUT /api/settings/model`
  - `GET /api/settings/system-prompt`, `PUT /api/settings/system-prompt`
  - `GET /api/presets/`, `GET /api/presets/{name}`
  - `POST /api/presets/`, `PUT /api/presets/{name}`, `DELETE /api/presets/{name}`
  - `POST /api/presets/{name}/apply`
- **Flow**:
  1. The frontend model picker persists the selected model through
     `model_settings_store`, keeping the backend and UI in sync.
  2. Presets snapshot the active backend state (model id, provider overrides,
     parameter overrides, system prompt, and MCP configs) so any client can
     restore the same environment later.
  3. When applying a preset the backend updates model settings and pushes new
     MCP server definitions to the orchestrator.
- **Troubleshooting**:
  - If presets appear to save the wrong model, confirm the UI successfully
    persisted the current picker value before snapshotting.
  - Inspect `data/model_settings.json` for the authoritative active model.
  - Backend defaults fall back to `OPENROUTER_DEFAULT_MODEL` and optional
    `OPENROUTER_SYSTEM_PROMPT` on first run.

## MCP servers

- **Config file**: `data/mcp_servers.json` (persisted by
  `MCPServerSettingsService`).
- **Runtime**: `ChatOrchestrator` loads the configs and keeps an instance of
  `chat.mcp_registry.MCPToolAggregator` warm.
- **Defaults**: The app bootstraps a calculator, housekeeping utilities, and
  Google integrations when no persisted config exists (see `backend.app`).
- **API surface**:
  - `GET /api/mcp/servers`
  - `PUT /api/mcp/servers`
  - `POST /api/mcp/servers/refresh`
- **Operational tips**:
  - Toggle servers in the UI or via API instead of editing JSON by hand; the
    aggregator hot-reloads definitions so the running instance stays in sync.
  - The aggregator prefixes tool names when multiple servers expose the same
    tool, which keeps OpenAI-compatible tool payloads conflict-free.

## Attachments and Gmail tooling

- **Service**: `backend.services.attachments.AttachmentService` manages uploads
  under `data/uploads/` and records metadata in the chat database.
- **Environment knobs**: `ATTACHMENTS_DIR`, `ATTACHMENTS_MAX_SIZE_BYTES`,
  `ATTACHMENTS_RETENTION_DAYS`.
- **Routes**: `POST /api/uploads`, `GET /api/uploads/{attachment_id}`,
  `DELETE /api/uploads/{attachment_id}`.
- **Behaviour**:
  - The same storage path backs Gmail downloads and manual uploads. Delivery
    URLs remain local (no ngrok or external tunnelling) so `display_url` and
    `delivery_url` always match.
  - Gmail helpers inside `backend.mcp_servers.gmail_server` can either stream
    attachment text directly (`read_gmail_attachment_text`) or save files for
    later extraction (`download_gmail_attachment`).
  - Attachments are associated with chat sessions; touching a message marks the
    referenced files as recently used so retention policies work as expected.

## Speech-to-text auto submit

- **Frontend**: `frontend/src/lib/stores/speech.ts` and related helpers wire up
  Deepgram streaming and auto-submit.
- **Backend**: `/api/stt/deepgram/token` mints temporary keys when the browser
  cannot hold the long-lived API secret.
- **Detection strategy**:
  - Prefer Deepgram's `speech_final` events to detect the end of an utterance.
  - Fall back to `UtteranceEnd` events if a final result never arrives.
  - Both paths respect the configurable delay exposed in the speech settings UI
    so users can fine-tune the behaviour for noisy rooms.
- **Configuration**: Adjustable parameters live under the speech settings panel
  (model id, interim results, VAD thresholds, auto-submit delay, etc.). Values
  are validated before the websocket session is negotiated.

## Data directory cheat sheet

| Path                     | Purpose                                               |
|--------------------------|-------------------------------------------------------|
| `data/chat_sessions.db`  | SQLite store for chat history and attachment metadata |
| `data/model_settings.json` | Active model configuration                           |
| `data/presets.json`      | Saved preset snapshots                                |
| `data/mcp_servers.json`  | Persisted MCP server definitions                      |
| `data/uploads/`          | Attachment binaries grouped by session                |
| `data/tokens/`           | OAuth tokens minted during Google flows               |

Keep these directories under version control only when you need deterministic
fixtures; the repository ignores them by default so local state stays local.
