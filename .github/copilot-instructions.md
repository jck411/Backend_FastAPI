# Copilot Instructions — Backend_FastAPI

FastAPI backend for AI chat with MCP tool orchestration. Deployed to Proxmox LXC 111. Public: `https://chat.jackshome.com`.

## Project Structure

- **Backend**: `src/backend/` — FastAPI with MCP client, AI orchestration, data management
- **Frontends** (SPAs served from `src/backend/static/`):
  - `frontend/` — Main web UI (Svelte), settings modals shared by other frontends
  - `frontend-cli/` — Terminal chat (Python)
  - `frontend-kiosk/` — Kiosk display (`/`)
  - `frontend-voice/` — Voice PWA (`/voice/`)

## Deployment

**Server**: LXC 111 at `/opt/backend-fastapi/`, branch `master`, systemd `backend-fastapi-dev` (auto-reloads Python changes).
**Public URL**: `https://chat.jackshome.com` (Cloudflare Tunnel).

### What type of change did you make?

#### Backend Python only (`src/backend/`)
Auto-reloads — just push and pull:
```bash
git push
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
```

#### Frontend source (`frontend/`, `frontend-voice/`, `frontend-kiosk/`)
**The server does NOT build frontends.** It serves pre-built files from `src/backend/static/`.
If you skip the rebuild, the deployed site stays STALE.
```bash
# 1. Rebuild whichever frontend(s) you changed:
cd frontend && npm run build && cd ..           # → src/backend/static/
cd frontend-voice && npm run build && cd ..     # → src/backend/static/voice/
cd frontend-kiosk && npm run build && cd ..     # → src/backend/static/kiosk/

# 2. Commit the built output + your source changes:
git add src/backend/static/ && git commit -m "build: rebuild frontends"
git push

# 3. Pull on server:
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
```

#### Dependencies changed (`pyproject.toml`)
```bash
git push
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && uv sync && systemctl restart backend-fastapi-dev"
```

#### Nuclear option (full reset)
Use when git pull fails or you need a clean slate. Safe — this preserves `data/` and `.env`:
```bash
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git fetch origin && git reset --hard origin/master && chown -R backend:backend /opt/backend-fastapi/src/backend/data/ && systemctl restart backend-fastapi-dev"
```

### Server-only files (never in git)
These live only on the server and must not be overwritten:
- `.env` — API keys, production URLs
- `data/mcp_servers.json` — MCP server URLs pointing to `192.168.1.110` (laptop uses localhost)
- `certs/` — self-signed SSL certs
- `credentials/` — Google service accounts and OAuth secrets
- `data/tokens/` — pre-authenticated OAuth tokens

## Architecture

- MCP tools are external (LXC 110, ports 9001–9015) — never embed tool logic in backend
- `ChatOrchestrator` coordinates streaming, tools, and persistence
- `StreamingHandler` manages SSE events and tool execution loops

## Code Style

- Python ≥3.11; use `from __future__ import annotations`
- Async for all I/O; always set timeouts
- Type hints on all signatures; Pydantic for schemas
- Prefer minimal targeted edits over rewrites

## Security

- Never commit `.env`, `credentials/`, `certs/`, or `data/tokens/`
- Check `.env.example` for required environment variables
