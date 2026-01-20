#!/usr/bin/env bash
# Build the Voice PWA and emit the bundle into src/backend/static/voice.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VOICE_DIR="$ROOT_DIR/frontend-voice"
OUTPUT_DIR="$ROOT_DIR/src/backend/static/voice"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to build the Voice PWA." >&2
  exit 1
fi

if [[ ! -d "$VOICE_DIR" ]]; then
  echo "Missing frontend-voice directory at $VOICE_DIR" >&2
  exit 1
fi

LOCK_FILE="$VOICE_DIR/package-lock.json"
NODE_LOCK="$VOICE_DIR/node_modules/.package-lock.json"

if [[ ! -d "$VOICE_DIR/node_modules" ]]; then
  echo "Installing frontend-voice dependencies (npm ci)..."
  (cd "$VOICE_DIR" && npm ci)
elif [[ -f "$LOCK_FILE" && ! -f "$NODE_LOCK" ]]; then
  echo "Refreshing frontend-voice dependencies (npm ci)..."
  (cd "$VOICE_DIR" && npm ci)
elif [[ -f "$LOCK_FILE" && -f "$NODE_LOCK" && "$LOCK_FILE" -nt "$NODE_LOCK" ]]; then
  echo "Lockfile changed; reinstalling frontend-voice dependencies (npm ci)..."
  (cd "$VOICE_DIR" && npm ci)
fi

echo "Building Voice PWA (frontend-voice)..."
(cd "$VOICE_DIR" && npm run build)

if [[ ! -f "$OUTPUT_DIR/index.html" ]]; then
  echo "Build finished, but $OUTPUT_DIR/index.html was not found." >&2
  echo "Check $VOICE_DIR/vite.config.js for the configured outDir." >&2
  exit 1
fi

echo ""
echo "✅ Voice PWA built. Output: $OUTPUT_DIR"
echo "Reload https://<host>:8000/voice/ or reinstall the PWA to pick up changes."
