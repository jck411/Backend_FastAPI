# OpenRouter Chat Backend

FastAPI backend that proxies streaming chat completions from OpenRouter with integrated Model Context Protocol (MCP) tools. Responses stream over Server-Sent Events (SSE) for real-time rendering.

## Key Features

- **Streaming chat** via OpenRouter API with HTTP keep-alive for fast response times
- **Configurable LLM planning** — Optional AI-driven tool selection for optimized context
- **Persistent chat history** with GCS-backed attachment storage and automatic cleanup
- **MCP tool aggregation** — Google Calendar, Gmail, Drive, PDF extraction, Monarch Money, and custom utilities
- **Speech-to-text** — Mint short-lived Deepgram tokens for browser-based voice input
- **Presets** — Save and restore complete chat configurations (model, tools, prompts)
- **OAuth integrations** — Google, Monarch Money, and Spotify authentication flows

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
   GOOGLE_APPLICATION_CREDENTIALS=credentials/googlecloud/sa.json

   # Optional defaults
   OPENROUTER_DEFAULT_MODEL=openai/gpt-4
   OPENROUTER_SYSTEM_PROMPT="You are a helpful assistant."
   ATTACHMENTS_MAX_SIZE_BYTES=10485760  # 10MB
   ATTACHMENTS_RETENTION_DAYS=7

   # Frontend URL (for OAuth redirects)
   FRONTEND_URL=http://localhost:5173
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/google-auth/callback

   # Optional: Deepgram for speech-to-text
   DEEPGRAM_API_KEY=...
   DEEPGRAM_TOKEN_TTL=30
   ```

4. **Add Google credentials**:
   - Place service account JSON at `credentials/googlecloud/sa.json`
   - For OAuth flows, add client credentials to `credentials/`

5. **Run the server**:
   ```bash
   uv run uvicorn backend.app:create_app --factory --reload --app-dir src
   ```

   Alternative commands:
   ```bash
   uv run backend  # CLI wrapper with defaults (host 0.0.0.0, port 8000)
   ```

## API Endpoints

### Core Chat

| Method & Path | Description |
|---------------|-------------|
| `GET /health` | Health check with active model info |
| `POST /api/chat/stream` | Stream chat completions via SSE |
| `GET /api/chat/test-stream` | Test SSE stream for debugging |
| `GET /api/chat/generation/{id}` | Get generation usage/cost details |
| `DELETE /api/chat/session/{id}` | Clear conversation history |
| `DELETE /api/chat/session/{id}/messages/{msg_id}` | Delete a single message |

### Models & Settings

| Method & Path | Description |
|---------------|-------------|
| `GET /api/models` | List available OpenRouter models |
| `GET /api/models/metadata` | Get model filtering metadata/facets |
| `GET /api/settings/model` | Get current model settings |
| `PUT /api/settings/model` | Update model configuration |
| `GET /api/settings/model/active-provider` | Get active provider info |
| `GET /api/settings/system-prompt` | Get system prompt |
| `PUT /api/settings/system-prompt` | Update system prompt |

### Attachments & Uploads

| Method & Path | Description |
|---------------|-------------|
| `POST /api/uploads` | Upload attachment, returns signed GCS URL |

### MCP Servers

| Method & Path | Description |
|---------------|-------------|
| `GET /api/mcp/servers` | List MCP server configurations |
| `PUT /api/mcp/servers` | Replace all MCP server configs |
| `PATCH /api/mcp/servers/{id}` | Update a single MCP server |
| `POST /api/mcp/servers/refresh` | Hot-reload MCP tools |

### Presets

| Method & Path | Description |
|---------------|-------------|
| `GET /api/presets/` | List saved presets |
| `GET /api/presets/default` | Get the default preset |
| `GET /api/presets/{name}` | Get a specific preset |
| `POST /api/presets/` | Create new preset from current state |
| `PUT /api/presets/{name}` | Save snapshot to existing preset |
| `DELETE /api/presets/{name}` | Delete a preset |
| `POST /api/presets/{name}/set-default` | Mark preset as default |
| `POST /api/presets/{name}/apply` | Apply saved preset |

### Suggestions

| Method & Path | Description |
|---------------|-------------|
| `GET /api/suggestions` | Get quick prompt suggestions |
| `POST /api/suggestions` | Add a new suggestion |
| `PUT /api/suggestions` | Replace all suggestions |
| `DELETE /api/suggestions/{index}` | Delete a suggestion by index |

### Speech-to-Text

| Method & Path | Description |
|---------------|-------------|
| `POST /api/stt/deepgram/token` | Mint browser STT token |

### OAuth Authentication

| Method & Path | Description |
|---------------|-------------|
| `GET /api/google-auth/status` | Check Google OAuth status |
| `POST /api/google-auth/authorize` | Start Google OAuth flow |
| `GET /api/google-auth/callback` | Google OAuth callback |
| `GET /api/monarch-auth/status` | Check Monarch Money auth status |
| `POST /api/monarch-auth/login` | Login to Monarch Money |
| `GET /api/spotify-auth/status` | Check Spotify auth status |
| `POST /api/spotify-auth/authorize` | Start Spotify OAuth flow |
| `GET /api/spotify-auth/callback` | Spotify OAuth callback |

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
  __init__.py         # Package exports create_app
  app.py              # FastAPI factory and lifespan
  main.py             # CLI entrypoint (uvicorn wrapper)
  config.py           # Settings via Pydantic
  repository.py       # SQLite data layer
  openrouter.py       # OpenRouter API client
  logging_handlers.py # Custom log handlers
  logging_settings.py # Log configuration parser
  routers/            # API endpoint modules
  schemas/            # Pydantic request/response models
  services/           # Business logic layer
  tasks/              # Background task definitions
  utils/              # Shared utilities
  chat/
    orchestrator.py   # Main chat coordination
    mcp_client.py     # MCP client wrapper
    mcp_registry.py   # MCP tool aggregator
    tool_utils.py     # Tool handling utilities
    streaming/        # Streaming pipeline modules

data/                 # Runtime state (gitignored)
  chat_sessions.db    # SQLite database
  model_settings.json # Active model config
  presets.json        # Saved presets
  suggestions.json    # Quick prompt suggestions
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

### MCP Tool Integration

MCP servers run as external services on Proxmox and are configured in `data/mcp_servers.json`. Available integrations:

- **Google Calendar** — create/search events
- **Gmail** — read/send messages, manage drafts
- **Google Drive** — search/read/create files
- **PDF tools** — extract text and metadata
- **Monarch Money** — personal finance data and transactions
- **Housekeeping** — utilities and system helpers

Servers are always-on systemd services discovered by URL. The backend acts as a pure MCP client (consumer), connecting to running servers and routing tool calls.

### Presets

Save complete configurations (model, tools, prompt, parameters) and restore them later. Presets capture:
- Active model ID
- Provider/parameter overrides
- System prompt
- Enabled MCP servers
- Model filter settings

Use the UI or the `/api/presets/` endpoints. You can set a default preset to auto-load on startup.

## Testing

```bash
uv run pytest              # Run all tests
uv run pytest tests/test_attachments.py  # Specific test file
uv run pytest -v          # Verbose output
```

Tests use isolated SQLite databases in `tests/data/` and clean up automatically.

## Documentation

- **[REFERENCE.md](docs/REFERENCE.md)** — Operations guide, system details, troubleshooting
- **[GCS_STORAGE.md](docs/GCS_STORAGE.md)** — GCS attachment storage implementation
- **[echo/](docs/echo/)** — Echo Show kiosk setup, memory optimization, and troubleshooting

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
- Verify required env vars (e.g., Google OAuth credentials) are set
- Use `POST /api/mcp/servers/refresh` to hot-reload

**Tests failing:**
- Run `uv sync` to ensure dependencies are current
- Check `tests/data/` for stale SQLite files (usually auto-cleaned)

## License

See LICENSE file for details.
