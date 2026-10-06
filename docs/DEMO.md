# Demo

Everything below runs locally with **no accounts**: no GitHub, no Teams tenant,
no Docker. `scripts/demo_check.sh` runs this exact script against a real server
and asserts every step; run it to prove the demo still works.

```bash
scripts/demo_check.sh          # about 10 seconds; prints one line per step
```

## Setup (once per demo)

From the repository root, with the virtual environment active (`source .venv/bin/activate`; see README's Getting started).

```bash
python -m scripts.fake_github --port 8091 &   # a local stand-in for the GitHub API
export STANDUP_TRACKER=github STANDUP_GITHUB_TOKEN=demo STANDUP_GITHUB_API_URL=http://127.0.0.1:8091
python -m scripts.fake_teams_connector --port 8092 &   # a local stand-in for Teams; records what the bot sends
export STANDUP_TEAMS_ENABLED=true CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED=True
export STANDUP_DATABASE_URL=sqlite:///./demo.db
export STANDUP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
export STANDUP_BASE_URL=http://127.0.0.1:8000
alembic upgrade head
python -m scripts.seed_demo --days 2      # two days of made-up updates; prints a login link per person
python -m scripts.set_github_repo --team core --repo demo/core
uvicorn standup.main:app --port 8000
```

`./run.sh` is the minimal web-only version: today's updates only, no fake GitHub or Teams, no repo set. It serves on `PORT` (default 8000); set `STANDUP_BASE_URL` to match if you change it, because the login links it prints use that address.

The seed prints `Now run: uvicorn standup.main:app --port <port>`: use that port, because the login links point at `STANDUP_BASE_URL`. All dates in the demo are **UTC dates**: "today" and "yesterday" mean the UTC calendar day, which can differ from your local date (for example, early morning in India is still the previous day in UTC).

## 1. Sign-in and team boundaries
- Open `/digests` without signing in: **401**, "Sign in with your personal link".
- Open **Ada's** link from the seed output: you land on **Digests**, which lists only Core Platform's days. Mobile also has a day today (Dana filed an update), and it is not listed; the header shows who you are signed in as.
- After step 3 (once a digest exists), open **Dana's** link (team Mobile) and paste a Core Platform digest or evidence URL: **404**. Another team's pages are not just forbidden; they do not exist for her.

## 1b. The Teams bot (no tenant needed)
Activities are replayed to the bot as Teams would send them (`scripts/teams_replay.py`); the bot's replies land at the fake connector. Open `http://127.0.0.1:8092/` to watch them. `teams_replay` assumes the app on port 8000 and the connector on 8092; on other ports pass `--app http://127.0.0.1:<port> --connector http://127.0.0.1:<port>`.
- As Ada, open **Teams** in the header: it shows `link <code>`. Send it: `python -m scripts.teams_replay personal_command --text "link <code>"` → "Linked. You're Ada Okafor on Core Platform".
- A code works once. Send the same code from another Teams account, `... --text "link <code>" --as aad-someone-else` → "That code is invalid or has expired", and Ada stays linked to her own account.
- `python -m scripts.teams_replay personal_command` (the text `standup`) → the bot replies with the update card.
- `python -m scripts.teams_replay channel_unaddressed` → no reply, nothing read; `/scope` counts one refusal.
- `python -m scripts.teams_replay channel_mention` → "I don't read channel conversations…".
- After the scheduler pass in step 3, the connector shows one "The Core Platform digest for <date> is ready (… blockers, 1 still open from an earlier day)" message for Ada per day's digest, sent with no credentials. (Each pass also logs an SDK warning, "App ID is not provided": expected in this anonymous demo mode.)
- `python -m scripts.teams_replay personal_card_submit` → "Recorded for Core Platform": a card submission goes through the same ingest path as the web form.

## 2. Submit, and resubmit
- As Ada, **Submit update**. The seed already gave her an update today, so this one replaces it in the digest; so does every later one (the earlier ones are kept unedited, because stored text is never rewritten). Double-clicking Submit is safe.
- On **Digests**, each day also has a **Build digest** (or **Rebuild**) button: anyone on the team can build the digest by hand before the scheduler does. The scheduler still announces it at the cutoff, once. Builds of one day run one at a time, and a Rebuild with nothing new returns the same digest, so double-clicking it is harmless. The list always links the most recent build, even after a scheduler pass on a demo clock set later in the day.

## 2b. Made-up updates from a spreadsheet
`docs/sample_updates.csv` shows the format: `date,team,member,progress,blockers,plan` (and an optional `time`, default 09:00). Dates are UTC; `team` is a slug; `member` a display name. Copy it, and change the copy's dates to the two days before today (the tracked file's dates are fixed, and old dates would load into old days):

```bash
cp docs/sample_updates.csv /tmp/mobile.csv                  # then edit the two dates
python -m scripts.import_updates_csv /tmp/mobile.csv   # "imported 2, skipped 0 unchanged, kept 0 later update(s), errors 0"
python -m scripts.import_updates_csv /tmp/mobile.csv   # again: "imported 0, skipped 2 unchanged, ...": nothing changes
```

Every row goes through the same path as the web form, filed on its own date, and is audited as an import (not as Dana). A file with any bad row, or a date in the future, imports nothing and names each problem by line. A file saved from Excel as "CSV UTF-8" works; any other encoding is refused in one line. A row never replaces a later update the member already has that day (it says "already has a later update"), and if a day already had a digest the import tells you to rebuild it. Sign in as Dana to see Mobile's days; the evidence page says the update came "via a spreadsheet import".

## 3. The daily digest, built by the scheduler
The digest builds itself at each team's cutoff (11:00 UTC for the demo teams). To show it at any hour, run one scheduler pass on a demo clock:

```bash
python -m scripts.tick                                   # after 11:00 UTC: the real clock is past the cutoff
                                                         # (before 11:00 it still builds every earlier day, not today)
python -m scripts.tick --at <today>T11:06:00Z           # before 11:00 UTC; <today> is today's UTC date
```

It reports `built 3 digest(s)`: Core Platform's yesterday and today, and Mobile's today; `built 5` if you imported Mobile's two earlier days in 2b (fewer if you already built one by hand with **Build digest**). Then open **Digests** and today's digest. If you use `--at` with a time earlier than your submissions, the digest's "built" time will read earlier than the updates it contains; that is the demo clock, not the app. The same goes for retention in step 5c, which stamps its future date ("purged on …"). A Rebuild you press after a future `--at` pass is still the digest the list shows: the latest build wins, whatever its clock said.

Run it again, or twice at once: nothing is built twice and no one is told twice, because only one pass may run at a time (a database lease) and each cycle is announced once. Run it with `STANDUP_BASE_URL` unset, or set to something that is not an absolute http(s) URL (`localhost:8000`), and it refuses in one line, because its links go into GitHub issues and Teams messages.

## 4. What the digest shows
- **Each heading explains itself.** Under **Still blocked**, **Blockers**, **Progress** and **Today** there is one plain-language line saying what belongs there, on the page and in the React app, for readers new to standup vocabulary. The Markdown and CSV downloads are unchanged.
- **Still blocked comes first.** Ada reported "Waiting on staging credentials from infra." yesterday and again today, so it is under **Still blocked**, with "Also reported on <yesterday>, and still open." It is today's words, verbatim, and it has two **source** links: today's and yesterday's.
- **Then Blockers**: new ones today.
- **Chen's misfiled blocker:** he typed "Stuck on the deploy pipeline." under Progress; it is under Blockers with 'Moved to Blockers: the author filed it elsewhere, but it says "stuck".' The text itself is unchanged.
- **Negation:** Bruno wrote "No blockers today." It is not reported as a blocker. Answers like "None", "N/A", "-", "Blockers: none" or "Nope, all clear" are not blockers either; "No longer stuck on X" is progress.
- **Not every problem is a blocker:** "Fixed the bug where users cannot log in." stays under Progress: "can't" or "cannot" counts only when the writer is the one who cannot ("I can't deploy until…", "Cannot access the build server").
- **Exceptions:** "No blockers except waiting on App Store review." *is* a blocker: "except", "apart from", "other than" and "besides" start a new clause.
- **Clauses:** a sentence such as "Merged the API changes, but waiting on review for the DB migration." (submit it as Bruno under Progress; it is not in the seed) is promoted: each clause is judged on its own, so "no blockers on X, but stuck on Y" still reports Y.
- Every line has a **source** link. The **Markdown** link at the bottom gives the same digest as text, including the "Moved to Blockers" notes.
- **Spreadsheet (CSV)** at the bottom downloads the digest: one row per line with its section, who, the verbatim text, the evidence link, the earlier report (for carried-over blockers) and the GitHub issue. Text that would run as a formula in Excel or Sheets (starting with `=`, `+`, `-` or `@`) is prefixed with `'`.

## 4b. Blockers become GitHub issues
The scheduler pass in step 3 also delivered the blockers to the (fake) GitHub, through the same client the app uses against github.com.
- Open `http://127.0.0.1:8091/`: one issue per blocker, labelled `standup-blocker`. Each quotes the blocker and links back to its evidence and digest.
- Ada reported the same blocker on both days. It is **one** issue, opened for the first day, with a "Still blocked on <today>" comment for the second.
- On the digest, each blocker shows its issue number (`#1`); click it to open the issue.
- Mobile has no repository yet, so its blockers were **skipped**, not lost. Connect one: `python -m scripts.set_github_repo --team mobile --repo demo/mobile` → "requeued N blocker(s)…", then `python -m scripts.drain_outbox`: Mobile's blockers from this week appear on the fake GitHub under `demo/mobile`.
- The output is **structured**, not just prose: each issue is labelled `standup-blocker` and `team:core`, and ends with a `json` block (fingerprint, team, who reported it, the quote, first reported, days reported, evidence and digest links). Each later day's comment carries a `json` update with the running `days_reported`.

## 5. Evidence, and proving nothing was edited
- Click a **source** link: the stored update, with the cited words highlighted and their character offsets.
- `python -m scripts.verify_integrity` → "audit chain intact; every stored update matches its pinned hash". This holds under load too: the demo check opens the same evidence 20 times at once first, and every view is recorded on one unbroken chain.
- Edit any stored update in a *copy* of the database and run it against the copy: it names the tampered update and exits 1. (`scripts/demo_check.sh` does exactly this.)
  ```bash
  cp demo.db tampered.db
  sqlite3 tampered.db "UPDATE \"update\" SET raw_text = replace(raw_text, 'staging', 'prod')"
  STANDUP_DATABASE_URL=sqlite:///./tampered.db python -m scripts.verify_integrity   # names each edited update; exit 1
  ```
- `python -m scripts.faithfulness_demo` → the validator at work on today's Core Platform updates. The rules summarizer's lines all pass; then seven claims an unfaithful summarizer could write, built from the same real updates, are each **withheld**, with the rule that caught it: an invented source (V2), a misquote (V3), "fully unblocked" citing the blocker (V9), the blocker hidden under Progress and progress filed as a blocker (V10), an added number (V4), the wrong person credited (V6). It reads only; nothing is built or stored.

## 5b. My data
- As Ada, open **My data** in the header: her updates, everything recorded about her, and **Who has opened your updates**. Open one of Ada's evidence pages as Bruno first, and his name appears there. This is the audit log, readable by the person it is about.
- **Download it as JSON** (`/me/export`): the same data as a file. The export is itself recorded.

## 5c. Retention
Stored submissions are kept for each team's retention period (30 days in the demo). The scheduler applies it on every pass. To see it:

```bash
python -m scripts.tick --at <a UTC date 40 days from now>T12:00:00Z   # "... purged N"
```

The full stored submissions are removed, and so is every line no digest quoted (Ada's replaced update from step 2, for example: **My data** now shows it as "a progress line, removed by retention"). The digest still reads, because the lines it quoted stay: the digest is the team's record. Evidence pages say the source expired, and `verify_integrity` still passes. **Digests** no longer offers Rebuild for those days ("Updates removed by retention"): there is nothing left to rebuild from, so the digest is final. Run this last: it removes the demo's stored text.

## 6. Ops
- `/version`: the build's version. **Sign out** in the header ends the session; `python -m scripts.issue_links` prints fresh login links at any time (links expire after `STANDUP_LOGIN_LINK_DAYS`; an expired one says so and asks for a fresh one).
- `STANDUP_SCHEDULER=true` (with `STANDUP_BASE_URL`) runs the same scheduler pass inside the app every minute (`STANDUP_SCHEDULER_INTERVAL_SECONDS`) instead of `scripts/tick`.
- `/scope`: a JSON count of out-of-scope Teams messages the bot refused, by reason. It is an ops endpoint like `/healthz`, open without sign-in, because it holds counts only: nothing about the refused messages is stored.
- `/healthz`, `/readyz`.
- Any error opened in a browser is an HTML page; API clients get `application/problem+json`.

## Optional: needs your accounts or tools
- **GitHub Issues write-back against a real repo:** leave `STANDUP_GITHUB_API_URL` unset, set `STANDUP_GITHUB_TOKEN` to a fine-grained token with Issues read/write on one repo, and `python -m scripts.set_github_repo --team core --repo owner/name`, then build a digest.
- **The rendered card in a real Teams client, without a tenant:** Microsoft 365 Agents Playground. Install it with `npm install -g @microsoft/m365agentsplayground` (checked on npm: version 0.2.28; the older `@microsoft/teams-app-test-tool` is deprecated in its favour), run the app with the two Teams variables above, then run `agentsplayground` and set its bot endpoint to `http://127.0.0.1:8000/api/messages` (see `agentsplayground --help` for the option). Type `standup` to get the card.
- **A real Teams tenant:** register an Entra app and Azure Bot, set the three `CONNECTIONS__…` variables and leave `ANONYMOUS_ALLOWED` unset, then sideload `python -m scripts.make_teams_zip --bot-id <app id> --base-url <public URL>`.
- **Postgres via Docker:** `export STANDUP_SECRET_KEY=...; docker compose up --build` (needs the Docker daemon running).
