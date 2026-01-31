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

## Quick Reference
- Source in `src/`, tests in `tests/`; use `uv` + `.venv/`
- Python 3.11+, PEP 8, type hints, `ruff`, Pydantic models
- Async for blocking I/O; always set timeouts
- Minimal changes over rewrites; shrink codebase when possible

See [docs/AI_PLAYBOOK.md](docs/AI_PLAYBOOK.md) for full details.
