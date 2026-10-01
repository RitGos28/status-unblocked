#!/usr/bin/env bash
# Run the whole demo (docs/DEMO.md) against a real server and assert every step.
#
# Usage: scripts/demo_check.sh            (from the repo root)
#        DEMO_PORT=8091 scripts/demo_check.sh
#
# Needs no accounts and touches nothing outside a temp directory: its own
# SQLite database, signing key and server, which is always stopped on exit.
# Exits non-zero on the first failed step, printing the server log tail.
set -euo pipefail

cd "$(dirname "$0")/.."
BIN="${VENV_BIN:-.venv/bin}"
PY="$BIN/python"
[ -x "$PY" ] || { echo "Missing $BIN/python (see README), or set VENV_BIN." >&2; exit 1; }

PORT="${DEMO_PORT:-8090}"
BASE="http://127.0.0.1:$PORT"
WORK="$(mktemp -d)"
SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; fi
    rm -rf "$WORK"
}
trap cleanup EXIT

export STANDUP_DATABASE_URL="sqlite:///$WORK/demo.db"
export STANDUP_SECRET_KEY="$($PY -c 'import secrets; print(secrets.token_urlsafe(48))')"
export STANDUP_BASE_URL="$BASE"
export STANDUP_ENV=local
export STANDUP_LOG_LEVEL=WARNING

STEP=0
pass() { STEP=$((STEP + 1)); printf '  ok %2d  %s\n' "$STEP" "$1"; }
fail() {
    printf '  FAIL    %s\n' "$1" >&2
    [ -f "$WORK/server.log" ] && { echo "--- server log (tail) ---" >&2; tail -20 "$WORK/server.log" >&2; }
    exit 1
}
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "Demo check against $BASE"

# --- setup: migrate, seed two days, start the server ------------------------
"$BIN/alembic" upgrade head >/dev/null 2>&1 || fail "alembic upgrade head"
$PY -m scripts.seed_demo --days 2 >"$WORK/seed.txt" || fail "seed_demo --days 2"
link_for() { grep -F " / $1: " "$WORK/seed.txt" | awk '{print $NF}'; }
ADA="$(link_for "Ada Okafor")"; DANA="$(link_for "Dana Park")"
[ -n "$ADA" ] && [ -n "$DANA" ] || fail "seed printed login links"
pass "seeded Core Platform (2 days of updates) and Mobile; login links printed"

"$BIN/uvicorn" standup.main:app --port "$PORT" >"$WORK/server.log" 2>&1 &
SERVER_PID=$!
curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null "$BASE/healthz" || fail "server came up"
pass "server is up"

# --- sign-in and scoping -----------------------------------------------------
[ "$(status "$BASE/digests")" = 401 ] || fail "signed-out /digests answers 401"
pass "signed out: /digests is 401"
[ "$(status -c "$WORK/ada.jar" "$ADA")" = 303 ] || fail "Ada's login link"
DIGESTS="$(curl -s -b "$WORK/ada.jar" "$BASE/digests")"
grep -q "Core Platform" <<<"$DIGESTS" || fail "Ada sees Core Platform"
! grep -q "Mobile" <<<"$DIGESTS" || fail "Ada does not see Mobile"
pass "Ada signs in with her link and sees only her team"

# --- submit, and resubmit to supersede ---------------------------------------
for text in "Reviewed the rollout plan." "Reviewed the rollout plan and the runbook."; do
    [ "$(status -b "$WORK/ada.jar" -X POST "$BASE/submit" \
        --data-urlencode "progress=$text" \
        --data-urlencode "blockers=Waiting on staging credentials from infra.")" = 303 ] \
        || fail "Ada submits"
done
pass "Ada submits twice; the second replaces the first"

# --- the daily build, at the cutoff (demo clock) -----------------------------
AT="$($PY - <<'EOF'
from datetime import UTC, datetime, timedelta
now = datetime.now(UTC)
cutoff = now.replace(hour=11, minute=5, second=0, microsecond=0)
print((max(now, cutoff) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
EOF
)"
TICK="$($PY -m scripts.tick --at "$AT" 2>/dev/null | tail -1)" || fail "scripts.tick --at"
grep -Eq "built [1-9]" <<<"$TICK" || fail "tick built digests (got: $TICK)"
pass "scheduler pass at $AT: $TICK"

DIGEST_ID="$(curl -s -b "$WORK/ada.jar" "$BASE/digests" | grep -o 'href="/digest/[0-9a-f-]*"' | head -1 | cut -d/ -f3 | tr -d '"')"
[ -n "$DIGEST_ID" ] || fail "today's digest is listed"
PAGE="$(curl -s -b "$WORK/ada.jar" "$BASE/digest/$DIGEST_ID")"
grep -q "Waiting on staging credentials from infra." <<<"$PAGE" || fail "Ada's blocker is in the digest"
grep -q "Moved to Blockers" <<<"$PAGE" || fail "Chen's misfiled blocker is promoted, with the reason"
grep -q "runbook" <<<"$PAGE" || fail "the resubmission is the one in the digest"
MD="$(curl -s -b "$WORK/ada.jar" "$BASE/digest/$DIGEST_ID.md")"
! grep -q "No blockers today" <<<"$MD" || fail "'No blockers today.' is not a blocker"
grep -q "$BASE/evidence/" <<<"$MD" || fail "every line links to its evidence"
pass "digest: blockers first, promotion explained, negation honoured, every line cited"

# --- evidence and integrity --------------------------------------------------
EVIDENCE="$(grep -o 'href="/evidence/[0-9a-f-]*"' <<<"$PAGE" | head -1 | cut -d'"' -f2)"
EV="$(curl -s -b "$WORK/ada.jar" "$BASE$EVIDENCE")"
grep -q "<mark>" <<<"$EV" || fail "evidence page highlights the cited span"
pass "evidence page shows the stored words with the span highlighted"

$PY -m scripts.verify_integrity >/dev/null || fail "verify_integrity passes on the live database"
cp "$WORK/demo.db" "$WORK/tampered.db"
$PY - "$WORK/tampered.db" <<'EOF'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("UPDATE \"update\" SET raw_text = replace(raw_text, 'staging', 'prod')")
con.commit()
EOF
if STANDUP_DATABASE_URL="sqlite:///$WORK/tampered.db" $PY -m scripts.verify_integrity >/dev/null; then
    fail "verify_integrity catches edited stored text"
fi
pass "audit chain intact; an edited update is caught by verify_integrity"

# --- another team cannot see it ----------------------------------------------
[ "$(status -c "$WORK/dana.jar" "$DANA")" = 303 ] || fail "Dana's login link"
[ "$(status -b "$WORK/dana.jar" "$BASE/digest/$DIGEST_ID")" = 404 ] || fail "Dana gets 404 on Core's digest"
[ "$(status -b "$WORK/dana.jar" "$BASE$EVIDENCE")" = 404 ] || fail "Dana gets 404 on Core's evidence"
pass "Dana (Mobile) gets 404 on Core Platform's digest and evidence"

# --- ops and error pages -----------------------------------------------------
curl -s "$BASE/scope" | grep -q '"scope_violations"' || fail "/scope reports counts"
ERR_TYPE="$(curl -s -o /dev/null -w '%{content_type}' -H 'accept: text/html' -b "$WORK/ada.jar" "$BASE/digest/nope")"
[[ "$ERR_TYPE" == text/html* ]] || fail "browser errors render as HTML (got $ERR_TYPE)"
pass "/scope counter answers; browser errors are HTML pages"

echo "All $STEP demo steps passed."
