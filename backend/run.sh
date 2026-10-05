#!/bin/sh
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
export STANDUP_DATABASE_URL="${STANDUP_DATABASE_URL:-sqlite:///./standup.db}"
if [ -z "${STANDUP_SECRET_KEY:-}" ]; then
    SECRET_FILE=".local-secret-key"
    if [ ! -s "$SECRET_FILE" ]; then
        (umask 077; $PYTHON -c 'import secrets; print(secrets.token_urlsafe(48))' > "$SECRET_FILE")
    fi
    STANDUP_SECRET_KEY="$(cat "$SECRET_FILE")"
    export STANDUP_SECRET_KEY
    echo "Using the local signing key in $SECRET_FILE."
fi

"$VENV_DIR/bin/alembic" upgrade head
$PYTHON -m scripts.seed_demo --with-updates
exec "$VENV_DIR/bin/uvicorn" standup.main:app --app-dir src --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
