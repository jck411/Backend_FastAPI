
## Deploy to Remote

**If you changed frontend-voice source:**
```bash
cd frontend-voice && npm run build
```
Then commit and push the built assets.

**Deploy via Proxmox:**

Go to https://proxmox.jackshome.com
Open LXC 111's console via the web UI
Run:
pct exec 111 -- bash -c "cd /opt/backend-fastapi && git fetch origin && git reset --hard origin/master && chown -R backend:backend /opt/backend-fastapi/src/backend/data/ && systemctl restart backend-fastapi-dev"



For full stack testing locally:
cd /home/human/REPOS/Backend_FastAPI
source .venv/bin/activate
uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000
