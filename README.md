# Backend_FastAPI

FastAPI backend for AI chat with MCP tool orchestration. Streams responses via SSE with integrated tool calling, presets, and multi-frontend support.

**Production**: `https://chat.jackshome.com` (Cloudflare Tunnel → Proxmox LXC 111)

## Quick Start

```bash
uv sync                    # Install all dependencies
cp .env.example .env       # Configure API keys (see .env.example)
uv run uvicorn backend.app:create_app --factory --reload --app-dir src --host 0.0.0.0 --port 8000
```

For frontend development:
```bash
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies to :8000
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐
│   LXC 110       │    │   LXC 111       │
│  mcp-servers    │◄───│ backend-fastapi │◄── chat.jackshome.com (Cloudflare Tunnel)
│ 192.168.1.110   │    │ 192.168.1.111   │
│ ports 9001-9013 │    │ port 8000       │
└─────────────────┘    └─────────────────┘
```

- **Backend**: FastAPI + Uvicorn, self-signed SSL, serves pre-built frontend SPAs from `src/backend/static/`
- **MCP tools**: 12 external servers on LXC 110 — backend is a pure client (consumer)
- **Frontends**: Svelte chat (`/`), React voice PWA (`/voice/`), kiosk (`/kiosk/`)

## API Endpoints

### Chat

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check with active model |
| POST | `/api/chat/stream` | Stream chat via SSE |
| GET | `/api/chat/generation/{id}` | Generation usage/cost |
| DELETE | `/api/chat/session/{id}` | Clear conversation |
| DELETE | `/api/chat/session/{id}/messages/{msg_id}` | Delete single message |

### Client Settings (per-client: `svelte`, `kiosk`, `cli`, etc.)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/clients/{client_id}` | Full client config |
| GET/PUT | `/api/clients/{client_id}/llm` | LLM settings (model, prompt, params) |
| GET/PUT | `/api/clients/{client_id}/tts` | TTS settings |
| GET/PUT | `/api/clients/{client_id}/stt` | STT settings |
| GET/PUT | `/api/clients/{client_id}/ui` | UI preferences |
| POST | `/api/clients/{client_id}/llm/reset` | Reset LLM to defaults |

### Presets (per-client)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/clients/{client_id}/presets` | List all presets |
| POST | `/api/clients/{client_id}/presets` | Create from current state |
| GET | `/api/clients/{client_id}/presets/by-name/{name}` | Get preset by name |
| POST | `/api/clients/{client_id}/presets/by-name/{name}/apply` | Apply preset |
| POST | `/api/clients/{client_id}/presets/by-name/{name}/set-active` | Set as default |
| DELETE | `/api/clients/{client_id}/presets/{index}` | Delete preset |

### MCP Servers

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mcp/servers/` | List servers + tool counts |
| POST | `/api/mcp/servers/connect` | Connect to a server URL |
| POST | `/api/mcp/servers/discover` | Auto-discover servers |
| POST | `/api/mcp/servers/refresh` | Hot-reload all tools |
| PATCH | `/api/mcp/servers/{id}` | Update server config |
| GET | `/api/mcp/servers/{id}/tools` | List tools for a server |
| GET/PUT | `/api/mcp/preferences/{client_id}` | Per-client tool preferences |

### Models

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/models` | List available OpenRouter models |
| GET | `/api/models/metadata` | Model filtering facets |

### Other

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/uploads` | Upload attachment (→ GCS) |
| GET | `/api/uploads/{id}/content` | Get attachment content |
| GET/POST/PUT/DELETE | `/api/suggestions` | Quick prompt suggestions |
| POST | `/api/stt/deepgram/token` | Mint browser STT token |
| GET/POST | `/api/google-auth/*` | Google OAuth flow |
| GET/POST | `/api/monarch-auth/*` | Monarch Money auth |
| GET/POST | `/api/spotify-auth/*` | Spotify auth |
| GET/POST/DELETE | `/api/alarms/*` | Alarm management |
| GET | `/api/weather` | Weather data |
| GET | `/api/kiosk/calendar` | Kiosk calendar events |
| GET | `/api/slideshow/*` | Photo slideshow |

## Project Structure

```
src/backend/
  app.py              # FastAPI factory + static file serving
  config.py           # Pydantic settings
  repository.py       # SQLite data layer
  openrouter.py       # OpenRouter API client
  routers/            # API endpoint modules
  schemas/            # Request/response models
  services/           # Business logic
  chat/
    orchestrator.py   # Chat coordination + tool loop
    mcp_client.py     # MCP protocol client
    mcp_registry.py   # Tool discovery + aggregation
    streaming/        # SSE streaming pipeline

frontend/             # Svelte chat UI → builds to src/backend/static/
frontend-voice/       # React voice PWA → builds to src/backend/static/voice/
frontend-kiosk/       # Kiosk display → builds to src/backend/static/kiosk/

data/                 # Runtime state (gitignored on server)
  mcp_servers.json    # MCP server URLs (env-specific)
  clients/            # Per-client settings + presets
  chat_sessions.db    # SQLite conversation store
  tokens/             # OAuth tokens
```

## Development & Deployment

### Local development

```bash
# Backend (auto-reloads on Python changes)
uv run uvicorn backend.app:create_app --factory --reload --app-dir src --host 0.0.0.0 --port 8000

# Frontend (proxies API to localhost:8000)
cd frontend && npm run dev
```

### Deploying changes

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the full deployment guide. Quick reference:

**Backend Python only** — auto-reloads:
```bash
git push && ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
```

**Frontend source changed** — must rebuild:
```bash
cd frontend && npm run build && cd ..
git add src/backend/static/ && git commit -m "build: rebuild frontend" && git push
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
```

**Dependencies changed**:
```bash
git push && ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && uv sync && systemctl restart backend-fastapi-dev"
```

> **Critical**: The server does NOT build frontends. If you change frontend source and don't rebuild + commit `src/backend/static/`, the deployed site will be stale.

### Server-only files (never in git)

- `.env` — API keys, production URLs
- `data/mcp_servers.json` — MCP URLs pointing to `192.168.1.110` (laptop uses localhost)
- `certs/` — self-signed SSL
- `credentials/` — Google service accounts, OAuth secrets
- `data/tokens/` — pre-authenticated OAuth tokens

## Testing

```bash
uv run pytest                              # All tests
uv run pytest tests/test_streaming.py      # Specific file
uv run pytest -v                           # Verbose
```

## Environment Variables

See `.env.example` for the full list. Required:

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | Core LLM API key |
| `GCS_BUCKET_NAME` | GCS bucket for attachments |
| `GCP_PROJECT_ID` | Google Cloud project |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON |

## Documentation

- [`.github/copilot-instructions.md`](.github/copilot-instructions.md) — **Development & deployment guide**
- [`docs/PROXMOX_DEPLOYMENT.md`](docs/PROXMOX_DEPLOYMENT.md) — Server architecture, systemd, troubleshooting
- [`docs/GCS_STORAGE.md`](docs/GCS_STORAGE.md) — Attachment storage details
- [`docs/REFERENCE.md`](docs/REFERENCE.md) — Operations reference
