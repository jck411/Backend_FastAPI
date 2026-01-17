# Development Environment & Connectivity Guide

## Work Network Configuration (Current Setup)
**Last Updated:** Jan 2026
**Context:** Development on Corporate/Guest Wi-Fi (`10.235.x.x`)

### 1. Network Restrictions
The current work network enforces strict port isolation.
- **Allowed:** Standard ports (80, 443) and some development ports (8000).
- **Blocked:** High random ports often used by Vite (5173, 5174, 5175).
- **Result:** Attempting to access `https://IP:5175` (Voice PWA) directly from a phone fails with `ERR_POLL_TIMEOUT` or `ERR_ADDRESS_UNREACHABLE`.

### 2. The Solution: Backend Tunneling
To bypass these restrictions without external tunneling (ngrok), we serve the frontend applications directly through the FastAPI backend, which runs on the allowed **Port 8000**.

| Component | Dev Port (Blocked) | Production/Tunnel Path (Allowed) |
|-----------|-------------------|----------------------------------|
| Backend | 8000 (Open) | `https://IP:8000` |
| Voice PWA | 5175 (Blocked) | `https://IP:8000/voice/` |
| Kiosk UI | 5174 (Blocked) | *Pending Integration* |

### 3. Voice PWA Deployment
The Voice PWA (`frontend-voice`) is a minimal React app designed for mobile usage.

#### Build & Serve Pipeline
1. **Build:** The React app is built using Vite.
   - Config: `vite.config.js` sets `base: '/voice/'`.
   - Output: `../src/backend/static/voice`.
2. **Serve:** FastAPI (`src/backend/app.py`) mounts this static directory.
   - Route: `/voice` -> Redirects to `/voice/`.
   - SPA Fallback: Any unknown path under `/voice/` serves `index.html`.

#### Audio & Protocols
- **HTTPS Required:** Accessing microphone requires a secure context. We use self-signed certificates (`certs/cert.pem`). You must accept the browser warning on the phone.
- **WebSocket:** The app connects to `wss://IP:8000/api/voice/connect`.
- **Message Format:**
  - **User Speech:** Backend sends `{ type: 'transcript', text: '...', is_final: true }`.
  - **AI Response:** Backend sends `{ type: 'assistant_response_chunk', text: '...' }`.
  *(Note: Previous version used 'transcription'/'llm_response' - ensured alignment matching Kiosk)*

### 4. How to Run
```bash
# Starts Backend (8000) + Frontends (5173/5174/5175)
./start_server.sh
```
*Note: The script starts independent Vite servers for local dev (localhost:5175), but for mobile testing, rely on the backend build at :8000/voice/.*
