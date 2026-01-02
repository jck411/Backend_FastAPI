#!/bin/bash
# Sync photos from public Google Photos album
# Run this via cron or systemd timer for automatic updates

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "$(date): Starting slideshow sync..."

# Run the Python sync script in the virtual environment
cd "$PROJECT_DIR"
source .venv/bin/activate
python scripts/sync_slideshow.py

echo "$(date): Sync complete."
