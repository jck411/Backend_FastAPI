# Copilot Instructions — Backend_FastAPI

FastAPI backend for AI chat with MCP tool orchestration. Deployed to Proxmox LXC 111.

## Related Repos

| Repo | Location | Purpose |
|------|----------|---------|
| mcp-servers | LXC 110 (192.168.1.110:9001-9012) | Standalone MCP tool servers |
| PROXMOX | Host (192.168.1.11) | Infrastructure scripts, service definitions |

- Backend auto-discovers MCP servers on 192.168.1.110 ports 9001–9015
- Memory tools (`remember_*`, `recall_*`) use Qdrant on LXC 110
- Conversation backup logs: `logs/conversations/memory_backups/{profile}/{date}/`

## Deployment

- LXC 111 at 192.168.1.111, port 8000 (HTTPS)
- Repo path: `/opt/Backend_FastAPI`
- Service: `systemctl restart backend-fastapi`
- Deploy: `ssh root@192.168.1.111 "cd /opt/Backend_FastAPI && git pull && systemctl restart backend-fastapi"`

## Architecture

- `src/backend/` — FastAPI app, routers, services
- `src/backend/chat/` — Streaming handler, MCP client, orchestrator
- `src/backend/services/` — Attachments, conversation logging, model settings
- Frontends: `frontend/` (Svelte), `frontend-cli/`, `frontend-kiosk/`, `frontend-voice/`

## Code Style

- Python ≥3.11; `from __future__ import annotations`
- Async for all I/O; always set timeouts
- Type hints on all signatures; Pydantic for schemas
- Ruff for linting; minimal changes over rewrites

## Key Patterns

- MCP tools are external (always-on) — never embed tool logic in backend
- `ChatOrchestrator` coordinates streaming, tools, and persistence
- `StreamingHandler` manages SSE events and tool execution loops
- Tool execution logs to `logs/conversations/` for debugging

## Security

- `.env` has secrets (gitignored), `.env.example` shows structure
- Credentials in `credentials/` (gitignored)
- HTTPS via certs in `certs/` — never commit private keys
