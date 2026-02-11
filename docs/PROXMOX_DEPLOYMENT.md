# Backend_FastAPI Proxmox Deployment

**Status:** ✅ Stages 1-6 Complete — All Frontends Deployed
**Target:** LXC 111 @ `192.168.1.111:8000`
**Started:** February 10, 2026

---

## Overview

Deploying Backend_FastAPI from the Dell XPS 13 development laptop to a dedicated Proxmox LXC container. This makes the backend always-available for frontends and devices (especially the Echo Show kiosk).

**Why now:**
- MCP servers already run on Proxmox (CT 110 @ 192.168.1.110)
- Backend API is stable
- Deployed backend = always-on for frontend development
- Kiosk needs network-accessible backend (can't reach localhost on laptop)
- Update workflow is trivial: `git pull && systemctl restart`

---

## Stage Checklist

### Stage 1: Prep Credentials & Config
**Status:** ✅ Complete
**Time:** ~15 min
**Location:** Laptop only

- [x] Create `credentials/googlecloud/` directory structure
- [x] Copy GCS service account JSON to `credentials/googlecloud/sa.json`
- [x] Create `.env.production` with production URLs:
  ```
  FRONTEND_URL=https://192.168.1.111:8000
  GOOGLE_OAUTH_REDIRECT_URI=https://192.168.1.111:8000/api/google-auth/callback
  ```
- [x] Verify `data/mcp_servers.json` uses `192.168.1.110` URLs (not localhost)
- [x] List all required env vars (see Secrets Inventory below)

---

### Stage 2: Create LXC Container
**Status:** ✅ Complete
**Time:** ~10 min
**Location:** SSH to Proxmox host (192.168.1.11)

Commands:
```bash
# On Proxmox host
pct create 111 local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst \
  --hostname backend-fastapi \
  --memory 2048 \
  --swap 512 \
  --cores 2 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.1.111/24,gw=192.168.1.1 \
  --nameserver "1.1.1.1 8.8.8.8" \
  --onboot 1 \
  --features nesting=1 \
  --unprivileged 1

pct start 111
```

- [x] Container created and started
- [x] Can SSH: `ssh root@192.168.1.111`
- [x] Install prerequisites:
  ```bash
  apt update && apt install -y git curl ca-certificates
  curl -LsSf https://astral.sh/uv/install.sh | sh
  source ~/.bashrc
  ```
- [x] Create service user: `useradd -r -s /usr/sbin/nologin -d /opt/backend-fastapi backend`

---

### Stage 3: Deploy Code & Secrets
**Status:** ✅ Complete
**Time:** ~15 min
**Location:** Laptop + SSH

From laptop:
```bash
# Clone repo on LXC (use separation branch - has newer MCP schema)
ssh root@192.168.1.111 "git clone -b separation https://github.com/jck411/Backend_FastAPI.git /opt/backend-fastapi"

# Copy production env (NOT local .env which has localhost URLs)
scp ~/REPOS/Backend_FastAPI/.env.production root@192.168.1.111:/opt/backend-fastapi/.env
scp -r ~/REPOS/Backend_FastAPI/credentials/ root@192.168.1.111:/opt/backend-fastapi/
scp -r ~/REPOS/Backend_FastAPI/data/tokens/ root@192.168.1.111:/opt/backend-fastapi/data/

# Copy SSL certs
scp -r ~/REPOS/Backend_FastAPI/certs/ root@192.168.1.111:/opt/backend-fastapi/
```

On LXC:
```bash
cd /opt/backend-fastapi
uv sync
chown -R backend:backend /opt/backend-fastapi
chmod 600 .env credentials/googlecloud/sa.json

# CRITICAL: Create production mcp_servers.json with REMOTE URLs
# (laptop config uses localhost which won't work from LXC)
cat > data/mcp_servers.json << 'EOF'
{
  "discovery_hosts": ["192.168.1.110"],
  "servers": [
    {"id": "shell-control", "url": "http://192.168.1.110:9001/mcp", "enabled": true},
    {"id": "housekeeping", "url": "http://192.168.1.110:9002/mcp", "enabled": true},
    {"id": "calculator", "url": "http://192.168.1.110:9003/mcp", "enabled": true},
    {"id": "calendar", "url": "http://192.168.1.110:9004/mcp", "enabled": true},
    {"id": "gmail", "url": "http://192.168.1.110:9005/mcp", "enabled": true},
    {"id": "gdrive", "url": "http://192.168.1.110:9006/mcp", "enabled": true},
    {"id": "pdf", "url": "http://192.168.1.110:9007/mcp", "enabled": true},
    {"id": "monarch", "url": "http://192.168.1.110:9008/mcp", "enabled": true},
    {"id": "notes", "url": "http://192.168.1.110:9009/mcp", "enabled": true},
    {"id": "spotify", "url": "http://192.168.1.110:9010/mcp", "enabled": true},
    {"id": "playwright", "url": "http://192.168.1.110:9011/mcp", "enabled": true}
  ]
}
EOF
chown backend:backend data/mcp_servers.json
```

- [x] Repo cloned to `/opt/backend-fastapi/`
- [x] `.env` copied and secured
- [x] `credentials/` copied
- [x] `data/tokens/` copied (Google OAuth tokens)
- [x] `certs/` copied (SSL key/cert)
- [x] `uv sync` completed successfully (required disk resize to 24GB)
- [x] Permissions set correctly
- [x] Production `mcp_servers.json` created with remote URLs (192.168.1.110)
- [x] MCP servers connected: 12 servers, 174 tools

---

### Stage 4: Create Systemd Services
**Status:** ✅ Complete
**Time:** ~10 min
**Location:** SSH to LXC

Two service files — **dev** (auto-reload on git pull) and **prod** (stable, manual restart):

**Development mode** — Create `/etc/systemd/system/backend-fastapi-dev.service`:
```ini
[Unit]
Description=Backend FastAPI (Development - Auto Reload)
After=network.target
Conflicts=backend-fastapi-prod.service

[Service]
Type=exec
User=backend
Group=backend
WorkingDirectory=/opt/backend-fastapi
ExecStart=/opt/backend-fastapi/.venv/bin/uvicorn backend.app:create_app --factory --host 0.0.0.0 --port 8000 --ssl-keyfile=certs/server.key --ssl-certfile=certs/server.crt --reload --reload-dir=src
Restart=always
RestartSec=5
EnvironmentFile=/opt/backend-fastapi/.env

[Install]
WantedBy=multi-user.target
```

**Production mode** — Create `/etc/systemd/system/backend-fastapi-prod.service`:
```ini
[Unit]
Description=Backend FastAPI (Production)
After=network.target
Conflicts=backend-fastapi-dev.service

[Service]
Type=exec
User=backend
Group=backend
WorkingDirectory=/opt/backend-fastapi
ExecStart=/opt/backend-fastapi/.venv/bin/uvicorn backend.app:create_app --factory --host 0.0.0.0 --port 8000 --ssl-keyfile=certs/server.key --ssl-certfile=certs/server.crt --workers 2 --log-level warning
Restart=always
RestartSec=5
EnvironmentFile=/opt/backend-fastapi/.env

[Install]
WantedBy=multi-user.target
```

**Setup and enable (start with dev mode):**
```bash
systemctl daemon-reload
systemctl enable --now backend-fastapi-dev
systemctl status backend-fastapi-dev
curl -sk https://localhost:8000/health
```

**Switching modes:**
```bash
# Switch to production (no auto-reload, lower CPU)
systemctl disable --now backend-fastapi-dev
systemctl enable --now backend-fastapi-prod

# Switch to development (auto-reload after git pull)
systemctl disable --now backend-fastapi-prod
systemctl enable --now backend-fastapi-dev
```

- [x] Both service files created
- [x] Dev service enabled and started
- [x] Health check passes: `curl -sk https://192.168.1.111:8000/health`
- [x] Logs clean: `journalctl -u backend-fastapi-dev -f`

---

### Stage 5: Update Network Docs & Router
**Status:** ✅ Complete
**Time:** ~5 min
**Location:** Laptop

- [x] Update `HOME_NETWORK/Network_Configuration_Overview.md`:
  - Add to Static IP Assignments table
  - Add to Reserved IP Ranges note
- [x] Update `PROXMOX/README.md`:
  - Add Backend FastAPI to Services table

> Note: No DHCP reservation needed — LXC has static IP configured in container config.

---

### Stage 6: Build & Deploy All Frontends
**Status:** ✅ Complete
**Time:** ~15 min
**Location:** Laptop + SSH

#### Frontend Overview

| Directory | Name | Framework | Deployment |
|-----------|------|-----------|------------|
| `frontend-kiosk/` | Kiosk | React | Static files at `/` |
| `frontend-voice/` | Voice Assistant | React | Static files at `/voice/` |
| `frontend/` | Main Chat | Svelte | Static files at `/chat/` |
| `frontend-cli/` | Shell Chat | Python | Runs locally (no deployment needed) |

The backend serves static frontends from `src/backend/static/`:

| Path | Frontend | Source Dir | Status |
|------|----------|-----------|--------|
| `/` | Kiosk | `frontend-kiosk/` | ✅ Deployed |
| `/voice/` | Voice Assistant | `frontend-voice/` | ✅ Deployed |
| `/chat/` | Main Chat | `frontend/` | ✅ Deployed |

> **CLI Note:** `frontend-cli/shell_chat.py` is a Python terminal client. Run it from any machine with `python shell_chat.py` — it connects to the API at whatever URL you configure.

#### 6a. Build Voice Frontend

From laptop:
```bash
cd ~/REPOS/Backend_FastAPI/frontend-voice
npm install && npm run build

# Copy build to static/voice/
rm -rf ../src/backend/static/voice
cp -r dist ../src/backend/static/voice

# Commit and push
cd ..
git add src/backend/static/voice
git commit -m "Build voice frontend for Proxmox deployment"
git push origin separation
```

On LXC:
```bash
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && systemctl restart backend-fastapi-dev"
```

Verify: `https://192.168.1.111:8000/voice/`

#### 6b. Add Main Chat Frontend (Optional)

The main chat frontend needs a route added to `app.py`. Similar pattern to voice:
1. Add `/chat/` route in `app.py` serving from `static/chat/`
2. Build `frontend/` and copy to `src/backend/static/chat/`
3. Deploy

**To add `/chat/` route** — edit `src/backend/app.py`:
```python
# Mount Chat app assets if they exist (after voice_dir block)
chat_dir = static_dir / "chat"
if chat_dir.exists():
    if (chat_dir / "assets").exists():
        app.mount(
            "/chat/assets",
            StaticFiles(directory=chat_dir / "assets"),
            name="chat_assets",
        )

    @app.get("/chat/{full_path:path}")
    async def serve_chat_spa(full_path: str):
        file_path = chat_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(
            chat_dir / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/chat")
    async def redirect_chat():
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/chat/")
```

Then build and deploy:
```bash
cd ~/REPOS/Backend_FastAPI/frontend
npm install && npm run build
rm -rf ../src/backend/static/chat
cp -r dist ../src/backend/static/chat
```

- [x] Voice frontend built and deployed
- [x] Voice accessible at `https://192.168.1.111:8000/voice/`
- [x] Chat frontend route added to app.py
- [x] Chat frontend built and deployed
- [x] Chat accessible at `https://192.168.1.111:8000/chat/`
- [x] CLI — no deployment needed (runs locally via `python frontend-cli/shell_chat.py`)

---

### Stage 7: Cloudflare Tunnel (Optional)
**Status:** ⬜ Not Started
**Time:** ~10 min
**Location:** SSH to Proxmox host

Only needed for public HTTPS access (e.g., `api.jackshome.com`).

Edit `/etc/cloudflared/config.yml` on Proxmox host:
```yaml
ingress:
  # ... existing services ...
  - hostname: api.jackshome.com
    service: https://192.168.1.111:8000
    originServerName: api.jackshome.com
  - service: http_status:404
```

```bash
systemctl restart cloudflared
```

- [ ] Tunnel config updated
- [ ] DNS CNAME added in Cloudflare dashboard
- [ ] Public URL works: `https://api.jackshome.com/health`
- [ ] Update `.env` OAuth redirect URIs to use public domain

---

## Secrets Inventory

Environment variables needed in `.env`:

| Variable | Required | Notes |
|----------|----------|-------|
| `OPENROUTER_API_KEY` | ✅ Yes | Core LLM API |
| `DEEPGRAM_API_KEY` | Optional | Browser STT tokens |
| `ACCUWEATHER_API_KEY` | Optional | Kiosk weather |
| `ACCUWEATHER_LOCATION_KEY` | Optional | Kiosk weather |
| `ELEVENLABS_API_KEY` | Optional | TTS provider |
| `OPENAI_API_KEY` | Optional | TTS provider |
| `GCS_BUCKET_NAME` | ✅ Yes | Attachment storage |
| `GCP_PROJECT_ID` | ✅ Yes | GCS project |

Credential files:
| File | Required | Notes |
|------|----------|-------|
| `credentials/googlecloud/sa.json` | ✅ Yes | GCS service account |
| `credentials/client_secret_*.json` | For OAuth | Google OAuth client |
| `data/tokens/*.json` | For OAuth | Pre-authenticated tokens |
| `certs/server.key` | ✅ Yes | SSL private key |
| `certs/server.crt` | ✅ Yes | SSL certificate |

---

## Update Workflow

> **Important:** LXC uses the `separation` branch. The laptop's local `data/mcp_servers.json` uses localhost URLs which won't work on LXC — don't overwrite it during updates.

**Dev mode (auto-reload enabled):**
```bash
# Just pull — uvicorn detects changes and reloads automatically
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"

# If dependencies changed:
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && uv sync"
```

**Prod mode (manual restart required):**
```bash
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && systemctl restart backend-fastapi-prod"

# If dependencies changed:
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull && uv sync && systemctl restart backend-fastapi-prod"
```

**Check which mode is active:**
```bash
ssh root@192.168.1.111 "systemctl is-active backend-fastapi-dev backend-fastapi-prod"
```

**Check logs:**
```bash
ssh root@192.168.1.111 "journalctl -u backend-fastapi-dev -f"   # or backend-fastapi-prod
```

---

## Architecture After Deployment

```
┌─────────────────────────────────────────────────────────────┐
│                     PROXMOX HOST                            │
│                   192.168.1.11                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │   LXC 110       │    │   LXC 111       │                │
│  │  mcp-servers    │◄───│ backend-fastapi │                │
│  │ 192.168.1.110   │    │ 192.168.1.111   │                │
│  │ ports 9001-9013 │    │ port 8000       │                │
│  └─────────────────┘    └────────▲────────┘                │
│                                  │                          │
│  ┌─────────────────┐             │                          │
│  │   VM 200        │             │                          │
│  │     Plex        │             │                          │
│  │ 192.168.1.20    │             │                          │
│  └─────────────────┘             │                          │
│                                  │                          │
└──────────────────────────────────┼──────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
     ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
     │  Frontend   │      │   Kiosk     │      │   Voice     │
     │ :5173 (dev) │      │ Echo Show   │      │ :5175 (dev) │
     │   Laptop    │      │   Browser   │      │   Laptop    │
     └─────────────┘      └─────────────┘      └─────────────┘
```

---

## Session Log

| Date | Session | Stages Completed | Notes |
|------|---------|------------------|-------|
| Feb 10, 2026 | Planning | — | Created deployment plan |
| Feb 10, 2026 | Deployment | 1, 2 | Credentials setup, LXC 111 created (Debian 13.1-2), SSH working, uv installed, backend user created |
| Feb 10, 2026 | Deployment | 3, 4 | Code deployed, disk resized 8GB→24GB for CUDA deps, 246 packages installed, systemd services created, dev service running, health check passed |
| Feb 10, 2026 | Deployment | — | **Fix:** Switched to `separation` branch (master had old MCP schema). Created production mcp_servers.json with remote URLs (192.168.1.110). MCP servers now connect: 12 servers, 174 tools. |
| Feb 11, 2026 | Deployment | 5 | Network docs updated: Added LXC 110/111 to Static IP Assignments, added to PROXMOX Services tables. |
| Feb 11, 2026 | Deployment | 6 | Built and deployed voice and chat frontends. All three UIs accessible: / (kiosk), /voice/, /chat/. |

---

## Quick Context for New Sessions

> **What:** Deploying Backend_FastAPI to Proxmox LXC 111 (192.168.1.111:8000)
>
> **Why:** Always-on backend for frontends, especially kiosk. MCP servers already on Proxmox.
>
> **Pattern:** Same as mcp-servers (LXC 110) — git clone, uv sync, systemd service.
>
> **Current stage:** Check the Stage Checklist above for ⬜/✅ status.
>
> **Key files:** This doc, `mcp-servers/deploy/setup-systemd.sh` (reference pattern).
