# Copilot Instructions — Backend_FastAPI

FastAPI backend for AI chat with MCP tool orchestration. Deployed to Proxmox LXC 111.

## Project Structure

- **Backend**: `src/backend/` — FastAPI with MCP client, AI orchestration, data management
- **Frontends** (SPAs served from `src/backend/static/`):
  - `frontend/` — Main web UI (Svelte), settings modals shared by other frontends
  - `frontend-cli/` — Terminal chat (Python)
  - `frontend-kiosk/` — Kiosk display (`/`)
  - `frontend-voice/` — Voice PWA (`/voice/`)

## Deployment

- Deploy backend: `ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && chown -R backend:backend /opt/backend-fastapi/src/backend/data/ && systemctl restart backend-fastapi-dev"`
- Build voice frontend locally: `cd frontend-voice && npm run build` (outputs to `src/backend/static/voice/`)
- Commit built frontend assets before deploying — server serves pre-built static files
- Use `git stash && git pull` on server if local settings files conflict

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
