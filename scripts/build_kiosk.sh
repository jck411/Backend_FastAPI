#!/usr/bin/env bash
# Build the Kiosk frontend and emit the bundle into src/backend/static.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KIOSK_DIR="$ROOT_DIR/frontend-kiosk"
OUTPUT_DIR="$ROOT_DIR/src/backend/static"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to build the Kiosk frontend." >&2
  exit 1
fi

if [[ ! -d "$KIOSK_DIR" ]]; then
  echo "Missing frontend-kiosk directory at $KIOSK_DIR" >&2
  exit 1
fi

LOCK_FILE="$KIOSK_DIR/package-lock.json"
NODE_LOCK="$KIOSK_DIR/node_modules/.package-lock.json"

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

echo "Building Kiosk frontend (frontend-kiosk)..."
(cd "$KIOSK_DIR" && npm run build)

if [[ ! -f "$OUTPUT_DIR/index.html" ]]; then
  echo "Build finished, but $OUTPUT_DIR/index.html was not found." >&2
  echo "Check $KIOSK_DIR/vite.config.js for the configured outDir." >&2
  exit 1
fi

echo ""
echo "✅ Kiosk frontend built. Output: $OUTPUT_DIR"
echo "Reload https://<host>:8000/ to pick up changes."
