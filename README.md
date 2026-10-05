# Status Unblocked — Team Task & Standup Bot

> An async standup bot for distributed teams. Members file short updates through a web form or a Microsoft Teams bot; each day at the team's cutoff it builds a **faithful, citation-backed** digest, writes every blocker to GitHub Issues as a structured, durable record, and stays out of the surveillance business.

**Stack:** Python 3.13 · FastAPI · SQLAlchemy 2.0 + Alembic · Postgres (SQLite in dev) · Docker

**See it work:** [`docs/DEMO.md`](docs/DEMO.md) walks through every feature with no accounts needed (a local fake GitHub and Teams connector stand in), and `scripts/demo_check.sh` runs that walkthrough against a real server on every CI run. **Working on the code:** [`CLAUDE.md`](CLAUDE.md) is the source of truth for architecture, invariants, commands and conventions.

## What it does

- **Collects** short async updates from each member: a web form, or a Teams card in a 1:1 chat. Members sign in with a personal link; each sees only their own team.
- **Builds one digest per team per day**, at the team's local cutoff, by itself (a scheduler), or on demand.
- **Summarises faithfully.** Every digest line is a verbatim quote, verified against the stored source before it ships, and links to an evidence page that highlights the exact words. Blockers come first; a blocker filed in the wrong box is moved up and says why; "No blockers today" or "None" is never read as a blocker; a blocker reported again is shown as **Still blocked**, citing both days.
- **Writes blockers back to GitHub Issues** as structured records: labels plus a `json` block, one issue per blocker, one comment per later day it is reported. Delivery never blocks a digest.
- **Exports and imports spreadsheets:** each digest downloads as CSV; made-up or historical updates load from CSV.
- **Respects boundaries:** the bot reads only what is sent to it directly and requests no Microsoft Graph permissions; there is no manager role; every opening of someone's stored update (its evidence page) is audited, and that person can see who opened it on **My data**; stored submissions are removed after the team's retention period.

Not built yet: consent for external processing (and validator rule V7), redaction, member-initiated deletion, contest/correct on digest lines, an LLM summarizer, syncing GitHub issue state back into the digest, a reconcile job, and deployment. CLAUDE.md lists them.

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

---

## Design decisions

### Why extractive-first (no LLM in v1)

Measured behaviour of summarization systems: **verbatim extraction has a near-zero hallucination rate; generative summarization fabricates in roughly 15% of outputs even under strong prompting.** For a digest whose entire value is faithfulness, a 15% fabrication rate on *blockers* — the highest-stakes content — is disqualifying.

So the ordering is deliberate: build the extractive pipeline **and the validator** first, reach 100%-cited output with zero model dependency, then add an AI behind the same protocol where it must clear the **same** validator. The AI improves readability and grouping; it is never trusted to introduce a fact. The system also degrades gracefully — API down, rate-limited, or out of budget, and the digest still ships.

### Three findings that shaped the build

**1. `botbuilder-python` is dead.** Bot Framework SDK v4 for Python stopped being serviced 31 Dec 2025; the repo was **archived 5 Jan 2026**. Nearly every tutorial online still uses it. We use the **Microsoft 365 Agents SDK for Python** (GA, Python 3.10–3.14, Pydantic-validated `Activity` objects, first-party `microsoft-agents-hosting-fastapi` package). Versions are pinned — the surface is about a year old and still moving.

**2. Bot Framework Emulator is dead too — and its replacement de-risks the project.** The **Microsoft 365 Agents Playground** (`npm install -g @microsoft/m365agentsplayground`, then `agentsplayground`) emulates the Teams client and Bot Framework service locally with **no tenant, no tunnel, and no bot registration**, and renders Adaptive Cards with the same renderer Teams uses. The Teams *experience* is therefore buildable and demoable regardless of tenant sideloading policy.

**3. True per-message Teams permalinks are not constructible from a 1:1 bot chat.** Message deep links require a `19:`-form chat ID; Microsoft's docs state that 1:1 bot payloads carry the conversation ID in **`a:xxx`** format. This is a hard constraint, not an unknown.

> **Consequence — the citation contract does not depend on Teams.** Every submission is stored immutably with every identifier Teams gives us, and the canonical citation target is an internal **evidence view** (`GET /evidence/{item_id}`) served by FastAPI. A native permalink is emitted *additionally* when constructible (channel messages). This is the more defensible answer anyway: the evidence store survives Teams retention/deletion, which a permalink does not. It is also tamper-evident: each update's content hash is pinned into the hash-chained audit log at ingestion, and `python -m scripts.verify_integrity` recomputes every hash and fails if any stored text was edited afterwards.

### Privacy: the legal nuance most implementations miss

Under GDPR, **consent is not a valid lawful basis in an employment context** — the power imbalance means an employee cannot freely refuse. So the design uses **legitimate interest with a documented assessment** (a written assessment, `docs/LIA.md`, is not yet written), plus strict data minimization and purpose limitation. The member-facing opt-in governs **scope** — notably `allow_external_processing`, which gates any future LLM — not participation.

Because workers must be able to see how a tool classified their activity and contest mistakes (GDPR Art. 21, and EU AI Act human-oversight obligations once AI lands), **every digest line should carry a contest/correct action**. That is not built yet; today a member can see everything recorded about them on **My data**.

**Anti-patterns explicitly not implemented** — and defensible from the code, not merely claimed:

- No productivity or velocity scoring
- No per-person metrics, leaderboards, streaks, or lateness stats
- No keystroke, presence, or activity monitoring
- No manager-only dashboards — **there is no manager role at all**
- No sentiment or "morale" inference on individuals
- No cross-team aggregation of individual data
- No silent collection — every capture answers an explicit prompt
- No retention past the stated window
- No third-party model sees anyone's text without that person's separate opt-in

Backed by code: the Teams app manifest (`teams/manifest/manifest.json`) requests **zero Microsoft Graph or resource-specific permissions**, which an admin can confirm by reading it and a test asserts. The bot ingests only standup-card submissions in a 1:1 chat. Typed commands there (`standup`, `link`) are answered, and a channel message that @mentions it gets a pointer to the 1:1 chat. Any other message is refused before ingestion and counted as a content-free `scope_violation` row (reason and conversation type only: no text, no sender), with the totals at `GET /scope`. Who a Teams user is comes from a short-lived link code they get from `/me/teams` while signed in, never from a Graph lookup. Also enforced: every page except `/` and `/healthz` requires sign-in through a personal, signed, expiring link (no passwords, no roles); a member sees only their own team's digests and evidence, and another team's resources answer 404 so their existence is not disclosed; who submitted an update comes from the session, never the form, so nobody can file as someone else; and every evidence view is audited under the viewing member's id.

### The faithfulness validator

| Rule | Check | Status |
|---|---|---|
| V1 | Every claim has at least one citation | live |
| V2 | Every cited `source_id` exists (kills fabricated IDs) | live |
| V3 | `quote == source.text[start:end]` after NFKC + whitespace collapse (kills paraphrase-as-quote) | live |
| V4 | Every number/date in the claim appears in a cited source, or is derivable from cited `captured_at` | live |
| V5 | Every entity ref (`#123`, URL, `@handle`) appears in a cited source | live |
| V6 | Claim's `member_id` matches every cited source (no cross-attribution) | live |
| V7 | No cited source is outside consented/visible scope (privacy failures are faithfulness failures) | not built — needs the consent model |
| V8 | Length-inflation guard for abstractive claims | live |

A failing claim is **dropped**, not silently corrected, and the digest reports how many were withheld. Under `STANDUP_VALIDATOR_STRICT=true` (as CI runs) the build raises instead.

A blocker's journey, in short: a line filed under Progress that says "stuck" is promoted to Blockers with its reason stored and shown; negation is judged per clause, so "no blockers on the API, but stuck on the migration" still reports the migration; the same blocker reported on a later day becomes **Still blocked**, in that day's words, citing both days; and its GitHub issue gets one comment per later day, carrying a running `days_reported`. Issue writes are idempotent (a fingerprint per team, member and normalised text; a marker in the issue body; one write per blocker per day) and go through an outbox, so GitHub being down or rate-limited never delays a digest.

---

## Getting started

```bash
git clone https://github.com/RitGos28/status-unblocked.git
cd status-unblocked
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# set STANDUP_SECRET_KEY in .env (required, 32+ chars):
python -c "import secrets; print(secrets.token_urlsafe(48))"

alembic upgrade head
python -m scripts.seed_demo --days 2   # made-up updates; prints a login link per member and the serve command
uvicorn standup.main:app --port 8000

# or, all in one: ./run.sh
# or containerised (Postgres + the API); reads STANDUP_SECRET_KEY from your shell:
docker compose up --build
```

Open a member's login link to sign in as them. Then follow [`docs/DEMO.md`](docs/DEMO.md).

## Testing

```bash
pytest                       # the full suite
scripts/demo_check.sh        # the demo, end to end, against a real server
ruff check . && mypy src && lint-imports
```

CI runs these on every pull request: lint, strict types, the import-linter layer contracts, the full suite in strict faithfulness mode with a 90% coverage gate on `summarize/` and `privacy/`, migrations and the integration tests on Postgres, the demo check, and a Docker build. Testing conventions are in CLAUDE.md.

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
