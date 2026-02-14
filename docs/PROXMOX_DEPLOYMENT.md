# Backend_FastAPI Proxmox Deployment

**LXC 111** · `192.168.1.111:8000` · Public: `https://chat.jackshome.com`

---

## Architecture

```
                    ┌──────────────────┐
                    │   Cloudflare     │
                    │   Tunnel         │
                    │                  │
                    │ chat.jackshome.  │
                    │     com          │
                    └────────┬─────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│                  PROXMOX HOST  192.168.1.11                 │
│                  cloudflared ───┘                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │   LXC 110       │    │   LXC 111       │                │
│  │  mcp-servers    │◄───│ backend-fastapi │                │
│  │ 192.168.1.110   │    │ 192.168.1.111   │                │
│  │ ports 9001-9013 │    │ port 8000       │                │
│  └─────────────────┘    └────────▲────────┘                │
│                                  │                          │
└──────────────────────────────────┼──────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
        Kiosk (/)          Chat (/chat/)        Voice (/voice/)
        Echo Show            Svelte               React PWA
```

- **Backend**: Uvicorn serving FastAPI + static frontends via self-signed SSL
- **MCP tools**: 12 servers on LXC 110 (ports 9001–9013) — backend connects over LAN
- **Tunnel**: `cloudflared` on Proxmox host routes `chat.jackshome.com` → `https://192.168.1.111:8000` (noTLSVerify)
- **Branch**: `master` (production `mcp_servers.json` with remote URLs is gitignored and maintained manually on server)

## Container Specs

| | |
|-|-|
| **OS** | Debian 13 (unprivileged, nesting=1, onboot=1) |
| **Resources** | 2 cores · 2GB RAM · 512MB swap · 24GB disk (local-lvm) |
| **Service user** | `backend` (nologin) |
| **Code** | `/opt/backend-fastapi/` |
| **Python** | uv-managed venv at `.venv/` |

## Frontends

| Path | Frontend | Source Dir | Build Command |
|------|----------|-----------|---------------|
| `/` | Kiosk | `frontend-kiosk/` | `cd frontend-kiosk && npm run build` |
| `/chat/` | Main Chat | `frontend/` | `cd frontend && npm run build` |
| `/voice/` | Voice PWA | `frontend-voice/` | `cd frontend-voice && npm run build` |

Builds output to `src/backend/static/`. The server does NOT build frontends — serve pre-built files only.

## Systemd Services

Two mutually exclusive services (Conflicts= prevents both running):

| Service | Use | Key Flags |
|---------|-----|-----------|
| `backend-fastapi-dev` | Active development | `--reload --reload-dir=src` |
| `backend-fastapi-prod` | Stable / lower CPU | `--workers 2 --log-level warning` |

```bash
# Switch modes
systemctl disable --now backend-fastapi-dev && systemctl enable --now backend-fastapi-prod
systemctl disable --now backend-fastapi-prod && systemctl enable --now backend-fastapi-dev

# Check which is active
systemctl is-active backend-fastapi-dev backend-fastapi-prod
```

## Update Workflow — What type of change did you make?

### Backend Python only (`src/backend/`)

Dev mode auto-reloads — just push and pull:
```bash
git push
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
```

### Frontend source (`frontend/`, `frontend-voice/`, `frontend-kiosk/`)

**The server does NOT build frontends.** If you skip the rebuild, the deployed site stays STALE.
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

### Dependencies changed (`pyproject.toml`)
```bash
git push
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && uv sync && systemctl restart backend-fastapi-dev"
```

### Nuclear option (full reset)

Use when `git pull` fails or you need a clean slate. Safe — preserves `.env` and `data/`:
```bash
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git fetch origin && git reset --hard origin/master && chown -R backend:backend /opt/backend-fastapi/src/backend/data/ && systemctl restart backend-fastapi-dev"
```

### Logs
```bash
ssh root@192.168.1.111 "journalctl -u backend-fastapi-dev -f"
```

### Server-only files (never in git)

These live only on the server and must not be overwritten:
- `.env` — API keys, production URLs
- `data/mcp_servers.json` — MCP server URLs pointing to `192.168.1.110` (laptop uses localhost)
- `certs/` — self-signed SSL certs
- `credentials/` — Google service accounts and OAuth secrets
- `data/tokens/` — pre-authenticated OAuth tokens

## Secrets

Environment variables in `/opt/backend-fastapi/.env`:

| Variable | Required | Notes |
|----------|----------|-------|
| `OPENROUTER_API_KEY` | Yes | Core LLM API |
| `GCS_BUCKET_NAME` | Yes | Attachment storage |
| `GCP_PROJECT_ID` | Yes | GCS project |
| `DEEPGRAM_API_KEY` | Optional | Browser STT tokens |
| `ACCUWEATHER_API_KEY` | Optional | Kiosk weather |
| `ACCUWEATHER_LOCATION_KEY` | Optional | Kiosk weather |
| `ELEVENLABS_API_KEY` | Optional | TTS provider |
| `OPENAI_API_KEY` | Optional | TTS provider |

Credential files:

| File | Required | Notes |
|------|----------|-------|
| `credentials/googlecloud/sa.json` | Yes | GCS service account |
| `credentials/client_secret_*.json` | For OAuth | Google OAuth client |
| `data/tokens/*.json` | For OAuth | Pre-authenticated tokens |
| `certs/server.key` + `server.crt` | Yes | SSL (self-signed) |

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Health check fails | `ssh root@192.168.1.111 "curl -sk https://localhost:8000/health"` |
| Service won't start | `journalctl -u backend-fastapi-dev -n 50` |
| MCP tools unavailable | `curl http://192.168.1.110:9003/mcp` (check LXC 110) |
| Tunnel not working | `ssh root@192.168.1.11 "systemctl status cloudflared"` |
| Frontend stale | Rebuild on laptop, commit static/, push, pull on server |
