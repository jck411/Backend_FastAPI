#!/bin/bash

# ============================================================
# Backend_FastAPI Component Launcher
# ============================================================
# Starts selected components of the stack:
#   1 - Backend        (FastAPI on :8000)
#   2 - Frontend       (Svelte chat UI on :5173)
#   3 - Frontend-Kiosk (Kiosk UI on :5174)
#   4 - Frontend-CLI   (Terminal chat client)
#   5 - Slideshow Sync (Download photos from Google Photos)
#   6 - Voice PWA      (Voice UI on :5175)
#
# MCP servers are always-on external services (deployed to
# Proxmox). The backend connects to them automatically —
# they do NOT need to be launched from this script.
#
# Usage:
#   ./start.sh         # Interactive menu
#   ./start.sh 1       # Start Backend only
#   ./start.sh 12      # Start Backend + Frontend
#   ./start.sh all     # Start Backend + Frontend + Kiosk + Slideshow + Voice
#   ./start.sh 5       # Just sync slideshow photos
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Ensure we're in the project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Track background processes
PIDS=()

cleanup() {
    echo ""
    echo "Stopping all servers..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    # Kill any child processes
    pkill -P $$ 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Kill any existing processes from a previous run
kill_existing() {
    echo -e "${YELLOW}Killing any existing processes...${NC}"

    # Kill uvicorn processes for this project
    pkill -f "uvicorn backend.app:create_app" 2>/dev/null || true

    # Kill node/npm processes for frontends
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

# Helper: Wait for backend to be ready
wait_for_backend() {
    local max_attempts=30
    local attempt=0
    echo -n "Waiting for backend..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -k https://localhost:8000/health > /dev/null 2>&1; then
            echo " ready!"
            return 0
        fi
        sleep 0.5
        attempt=$((attempt + 1))
        echo -n "."
    done
    echo " timeout (backend may still be starting)"
    return 1
}

# Get selection from argument or prompt
if [[ -n "$1" ]]; then
    selection="$1"
else
    # Display menu
    echo ""
    echo -e "${BOLD}╔════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║     Backend_FastAPI Component Launcher     ║${NC}"
    echo -e "${BOLD}╚════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}1${NC} - Backend        (FastAPI on :8000)"
    echo -e "  ${CYAN}2${NC} - Frontend       (Svelte chat UI on :5173)"
    echo -e "  ${CYAN}3${NC} - Frontend-Kiosk (Kiosk UI on :5174)"
    echo -e "  ${CYAN}4${NC} - Frontend-CLI   (Terminal chat client)"
    echo -e "  ${CYAN}5${NC} - Slideshow Sync (Download & preload photos from Google Photos)"
    echo -e "  ${CYAN}6${NC} - Voice PWA      (Voice UI on :5175)"
    echo ""
    echo -e "  ${YELLOW}MCP servers are always-on (external). No launch needed.${NC}"
    echo ""
    echo -e "  ${CYAN}all${NC} - Start 1, 2, 3, 5, and 6 (full web stack + slideshow)"
    echo ""
    echo -e "${BOLD}Enter selection (e.g., '12' or '135' or 'all'):${NC} "
    read -r selection
fi

# Handle 'all' shortcut
if [[ "$selection" == "all" ]]; then
    selection="12356"
fi

# Validate input
if [[ -z "$selection" ]]; then
    echo -e "${RED}No selection made. Exiting.${NC}"
    exit 1
fi

if [[ ! "$selection" =~ ^[1-6]+$ ]]; then
    echo -e "${RED}Invalid selection. Use only numbers 1-6 or 'all'.${NC}"
    exit 1
fi

echo ""

# Track what we're starting
START_BACKEND=false
START_FRONTEND=false
START_KIOSK=false
START_CLI=false
START_SLIDESHOW=false
START_VOICE=false

# Parse selection
[[ "$selection" == *"1"* ]] && START_BACKEND=true
[[ "$selection" == *"2"* ]] && START_FRONTEND=true
[[ "$selection" == *"3"* ]] && START_KIOSK=true
[[ "$selection" == *"4"* ]] && START_CLI=true
[[ "$selection" == *"5"* ]] && START_SLIDESHOW=true
[[ "$selection" == *"6"* ]] && START_VOICE=true

# Sync Slideshow Photos (option 5) - run first so photos are ready for preload
if $START_SLIDESHOW; then
    echo -e "${GREEN}[5] Syncing & Preparing Slideshow Photos (40 max)...${NC}"
    uv run python scripts/echo/sync_slideshow.py --max-photos 40
    echo ""
fi

# Start Backend (option 1)
if $START_BACKEND; then
    echo -e "${GREEN}[1] Starting Backend...${NC}"
    uv run python scripts/kill_port.py 8000
    uv run uvicorn backend.app:create_app \
        --factory \
        --host 0.0.0.0 \
        --ssl-keyfile=certs/server.key \
        --ssl-certfile=certs/server.crt \
        --reload &
    PIDS+=($!)
    sleep 2
fi

# Avoid frontend proxy errors by waiting for backend to accept requests.
if $START_BACKEND && ($START_FRONTEND || $START_KIOSK || $START_VOICE); then
    wait_for_backend
fi

# Start Frontend (option 2)
if $START_FRONTEND; then
    echo -e "${GREEN}[2] Starting Frontend (Svelte)...${NC}"
    uv run python scripts/kill_port.py 5173
    cd frontend && npm run dev &
    PIDS+=($!)
    cd "$SCRIPT_DIR"
fi

# Start Kiosk (option 3)
if $START_KIOSK; then
    echo -e "${GREEN}[3] Starting Frontend-Kiosk...${NC}"
    uv run python scripts/kill_port.py 5174
    cd frontend-kiosk && npm run dev &
    PIDS+=($!)
    cd "$SCRIPT_DIR"
fi

# Start Voice PWA (option 6)
if $START_VOICE; then
    echo -e "${GREEN}[6] Starting Voice PWA...${NC}"
    uv run python scripts/kill_port.py 5175
    cd frontend-voice && npm run dev &
    PIDS+=($!)
    cd "$SCRIPT_DIR"
fi


# Start CLI (option 4) - interactive, runs in foreground
if $START_CLI; then
    if $START_BACKEND || $START_FRONTEND || $START_KIOSK || $START_VOICE; then
        # Other services running, start CLI after them
        echo -e "${GREEN}[4] Starting Frontend-CLI...${NC}"
        echo ""
        sleep 1
        source .venv/bin/activate && shell-chat
        # After CLI exits, keep waiting for other services
        echo ""
        echo -e "${YELLOW}CLI exited. Background services still running.${NC}"
        echo -e "Press ${RED}Ctrl+C${NC} to stop all servers"
    else
        # CLI is the only selection
        echo -e "${GREEN}[4] Starting Frontend-CLI...${NC}"
        echo -e "${YELLOW}Note: Backend is not running. Start with './start.sh 14' to run both.${NC}"
        echo ""
        source .venv/bin/activate && shell-chat
        exit 0
    fi
fi

# Show status (only if we have background services)
if $START_BACKEND || $START_FRONTEND || $START_KIOSK || $START_VOICE; then
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
    echo -e "${BOLD}Running Services:${NC}"

    if $START_SLIDESHOW; then
        echo -e "  ${GREEN}✓${NC} Slideshow:      Photos synced"
    fi
    if $START_BACKEND; then
        echo -e "  ${GREEN}✓${NC} Backend:        https://localhost:8000"
    fi
    if $START_FRONTEND; then
        echo -e "  ${GREEN}✓${NC} Frontend:       http://localhost:5173"
    fi
    if $START_KIOSK; then
        echo -e "  ${GREEN}✓${NC} Frontend-Kiosk: http://localhost:5174"
    fi
    if $START_VOICE; then
        echo -e "  ${GREEN}✓${NC} Voice PWA:      http://localhost:5175"
    fi

    echo -e "  ${CYAN}ℹ${NC} MCP Servers:    Always-on (external)"

    # Show network access info
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP=$(ip route get 1 2>/dev/null | awk '{print $7}' | head -1)
    fi

    if [ -n "$LOCAL_IP" ]; then
        echo ""
        echo -e "${BOLD}Network Access (from other machines):${NC}"
        if $START_BACKEND; then
            echo -e "  Backend:        https://${LOCAL_IP}:8000"
        fi
        if $START_FRONTEND; then
            echo -e "  Frontend:       http://${LOCAL_IP}:5173"
        fi
        if $START_KIOSK; then
            echo -e "  Frontend-Kiosk: http://${LOCAL_IP}:5174"
        fi
        if $START_VOICE; then
            echo -e "  Voice PWA:      http://${LOCAL_IP}:5175"
        fi
    fi

    echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
    echo -e "Press ${RED}Ctrl+C${NC} to stop all servers"
    echo ""

    # Wait for all background processes
    wait
fi
