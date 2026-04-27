# Copilot Instructions — Backend_FastAPI

FastAPI backend for AI chat with MCP tool orchestration.

---

## Core Operating Principles

### Prefer the best change, not the smallest
- Choose the approach that produces the cleanest, simplest, most maintainable result.
- If a rewrite is clearly better than patching, rewrite.
- Avoid layered fixes that preserve messy structure.

### Zero legacy leftovers
When changing or replacing behavior:
- Do **not** leave old code behind (no commented-out code, unused modules, dead branches).
- Remove obsolete files, configs, scripts, routes, flags, and assets.
- Repo-wide sweep for old names, config keys, dead references in docs/tests, unused imports.

### Keep the codebase shrinking
- Prefer deletion over preservation when something is no longer needed.
- Avoid parallel implementations of the same concept.

### Tests must stay relevant
- Update tests to reflect new design; remove tests for removed behavior.

### Documentation must be concise and current
- Keep docs short and correct. One source of truth per topic — don't duplicate.
- Update docs every time behavior changes. All substantial docs live under `docs/`.

### Always protect sensitive / local-only files
- Never commit secrets, credentials, tokens, real `.env`, private keys, local DBs, logs.
- If uncertain whether a file is safe to commit: assume it is not.

---

## Project Structure

- `src/backend/` — FastAPI application source
- `frontend/` — Main web UI (Svelte 5)
- `frontend-kiosk/` — Kiosk display interface
- `frontend-voice/` — Voice interaction PWA
- `frontend-cli/` — Terminal chat client (Python)
- `data/` — Runtime mutable data (preferences, DBs, tokens, uploads) — **never in git**
- `src/backend/data/clients/` — Bundled default settings (read-only fallback)
- `docs/` — Documentation (source of truth)
- `scripts/` — Automation / deployment tooling
- `tests/` — Test suite

---

## Deployment

- Use `./scripts/deploy.sh "commit message"` for all frontend changes — cleans, builds, verifies, commits, pushes, deploys
- Backend Python changes auto-reload — just `git push` then pull on server
- Server is LXC 111 at `192.168.1.111` (configured via `PROXMOX_LXC_IP` in `.env`) — **no direct SSH**; access via Proxmox host (`192.168.1.11`, configured via `PROXMOX_HOST` in `.env`) using `pct exec 111`
- Service user `backend`, public URL `https://chat.jackshome.com`
- See `docs/PROXMOX_DEPLOYMENT.md` for manual deployment steps and access patterns

### Kiosk Device — Echo Show 5
- IP: 192.168.1.28 (DHCP — may change) — configured via `ECHO_SHOW_IP` in `.env`
- Runs Fully Kiosk Browser (`de.ozerov.fully`)
- Remote Admin port: 2323 — configured via `FULLY_KIOSK_PORT` in `.env`
- Password: configured via `FULLY_KIOSK_PASSWORD` in `.env`
- ADB: `adb root` works; port forward with `adb forward tcp:2323 tcp:2323`
- Fully Kiosk prefs: `/data/data/de.ozerov.fully/shared_prefs/de.ozerov.fully_preferences.xml`
- Kiosk start URL: `https://192.168.1.111:8000/kiosk/` (always LAN, never public internet) — configured via `FULLY_KIOSK_START_URL` in `.env`

### File ownership (critical)
The backend service runs as `User=backend`. After any `git pull` or `git reset --hard` on the server, files created by git operations will be owned by `root`. The runtime `data/` directory must remain writable by the service user.

**Every deployment must include:**
```bash
chown -R backend:backend /opt/backend-fastapi/data/
```

The deploy script handles this automatically. If deploying manually, always run the chown. Symptoms of ownership problems: 500 errors on PUT/POST endpoints that write to `data/`, `PermissionError` in server logs.

---

## Architecture

- MCP tools are external (LXC 110, ports 9001–9015) — never embed tool logic in backend
- `ChatOrchestrator` coordinates streaming, tools, persistence
- `StreamingHandler` manages SSE events and tool execution loops
- Frontends build to `src/backend/static/` — server does NOT build them
- Runtime data lives in `data/` at project root (not `src/backend/data/`)

---

## Code Style

- Python ≥3.11 with `from __future__ import annotations`
- Use async for all I/O with explicit timeouts
- Type hints on all signatures; Pydantic for schemas
- Ruff for formatting, linting, import sorting
- Frontend: Svelte 5 — use modern syntax (`onclick`, `onchange`, not legacy `on:click`)
- Prefer clarity over cleverness; avoid unnecessary abstractions

---

## Security

- Never commit `.env`, `credentials/`, `certs/`, or `data/tokens/`
- Server-only files that differ from local: `data/mcp_servers.json`, `.env`
- All credentials and sensitive configuration should be stored in `.env` file
- Check `.env.example` for required environment variables and their descriptions
- Copy `.env.example` to `.env` and fill in your actual values
- Never hardcode passwords or API keys in source files or documentation

---

## After-Change Checklist

- [ ] Old code removed (no dead paths, no duplicate implementations)
- [ ] Repo-wide search for leftovers (names, config keys, references)
- [ ] Tests updated and irrelevant tests removed
- [ ] Docs updated in `docs/` (concise, non-duplicative)
- [ ] `.gitignore` updated for any new sensitive/local artifacts

---

## Primary Doc Pointers

- `docs/PROXMOX_DEPLOYMENT.md` — Server setup, deploy workflows, troubleshooting
- `docs/AI_PLAYBOOK.md` — Detailed coding guidelines for AI assistants
- `docs/DEVELOPMENT_ENVIRONMENT.md` — Local dev setup
