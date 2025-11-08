#!/usr/bin/env bash
# Start both FastAPI backend and frontend dev server

# Ensure logs directory exists
mkdir -p logs

# Function to cleanup background processes on exit
cleanup() {
    echo "Stopping servers..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

# Start the backend
echo "Starting FastAPI backend..."
uv run uvicorn backend.app:create_app \
    --factory \
    --reload &

BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start the frontend
echo "Starting frontend dev server..."
cd frontend && npm run dev &

FRONTEND_PID=$!

echo ""
echo "======================================"
echo "Backend running on http://localhost:8000"
echo "Frontend running on http://localhost:5173"
echo "======================================"
echo "Press Ctrl+C to stop both servers"
echo ""

# Wait for both processes
wait
