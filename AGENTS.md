# Agents Guide

## Project Snapshot

- **Project**: FastAPI backend proxy for OpenRouter with MCP servers
- **Core**: Streams SSE chat completions, integrates Google APIs, stores history in SQLite
- **Key Tech**: FastAPI · Python 3.13+ · aiosqlite · OpenRouter API · MCP · Svelte/TS frontend

## Structure

- `app.py` → FastAPI factory
- `routers/` → API endpoints
- `services/` → business logic
- `chat/` → orchestrator + MCP clients
- `mcp_servers/` → individual tools
- `data/` → SQLite + configs

## MCP Notes

- Each server lives under `mcp_servers/`
- Managed by `MCPToolAggregator`
- Tool names are prefixed by server ID

## Dev Standards

- Async everywhere; type hints required
- Lint with Ruff (PEP 8 + import sorting)
- Tests via `pytest` + `pytest-asyncio`
- Manage dependencies with `uv`; sync via `uv sync`

## Security & Performance

- No secrets in code (use `.env`)-
- feel free to edit the .env
- Enforce upload limits and safe paths
- Stream with SSE and reuse HTTP clients

## Quick Start

- `uv run uvicorn backend.app:create_app --factory --reload`
- `cd frontend && npm run dev`
