# OpenRouter Chat Backend

FastAPI backend that proxies streaming chat completions from OpenRouter and keeps
Model Context Protocol (MCP) tools online for the chat UI. Responses are streamed
over Server-Sent Events (SSE) so any client can render tokens as they arrive.

## Highlights

- **OpenRouter-first streaming** with HTTP keep-alive so replies start quickly.
- **Persisted chat history** with attachment support and retention controls.
- **MCP tool aggregation** for Google Calendar, Gmail, Drive, PDF extraction, and
  custom local utilities.
- **Browser speech-to-text** helpers that mint short-lived Deepgram tokens.

## Requirements

- Python 3.13+
- [`uv`](https://github.com/astral-sh/uv) for dependency and task management
- Local `.env` file (copy from `.env.example` and fill in at least
  `OPENROUTER_API_KEY`)
- Google OAuth client credentials stored under `credentials/`

## Setup

```bash
uv sync
```

`uv` will reuse a virtual environment under `.venv/` inside the project root.

## Running the API

During development you will usually want reload enabled:

```bash
uv run uvicorn backend.app:app --reload --app-dir src
```

Alternative entrypoints:

```bash
uv run python -m uvicorn backend.app:app --app-dir src
uv run fastapi dev backend.app:app --app-dir src  # requires fastapi[standard]
uv run backend  # CLI wrapper that calls uvicorn with sensible defaults
```

The service exposes a lightweight HTTP surface:

| Method & Path | Description |
|---------------|-------------|
| `GET /health` | Readiness probe with default/active model hints |
| `POST /api/chat/stream` | Stream OpenRouter chat completions via SSE |
| `DELETE /api/chat/session/{id}` | Clear server-side conversation state |
| `GET /api/models` | Return the OpenRouter catalog (filterable) |
| `POST /api/stt/deepgram/token` | Mint short-lived Deepgram keys for browser STT |
| `POST /api/uploads` | Store attachments for reuse in later turns |
| `GET /api/mcp/servers` | Inspect configured MCP servers and their status |
| `GET /api/presets/` | Manage presets built from current backend state |

### Streaming example

```bash
curl -N \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{
        "model": "openrouter/auto",
        "messages": [{"role": "user", "content": "Hello from FastAPI!"}]
      }' \
  http://localhost:8000/api/chat/stream
```

### Attachments

Uploads are persisted to private Google Cloud Storage. The `AttachmentService`
stores metadata in SQLite, returns signed delivery URLs on write, and refreshes
expired links when chat history is read. Size and retention are controlled via
`ATTACHMENTS_MAX_SIZE_BYTES` and `ATTACHMENTS_RETENTION_DAYS`. A legacy
`LEGACY_ATTACHMENTS_DIR` knob remains for MCP servers that still stage files on
disk during development.

## Notion MCP server

The backend ships with a bundled Notion MCP server (`custom-notion`). Provide a
workspace integration token before enabling it:

1. Create a Notion integration at <https://www.notion.so/profile/integrations>
   and copy the secret value.
2. Add the following variables to your `.env` file:

   ```bash
   NOTION_TOKEN=notion_secret_xxx  # or NOTION_API_KEY
   # Optional overrides:
   NOTION_VERSION=2022-06-28
   NOTION_PAGE_ID=<default parent page>
   NOTION_DATABASE_ID=<default parent database>
   ```

3. Share the desired pages or databases with the integration from the Notion
   UI so the MCP tools can access them.

The orchestrator automatically loads the exported configuration, which sets a
`custom-notion__` tool prefix to avoid collisions when other MCP servers expose
similarly named tools.

## Frontend companion app

A Svelte + TypeScript client lives in `frontend/`. It proxies `/api/*` requests
to the FastAPI backend while developing:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` in `frontend/.env` if you need to target a remote
backend.

## Documentation

Additional implementation notes (model settings, MCP orchestration, speech
settings, attachment tooling, and data layout) live in
[`docs/REFERENCE.md`](docs/REFERENCE.md).

## Testing

```bash
uv run pytest
```

The test suite currently covers attachment storage helpers, SSE parsing, and MCP
aggregation utilities.
