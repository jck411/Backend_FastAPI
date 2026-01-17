#!/usr/bin/env bash
# Start FastAPI backend and both frontend dev servers

set -e

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure logs directory exists
mkdir -p logs

# Kill any existing processes from a previous run
kill_existing() {
    echo "Killing any existing backend/frontend processes..."

    # Kill uvicorn processes for this project
    pkill -f "uvicorn backend.app:create_app" 2>/dev/null || true

    # Kill node/npm processes for frontend and frontend-kiosk
    pkill -f "node.*frontend" 2>/dev/null || true
    pkill -f "npm.*frontend" 2>/dev/null || true
    pkill -f "vite.*5173" 2>/dev/null || true
    pkill -f "vite.*5174" 2>/dev/null || true
    pkill -f "vite.*5175" 2>/dev/null || true

    # Give processes time to exit
    sleep 1
}

# Kill existing processes before starting
kill_existing

# Function to cleanup background processes on exit
cleanup() {
    echo "Stopping servers..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

# Start the backend
echo "Cleaning up port 8000..."
uv run python scripts/kill_port.py 8000

echo "Starting FastAPI backend with HTTPS..."
uv run uvicorn backend.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --ssl-keyfile=certs/server.key \
    --ssl-certfile=certs/server.crt \
    --reload &

BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start the Svelte frontend (main chat UI)
echo "Cleaning up port 5173..."
uv run python scripts/kill_port.py 5173

echo "Starting Svelte frontend (chat UI) on port 5173..."
(cd "$SCRIPT_DIR/frontend" && npm run dev) &

SVELTE_PID=$!

# Start the Kiosk frontend
echo "Cleaning up port 5174..."
uv run python scripts/kill_port.py 5174

echo "Starting Kiosk frontend on port 5174..."
(cd "$SCRIPT_DIR/frontend-kiosk" && npm run dev) &

KIOSK_PID=$!

# Start the Voice PWA frontend
echo "Cleaning up port 5175..."
uv run python scripts/kill_port.py 5175

echo "Starting Voice PWA frontend on port 5175..."
(cd "$SCRIPT_DIR/frontend-voice" && npm run dev) &

VOICE_PID=$!

echo ""
echo "=============================================="
echo "Backend:        https://localhost:8000"
echo "Svelte Chat UI: http://localhost:5173"
echo "Kiosk UI:       https://localhost:5174"
echo "Voice PWA:      https://localhost:5175"
echo ""
# Detect the primary IP address
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(ip route get 1 2>/dev/null | awk '{print $7}' | head -1)
fi
if [ -n "$LOCAL_IP" ]; then
    echo "From other machines (use your IP):"
    echo "  Backend:        https://${LOCAL_IP}:8000"
    echo "  Svelte Chat UI: http://${LOCAL_IP}:5173"
    echo "  Kiosk UI:       https://${LOCAL_IP}:5174"
    echo "  Voice PWA:      https://${LOCAL_IP}:5175"
    echo ""
    echo "NOTE: Accept the certificate warning on first visit."
else
    echo "From other machines, use your machine's IP address."
fi
echo "=============================================="
echo "Press Ctrl+C to stop all servers"
echo ""

# Wait for all processes
wait
