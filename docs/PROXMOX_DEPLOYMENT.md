# Backend_FastAPI Proxmox Deployment

**Status:** 🟡 Planning Complete — Ready to Execute
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
**Status:** ⬜ Not Started
**Time:** ~15 min
**Location:** Laptop only

- [ ] Create `credentials/googlecloud/` directory structure
- [ ] Copy GCS service account JSON to `credentials/googlecloud/sa.json`
- [ ] Create `.env.production` with production URLs:
  ```
  FRONTEND_URL=https://192.168.1.111:8000
  GOOGLE_OAUTH_REDIRECT_URI=https://192.168.1.111:8000/api/google-auth/callback
  ```
- [ ] Verify `data/mcp_servers.json` uses `192.168.1.110` URLs (not localhost)
- [ ] List all required env vars (see Secrets Inventory below)

---

### Stage 2: Create LXC Container
**Status:** ⬜ Not Started
**Time:** ~10 min
**Location:** SSH to Proxmox host (192.168.1.11)

Commands:
```bash
# On Proxmox host
pct create 111 local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst \
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

- [ ] Container created and started
- [ ] Can SSH: `ssh root@192.168.1.111`
- [ ] Install prerequisites:
  ```bash
  apt update && apt install -y git curl ca-certificates
  curl -LsSf https://astral.sh/uv/install.sh | sh
  source ~/.bashrc
  ```
- [ ] Create service user: `useradd -r -s /usr/sbin/nologin -d /opt/backend-fastapi backend`

---

### Stage 3: Deploy Code & Secrets
**Status:** ⬜ Not Started
**Time:** ~15 min
**Location:** Laptop + SSH

From laptop:
```bash
# Clone repo on LXC
ssh root@192.168.1.111 "git clone https://github.com/YOUR_USERNAME/Backend_FastAPI.git /opt/backend-fastapi"

# Copy secrets (from laptop)
scp ~/REPOS/Backend_FastAPI/.env root@192.168.1.111:/opt/backend-fastapi/
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
```

- [ ] Repo cloned to `/opt/backend-fastapi/`
- [ ] `.env` copied and secured
- [ ] `credentials/` copied
- [ ] `data/tokens/` copied (Google OAuth tokens)
- [ ] `certs/` copied (SSL key/cert)
- [ ] `uv sync` completed successfully
- [ ] Permissions set correctly

---

### Stage 4: Create Systemd Services
**Status:** ⬜ Not Started
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
ExecStart=/opt/backend-fastapi/.venv/bin/uvicorn backend.app:create_app --factory --host 0.0.0.0 --port 8000 --ssl-keyfile=certs/server.key --ssl-certfile=certs/server.crt
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

- [ ] Both service files created
- [ ] Dev service enabled and started
- [ ] Health check passes: `curl -sk https://192.168.1.111:8000/health`
- [ ] Logs clean: `journalctl -u backend-fastapi-dev -f`

---

### Stage 5: Update Network Docs & Router
**Status:** ⬜ Not Started
**Time:** ~5 min
**Location:** Laptop

- [ ] Add DHCP reservation in router for LXC 111 MAC → 192.168.1.111
- [ ] Update `HOME_NETWORK/Network_Configuration_Overview.md`:
  - Add to Static IP Assignments table
  - Add to Reserved IP Ranges note
- [ ] Update `PROXMOX/README.md`:
  - Add Backend FastAPI to Services table

---

### Stage 6: Cloudflare Tunnel (Optional)
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

### Stage 7: Update Frontends
**Status:** ⬜ Not Started
**Time:** ~5 min
**Location:** Laptop

Update each frontend's `.env` or config:

**frontend/.env:**
```
VITE_API_BASE_URL=https://192.168.1.111:8000
```

**frontend-kiosk/.env:**
```
VITE_API_BASE_URL=https://192.168.1.111:8000
```

**frontend-voice/.env:**
```
VITE_API_BASE_URL=https://192.168.1.111:8000
```

- [ ] Main frontend updated and tested
- [ ] Kiosk frontend updated and tested
- [ ] Voice frontend updated and tested
- [ ] CLI works against deployed backend

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
│  │ ports 9001-9012 │    │ port 8000       │                │
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
| | | | |
| | | | |

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
