#!/bin/bash
# Deploy to Proxmox LXC 111 via the Proxmox host
#
# Usage:
#   ./scripts/deploy.sh              # Backend only: push + pull (auto-reloads)
#   ./scripts/deploy.sh frontend     # Build frontend, push, pull, restart
#   ./scripts/deploy.sh deps         # Push, pull, uv sync, restart
#   ./scripts/deploy.sh restart      # Just restart the service
#   ./scripts/deploy.sh status       # Check service status + current commit
#   ./scripts/deploy.sh logs         # Tail recent service logs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Load Proxmox credentials from .env
if [[ -f "$ROOT_DIR/.env" ]]; then
    PROXMOX_HOST=$(grep -E '^PROXMOX_HOST=' "$ROOT_DIR/.env" | cut -d= -f2)
    PROXMOX_USER=$(grep -E '^PROXMOX_USER=' "$ROOT_DIR/.env" | cut -d= -f2)
    PROXMOX_PASSWORD=$(grep -E '^PROXMOX_PASSWORD=' "$ROOT_DIR/.env" | cut -d= -f2)
    PROXMOX_LXC_ID=$(grep -E '^PROXMOX_LXC_ID=' "$ROOT_DIR/.env" | cut -d= -f2)
fi

PROXMOX_HOST="${PROXMOX_HOST:-192.168.1.11}"
PROXMOX_USER="${PROXMOX_USER:-root}"
PROXMOX_LXC_ID="${PROXMOX_LXC_ID:-111}"
APP_DIR="/opt/backend-fastapi"

# Detect if we're on the home LAN by pinging the Proxmox host
ON_LAN=false
if ping -c1 -W1 "$PROXMOX_HOST" &>/dev/null; then
    ON_LAN=true
fi

if [[ "$ON_LAN" == true ]]; then
    if [[ -z "$PROXMOX_PASSWORD" ]]; then
        echo -e "${RED}PROXMOX_PASSWORD not set in .env${NC}"
        exit 1
    fi
fi

# SSH into Proxmox host, run command inside the LXC container
run_on_server() {
    sshpass -p "$PROXMOX_PASSWORD" ssh -o StrictHostKeyChecking=accept-new \
        "${PROXMOX_USER}@${PROXMOX_HOST}" \
        "pct exec ${PROXMOX_LXC_ID} -- bash -c '$1'"
}

# Print commands for manual paste when off-LAN
print_server_commands() {
    local cmds="$1"
    echo ""
    echo -e "${YELLOW}=== Not on home LAN — paste this into your Proxmox shell ===${NC}"
    echo ""
    echo -e "${GREEN}pct exec ${PROXMOX_LXC_ID} -- bash -c '${cmds}'${NC}"
    echo ""
}

# Run on server if on LAN, otherwise print paste-able command
deploy_to_server() {
    local cmds="$1"
    if [[ "$ON_LAN" == true ]]; then
        run_on_server "$cmds"
    else
        print_server_commands "$cmds"
    fi
}

MODE="${1:-backend}"

case "$MODE" in
    backend)
        echo -e "${YELLOW}=== Backend Deploy ===${NC}"
        cd "$ROOT_DIR"

        # Warn if frontend source is newer than last build
        LAST_SRC_COMMIT=$(git log -1 --format="%H" -- frontend/src/ frontend/index.html frontend/package.json 2>/dev/null)
        LAST_BUILD_COMMIT=$(git log -1 --format="%H" -- src/backend/static/ 2>/dev/null)
        if [[ -n "$LAST_SRC_COMMIT" && -n "$LAST_BUILD_COMMIT" ]]; then
            if ! git merge-base --is-ancestor "$LAST_SRC_COMMIT" "$LAST_BUILD_COMMIT" 2>/dev/null; then
                echo -e "${RED}WARNING: Frontend source has changes newer than the last build!${NC}"
                echo -e "${RED}Run: ./scripts/deploy.sh frontend${NC}"
                echo ""
                read -rp "Deploy backend anyway? [y/N] " REPLY
                [[ "$REPLY" =~ ^[Yy]$ ]] || exit 1
            fi
        fi

        git push
        echo -e "${YELLOW}Pulling on server...${NC}"
        deploy_to_server "cd $APP_DIR && git pull && chown -R backend:backend $APP_DIR/data/"
        [[ "$ON_LAN" == true ]] && echo -e "${GREEN}Pushed + pulled. Dev service auto-reloads.${NC}"
        ;;

    frontend)
        echo -e "${YELLOW}=== Frontend Build & Deploy ===${NC}"
        STATIC_DIR="$ROOT_DIR/src/backend/static"
        ASSETS_DIR="$STATIC_DIR/assets"

        # Clean + build
        rm -rf "$ASSETS_DIR"/*
        cd "$ROOT_DIR/frontend"
        npm run build

        if [[ ! -f "$STATIC_DIR/index.html" ]]; then
            echo -e "${RED}Build failed — no index.html${NC}"
            exit 1
        fi
        echo -e "${GREEN}Built $(ls -1 "$ASSETS_DIR" 2>/dev/null | wc -l) asset files${NC}"

        # Verify CSS references
        MISSING=0
        for js in "$ASSETS_DIR"/*.js; do
            for css in $(grep -oE '[A-Za-z0-9_-]+\.css' "$js" 2>/dev/null | sort -u); do
                if [[ "$css" != ".css" && "$css" != "style.css" ]]; then
                    if [[ ! -f "$ASSETS_DIR/$css" ]]; then
                        echo -e "${RED}Missing: $css (referenced in $(basename "$js"))${NC}"
                        MISSING=1
                    fi
                fi
            done
        done
        if [[ $MISSING -eq 1 ]]; then
            echo -e "${RED}Missing referenced CSS files!${NC}"
            exit 1
        fi

        # Commit, push, pull, restart
        cd "$ROOT_DIR"
        git add src/backend/static/
        git commit -m "${2:-build: rebuild frontend}" || echo "Nothing to commit"
        git push
        echo -e "${YELLOW}Pulling + restarting on server...${NC}"
        deploy_to_server "cd $APP_DIR && git pull && chown -R backend:backend $APP_DIR/data/ && systemctl restart backend-fastapi-dev"
        [[ "$ON_LAN" == true ]] && echo -e "${GREEN}Frontend deployed.${NC}"
        ;;

    deps)
        echo -e "${YELLOW}=== Dependency Deploy ===${NC}"
        cd "$ROOT_DIR"
        git push
        echo -e "${YELLOW}Pulling + syncing deps + restarting...${NC}"
        deploy_to_server "cd $APP_DIR && git pull && uv sync && chown -R backend:backend $APP_DIR/data/ && systemctl restart backend-fastapi-dev"
        [[ "$ON_LAN" == true ]] && echo -e "${GREEN}Dependencies synced and service restarted.${NC}"
        ;;

    restart)
        echo -e "${YELLOW}Restarting service...${NC}"
        deploy_to_server "systemctl restart backend-fastapi-dev"
        [[ "$ON_LAN" == true ]] && echo -e "${GREEN}Restarted.${NC}"
        ;;

    status)
        echo -e "${YELLOW}=== Server Status ===${NC}"
        deploy_to_server "cd $APP_DIR && echo 'Commit:' && git log --oneline -3 && echo '---' && systemctl status backend-fastapi-dev --no-pager -l 2>&1 | head -15"
        ;;

    logs)
        deploy_to_server "journalctl -u backend-fastapi-dev --no-pager -n 50"
        ;;

    *)
        echo "Usage: ./scripts/deploy.sh [backend|frontend|deps|restart|status|logs]"
        exit 1
        ;;
esac

echo -e "${GREEN}Done.${NC} https://chat.jackshome.com"
