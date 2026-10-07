# Status Unblocked — Team Task & Standup Bot

> An async standup bot for distributed teams. Members file short updates through a web form or a Microsoft Teams bot; each day at the team's cutoff it builds a **faithful, citation-backed** digest, writes every blocker to GitHub Issues as a structured, durable record, and stays out of the surveillance business.

**Stack:** Python 3.13 · FastAPI · SQLAlchemy 2.0 + Alembic · React 18 (Vite + JSX) · Postgres (SQLite in dev) · Docker

**See it work:** [`docs/DEMO.md`](docs/DEMO.md) walks through every feature with no accounts needed (a local fake GitHub and Teams connector stand in), and `backend/scripts/demo_check.sh` runs that walkthrough against a real server on every CI run. **Working on the code:** [`CLAUDE.md`](CLAUDE.md) is the source of truth for architecture, invariants, commands and conventions.

## What it does

- **Collects** short async updates from each member: a web form, React frontend, or a Teams card in a 1:1 chat. Members sign in with their team's shared code and their name; each sees only their own team.
- **Builds one digest per team per day**, at the team's local cutoff, by itself (a scheduler), or on demand.
- **Summarises faithfully.** Every digest line is a verbatim quote, verified against the stored source before it ships, and links to an evidence page that highlights the exact words. Blockers come first; a blocker filed in the wrong box is moved up and says why; "No blockers today" or "None" is never read as a blocker; a blocker reported again is shown as **Still blocked**, citing both days.
- **Writes blockers back to GitHub Issues** as structured records: labels plus a `json` block, one issue per blocker, one comment per later day it is reported. Delivery never blocks a digest.
- **Exports and imports spreadsheets:** each digest downloads as CSV; made-up or historical updates load from CSV.
- **Respects boundaries:** the bot reads only what is sent to it directly and requests no Microsoft Graph permissions; there is no manager role; every opening of someone's stored update (its evidence page) is audited, and that person can see who opened it on **My data**; after the team's retention period the stored submission and every line no digest quoted are removed (the quoted lines stay, as the digest's record).

Not built yet: consent for external processing (and validator rule V7), redaction, member-initiated deletion, contest/correct on digest lines, an LLM summarizer, syncing GitHub issue state back into the digest (a reconcile job), the written legitimate-interest assessment (`docs/LIA.md`), and a production deployment (HTTPS, a managed host; Docker Compose runs it on one server over HTTP). CLAUDE.md's "not yet written" list is the same.

Two consequences to know. Sign-in tells teams apart, not people: a team code is shared, so anyone holding it can sign in under any name on that team. That is the price of having no accounts, passwords or email, and it suits a small team that knows each other; the audit trail and "who opened my updates" are only as trustworthy as that assumption. `python -m scripts.team_codes --team core --rotate` replaces a code that has leaked. And with GitHub write-back on, each blocker's verbatim text and its author's name go to the configured repository, with no per-member opt-in yet. Point a team at a private repository that the team can already see.

---

## The problem

On a distributed team the daily standup costs more than it returns. A synchronous call forces 6–10 people into one timezone-hostile slot to hear 8 updates, 7 of which are irrelevant to any given listener. Replacing it with "just post your update in the channel" trades one tax for another: a wall of text nobody reads, and blockers typed into the void.

The research on existing tools is blunt about the failure mode. The most common complaint across the incumbents is that **collected standup information goes unread** — teams install a bot, fill rates hold for two to four weeks, then decay. And the sharpest practitioner observation:

> *A blocker posted and un-answered is worse than a blocker raised live and forgotten* — because now there is a written record of the team not helping.

So collection is not the problem. Collection is solved. The problem is **synthesis, follow-through, and trust**:

| Failure | What it looks like |
|---|---|
| **Synthesis** | Ten individual task lists is not a digest. Signal-to-noise is terrible; everyone skims for their own name and closes the tab. |
| **Follow-through** | A blocker in a chat message has no owner, no state, no expiry. It scrolls away. Nothing in the system knows it is still open tomorrow. |
| **Trust** | The moment a status tool reads as surveillance, people write defensive updates and the data becomes worthless. |

**Intended outcome.** Kill the standup call; keep the coordination. ~90s/day to write, ~30s to read. Every blocker is one click from the exact words its author wrote. Every blocker older than a day is visible as an aging item — not a message that scrolled away.

---

## Competitive analysis

| Tool | Does well | The gap we exploit |
|---|---|---|
| **Geekbot** | Best-in-class UX, 10 users free, category default | Tracker integration is **read-only** — cannot create or update an issue from a standup. Blockers stay as chat text. |
| **Standuply** | 20+ scrum workflows, strong managerial control | Its headline feature — answers routed privately to *managers* rather than the team — is precisely the surveillance anti-pattern. Optimizes reporting *up*, not unblocking *across*. |
| **DailyBot** | Broad platform + feature coverage | Breadth over depth; digest is still concatenation. No blocker lifecycle. |
| **Polly / Troopr / Jell** | Cheap, simple, fast adoption | Same model: collect then post. Free tiers cap at 3–5 users. |

**Shared blind spot: the digest is a terminal artifact.** It is produced, posted, forgotten. Nothing in any of these products knows on Wednesday that Monday's blocker is still open.

### Four improvements this project is built around

1. **Blocker lifecycle, not blocker mention.** Each blocker becomes a GitHub Issue, linked from its digest line with its age (`#42 · 3d`). The same blocker on a later day adds a comment rather than a new issue, and the digest lists it under **Still blocked**, citing both days.
2. **Faithfulness as an enforced invariant, not a prompt instruction.** A validator that runs after every summarizer and drops any claim that fails (strict mode fails the build instead): every claim carries at least one citation; every quote must be a verifiable substring of the immutable source.
3. **Write-back, not read-only.** Geekbot's explicit weakness, inverted into the core feature.
4. **Privacy as architecture with a user-facing surface.** Not a policy page. Built today: a hash-chained audit log of reads, a `/me/data` view, and retention purge jobs.

---

## Design decisions

### Why extractive-first (no LLM in v1)

Measured behaviour of summarization systems: **verbatim extraction has a near-zero hallucination rate; generative summarization fabricates in roughly 15% of outputs even under strong prompting.** For a digest whose entire value is faithfulness, a 15% fabrication rate on *blockers* — the highest-stakes content — is disqualifying.

So the ordering is deliberate: build the extractive pipeline **and the validator** first, reach 100%-cited output with zero model dependency, then add an AI behind the same protocol where it must clear the **same** validator. The AI improves readability and grouping; it is never trusted to introduce a fact. The system also degrades gracefully — API down, rate-limited, or out of budget, and the digest still ships.

### Privacy: the legal nuance most implementations miss

Under GDPR, **consent is not a valid lawful basis in an employment context** — the power imbalance means an employee cannot freely refuse. So the design uses **legitimate interest with a documented assessment** (`docs/LIA.md`), plus strict data minimization and purpose limitation.

**Anti-patterns explicitly not implemented** — and defensible from the code, not merely claimed:

- No productivity or velocity scoring
- No per-person metrics, leaderboards, streaks, or lateness stats
- No keystroke, presence, or activity monitoring
- No manager-only dashboards — **there is no manager role at all**
- No sentiment or "morale" inference on individuals
- No cross-team aggregation of individual data
- No silent collection — every capture is a member's own submission (the one exception is a CSV import of made-up or historical data, audited as an import, not as the member)
- No retention past the stated window, except the lines a digest quoted, which are the team's record
- No third-party model sees anyone's text without that person's separate opt-in

Backed by code: the Teams app manifest (`backend/teams/manifest/manifest.json`) requests **zero Microsoft Graph or resource-specific permissions**, which an admin can confirm by reading it and a test asserts. The bot ingests only standup-card submissions in a 1:1 chat. Typed commands there (`standup`, `link`) are answered, and a channel message that @mentions it gets a pointer to the 1:1 chat. Any other message is refused before ingestion and counted as a content-free `scope_violation` row (reason and conversation type only: no text, no sender), with the totals at `GET /scope`. Who a Teams user is comes from a short-lived link code they get from `/me/teams` while signed in, never from a Graph lookup. Also enforced: every page except `/`, `/login` and `/healthz` requires sign-in with the team's shared code and the member's name (no passwords, no accounts, no roles: the code is on every member's Team page); a member sees only their own team's digests and evidence, and another team's resources answer 404 so their existence is not disclosed; who submitted an update comes from the session, never the form, so nobody can file as someone else; and every evidence view is audited under the viewing member's id.

### The faithfulness validator

| Rule | Check | Status |
|---|---|---|
| V1 | Every claim has at least one citation | live |
| V2 | Every cited `source_id` exists (kills fabricated IDs) | live |
| V3 | `quote == source.text[start:end]` after NFKC + whitespace collapse (kills paraphrase-as-quote) | live |
| V4 | Every number in the claim appears, as a whole token, in a cited quote | live |
| V5 | Every entity ref (`#123`, URL, `@handle`, `ABC-12`) appears in a cited quote | live |
| V6 | Claim's `member_id` matches every cited source (no cross-attribution) | live |
| V7 | No cited source is outside consented/visible scope (privacy failures are faithfulness failures) | not built — needs the consent model |
| V8 | Length-inflation guard for abstractive claims | live |
| V9 | An extractive claim's text is its quote (a real citation cannot carry a different sentence) | live |
| V10 | The claim's section follows the one classification policy (`rules.classify`) for its source; a carry-over also cites the earlier report | live |

`python -m scripts.faithfulness_demo` runs these rules on a real day's updates: the rules summarizer's lines all pass, and seven plausible bad claims (an invented source, a misquote, "the blocker is solved", a blocker hidden under Progress, progress filed as a blocker, an added number, the wrong person) are each withheld.

A failing claim is **dropped**, not silently corrected, and the digest reports how many were withheld. Under `STANDUP_VALIDATOR_STRICT=true` (as CI runs) the build raises instead.

A blocker's journey, in short: a line filed under Progress that says "stuck" is promoted to Blockers with its reason stored and shown; negation is judged per clause, so "no blockers on the API, but stuck on the migration" still reports the migration; the same blocker reported on a later day becomes **Still blocked**, in that day's words, citing both days; and its GitHub issue gets one comment per later day, carrying a running `days_reported`. Issue writes are idempotent (a fingerprint per team, member and normalised text; a marker in the issue body; one write per blocker per day) and go through an outbox, so GitHub being down or rate-limited never delays a digest.

---

## Repository Structure

- **[`backend/`](backend/)**: Python 3.13 FastAPI backend, SQLAlchemy database models, Alembic migrations, extractive rules summarizer, Microsoft Teams bot adapter, and structured REST JSON API.
- **[`frontend/`](frontend/)**: Modern React application built with Vite, JSX components, responsive design system, and dark/light mode.

---

## Getting started

Nothing to configure for the demo: with no `backend/.env`, the demo values in [`backend/.env.example`](backend/.env.example) fill in every unset variable (a local fake GitHub, the Teams bot in anonymous mode, and a public demo signing key that the app refuses unless `STANDUP_ENV` is `local` or `test`). [`docs/DEMO.md`](docs/DEMO.md) walks through every demoable feature.

### Docker (one command)

```bash
docker compose up --build
docker compose logs api | grep -A4 "Team codes"   # sign-in codes
```

React app on `http://localhost:3000` (the server pages are there too, e.g. `http://localhost:3000/login`, and on `http://localhost:8000/login`), fake GitHub on `http://localhost:8091`, Postgres behind them, and two days of made-up updates seeded. Change ports with `WEB_PORT`, `APP_PORT` and `GITHUB_PORT`, e.g. `APP_PORT=9000 WEB_PORT=8080 docker compose up --build`.

### Local (Python 3.13 and Node 20)

```bash
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd ../frontend && npm install && cd ..

./run.sh all          # backend :8000 (with fake GitHub :8091 and Teams :8092), React :5173
./run.sh              # backend only
PORT=9000 WEB_PORT=5174 ./run.sh all   # other ports (also GITHUB_PORT, TEAMS_PORT)
```

Then open `http://127.0.0.1:5173` (React) or `http://127.0.0.1:8000/login`, and sign in with a code the seed printed and one of that team's names.

For anything real, `cp backend/.env.example backend/.env` and replace the demo values: a `.env` switches the fallback off.

### Hosting on a server

On a Linux server with Docker (Ubuntu shown). Replace `203.0.113.10` with the server's public IP or domain, and change the ports if you like.

```bash
curl -fsSL https://get.docker.com | sudo sh
git clone https://github.com/RitGos28/status-unblocked.git
cd status-unblocked
printf 'STANDUP_ENV=production\nSTANDUP_SECRET_KEY=%s\nPUBLIC_HOST=http://203.0.113.10\nWEB_PORT=80\nAPP_PORT=8000\nGITHUB_PORT=8091\n' \
  "$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" > .env
sudo docker compose up -d --build
sudo docker compose logs api | grep -A4 "Team codes"
```

Open `http://203.0.113.10` (React app), `http://203.0.113.10:8000/login` (server pages) and `http://203.0.113.10:8091` (fake GitHub). Allow those ports in the server's firewall or cloud security group. Compose reads the `.env` next to `docker-compose.yml`; `STANDUP_ENV=production` makes the app refuse the public demo key. Update with `git pull && sudo docker compose up -d --build`; data lives in the `pgdata` volume. This serves plain HTTP: for HTTPS, put a reverse proxy such as Caddy in front and set `STANDUP_COOKIE_SECURE=true` on the `api` service.


### Behind a Cloudflare Tunnel (or any HTTPS proxy)

Port `WEB_PORT` serves the whole app: the React app at `/`, and the server pages (`/login`, `/digests`, `/evidence/...`) and `/api` through to the backend. So the tunnel needs one hostname for the app, plus one for the fake GitHub if you want its issues reachable. Use this `.env` instead (replace `example.com` with your domain):

```bash
printf 'STANDUP_ENV=production\nSTANDUP_SECRET_KEY=%s\nSTANDUP_BASE_URL=https://standup.example.com\nGITHUB_PUBLIC_URL=https://standup-github.example.com\nSTANDUP_COOKIE_SECURE=true\nBIND_ADDR=127.0.0.1\nWEB_PORT=8300\nAPP_PORT=8301\nGITHUB_PORT=8302\n' \
  "$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" > .env
docker compose up -d --build
```

Then in Cloudflare (Zero Trust > Networks > Tunnels > your tunnel > Public hostnames), add `standup.example.com` with service `http://localhost:8300`, and `standup-github.example.com` with service `http://localhost:8302`. `BIND_ADDR=127.0.0.1` keeps the ports off the public interface, so nothing needs opening in the firewall; drop it if `cloudflared` runs in a Docker container rather than on the host, and point the service at the host's address instead. `STANDUP_BASE_URL` and `GITHUB_PUBLIC_URL` are the addresses links in digests and issues use, and `STANDUP_COOKIE_SECURE=true` sends the sign-in cookie over HTTPS only.

---

## Testing

```bash
cd backend
pytest                       # the full suite (370 tests)
scripts/demo_check.sh        # the demo, end to end, against a real server
ruff check . && mypy src && PYTHONPATH=src lint-imports
```

CI runs these on every pull request: lint, strict types, the import-linter layer contracts, the full suite in strict faithfulness mode with a 90% coverage gate on `summarize/` and `privacy/`, migrations and the integration tests on Postgres, the demo check, a frontend build check, and Docker builds. Testing conventions are in CLAUDE.md.

---

## Efficiency

| Dimension | Cost |
|---|---|
| Per-member daily effort | ~90s write, ~30s read — vs a 15-min call times N people |
| Team time reclaimed | ~15 min/person/day, i.e. **~1.25 h/person/week** |
| Runtime | Extractive path: zero marginal inference cost. Digest build is O(updates/day), tens of rows — milliseconds |
| Infra | One FastAPI container + Postgres. Azure Bot **F0 is free**, Teams channel is a free standard channel, GitHub API free |
| Added AI cost later | Bounded — **one call per digest per day**, not per message |

---

## References

**Product research** — [Geekbot reviews](https://www.capterra.com/p/148076/geekbot/reviews/) · [Async standup bots compared](https://www.standin.co/blog/async-standup-bots-compared) · [Geekbot alternatives for engineering teams](https://www.standin.co/blog/geekbot-alternatives) · [Async standups people actually read](https://pickuma.com/for-dev/async-standups-people-actually-read/) · [Async standups guide](https://www.vereda.ai/guides/async-standups)

**Summarization faithfulness** — [AI summaries are unreliable](https://www.baldurbjarnason.com/2023/ai-summaries-unreliable/) · [Avoiding hallucination in content extraction](https://madhudadi.in/blog/posts/ai-summaries-avoiding-hallucination-in-content-extraction)

**Privacy and compliance** — [GDPR employee monitoring](https://secureprivacy.ai/blog/employee-monitoring-gdpr-guide) · [GDPR-compliant monitoring checklist](https://gstride.ai/blog/gdpr-compliant-employee-monitoring/)

**Microsoft Teams** — [Bot Framework to M365 Agents SDK Python migration](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/bf-migration-python) · [botbuilder-python (archived)](https://github.com/microsoft/botbuilder-python) · [microsoft-agents-hosting-fastapi](https://pypi.org/project/microsoft-agents-hosting-fastapi/) · [Teams deep links](https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-teams) · [Manage custom app policies](https://learn.microsoft.com/en-us/microsoftteams/teams-custom-app-policies-and-settings) · [Agents Playground](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/debug-your-agents-playground) · [Proactive messages](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages) · [Azure Bot Service pricing](https://azure.microsoft.com/en-us/pricing/details/bot-services/)

**GitHub** — [Issues REST API](https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28) · [REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
