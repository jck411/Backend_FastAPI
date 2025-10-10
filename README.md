# OpenRouter Chat Backend

FastAPI backend that proxies streaming chat completions from OpenRouter and exposes a Model Context Protocol (MCP) server. All chat responses are streamed over Server-Sent Events (SSE), making it simple to drive a reactive frontend.

## Prerequisites

- Python 3.13+
- [`uv`](https://github.com/astral-sh/uv) for dependency and task management
- `.env` file populated with at least `OPENROUTER_API_KEY` (see `.env` in the repository root for an example)

## Install dependencies

```bash
uv sync
```

`uv` will create and reuse a virtual environment under `.venv`.

## Run the FastAPI server

Recommended (reload, dev):

```bash
uv run uvicorn backend.app:app --reload --app-dir src
```

Alternate (without reload):

```bash
uv run python -m uvicorn backend.app:app --app-dir src
```

If you prefer the FastAPI CLI, ensure `fastapi[standard]` is installed (included in this project) and run:

```bash
uv run fastapi dev backend.app:app --app-dir src
```

You can also use the CLI entrypoint:

```bash
uv run backend
```

The service exposes a clean API surface that any client (web, desktop, mobile) can consume:

- `GET /health` — quick readiness probe that also reports the configured default model.
- `POST /api/chat/stream` — accepts an OpenRouter-compatible chat body and streams completions via SSE.
- `GET /api/models` — returns the upstream OpenRouter model catalog so the frontend can offer a picker.
- `POST /api/stt/deepgram/token` — optional helper to mint short-lived Deepgram access tokens without exposing API keys to clients.

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

## Frontend (Svelte)

A Svelte + TypeScript client lives in `frontend/`. It proxies `/api/*` calls to the FastAPI backend during development and ships with a model explorer for filtering OpenRouter models.

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` in `frontend/.env` if you need to target a remote backend instead of the local proxy.

## Documentation

- Models, Active Settings, and Presets: [docs/MODELS_AND_PRESETS.md](docs/MODELS_AND_PRESETS.md)

## MCP server aggregation

The chat orchestrator can launch multiple MCP servers and expose their tools via OpenRouter. Server definitions live in `data/mcp_servers.json` and can be enabled or disabled without code changes.

```json
{
  "servers": [
    {
      "id": "local-calculator",
      "module": "backend.mcp_server"
    },
    {
      "id": "google-workspace",
      "command": ["uvx", "google-workspace-mcp"],
      "enabled": true
    },
    {
      "id": "test-toolkit",
      "module": "backend.mcp_servers.sample_server",
      "enabled": false
    }
  ]
}
```

Each entry must supply either a Python module (`module`) launched with `python -m`, or an explicit `command` array. Set `enabled` to `false` to keep a definition available without starting it. When multiple servers expose tools with the same name, the orchestrator automatically prefixes them with the server id to keep them unique.

The built-in `test-toolkit` server exposes two simple tools (`test_echo` and `current_time`) that are useful for validating aggregation end-to-end. Toggle `enabled` to `true` in `data/mcp_servers.json` to include it alongside the calculator or third-party MCP servers.

## Run the MCP server

The MCP server exposes a `chat.completions` tool that mirrors the OpenRouter request schema and returns the final assistant message (including any streamed tool call arguments).

```bash
uv run python -m backend.mcp_server
```

Note: This repo uses a `src/` layout. When using uvicorn or the FastAPI CLI, pass `--app-dir src`. If you run Python directly, ensure `PYTHONPATH` includes `src` (uv/pytest already do):

```bash
PYTHONPATH=src uv run python -c "import backend, sys; print('ok')"
```

Factory-style alternative (optional):

```bash
uv run uvicorn backend.app:create_app --reload --factory --app-dir src
```

## Testing

```bash
uv run pytest
```

The test suite covers the SSE parser and MCP tool-call aggregation helpers.
