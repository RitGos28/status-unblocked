#!/bin/sh
# Start Status Unblocked services (backend / frontend)
set -eu

cd "$(dirname "$0")"

TARGET="${1:-backend}"

case "$TARGET" in
  backend)
    echo "Starting FastAPI backend from backend/..."
    exec backend/run.sh
    ;;
  frontend)
    echo "Starting React frontend from frontend/..."
    cd frontend && npm run dev
    ;;
  all)
    echo "Starting both backend and frontend..."
    backend/run.sh &
    BACKEND_PID=$!
    trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT
    cd frontend && npm run dev
    ;;
  *)
    echo "Usage: ./run.sh [backend|frontend|all]"
    exit 1
    ;;
esac
