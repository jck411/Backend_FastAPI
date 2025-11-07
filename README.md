# OpenRouter Chat Backend

FastAPI backend that proxies streaming chat completions from OpenRouter with integrated Model Context Protocol (MCP) tools. Responses stream over Server-Sent Events (SSE) for real-time rendering.

## Key Features

- **Streaming chat** via OpenRouter API with HTTP keep-alive for fast response times
- **LLM-based context planning** — AI-driven tool selection without hardcoded keyword rules
- **Persistent chat history** with GCS-backed attachment storage and automatic cleanup
- **MCP tool aggregation** — Google Calendar, Gmail, Drive, Notion, PDF extraction, and custom utilities
- **Speech-to-text** — Mint short-lived Deepgram tokens for browser-based voice input
- **Presets** — Save and restore complete chat configurations (model, tools, prompts)

## Requirements

- **Python 3.13+**
- **[uv](https://github.com/astral-sh/uv)** for dependency and environment management
- **Google Cloud** credentials for attachment storage (service account JSON)
- **Environment variables** in `.env` (see Setup below)

## Quick Start

1. **Install uv** if you haven't already:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone and setup**:
   ```bash
   uv sync  # Creates .venv/ and installs all dependencies
   ```

3. **Configure environment** — create `.env` in project root:
   ```bash
   # Required
   OPENROUTER_API_KEY=sk-or-v1-...

   # Google Cloud Storage (for attachments)
   GCS_BUCKET_NAME=your-bucket-name
   GCP_PROJECT_ID=your-project-id
   GOOGLE_APPLICATION_CREDENTIALS=credentials/sa.json

   # Optional defaults
   OPENROUTER_DEFAULT_MODEL=openai/gpt-4
   OPENROUTER_SYSTEM_PROMPT="You are a helpful assistant."
   USE_LLM_PLANNER=true
   ATTACHMENTS_MAX_SIZE_BYTES=10485760  # 10MB
   ATTACHMENTS_RETENTION_DAYS=7

   # Optional: Notion integration
   NOTION_TOKEN=notion_secret_xxx

   # Optional: Deepgram for speech-to-text
   DEEPGRAM_API_KEY=...
   ```

4. **Add Google credentials**:
   - Place service account JSON at `credentials/sa.json`
   - For OAuth flows, add client credentials to `credentials/`

5. **Run the server**:
   ```bash
   uv run uvicorn backend.app:app --reload --app-dir src
   ```

   Alternative commands:
   ```bash
   uv run uvicorn backend.app:create_app --factory --reload  # Factory pattern
   uv run backend  # CLI wrapper with defaults
   ```

## API Endpoints

| Method & Path | Description |
|---------------|-------------|
| `GET /health` | Health check with active model info |
| `POST /api/chat/stream` | Stream chat completions via SSE |
| `DELETE /api/chat/session/{id}` | Clear conversation history |
| `GET /api/models` | List available OpenRouter models |
| `GET /api/settings/model` | Get current model settings |
| `PUT /api/settings/model` | Update model configuration |
| `GET /api/settings/system-prompt` | Get system prompt |
| `PUT /api/settings/system-prompt` | Update system prompt |
| `POST /api/uploads` | Upload attachment, returns signed GCS URL |
| `GET /api/mcp/servers` | List MCP server configurations |
| `PUT /api/mcp/servers` | Update MCP servers (hot-reload) |
| `GET /api/presets/` | List saved presets |
| `POST /api/presets/` | Create new preset from current state |
| `POST /api/presets/{name}/apply` | Apply saved preset |
| `POST /api/stt/deepgram/token` | Mint browser STT token |

### Example: Stream a chat

```bash
curl -N \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{
        "model": "openrouter/auto",
        "messages": [{"role": "user", "content": "Hello!"}]
      }' \
  http://localhost:8000/api/chat/stream
```

## Project Structure

```
src/backend/
  app.py              # FastAPI factory
  config.py           # Settings via Pydantic
  repository.py       # SQLite data layer
  routers/            # API endpoints
  services/           # Business logic
  chat/
    orchestrator.py   # Main chat coordination
    llm_planner.py    # LLM-based tool selection
    mcp_registry.py   # MCP tool aggregator
  mcp_servers/        # Bundled MCP integrations

data/                 # Runtime state (gitignored)
  chat_sessions.db    # SQLite database
  model_settings.json # Active model config
  presets.json        # Saved presets
  mcp_servers.json    # MCP configurations
  tokens/             # OAuth tokens

tests/                # Pytest suite
frontend/             # Svelte + TypeScript UI
```

## Frontend Development

The Svelte UI is in `frontend/` and proxies API requests during development:

```bash
cd frontend
npm install
npm run dev  # Defaults to http://localhost:5173
```

Configure backend URL in `frontend/.env`:
```bash
VITE_API_BASE_URL=http://localhost:8000
```

## Feature Highlights

### Attachments

All uploads (images, PDFs) are stored in **private Google Cloud Storage**:
- Metadata stored in SQLite
- Signed URLs with configurable expiration (default 7 days)
- Automatic URL refresh when serving chat history
- Background cleanup job removes expired attachments

Supported types: `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `application/pdf`

### LLM Context Planning

By default, an LLM planner selects which tools to make available based on conversation context. This eliminates brittle keyword-based rules. Toggle with `USE_LLM_PLANNER=true/false`.

See [`docs/LLM_PLANNER.md`](docs/LLM_PLANNER.md) for details.

### MCP Tool Integration

MCP servers are configured in `data/mcp_servers.json` and hot-reloaded via API. Built-in integrations:

- **Google Calendar** — create/search events
- **Gmail** — read/send messages, manage drafts
- **Google Drive** — search/read/create files
- **Notion** — create/search pages, manage databases
- **PDF tools** — extract text and metadata
- **Calculator & utilities** — housekeeping helpers

Each server's tools are prefixed (e.g., `custom-notion__notion_search`) to avoid naming conflicts.

### Notion Setup

1. Create integration at https://www.notion.so/profile/integrations
2. Add `NOTION_TOKEN=notion_secret_xxx` to `.env`
3. Share target pages/databases with your integration
4. Enable in MCP settings via UI or API

See [`docs/NOTION_REMINDERS.md`](docs/NOTION_REMINDERS.md) for usage patterns.

### Presets

Save complete configurations (model, tools, prompt, parameters) and restore them later. Presets capture:
- Active model ID
- Provider/parameter overrides
- System prompt
- Enabled MCP servers

Use the UI or `GET/POST /api/presets/` endpoints.

## Testing

```bash
uv run pytest              # Run all tests
uv run pytest tests/test_attachments.py  # Specific test file
uv run pytest -v          # Verbose output
```

Tests use isolated SQLite databases in `tests/data/` and clean up automatically.

## Documentation

- **[REFERENCE.md](docs/REFERENCE.md)** — Operations guide, system details, troubleshooting
- **[LLM_PLANNER.md](docs/LLM_PLANNER.md)** — LLM-based context planning architecture
- **[NOTION_REMINDERS.md](docs/NOTION_REMINDERS.md)** — Notion MCP usage patterns
- **[GCS_STORAGE.md](docs/GCS_STORAGE.md)** — GCS attachment storage implementation

## Development Guidelines

- **Code style**: PEP 8, type hints required, `ruff` for linting
- **Async first**: Use `async`/`await` for all I/O operations
- **Error handling**: Fail fast with clear errors, catch broad exceptions only at boundaries
- **Tests**: `pytest` + `pytest-asyncio`, one test file per module
- **Dependencies**: Manage via `uv`, sync with `uv sync`
- **Secrets**: Never commit credentials, use `.env` only

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for AI agent guidelines.

## Troubleshooting

**Import errors after adding dependencies:**
```bash
uv sync  # Regenerate .venv
```

**Attachments not uploading:**
- Verify GCS bucket exists and service account has `storage.objects.create` permission
- Check `GOOGLE_APPLICATION_CREDENTIALS` points to valid JSON

**MCP tools not appearing:**
- Check `data/mcp_servers.json` has enabled servers
- Verify required env vars (e.g., `NOTION_TOKEN`) are set
- Use `POST /api/mcp/servers/refresh` to hot-reload

**Tests failing:**
- Run `uv sync` to ensure dependencies are current
- Check `tests/data/` for stale SQLite files (usually auto-cleaned)

## License

See LICENSE file for details.
