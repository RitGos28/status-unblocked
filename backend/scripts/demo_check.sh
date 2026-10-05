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
if [ -z "${VENV_BIN:-}" ]; then
    if [ -x ".venv/bin/python" ]; then
        BIN=".venv/bin"
    elif [ -x "../.venv/bin/python" ]; then
        BIN="../.venv/bin"
    else
        BIN=".venv/bin"
    fi
else
    BIN="$VENV_BIN"
fi
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

export PYTHONPATH=src
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
CODE="$(curl -s -b "$WORK/ada.jar" "$BASE/me/teams" | grep -o '<pre class="raw">link [A-Za-z0-9._-]*' | head -1 | cut -d' ' -f3)"
[ -n "$CODE" ] || fail "/me/teams shows Ada a link code"
replay personal_command --text "link $CODE" || fail "the bot accepts 'link <code>'"
grep -q "Linked. You're Ada Okafor" <<<"$(bot_said)" || fail "the bot confirms the link"
replay personal_command --text "link $CODE" --as aad-someone-else || fail "the bot accepts a reused code"
grep -q "invalid or has expired" <<<"$(bot_said)" || fail "a used link code is refused from another account"
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
    --data-urlencode $'progress=Merged the API changes, but waiting on review for the DB migration.\nFixed the bug where users cannot log in.' \
    --data-urlencode "blockers=Nope, all clear")" = 303 ] || fail "Bruno submits"
pass "Bruno answers 'Nope, all clear' for blockers and mentions a wait inside Progress"

# --- made-up updates from a spreadsheet: two earlier days for Mobile --------
D2="$($PY -c 'from datetime import UTC, datetime, timedelta; print((datetime.now(UTC) - timedelta(days=2)).date())')"
D1="$($PY -c 'from datetime import UTC, datetime, timedelta; print((datetime.now(UTC) - timedelta(days=1)).date())')"
printf '%s\n' "date,team,member,progress,blockers,plan" \
    "$D2,mobile,Dana Park,Profiled the cold start.,Waiting on the signing certificate from IT.,Cut the cold start time." \
    "$D1,mobile,Dana Park,Cut cold start by 40 percent.,Waiting on the signing certificate from IT.,Ship the beta build." \
    >"$WORK/mobile.body"
# Saved as Excel's "CSV UTF-8": a byte-order mark in front of the header.
{ printf '\xef\xbb\xbf'; cat "$WORK/mobile.body"; } >"$WORK/mobile.csv"
$PY -m scripts.import_updates_csv "$WORK/mobile.csv" 2>/dev/null | grep -q "imported 2, skipped 0" || fail "two CSV rows import"
$PY -m scripts.import_updates_csv "$WORK/mobile.csv" 2>/dev/null | grep -q "imported 0, skipped 2" || fail "re-importing the same CSV changes nothing"
printf '%s\n' "date,team,member,progress,blockers,plan" "$D1,mobile,Nobody,x,," >"$WORK/bad.csv"
if $PY -m scripts.import_updates_csv "$WORK/bad.csv" >"$WORK/bad.out" 2>/dev/null; then fail "a CSV with a bad row is refused"; fi
grep -q "line 2: no active member 'Nobody' in team 'mobile'" "$WORK/bad.out" || fail "the refusal names the line and the problem"
printf '%s\n' "date,team,member,progress,blockers,plan" "2031-01-01,mobile,Dana Park,x,," >"$WORK/future.csv"
if $PY -m scripts.import_updates_csv "$WORK/future.csv" >"$WORK/future.out" 2>/dev/null; then fail "a future-dated row is refused"; fi
grep -q "is in the future" "$WORK/future.out" || fail "the refusal says the date is in the future"
pass "spreadsheet import (Excel's CSV UTF-8): two earlier days for Mobile load; re-import changes nothing; a bad or future row is refused with its line"

# --- the daily build, at the cutoff (demo clock) -----------------------------
AT="$($PY - <<'EOF'
from datetime import UTC, datetime, timedelta
now = datetime.now(UTC)
cutoff = now.replace(hour=11, minute=5, second=0, microsecond=0)
print((max(now, cutoff) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
EOF
)"
if STANDUP_BASE_URL= $PY -m scripts.tick --at "$AT" >/dev/null 2>"$WORK/nobase.err"; then
    fail "a scheduler pass without STANDUP_BASE_URL refuses (its links would be relative)"
fi
grep -q "STANDUP_BASE_URL is required" "$WORK/nobase.err" && ! grep -q Traceback "$WORK/nobase.err" \
    || fail "the refusal is one clear line, not a traceback"
if STANDUP_BASE_URL="localhost:$PORT" $PY -m scripts.tick --at "$AT" >/dev/null 2>"$WORK/badbase.err"; then
    fail "a scheduler pass with a scheme-less STANDUP_BASE_URL refuses"
fi
grep -q "must be an absolute http(s) URL" "$WORK/badbase.err" && ! grep -q Traceback "$WORK/badbase.err" \
    || fail "a bad STANDUP_BASE_URL is named in one line"
# Wait on these two by PID: a bare `wait` would also wait for the server.
$PY -m scripts.tick --at "$AT" 2>/dev/null | tail -1 >"$WORK/tick1.txt" &
TICK1=$!
$PY -m scripts.tick --at "$AT" 2>/dev/null | tail -1 >"$WORK/tick2.txt" &
TICK2=$!
wait "$TICK1" "$TICK2"
TICK="$(cat "$WORK/tick1.txt") / $(cat "$WORK/tick2.txt")"
BUILT=$(grep -Eho "built [0-9]+" "$WORK/tick1.txt" "$WORK/tick2.txt" | awk '{s += $2} END {print s}')
# Core Platform has two days and Mobile three (one seeded, two imported):
# five digests, each built once.
[ "$BUILT" = 5 ] || fail "two simultaneous passes build each day's digest exactly once (got: $TICK)"
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
grep -q "requeued [1-9]" <<<"$($PY -m scripts.set_github_repo --team mobile --repo demo/mobile)" \
    || fail "connecting Mobile's repo requeues the blockers skipped without one"
$PY -m scripts.drain_outbox >/dev/null || fail "drain_outbox runs"
MOBILE_ISSUES="$(curl -s -H 'authorization: Bearer demo-token' "$GH/repos/demo/mobile/issues?labels=standup-blocker&state=all")"
grep -q '"number"' <<<"$MOBILE_ISSUES" || fail "Mobile's earlier blockers are filed once its repo is set"
pass "a team's repo set later still gets this week's blockers: Mobile's skipped rows are filed"
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
! grep -q "Nope, all clear" <<<"$MD" || fail "'Nope, all clear' in the Blockers box is not a blocker"
grep -q "users cannot log in" <<<"$(sed -n '/## Progress/,$p' <<<"$MD")" \
    || fail "progress that mentions what users cannot do stays under Progress"
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

CSV="$(curl -s -b "$WORK/ada.jar" "$BASE/digest/$DIGEST_ID.csv")"
[ "$(head -1 <<<"$CSV" | tr -d '\r')" = "section,member,text,evidence_url,earlier_report_url,issue_url" ] \
    || fail "the digest downloads as a CSV with a header row"
ADA_ROW="$(grep '^Still blocked,Ada Okafor' <<<"$CSV")"
grep -q "$BASE/evidence/.*,$BASE/evidence/.*,$GH/demo/core/issues/" <<<"$ADA_ROW" \
    || fail "Ada's carried-over row has today's source, the earlier report and its issue"
pass "the digest downloads as a spreadsheet: one row per line, with evidence and issue links"

# Ada's card submission above changed today: press Build five times at once.
TODAY_CYCLE="$($PY - "$WORK/demo.db" "$DIGEST_ID" <<'EOF2'
import sqlite3, sys
print(sqlite3.connect(sys.argv[1]).execute("select cycle_id from digest where id=?", (sys.argv[2],)).fetchone()[0])
EOF2
)"
seq 5 | xargs -P 5 -I{} curl -s -o /dev/null -w '%{redirect_url}\n' -b "$WORK/ada.jar" -X POST \
    "$BASE/digests/build/$TODAY_CYCLE" >"$WORK/builds.txt"
[ "$(sort -u "$WORK/builds.txt" | wc -l | tr -d ' ')" = 1 ] || fail "five simultaneous builds make one digest"
REBUILT="$(head -1 "$WORK/builds.txt" | sed 's#.*/digest/##')"
[ "$REBUILT" != "$DIGEST_ID" ] || fail "the rebuild includes Ada's card submission"
grep -q "href=\"/digest/$REBUILT\"" <<<"$(curl -s -b "$WORK/ada.jar" "$BASE/digests")" \
    || fail "the list links the latest build, even though the scheduler's ran on a later demo clock"
AGAIN="$(curl -s -o /dev/null -w '%{redirect_url}' -b "$WORK/ada.jar" -X POST "$BASE/digests/build/$TODAY_CYCLE")"
[ "${AGAIN##*/digest/}" = "$REBUILT" ] || fail "rebuilding with nothing new returns the same digest"
pass "Build pressed five times at once makes one new digest; with nothing new, Rebuild returns it again"

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
FAITH="$($PY -m scripts.faithfulness_demo)" || fail "faithfulness_demo: every real line passes and every bad claim is withheld"
grep -q "withheld 7 of 7" <<<"$FAITH" && grep -q "V9 .*says the blocker is solved" <<<"$FAITH" \
    || fail "faithfulness_demo names the rule for each withheld claim"
pass "the validator passes every real line and withholds 7 of 7 unfaithful claims, naming each rule"

# --- another team cannot see it ----------------------------------------------
[ "$(status -c "$WORK/dana.jar" "$DANA")" = 303 ] || fail "Dana's login link"
[ "$(status -b "$WORK/dana.jar" "$BASE/digest/$DIGEST_ID")" = 404 ] || fail "Dana gets 404 on Core's digest"
[ "$(status -b "$WORK/dana.jar" "$BASE$EVIDENCE")" = 404 ] || fail "Dana gets 404 on Core's evidence"
NOTFOUND="$(curl -s -H 'accept: text/html' -b "$WORK/dana.jar" "$BASE/digest/$DIGEST_ID")"
grep -q "Dana Park" <<<"$NOTFOUND" || fail "the 404 page keeps Dana's signed-in header"
! grep -q "$DIGEST_ID" <<<"$NOTFOUND" || fail "the 404 page does not echo the digest id"
DANA_LIST="$(curl -s -b "$WORK/dana.jar" "$BASE/digests")"
[ "$(grep -c 'Read digest' <<<"$DANA_LIST")" = 3 ] || fail "Dana sees Mobile's three days, two of them imported"
pass "Dana (Mobile) gets 404 on Core Platform's digest and evidence, and sees Mobile's three days"

# --- my data: who opened my updates, and an export ----------------------------
curl -s -o /dev/null -b "$WORK/bruno.jar" "$BASE$EVIDENCE" || fail "Bruno opens Ada's evidence"
MINE="$(curl -s -b "$WORK/ada.jar" "$BASE/me/data")"
grep -q "Bruno Silva" <<<"$(sed -n '/Who has opened your updates/,/Your updates/p' <<<"$MINE")" \
    || fail "Ada's My data page shows Bruno opened her update"
curl -s -b "$WORK/ada.jar" "$BASE/me/export" | $PY -c 'import json,sys; d=json.load(sys.stdin); assert d["member"]["display_name"] == "Ada Okafor" and d["updates"]' \
    || fail "Ada's export is JSON with her updates"
pass "My data: Ada sees that Bruno opened her update, and exports everything as JSON"

# --- ops and error pages -----------------------------------------------------
curl -s "$BASE/scope" | grep -q '"scope_violations":1' || fail "/scope counts the one refused channel message"
ERR_TYPE="$(curl -s -o /dev/null -w '%{content_type}' -H 'accept: text/html' -b "$WORK/ada.jar" "$BASE/digest/nope")"
[[ "$ERR_TYPE" == text/html* ]] || fail "browser errors render as HTML (got $ERR_TYPE)"
UNKNOWN_TYPE="$(curl -s -o /dev/null -w '%{content_type}' -H 'accept: text/html' -b "$WORK/ada.jar" "$BASE/no-such-page")"
[[ "$UNKNOWN_TYPE" == text/html* ]] || fail "an unknown address is an HTML page too (got $UNKNOWN_TYPE)"
pass "/scope counts the refused channel message (content-free); browser errors are HTML pages"
! grep -Eq '/login/[A-Za-z0-9]' "$WORK/server.log" || fail "no login token appears in the server's access log"
pass "the server's access log shows /login/[redacted], never a login token"

# --- retention (last: it removes the demo's stored text) ----------------------
LATER="$($PY -c 'from datetime import UTC, datetime, timedelta; print((datetime.now(UTC) + timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
$PY -m scripts.tick --at "$LATER" 2>/dev/null | tail -1 | grep -Eq "purged [1-9]" || fail "a pass 40 days later purges old submissions"
grep -q "Waiting on staging credentials" <<<"$(curl -s -b "$WORK/ada.jar" "$BASE/digest/$DIGEST_ID")" \
    || fail "the digest still reads after retention"
grep -q "expired" <<<"$(curl -s -b "$WORK/ada.jar" "$BASE$EVIDENCE")" || fail "the evidence page says the source expired"
$PY -m scripts.verify_integrity >/dev/null || fail "the audit chain and pinned hashes still verify after retention"
grep -q "removed by retention" <<<"$(curl -s -b "$WORK/ada.jar" "$BASE/me/data")" || fail "My data says the text was removed"
grep -q "line, removed by retention" <<<"$(curl -s -b "$WORK/ada.jar" "$BASE/me/data")" \
    || fail "lines no digest quoted (Ada's replaced update) are removed too"
LISTING="$(curl -s -b "$WORK/ada.jar" "$BASE/digests")"
! grep -q ">Rebuild<" <<<"$LISTING" && grep -q "Updates removed by retention" <<<"$LISTING" \
    || fail "a purged day offers no Rebuild"
PURGED_CYCLE="$($PY - "$WORK/demo.db" "$DIGEST_ID" <<'EOF2'
import sqlite3, sys
print(sqlite3.connect(sys.argv[1]).execute("select cycle_id from digest where id=?", (sys.argv[2],)).fetchone()[0])
EOF2
)"
[ "$(status -X POST -b "$WORK/ada.jar" "$BASE/digests/build/$PURGED_CYCLE")" = 409 ] \
    || fail "rebuilding a purged day is refused (409), and its digest stays"
pass "retention 40 days on: stored text and unquoted lines removed, the digest still reads and cannot be rebuilt, integrity holds"

echo "All $STEP demo steps passed."
