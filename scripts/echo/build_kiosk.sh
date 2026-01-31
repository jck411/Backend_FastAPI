#!/usr/bin/env bash
# Build (default) or serve the Kiosk frontend. Build outputs to src/backend/static.

set -euo pipefail

ACTION="${1:-build}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KIOSK_DIR="$ROOT_DIR/frontend-kiosk"
OUTPUT_DIR="$ROOT_DIR/src/backend/static"

usage() {
  cat <<'EOF'
Usage: scripts/build_kiosk.sh [build|serve]

build (default): Install deps if needed and emit production bundle to src/backend/static.
serve: Start Vite dev server on https://0.0.0.0:5174 (uses certs from certs/ if present).
EOF
}

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to build or serve the Kiosk frontend." >&2
  exit 1
fi

if [[ ! -d "$KIOSK_DIR" ]]; then
  echo "Missing frontend-kiosk directory at $KIOSK_DIR" >&2
  exit 1
fi

LOCK_FILE="$KIOSK_DIR/package-lock.json"
NODE_LOCK="$KIOSK_DIR/node_modules/.package-lock.json"

ensure_deps() {
  if [[ ! -d "$KIOSK_DIR/node_modules" ]]; then
    echo "Installing frontend-kiosk dependencies (npm ci)..."
    (cd "$KIOSK_DIR" && npm ci)
  elif [[ -f "$LOCK_FILE" && ! -f "$NODE_LOCK" ]]; then
    echo "Refreshing frontend-kiosk dependencies (npm ci)..."
    (cd "$KIOSK_DIR" && npm ci)
  elif [[ -f "$LOCK_FILE" && -f "$NODE_LOCK" && "$LOCK_FILE" -nt "$NODE_LOCK" ]]; then
    echo "Lockfile changed; reinstalling frontend-kiosk dependencies (npm ci)..."
    (cd "$KIOSK_DIR" && npm ci)
  fi
}

case "$ACTION" in
  build)
    ensure_deps
    echo "Building Kiosk frontend (frontend-kiosk)..."
    (cd "$KIOSK_DIR" && npm run build)

    if [[ ! -f "$OUTPUT_DIR/index.html" ]]; then
      echo "Build finished, but $OUTPUT_DIR/index.html was not found." >&2
      echo "Check $KIOSK_DIR/vite.config.js for the configured outDir." >&2
      exit 1
    fi

    echo ""
    echo "✅ Kiosk frontend built. Output: $OUTPUT_DIR"
    echo "Reload https://<host>:8000/ to pick up changes (backend serves built assets)."
    ;;

  serve)
    ensure_deps
    echo "Starting Vite dev server for kiosk on https://0.0.0.0:5174 (ctrl+c to stop)..."
    (cd "$KIOSK_DIR" && npm run dev -- --host --https --port 5174)
    ;;

  *)
    usage
    exit 1
    ;;
esac
