
## Deploy to Remote

The server does NOT build frontends — it serves pre-built files from `src/backend/static/`.
**You must rebuild locally and commit the output before deploying, or your changes won't appear.**

---

### Step 1: Rebuild any frontends you changed

If you changed **frontend/** (main Svelte chat UI → `chat.jackshome.com`):
```bash
cd frontend && npm run build
```

If you changed **frontend-voice/** (voice PWA → `chat.jackshome.com/voice/`):
```bash
cd frontend-voice && npm run build
```

If you changed **frontend-kiosk/** (kiosk display → `chat.jackshome.com/kiosk/`):
```bash
cd frontend-kiosk && npm run build
```

Or rebuild everything at once:
```bash
cd frontend && npm run build && cd ../frontend-voice && npm run build && cd ../frontend-kiosk && npm run build && cd ..
```

### Step 2: Commit and push (including the built assets)

```bash
git add src/backend/static/
git commit -m "build: rebuild frontends"
git push
```

### Step 3: Deploy to LXC 111

Go to https://proxmox.jackshome.com → LXC 111 console, then run:
```bash
pct exec 111 -- bash -c "cd /opt/backend-fastapi && git fetch origin && git reset --hard origin/master && chown -R backend:backend /opt/backend-fastapi/src/backend/data/ && systemctl restart backend-fastapi-dev"
```

---

### Quick one-liner (after rebuilding)

```bash
git add src/backend/static/ && git commit -m "build: rebuild frontends" && git push
```
Then deploy from Proxmox console.

---

### Local full-stack testing

```bash
cd /home/human/REPOS/Backend_FastAPI
source .venv/bin/activate
uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000
```
