#!/usr/bin/env bash
# Start the FastAPI backend with full logging to file

# Ensure logs directory exists
mkdir -p logs

# Start uvicorn with logging configuration
uv run uvicorn backend.app:create_app \
    --factory \
    --reload \
    --log-config logging_config.json \
    --log-level debug
