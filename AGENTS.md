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

## Environment Setup

- Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if it's not already available
- Create the local environment and install deps via `uv sync`
- Copy any secret material into `.env` (never commit it) and keep Google OAuth JSON files under `credentials/`
- For MCP extras you can add additional servers under `src/backend/mcp_servers/`

## Security & Performance

- No secrets in code (use `.env`)
- Feel free to edit the `.env` locally but keep it out of git
- Enforce upload limits and safe paths
- Stream with SSE and reuse HTTP clients

## Quick Start

- `uv sync`
- `uv run uvicorn backend.app:create_app --factory --reload`
- `cd frontend && npm run dev`

## Testing

- Always run tests through uv: `uv run pytest`
- If pytest fails with missing FastAPI/Pydantic/MCP packages, rerun `uv sync` to hydrate the virtualenv
- Tests touch SQLite files in `data/`; they clean up automatically but keep an eye on local changes
