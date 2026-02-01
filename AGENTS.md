# GitHub Copilot Instructions

These guidelines help Copilot generate code consistent with this repo.

## Project Structure
- **Backend**: `src/backend/` - FastAPI backend with MCP servers, AI orchestration, and data management
- **Frontends**:
  - `frontend/` - Main web UI (Svelte), also contains settings modals for other frontends
  - `frontend-cli/` - Terminal-based chat interface (Python)
  - `frontend-kiosk/` - Kiosk display interface
  - `frontend-voice/` - Voice interaction PWA

## Rule 0: Context7
- If the **Context7** MCP server is available, consult its docs before architectural or dependency changes. If unavailable, rely on existing repo docs and established patterns.

## Available MCP Servers
The following MCP servers are configured and available:

- **Context7**: Query up-to-date library docs (FastAPI, Pydantic, Svelte, etc.). Use before adding dependencies or changing architectures.
- **SQLite**: Query `data/chat_sessions.db` for conversation history, debugging data issues, analyzing chat patterns.
- **Filesystem**: Read/write files in workspace. Use for logs, data files, credentials, uploads, client profiles.
- **Playwright**: Browser automation, web scraping, E2E testing. Use for testing frontend or web interactions.
- **Chrome DevTools**: Performance analysis, network monitoring, debugging. Use for frontend performance issues.

## Quick Reference
- Source in `src/`, tests in `tests/`; use `uv` + `.venv/`
- Python 3.11+, PEP 8, type hints, `ruff`, Pydantic models
- Async for blocking I/O; always set timeouts
- Minimal changes over rewrites; shrink codebase when possible

See [docs/AI_PLAYBOOK.md](docs/AI_PLAYBOOK.md) for full details.
