#!/usr/bin/env bash
# Interactive launcher for Backend_FastAPI components
# Allows starting any combination of backend and frontends
#
# Usage:
#   ./start.sh         # Interactive menu
#   ./start.sh 12      # Start backend + frontend
#   ./start.sh 123     # Start backend + both web frontends
#   ./start.sh all     # Start everything (except CLI)

set -e

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure logs directory exists
mkdir -p logs

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Pids to track
declare -a PIDS=()

# Wait for backend health endpoint to be available before launching frontends
wait_for_backend() {
    local health_url="http://127.0.0.1:8000/health"

    if ! command -v curl >/dev/null 2>&1; then
        echo -e "${YELLOW}curl not found; skipping backend readiness check.${NC}"
        return
    fi

    echo -e "${BLUE}Waiting for backend readiness...${NC}"
    for _ in {1..60}; do
        if curl -fsS "$health_url" >/dev/null 2>&1; then
            echo -e "${GREEN}Backend is ready.${NC}"
            return
        fi
        sleep 0.5
    done
    echo -e "${YELLOW}Backend readiness check timed out; continuing anyway.${NC}"
}

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping all servers...${NC}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Also kill any remaining child processes
    kill $(jobs -p) 2>/dev/null || true
    exit
}

trap cleanup SIGINT SIGTERM

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
    echo -e "  ${CYAN}1${NC} - Backend        (FastAPI on :8000; MCP servers managed inside backend)"
    echo -e "  ${CYAN}2${NC} - Frontend       (Svelte chat UI on :5173)"
    echo -e "  ${CYAN}3${NC} - Frontend-Kiosk (Kiosk UI on :5174)"
    echo -e "  ${CYAN}4${NC} - Frontend-CLI   (Terminal chat client)"
    echo ""
    echo -e "  ${CYAN}all${NC} - Start 1, 2, and 3 (web stack)"
    echo ""
    echo -e "${BOLD}Enter selection (e.g., '12' or '123' or 'all'):${NC} "
    read -r selection
fi

# Handle 'all' shortcut
if [[ "$selection" == "all" ]]; then
    selection="123"
fi

# Validate input
if [[ -z "$selection" ]]; then
    echo -e "${RED}No selection made. Exiting.${NC}"
    exit 1
fi

if [[ ! "$selection" =~ ^[1-4]+$ ]]; then
    echo -e "${RED}Invalid selection. Use only numbers 1-4 or 'all'.${NC}"
    exit 1
fi

echo ""

# Track what we're starting
START_BACKEND=false
START_FRONTEND=false
START_KIOSK=false
START_CLI=false

# Parse selection
[[ "$selection" == *"1"* ]] && START_BACKEND=true
[[ "$selection" == *"2"* ]] && START_FRONTEND=true
[[ "$selection" == *"3"* ]] && START_KIOSK=true
[[ "$selection" == *"4"* ]] && START_CLI=true

# Start Backend
if $START_BACKEND; then
    echo -e "${GREEN}[1/4] Starting Backend (includes MCP servers)...${NC}"
    uv run python scripts/kill_port.py 8000
    for port in {9001..9010}; do
        uv run python scripts/kill_port.py "$port"
    done
    uv run uvicorn backend.app:create_app \
        --factory \
        --host 0.0.0.0 \
        --reload &
    PIDS+=($!)
    sleep 2  # Give backend time to start
fi

# Avoid frontend proxy errors by waiting for backend to accept requests.
if $START_BACKEND && ($START_FRONTEND || $START_KIOSK); then
    wait_for_backend
fi

# Start Svelte Frontend
if $START_FRONTEND; then
    echo -e "${GREEN}[2/4] Starting Frontend (Svelte)...${NC}"
    uv run python scripts/kill_port.py 5173
    (cd "$SCRIPT_DIR/frontend" && npm run dev) &
    PIDS+=($!)
fi

# Start Kiosk Frontend
if $START_KIOSK; then
    echo -e "${GREEN}[3/4] Starting Frontend-Kiosk...${NC}"
    uv run python scripts/kill_port.py 5174
    (cd "$SCRIPT_DIR/frontend-kiosk" && npm run dev) &
    PIDS+=($!)
fi

# Handle CLI
if $START_CLI; then
    # Check if other services are running
    if $START_BACKEND || $START_FRONTEND || $START_KIOSK; then
        # Other services are running in background, wait a moment then start CLI in foreground
        echo -e "${GREEN}[4/4] Starting Frontend-CLI...${NC}"
        echo ""
        sleep 1
        source .venv/bin/activate && shell-chat
        # After CLI exits, keep waiting for other services
        echo ""
        echo -e "${YELLOW}CLI exited. Background services still running.${NC}"
        echo -e "Press ${RED}Ctrl+C${NC} to stop all servers"
    else
        # CLI is the only selection
        echo -e "${GREEN}[4/4] Starting Frontend-CLI...${NC}"
        echo -e "${YELLOW}Note: Backend is not running. Start with './start.sh 14' to run both.${NC}"
        echo ""
        source .venv/bin/activate && shell-chat
        exit 0
    fi
fi

# Show status (only if we have background services)
if $START_BACKEND || $START_FRONTEND || $START_KIOSK; then
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
    echo -e "${BOLD}Running Services:${NC}"

    if $START_BACKEND; then
        echo -e "  ${GREEN}✓${NC} Backend:        http://localhost:8000"
    fi
    if $START_FRONTEND; then
        echo -e "  ${GREEN}✓${NC} Frontend:       http://localhost:5173"
    fi
    if $START_KIOSK; then
        echo -e "  ${GREEN}✓${NC} Frontend-Kiosk: http://localhost:5174"
    fi

    # Show network access info
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP=$(ip route get 1 2>/dev/null | awk '{print $7}' | head -1)
    fi

    if [ -n "$LOCAL_IP" ]; then
        echo ""
        echo -e "${BOLD}Network Access (from other machines):${NC}"
        if $START_BACKEND; then
            echo -e "  Backend:        http://${LOCAL_IP}:8000"
        fi
        if $START_FRONTEND; then
            echo -e "  Frontend:       http://${LOCAL_IP}:5173"
        fi
        if $START_KIOSK; then
            echo -e "  Frontend-Kiosk: http://${LOCAL_IP}:5174"
        fi
    fi

    echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
    echo -e "Press ${RED}Ctrl+C${NC} to stop all servers"
    echo ""

    # Wait for all background processes
    wait
fi
