#!/bin/bash
# Deploy script - builds frontend cleanly and deploys to server
# Usage: ./scripts/deploy.sh [message]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
STATIC_DIR="$ROOT_DIR/src/backend/static"
ASSETS_DIR="$STATIC_DIR/assets"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Frontend Build & Deploy ===${NC}"

# 1. Clean old assets (prevents stale file issues)
echo -e "${YELLOW}Cleaning old assets...${NC}"
rm -rf "$ASSETS_DIR"/*

# 2. Build frontend
echo -e "${YELLOW}Building frontend...${NC}"
cd "$ROOT_DIR/frontend"
npm run build

# 3. Verify build output
if [ ! -f "$STATIC_DIR/index.html" ]; then
    echo -e "${RED}ERROR: Build failed - no index.html${NC}"
    exit 1
fi

# Count assets
ASSET_COUNT=$(ls -1 "$ASSETS_DIR" 2>/dev/null | wc -l)
echo -e "${GREEN}Built $ASSET_COUNT asset files${NC}"

# 4. Verify all CSS references exist
echo -e "${YELLOW}Verifying asset references...${NC}"
MISSING=0
for js in "$ASSETS_DIR"/*.js; do
    for css in $(grep -oE '[A-Za-z0-9_-]+\.css' "$js" 2>/dev/null | sort -u); do
        if [ "$css" != ".css" ] && [ "$css" != "style.css" ]; then
            if [ ! -f "$ASSETS_DIR/$css" ]; then
                echo -e "${RED}Missing: $css (referenced in $(basename $js))${NC}"
                MISSING=1
            fi
        fi
    done
done

if [ $MISSING -eq 1 ]; then
    echo -e "${RED}ERROR: Missing referenced CSS files!${NC}"
    exit 1
fi
echo -e "${GREEN}All asset references valid${NC}"

# 5. Git commit
echo -e "${YELLOW}Committing changes...${NC}"
cd "$ROOT_DIR"
git add src/backend/static/
COMMIT_MSG="${1:-build: rebuild frontend}"
git commit -m "$COMMIT_MSG" || echo "Nothing to commit"

# 6. Push
echo -e "${YELLOW}Pushing to origin...${NC}"
git push

# 7. Deploy to server
echo -e "${YELLOW}Deploying to server...${NC}"
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git fetch origin && git reset --hard origin/master && chown -R backend:backend /opt/backend-fastapi/src/backend/data/ && systemctl restart backend-fastapi-dev"

echo -e "${GREEN}=== Deploy complete ===${NC}"
echo -e "Test at: https://chat.jackshome.com"
