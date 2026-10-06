#!/bin/sh
# The accountless demo in one command: migrate, seed two days of made-up
# updates, start the fake GitHub and fake Teams connector, and serve the app.
#
# Ports: PORT (app, 8000), GITHUB_PORT (8091), TEAMS_PORT (8092). Links in
# digests, issues and Teams notices follow PORT, e.g. PORT=9000 ./run.sh
#
# Configuration comes from backend/.env.example's demo values, which fill in
# anything unset when there is no backend/.env (see config.py). Export a
# variable, or create backend/.env, to change it.
set -eu

cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
    VENV_DIR=".venv"
elif [ -x "../.venv/bin/python" ]; then
    VENV_DIR="../.venv"
else
    echo "Missing .venv. Set up the project environment first (see README.md)." >&2
    exit 1
fi
PYTHON="$VENV_DIR/bin/python"
export PYTHONPATH=src

PORT="${PORT:-8000}"
GITHUB_PORT="${GITHUB_PORT:-8091}"
TEAMS_PORT="${TEAMS_PORT:-8092}"
# Only when a port moved: otherwise .env.example (or your .env) decides.
if [ "$PORT" != 8000 ]; then
    export STANDUP_BASE_URL="${STANDUP_BASE_URL:-http://127.0.0.1:$PORT}"
fi
if [ "$GITHUB_PORT" != 8091 ]; then
    export STANDUP_GITHUB_API_URL="${STANDUP_GITHUB_API_URL:-http://127.0.0.1:$GITHUB_PORT}"
fi

# The stand-ins the demo values point at. Stopped when this script exits.
$PYTHON -m scripts.fake_github --port "$GITHUB_PORT" >/dev/null 2>&1 &
GITHUB_PID=$!
$PYTHON -m scripts.fake_teams_connector --port "$TEAMS_PORT" >/dev/null 2>&1 &
TEAMS_PID=$!
trap 'kill $GITHUB_PID $TEAMS_PID 2>/dev/null || true' EXIT INT TERM

"$VENV_DIR/bin/alembic" upgrade head
$PYTHON -m scripts.seed_demo --days 2
$PYTHON -m scripts.set_github_repo --team core --repo demo/core
echo "App: http://127.0.0.1:$PORT   Fake GitHub: http://127.0.0.1:$GITHUB_PORT   Fake Teams connector: http://127.0.0.1:$TEAMS_PORT"
"$VENV_DIR/bin/uvicorn" standup.main:app --app-dir src --host "${HOST:-127.0.0.1}" --port "$PORT"
