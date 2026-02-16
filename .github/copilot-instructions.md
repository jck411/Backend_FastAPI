# Copilot Instructions — Backend_FastAPI

FastAPI backend for AI chat with MCP tool orchestration.

## Deployment

- Use `./scripts/deploy.sh "commit message"` for all frontend changes — cleans, builds, verifies, commits, pushes, deploys
- Backend Python changes auto-reload — just `git push` then `git pull` on server
- Server is LXC 111 at `192.168.1.111`, public URL `https://chat.jackshome.com`
- See `docs/PROXMOX_DEPLOYMENT.md` for manual deployment steps

## Architecture

- MCP tools are external (LXC 110, ports 9001–9015) — never embed tool logic in backend
- `ChatOrchestrator` coordinates streaming, tools, persistence
- `StreamingHandler` manages SSE events and tool execution loops
- Frontends build to `src/backend/static/` — server does NOT build them

## Code Style

- Use Python ≥3.11 with `from __future__ import annotations`
- Use async for all I/O with explicit timeouts
- Add type hints on all signatures; use Pydantic for schemas
- Prefer minimal targeted edits over rewrites

## Security

- Never commit `.env`, `credentials/`, `certs/`, or `data/tokens/`
- Server-only files that differ from local: `data/mcp_servers.json`, `.env`
- Check `.env.example` for required environment variables
