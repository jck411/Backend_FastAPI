# Models, Active Settings, and Presets

This document explains how model selection, active model settings, and presets work end‑to‑end across the frontend and backend.

Contents
- Overview
- Active Model Settings (backend)
- Frontend model selection flow
- Presets (create, save snapshot, apply)
- Data locations
- Default model and environment variables
- Troubleshooting
- Developer reference (key files)

## Overview

- The “active model” and its parameters live on the backend and are persisted to disk.
- The frontend’s model picker changes the UI selection and also persists it to the backend active model.
- “Create from current” and “Save snapshot” build a Preset from the current backend state (model, provider preferences, parameters, system prompt, MCP servers).
- Applying a Preset updates the backend active state and synchronizes the UI.

This separation ensures any client can read or update the active settings consistently via API.

---

## Active Model Settings (backend)

Service: `ModelSettingsService`
Persisted file: `data/model_settings.json`
API:
- GET `/api/settings/model` — Read active settings
- PUT `/api/settings/model` — Replace active settings
- GET `/api/settings/system-prompt` — Read system prompt
- PUT `/api/settings/system-prompt` — Update system prompt
- GET `/api/settings/model/active-provider` — Diagnostic endpoint (provider details/routing for the active model)

Shape:
```json
{
  "model": "openrouter/auto",
  "provider": { ... },          // optional provider routing preferences
  "parameters": { ... },        // optional hyperparameters
  "system_prompt": "...",       // only present when set
  "updated_at": "ISO-8601 timestamp"
}
```

On startup, the backend initializes with:
- `default_model` from env (see below), falling back to `openrouter/auto`
- Optional `openrouter_system_prompt`

The service then loads `data/model_settings.json` if present.

---

## Frontend model selection flow

Key stores/components:
- `chatStore.selectedModel` (UI state for the picker)
- `modelSettingsStore` (persists active settings to backend)
- `ModelPicker` in `ChatHeader` (UI for choosing a model)
- `App.svelte` wires the pieces together

Important behavior:
- When the user selects a model in the header, `chatStore.setModel(id)` is called.
- `chatStore.setModel` updates UI state AND persists to backend by calling:
  - `modelSettingsStore.load(selectedModel)` which:
    - GETs `/api/settings/model`
    - If different, PUTs `/api/settings/model { model: selectedModel, ... }`

Why this matters:
- Presets are snapshots of the BACKEND state. Ensuring the backend active model matches the UI selection avoids saving stale model ids.

---

## Presets (create, save snapshot, apply)

Service: `PresetService`
Persisted file: `data/presets.json`
API:
- GET `/api/presets/` — List presets (name, model, timestamps)
- GET `/api/presets/{name}` — Read a full preset
- POST `/api/presets/` — Create a new preset from current backend configuration
- PUT `/api/presets/{name}` — Overwrite a preset with a snapshot of current backend configuration
- DELETE `/api/presets/{name}` — Delete a preset
- POST `/api/presets/{name}/apply` — Apply a preset to the backend (and MCP)

What’s in a Preset:
```json
{
  "name": "my-preset",
  "model": "openrouter/auto",
  "provider": { ... },       // routing preferences
  "parameters": { ... },     // hyperparameters
  "system_prompt": "...",
  "mcp_servers": [ ... ],    // server configs
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

Frontend flow:
- Create from current:
  - UI calls `modelSettingsStore.load($chatStore.selectedModel)` to ensure backend matches the UI.
  - Calls `POST /api/presets/ { name }`.
  - The backend snapshots the current MODEL SETTINGS + system prompt + MCP configs.
- Save snapshot:
  - Same sync step to ensure backend model = UI.
  - Calls `PUT /api/presets/{name}` to overwrite the preset with a fresh snapshot.
- Apply:
  - Calls `POST /api/presets/{name}/apply`.
  - Backend updates active model, provider, parameters, prompt, and MCP configs.
  - Frontend sets `chatStore.selectedModel` to the preset’s model to keep the UI in sync.

---

## Data locations

- Active model settings: `data/model_settings.json`
- Presets: `data/presets.json`
- MCP servers: `data/mcp_servers.json`
- Chat history (server-side): `data/chat_sessions.db` (if enabled/used by the app)

Tip: Prefer changing settings through the app or API. Editing these files manually won’t notify a live server; your changes may be overwritten by subsequent API calls.

---

## Default model and environment variables

Configured in `src/backend/config.py` via `pydantic_settings`.

- `OPENROUTER_DEFAULT_MODEL` (alias: `default_model`)
  - Default: `openrouter/auto`
  - Example: `OPENROUTER_DEFAULT_MODEL=openai/gpt-4o`

- `OPENROUTER_SYSTEM_PROMPT` (alias: `system_prompt`)
  - Optional default system prompt applied on first run when no prompt is stored

Paths (can be overridden):
- `MODEL_SETTINGS_PATH` (default `data/model_settings.json`)
- `PRESETS_PATH` (default `data/presets.json`)
- `MCP_SERVERS_PATH` (default `data/mcp_servers.json`)

---

## Troubleshooting

Symptoms: Presets always save the wrong model (e.g., `google/gemma-2-9b-it:free`)
- Cause: The UI selection wasn’t persisted to the backend before snapshotting. Presets are based on backend active settings.
- Behavior fixed: The UI now persists selection automatically; Presets modal also syncs model before “Create” or “Save snapshot”.

Checklist:
- Ensure you changed the model via the header picker
- Open presets and click “Create from current” — the list should show the correct model
- Inspect `data/model_settings.json` after selection; `"model"` should match what you chose
- If running a cached/old frontend, hard-reload your browser

Other tips:
- If applying a preset doesn’t update the UI picker, confirm the server is running and reachable; the app relies on `POST /api/presets/{name}/apply` result and updates picker from that response.
- If you edited data files manually, restart the backend or re-open the app to avoid stale state.

---

## Developer reference (key files)

Backend
- Active settings
  - Service: `src/backend/services/model_settings.py` (`ModelSettingsService`)
  - Router: `src/backend/routers/settings.py`
  - Config/env: `src/backend/config.py`
- Presets
  - Schema: `src/backend/schemas/presets.py`
  - Service: `src/backend/services/presets.py` (`PresetService`)
  - Router: `src/backend/routers/presets.py`

Frontend
- Model selection & chat payloads
  - Store: `frontend/src/lib/stores/chat.ts` (`chatStore.selectedModel`)
  - Picker UI: `frontend/src/lib/components/chat/ModelPicker.svelte`
  - Header wiring: `frontend/src/lib/components/chat/ChatHeader.svelte`
  - App wiring: `frontend/src/App.svelte`
- Model settings persistence
  - Store: `frontend/src/lib/stores/modelSettings.ts` (`modelSettingsStore`)
  - Modal hook: `frontend/src/lib/components/chat/model-settings/useModelSettings.ts`
  - Modal UI: `frontend/src/lib/components/chat/ModelSettingsModal.svelte`
- Presets
  - Store: `frontend/src/lib/stores/presets.ts` (`presetsStore`)
  - Modal UI: `frontend/src/lib/components/chat/PresetsModal.svelte`
- API client
  - `frontend/src/lib/api/client.ts` and types in `frontend/src/lib/api/types.ts`
