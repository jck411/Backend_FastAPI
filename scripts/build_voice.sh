#!/usr/bin/env bash
# Build the Voice PWA and emit the bundle into src/backend/static/voice.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR/frontend-voice"

echo "Building Voice PWA (frontend-voice)..."
npm run build

echo ""
echo "✅ Voice PWA built. Output: $ROOT_DIR/src/backend/static/voice"
echo "Reload https://<host>:8000/voice/ or reinstall the PWA to pick up changes."
