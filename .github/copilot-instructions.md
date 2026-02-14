# Copilot Instructions — Backend_FastAPI

FastAPI backend for AI chat with MCP tool orchestration. Deployed to Proxmox LXC 111.

## Project Structure

- **Backend**: `src/backend/` — FastAPI with MCP client, AI orchestration, data management
- **Frontends** (SPAs served from `src/backend/static/`):
  - `frontend/` — Main web UI (Svelte), settings modals shared by other frontends
  - `frontend-cli/` — Terminal chat (Python)
  - `frontend-kiosk/` — Kiosk display (`/`)
  - `frontend-voice/` — Voice PWA (`/voice/`)

## Deployment — CRITICAL: Rebuild Frontends Before Deploying

**The server does NOT build frontends. It serves pre-built files from `src/backend/static/`.**
**If you change ANY frontend source and don't rebuild + commit, the deployed site will be STALE.**

After ANY change to frontend source, you MUST:

1. **Rebuild** the changed frontend(s):
   - `frontend/` → `cd frontend && npm run build` (outputs to `src/backend/static/`)
   - `frontend-voice/` → `cd frontend-voice && npm run build` (outputs to `src/backend/static/voice/`)
   - `frontend-kiosk/` → `cd frontend-kiosk && npm run build` (outputs to `src/backend/static/kiosk/`)
2. **Commit the built output**: `git add src/backend/static/ && git commit -m "build: rebuild frontends"`
3. **Push**: `git push`
4. **Deploy**: from Proxmox LXC 111 console:
   ```
   pct exec 111 -- bash -c "cd /opt/backend-fastapi && git fetch origin && git reset --hard origin/master && chown -R backend:backend /opt/backend-fastapi/src/backend/data/ && systemctl restart backend-fastapi-dev"
   ```

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
