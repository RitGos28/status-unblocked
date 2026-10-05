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
GH_PORT="${DEMO_GITHUB_PORT:-$((PORT + 1))}"
BASE="http://127.0.0.1:$PORT"
GH="http://127.0.0.1:$GH_PORT"
TEAMS_PORT="${DEMO_TEAMS_PORT:-$((PORT + 2))}"
TEAMS="http://127.0.0.1:$TEAMS_PORT"
WORK="$(mktemp -d)"
SERVER_PID=""
GITHUB_PID=""
TEAMS_PID=""

cleanup() {
    for pid in "$SERVER_PID" "$GITHUB_PID" "$TEAMS_PID"; do
        if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
    done
    rm -rf "$WORK"
}
trap cleanup EXIT

export STANDUP_DATABASE_URL="sqlite:///$WORK/demo.db"
export STANDUP_SECRET_KEY="$($PY -c 'import secrets; print(secrets.token_urlsafe(48))')"
export STANDUP_BASE_URL="$BASE"
export STANDUP_ENV=local
export STANDUP_LOG_LEVEL=WARNING
# Blockers go to a local fake GitHub, through the real GitHub client.
export STANDUP_TRACKER=github
export STANDUP_GITHUB_TOKEN=demo-token
export STANDUP_GITHUB_API_URL="$GH"
# The Teams bot, in the anonymous mode Agents Playground uses; its replies go
# to a local fake connector instead of Microsoft.
export STANDUP_TEAMS_ENABLED=true
export CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED=True
replay() { $PY -m scripts.teams_replay "$@" --app "$BASE" --connector "$TEAMS" >/dev/null; }
bot_said() { curl -s "$TEAMS/messages"; }

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
pass "seeded Core Platform (2 days of updates) and Mobile (today); login links printed"

$PY -m scripts.set_github_repo --team core --repo demo/core >/dev/null || fail "point Core Platform at a repo"
$PY -m scripts.fake_github --port "$GH_PORT" >"$WORK/github.log" 2>&1 &
GITHUB_PID=$!
curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null "$GH/" || fail "fake GitHub came up"
pass "fake GitHub is up at $GH; Core Platform's blockers go to demo/core"
$PY -m scripts.fake_teams_connector --port "$TEAMS_PORT" >"$WORK/teams.log" 2>&1 &
TEAMS_PID=$!
curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null "$TEAMS/" || fail "fake Teams connector came up"
pass "fake Teams connector is up at $TEAMS"

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

# --- Teams: link Ada's account, then talk to the bot -----------------------
CODE="$(curl -s -b "$WORK/ada.jar" "$BASE/me/teams" | grep -o 'link [A-Za-z0-9._-]*' | head -1 | cut -d' ' -f2)"
[ -n "$CODE" ] || fail "/me/teams shows Ada a link code"
replay personal_command --text "link $CODE" || fail "the bot accepts 'link <code>'"
grep -q "Linked. You're Ada Okafor" <<<"$(bot_said)" || fail "the bot confirms the link"
replay personal_command --text "standup" || fail "the bot accepts 'standup'"
grep -q "application/vnd.microsoft.card.adaptive" <<<"$(bot_said)" || fail "'standup' gets the update card"
replay channel_unaddressed || fail "the bot accepts a channel message"
replay channel_mention || fail "the bot accepts a channel @mention"
grep -q "read channel conversations" <<<"$(bot_said)" || fail "a channel @mention gets a pointer to the 1:1 chat"
pass "Teams: Ada links her account, 'standup' returns the card, a channel mention gets a pointer"

# --- submit, and resubmit to supersede ---------------------------------------
for text in "Reviewed the rollout plan." "Reviewed the rollout plan and the runbook."; do
    [ "$(status -b "$WORK/ada.jar" -X POST "$BASE/submit" \
        --data-urlencode "progress=$text" \
        --data-urlencode "blockers=Waiting on staging credentials from infra.")" = 303 ] \
        || fail "Ada submits"
done
seq 6 | xargs -P 6 -I{} curl -s -o /dev/null -b "$WORK/ada.jar" -X POST "$BASE/submit" \
    --data-urlencode "progress=Double-clicked submit {}" \
    --data-urlencode "blockers=Waiting on staging credentials from infra."
[ "$(status -b "$WORK/ada.jar" -X POST "$BASE/submit" \
    --data-urlencode "progress=Reviewed the rollout plan and the runbook." \
    --data-urlencode "blockers=Waiting on staging credentials from infra.")" = 303 ] \
    || fail "Ada can still submit after six simultaneous submits"
pass "Ada submits twice, then six times at once; she is never locked out and the last one counts"
[ "$(status -c "$WORK/chen.jar" "$(link_for "Chen Wei")")" = 303 ] || fail "Chen's login link"
[ "$(status -b "$WORK/chen.jar" -X POST "$BASE/submit" \
    --data-urlencode $'progress=Drafted the schema update.\nBlockers:\nnot really' \
    --data-urlencode "blockers=Stuck on the deploy pipeline.")" = 303 ] \
    || fail "a section heading typed into another box is accepted, not a 500"
pass "Chen types 'Blockers:' inside Progress; the submission is stored correctly"
[ "$(status -c "$WORK/bruno.jar" "$(link_for "Bruno Silva")")" = 303 ] || fail "Bruno's login link"
[ "$(status -b "$WORK/bruno.jar" -X POST "$BASE/submit" \
    --data-urlencode "progress=Merged the API changes, but waiting on review for the DB migration." \
    --data-urlencode "blockers=None")" = 303 ] || fail "Bruno submits"
pass "Bruno answers 'None' for blockers and mentions a wait inside Progress"

# --- the daily build, at the cutoff (demo clock) -----------------------------
AT="$($PY - <<'EOF'
from datetime import UTC, datetime, timedelta
now = datetime.now(UTC)
cutoff = now.replace(hour=11, minute=5, second=0, microsecond=0)
print((max(now, cutoff) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
EOF
)"
if STANDUP_BASE_URL= $PY -m scripts.tick --at "$AT" >/dev/null 2>&1; then
    fail "a scheduler pass without STANDUP_BASE_URL refuses (its links would be relative)"
fi
# Wait on these two by PID: a bare `wait` would also wait for the server.
$PY -m scripts.tick --at "$AT" 2>/dev/null | tail -1 >"$WORK/tick1.txt" &
TICK1=$!
$PY -m scripts.tick --at "$AT" 2>/dev/null | tail -1 >"$WORK/tick2.txt" &
TICK2=$!
wait "$TICK1" "$TICK2"
TICK="$(cat "$WORK/tick1.txt") / $(cat "$WORK/tick2.txt")"
BUILT=$(grep -Eho "built [0-9]+" "$WORK/tick1.txt" "$WORK/tick2.txt" | awk '{s += $2} END {print s}')
# Core Platform has two days and Mobile one: three digests, each built once.
[ "$BUILT" = 3 ] || fail "two simultaneous passes build each day's digest exactly once (got: $TICK)"
pass "two scheduler passes at once ($AT) build each digest once; no base URL refuses"

ISSUES="$(curl -s -H 'authorization: Bearer demo-token' "$GH/repos/demo/core/issues?labels=standup-blocker&state=all")"
ADA_ISSUES="$($PY -c '
import json, sys
for issue in json.load(sys.stdin):
    if "staging credentials" in issue["title"]:
        print(issue["number"], issue["comments"])' <<<"$ISSUES")"
[ "$(wc -l <<<"$ADA_ISSUES" | tr -d ' ')" = 1 ] || fail "Ada's blocker, reported on both days, is a single issue"
! grep -q '"title":"Blocker: Blockers:' <<<"$ISSUES" || fail "a heading typed on its own line is not filed as a blocker"
[ "$(cut -d' ' -f2 <<<"$ADA_ISSUES")" = 1 ] || fail "the second day added one comment to it"
grep -q "Still blocked on" <<<"$(curl -s "$GH/demo/core/issues/$(cut -d' ' -f1 <<<"$ADA_ISSUES")")" \
    || fail "the second day's comment says 'Still blocked on'"
ADA_PAGE="$(curl -s "$GH/demo/core/issues/$(cut -d' ' -f1 <<<"$ADA_ISSUES")")"
grep -q "team:core" <<<"$ADA_PAGE" || fail "the issue is labelled with its team"
grep -q '&#34;days_reported&#34;: 2\|&quot;days_reported&quot;: 2\|"days_reported": 2' <<<"$ADA_PAGE" \
    || fail "the day-2 comment carries a JSON update with days_reported 2"
grep -q "standup_blocker" <<<"$ADA_PAGE" || fail "the issue carries a structured JSON record"
pass "blockers became GitHub issues: Ada's two-day blocker is one issue plus a 'Still blocked' comment"
NOTICES="$(bot_said | grep -o 'Core Platform digest for [0-9-]* is ready' | sort -u | wc -l | tr -d ' ')"
TOTAL_NOTICES="$(bot_said | grep -o 'digest for [0-9-]* is ready' | wc -l | tr -d ' ')"
[ "$TOTAL_NOTICES" = "$NOTICES" ] || fail "no digest was announced twice ($TOTAL_NOTICES notices for $NOTICES digests)"
grep -q "still open from an earlier day" <<<"$(bot_said)" || fail "today's notice counts the carried-over blocker"
[ "$NOTICES" = 2 ] || fail "Ada got one 'digest is ready' notice per day's digest, not one per pass (got $NOTICES)"
pass "Teams: the scheduler told Ada each day's digest is ready (dated, counting carried-over blockers), once each, with no credentials"

DIGEST_ID="$(curl -s -b "$WORK/ada.jar" "$BASE/digests" | grep -o 'href="/digest/[0-9a-f-]*"' | head -1 | cut -d/ -f3 | tr -d '"')"
[ -n "$DIGEST_ID" ] || fail "today's digest is listed"
PAGE="$(curl -s -b "$WORK/ada.jar" "$BASE/digest/$DIGEST_ID")"
grep -q "Waiting on staging credentials from infra." <<<"$PAGE" || fail "Ada's blocker is in the digest"
STILL="$(sed -n '/## Still blocked/,/## Blockers/p' <<<"$(curl -s -b "$WORK/ada.jar" "$BASE/digest/$DIGEST_ID.md")")"
grep -q "Ada Okafor\*\* - Waiting on staging credentials" <<<"$STILL" || fail "Ada's two-day blocker is under Still blocked"
ADA_LINE="$(grep 'Ada Okafor' <<<"$STILL" | head -1)"
grep -q '\[source\]' <<<"$ADA_LINE" && grep -q '\[earlier report\]' <<<"$ADA_LINE" \
    || fail "the carried-over blocker cites both days: today's source and the earlier report"
grep -q "Also reported on" <<<"$PAGE" || fail "the page says when it was first reported"
grep -q "Moved to Blockers" <<<"$PAGE" || fail "Chen's misfiled blocker is promoted, with the reason"
grep -q "runbook" <<<"$PAGE" || fail "the resubmission is the one in the digest"
MD="$(curl -s -b "$WORK/ada.jar" "$BASE/digest/$DIGEST_ID.md")"
! grep -q "No blockers today" <<<"$MD" || fail "'No blockers today.' is not a blocker"
! grep -q "Bruno Silva\*\* - None" <<<"$MD" || fail "'None' in the Blockers box is not a blocker"
grep -q "waiting on review for the DB migration" <<<"$(sed -n '/## Blockers/,/## Progress/p' <<<"$MD")" \
    || fail "a blocker in one clause survives a negation-free sentence and is promoted"
grep -q "$BASE/evidence/" <<<"$MD" || fail "every line links to its evidence"
grep -q "Moved to Blockers" <<<"$MD" || fail "the Markdown digest explains a promoted blocker, like the page"
! grep -q '\[\[source\]\]' <<<"$MD" || fail "the Markdown digest's links are ordinary links"
# Blockers and carried-over blockers ("Still blocked") both get an issue link.
BLOCKER_LINES="$(sed -n '/## Still blocked/,/## Progress/p' <<<"$MD" | grep -c '^- ')"
ISSUE_LINKS="$(grep -o "href=\"$GH/demo/core/issues/[0-9]*\"" <<<"$PAGE" | wc -l | tr -d ' ')"
[ "$ISSUE_LINKS" = "$BLOCKER_LINES" ] || fail "every blocker links to its issue ($ISSUE_LINKS links, $BLOCKER_LINES blockers)"
pass "digest: Ada's repeat blocker is 'Still blocked' citing both days; promotion explained, negation honoured, every line cited, every blocker linked to its issue"

replay personal_card_submit || fail "the bot accepts a card submission"
grep -q "Recorded for Core Platform" <<<"$(bot_said)" || fail "a card submission is recorded"
pass "Teams: Ada files her update through the card, through the same ingest path as the web form"

# --- evidence and integrity --------------------------------------------------
EVIDENCE="$(grep -o 'href="/evidence/[0-9a-f-]*"' <<<"$PAGE" | head -1 | cut -d'"' -f2)"
EV="$(curl -s -b "$WORK/ada.jar" "$BASE$EVIDENCE")"
grep -q "<mark>" <<<"$EV" || fail "evidence page highlights the cited span"
grep -q "web form" <<<"$EV" || fail "the evidence page says in words why there is no message link"
pass "evidence page shows the stored words with the span highlighted"

seq 20 | xargs -P 20 -I{} curl -s -o /dev/null -b "$WORK/ada.jar" "$BASE$EVIDENCE"
$PY -m scripts.verify_integrity >/dev/null || fail "verify_integrity passes after 20 simultaneous evidence views"
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
pass "20 simultaneous evidence views leave the audit chain intact; an edited update is caught"

# --- another team cannot see it ----------------------------------------------
[ "$(status -c "$WORK/dana.jar" "$DANA")" = 303 ] || fail "Dana's login link"
[ "$(status -b "$WORK/dana.jar" "$BASE/digest/$DIGEST_ID")" = 404 ] || fail "Dana gets 404 on Core's digest"
[ "$(status -b "$WORK/dana.jar" "$BASE$EVIDENCE")" = 404 ] || fail "Dana gets 404 on Core's evidence"
NOTFOUND="$(curl -s -H 'accept: text/html' -b "$WORK/dana.jar" "$BASE/digest/$DIGEST_ID")"
grep -q "Dana Park" <<<"$NOTFOUND" || fail "the 404 page keeps Dana's signed-in header"
! grep -q "$DIGEST_ID" <<<"$NOTFOUND" || fail "the 404 page does not echo the digest id"
pass "Dana (Mobile) gets 404 on Core Platform's digest and evidence"

# --- ops and error pages -----------------------------------------------------
curl -s "$BASE/scope" | grep -q '"scope_violations":1' || fail "/scope counts the one refused channel message"
ERR_TYPE="$(curl -s -o /dev/null -w '%{content_type}' -H 'accept: text/html' -b "$WORK/ada.jar" "$BASE/digest/nope")"
[[ "$ERR_TYPE" == text/html* ]] || fail "browser errors render as HTML (got $ERR_TYPE)"
pass "/scope counts the refused channel message (content-free); browser errors are HTML pages"
! grep -Eq '/login/[A-Za-z0-9]' "$WORK/server.log" || fail "no login token appears in the server's access log"
pass "the server's access log shows /login/[redacted], never a login token"

echo "All $STEP demo steps passed."
