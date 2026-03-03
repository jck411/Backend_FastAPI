#!/bin/bash
# Deploy to Proxmox LXC 111 via the Proxmox host
#
# Usage:
#   ./scripts/deploy.sh              # Backend only: push + pull + check deps/env
#   ./scripts/deploy.sh frontend     # Build frontend, push, pull, restart
#   ./scripts/deploy.sh deps         # Push, pull, uv sync, restart
#   ./scripts/deploy.sh restart      # Just restart the service
#   ./scripts/deploy.sh status       # Check service status + current commit
#   ./scripts/deploy.sh logs         # Tail recent service logs
#   ./scripts/deploy.sh env          # Check/push missing .env keys to server
#   ./scripts/deploy.sh check        # Run dependency + env checks only (no deploy)

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

# Check if server has any missing Python dependencies (compares against pyproject.toml)
check_deps() {
    if [[ "$ON_LAN" != true ]]; then return; fi
    echo -e "${YELLOW}Checking dependencies...${NC}"
    local result
    result=$(run_on_server "cd $APP_DIR && uv sync --dry-run 2>&1" 2>/dev/null) || true
    if echo "$result" | grep -qE "^(Would install|Resolved .* packages)"; then
        local to_install
        to_install=$(echo "$result" | grep "^Would install" || true)
        if [[ -n "$to_install" ]]; then
            echo -e "${RED}Server is missing packages:${NC}"
            echo "$to_install"
            read -rp "Install now? [Y/n] " REPLY
            REPLY="${REPLY:-y}"
            if [[ "$REPLY" =~ ^[Yy]$ ]]; then
                run_on_server "cd $APP_DIR && uv sync"
                echo -e "${GREEN}Dependencies synced.${NC}"
                return 0  # signal that a restart is needed
            fi
        fi
    else
        echo -e "${GREEN}Dependencies up to date.${NC}"
    fi
    return 1  # no restart needed
}

# Check if server .env is missing any keys present in local .env
check_env_keys() {
    if [[ "$ON_LAN" != true ]]; then return; fi
    if [[ ! -f "$ROOT_DIR/.env" ]]; then return; fi

    echo -e "${YELLOW}Checking .env keys...${NC}"

    # Extract key names from local .env (skip comments, blanks)
    local local_keys
    local_keys=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ROOT_DIR/.env" | cut -d= -f1 | sort -u)

    # Extract key names from server .env
    local server_keys
    server_keys=$(run_on_server "grep -E '^[A-Za-z_][A-Za-z0-9_]*=' $APP_DIR/.env" 2>/dev/null | cut -d= -f1 | tr -d '\r' | sort -u)

    # Find keys in local but not on server (exclude PROXMOX_* — those are local-only)
    local missing
    missing=$(comm -23 <(echo "$local_keys" | grep -v '^PROXMOX_' | grep -E '^[A-Z]') <(echo "$server_keys"))

    if [[ -n "$missing" ]]; then
        echo -e "${RED}Server .env is missing these keys:${NC}"
        echo "$missing"
        echo ""
        echo -e "${YELLOW}Add them to the server with:${NC}"
        echo -e "${GREEN}  ./scripts/deploy.sh env${NC}"
        echo ""
        read -rp "Push missing keys to server now? [Y/n] " REPLY
        REPLY="${REPLY:-y}"
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            local additions=""
            for key in $missing; do
                local value
                value=$(grep -E "^${key}=" "$ROOT_DIR/.env" | cut -d= -f2-)
                additions="${additions}${key}=${value}\n"
            done
            run_on_server "printf '${additions}' >> $APP_DIR/.env"
            echo -e "${GREEN}Added $(echo "$missing" | wc -w) key(s) to server .env.${NC}"
        fi
    else
        echo -e "${GREEN}.env keys in sync.${NC}"
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

        # Post-pull checks
        NEEDS_RESTART=false
        if check_deps; then NEEDS_RESTART=true; fi
        check_env_keys

        if [[ "$NEEDS_RESTART" == true ]]; then
            echo -e "${YELLOW}Restarting service (deps changed)...${NC}"
            deploy_to_server "systemctl restart backend-fastapi-dev"
        fi

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

    env)
        echo -e "${YELLOW}=== .env Key Check ===${NC}"
        check_env_keys
        ;;

    check)
        echo -e "${YELLOW}=== Pre-flight Checks ===${NC}"
        check_deps || true
        check_env_keys
        ;;

    *)
        echo "Usage: ./scripts/deploy.sh [backend|frontend|deps|restart|status|logs|env|check]"
        exit 1
        ;;
esac

echo -e "${GREEN}Done.${NC} https://chat.jackshome.com"
