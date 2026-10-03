# Status Unblocked — Team Task & Standup Bot

> An async standup bot for distributed teams. Collects short updates through a web form or a Microsoft Teams bot and produces a **faithful, citation-backed** digest each day at the team's cutoff — without becoming a surveillance tool. Each blocker is written back to GitHub Issues as a durable tracked object; see [Roadmap](#roadmap) for what exists today.

**Stack:** Python 3.13 · FastAPI · SQLAlchemy 2.0 + Alembic · Postgres (SQLite in dev) · Docker
**Status:** Week 1 complete — the walking skeleton runs end to end: submit → digest → click through to the verbatim source, behind per-member sign-in with team-scoped access, from the web form or the Teams bot, with blockers written back to GitHub Issues and the digest built daily at each team's cutoff. 179 tests green. See [Roadmap](#roadmap).

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

Only part of each is built today; the Roadmap says which.

1. **Blocker lifecycle, not blocker mention.** Each blocker becomes a GitHub Issue, linked from its digest line with its age (`#42 · 3d`). The same blocker on a later day adds a comment rather than a new issue. *(Not yet: syncing the issue's open/closed state back into the digest.)* This automates the manual ritual teams converge on — a rotating owner spending three minutes a day checking yesterday's blockers.
2. **Faithfulness as an enforced invariant, not a prompt instruction.** A validator that runs after every summarizer and drops any claim that fails (strict mode fails the build instead): every claim carries at least one citation; every quote must be a verifiable substring of the immutable source. Incumbents ship AI summaries with no provenance at all.
3. **Write-back, not read-only.** Geekbot's explicit weakness, inverted into the core feature.
4. **Privacy as architecture with a user-facing surface.** Not a policy page. Built today: a hash-chained audit log of reads. Planned for week 4: a `/me/data` view, redaction, retention jobs, and a **contest/correct** action on any digest line.

---

## Design decisions

### Why extractive-first (no LLM in v1)

Measured behaviour of summarization systems: **verbatim extraction has a near-zero hallucination rate; generative summarization fabricates in roughly 15% of outputs even under strong prompting.** For a digest whose entire value is faithfulness, a 15% fabrication rate on *blockers* — the highest-stakes content — is disqualifying.

So the ordering is deliberate: build the extractive pipeline **and the validator** first, reach 100%-cited output with zero model dependency, then add an AI behind the same protocol where it must clear the **same** validator. The AI improves readability and grouping; it is never trusted to introduce a fact. The system also degrades gracefully — API down, rate-limited, or out of budget, and the digest still ships.

### Three findings that shaped the build

**1. `botbuilder-python` is dead.** Bot Framework SDK v4 for Python stopped being serviced 31 Dec 2025; the repo was **archived 5 Jan 2026**. Nearly every tutorial online still uses it. We use the **Microsoft 365 Agents SDK for Python** (GA, Python 3.10–3.14, Pydantic-validated `Activity` objects, first-party `microsoft-agents-hosting-fastapi` package). Versions are pinned — the surface is about a year old and still moving.

**2. Bot Framework Emulator is dead too — and its replacement de-risks the project.** The **Microsoft 365 Agents Playground** (`teamsapptester start`) emulates the Teams client and Bot Framework service locally with **no tenant, no tunnel, and no bot registration**, and renders Adaptive Cards with the same renderer Teams uses. The Teams *experience* is therefore buildable and demoable regardless of tenant sideloading policy.

**3. True per-message Teams permalinks are not constructible from a 1:1 bot chat.** Message deep links require a `19:`-form chat ID; Microsoft's docs state that 1:1 bot payloads carry the conversation ID in **`a:xxx`** format. This is a hard constraint, not an unknown.

> **Consequence — the citation contract does not depend on Teams.** Every submission is stored immutably with every identifier Teams gives us, and the canonical citation target is an internal **evidence view** (`GET /evidence/{item_id}`) served by FastAPI. A native permalink is emitted *additionally* when constructible (channel messages). This is the more defensible answer anyway: the evidence store survives Teams retention/deletion, which a permalink does not. It is also tamper-evident: each update's content hash is pinned into the hash-chained audit log at ingestion, and `python -m scripts.verify_integrity` recomputes every hash and fails if any stored text was edited afterwards.

### Privacy: the legal nuance most implementations miss

Under GDPR, **consent is not a valid lawful basis in an employment context** — the power imbalance means an employee cannot freely refuse. So the design uses **legitimate interest with a documented assessment** (`docs/LIA.md`, not yet written), plus strict data minimization and purpose limitation. The member-facing opt-in governs **scope** — notably `allow_external_processing`, which gates any future LLM — not participation.

Because workers must be able to see how a tool classified their activity and contest mistakes (GDPR Art. 21, and EU AI Act human-oversight obligations once AI lands), **every digest line will carry a contest/correct action** (week 4; not built yet).

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

---

## Architecture

Target layout; modules not yet written are listed in CLAUDE.md.

```
src/standup/
  main.py config.py logging_conf.py deps.py
  api/        health web_forms teams_router evidence digests privacy admin
  domain/     models enums errors            # pure, zero I/O
  ingestion/  base teams_adapter web_adapter normalizer permalink
  summarize/  base rules llm prompts validator render service
  tracker/    base github noop idempotency outbox credentials
  privacy/    consent visibility redaction retention audit export
  scheduling/ tick jobs timezones
  db/         session models repositories/
```

**Dependency rule.** `domain` imports nothing from the project; `summarize` imports only `domain`; `api` / `ingestion` / `tracker` are the only I/O layers. Enforced by **import-linter** contracts, run in CI (`.github/workflows/ci.yml`) — cheap, and it is what stops the LLM seam from leaking real data.

### Key seams

| Module | Role |
|---|---|
| `ingestion/base.py` | `IngestionAdapter` protocol + `RawSubmission`. Teams and the web form are two adapters; everything downstream sees only canonical `Update`/`UpdateItem`. **This is what makes Teams optional.** |
| `summarize/base.py` | `Summarizer` protocol (`SummaryRequest`/`SummaryResult`/`Claim`/`Citation`). The **prompt boundary**: a summarizer receives no ORM objects, no DB session, no emails, no unredacted text, and (once the consent model lands in week 4) nothing from members who have not opted into external processing. |
| `summarize/validator.py` | Runs in `service.py` **after** any summarizer so it cannot be bypassed. Failing claims are dropped; the digest reports "*N withheld*". |
| `tracker/base.py` | `TrackerAdapter` with `GitHubTracker` + `NoopTracker`. All writes go through `tracker_outbox` with backoff — **a GitHub outage must never lose a standup update.** |
| `scheduling/tick.py` | A **pure** `tick(now, cycles) -> [BuildDigest | DrainOutbox]`, enforced by an import-linter contract. `scheduling/jobs.py` runs it: each team's digest builds once its local cutoff passes, rebuilds quietly after a late update, notifies linked Teams users once per cycle with a link and a blocker count (never anyone's words), and drains the tracker outbox. It is single-runner (a database lease), so several workers or cron plus the in-app loop never build or announce twice; its database and HTTP work runs off the event loop; and it refuses to run without `STANDUP_BASE_URL`. It runs in-app every 60s with `STANDUP_SCHEDULER=true`, or once per call with `python -m scripts.tick` for cron. Pure function + injected clock = zero flaky tests; "simulate three days" is a loop in a test, and there is one. |

### The faithfulness validator

| Rule | Check | Status |
|---|---|---|
| V1 | Every claim has at least one citation | live |
| V2 | Every cited `source_id` exists (kills fabricated IDs) | live |
| V3 | `quote == source.text[start:end]` after NFKC + whitespace collapse (kills paraphrase-as-quote) | live |
| V4 | Every number/date in the claim appears in a cited source, or is derivable from cited `captured_at` | live |
| V5 | Every entity ref (`#123`, URL, `@handle`) appears in a cited source | live |
| V6 | Claim's `member_id` matches every cited source (no cross-attribution) | live |
| V7 | No cited source is outside consented/visible scope (privacy failures are faithfulness failures) | week 4 — needs the consent model |
| V8 | Length-inflation guard for abstractive claims | live |

A failing claim is **dropped**, not silently corrected, and the digest reports how many were withheld. Under `STANDUP_VALIDATOR_STRICT=true` (the CI setting) the build raises instead.

### Misfiled blockers get promoted, with a recorded reason

People put blockers in the wrong box. Someone types "Stuck on the deploy pipeline" into **Progress**, and a tool that trusts the form field alone buries the one line the team needed to see.

So a progress or plan line carrying a blocker marker (`blocked`, `waiting on`, `stuck`, `cannot`, `needs review`, …) is promoted into the Blockers section, and the claim records *why* as `matched_rule` — e.g. `promoted:marker:stuck`. The reason is stored with the digest and shown under the line ("Moved to Blockers: the author filed it elsewhere, but it says “stuck”."). Promotion never rewrites the text; the claim is still the verbatim span, so V3 holds and the citation still resolves.

Negations are checked first and win: `no blockers`, `not blocked`, `no longer blocked`, `unblocked` never produce a blocker, and neither do empty answers such as `None`, `N/A` or `-` in the Blockers box. Negation is judged per clause, so "no blockers on the API, but stuck on the migration" still reports the migration. That false positive — "No blockers today" reported as a blocker — is the most common failure in this category of tool, and it has its own parametrized test.

### Blocker to Issue idempotency (three layers)

1. **Fingerprint** — `sha256(team | member | normalized_blocker_key)` with a UNIQUE constraint on `tracker_link.fingerprint`
2. **Machine marker in the issue body** — `<!-- standup-bot:blocker:{fingerprint} -->` plus a `standup-blocker` label, so the mapping is rebuildable from GitHub alone
3. **One write per blocker per cycle** — UNIQUE `(fingerprint, cycle_id)` on `tracker_outbox`, so rebuilding a digest never writes twice

Before creating an issue, the drain looks for an existing one carrying the marker, so a crash between "issue created" and "link saved" cannot open a duplicate. Recurrence adds **one** comment per cycle. The bot never closes issues; people do. *(Planned, not built: a periodic reconcile job that rebuilds every link from labelled issues.)*

**Delivery never blocks a digest (invariant 8).** Building a digest only queues `tracker_outbox` rows. A drain then calls GitHub, running in the background after each build, or on demand with `python -m scripts.drain_outbox`. Only one drain runs at a time (a database lease), so concurrent drains cannot create the same issue twice. Rate limits (403 with `x-ratelimit-remaining: 0`, or 429) and 5xx errors back off and retry, honouring `retry-after`, for up to 8 attempts. A bad token or a missing repo fails the row at once with a stated reason. Every write is audited (`tracker.write`).

To try it with no account, run `python -m scripts.fake_github` and point `STANDUP_GITHUB_API_URL` at it (see [docs/DEMO.md](docs/DEMO.md)); the demo exercises the real GitHub client against it. To switch it on: `STANDUP_TRACKER=github`, `STANDUP_GITHUB_TOKEN` (a fine-grained token with Issues read/write on one repo), then `python -m scripts.set_github_repo --team core --repo owner/name`.

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

## Roadmap

Walking-skeleton first. **Something demoable at the end of every week.** Risky Azure work starts day 1 and is hard-timeboxed.

### Week 1 — Walking skeleton + start the Azure clock

**Why.** Two independent risks can sink the project: discovering in week 3 that the tenant blocks sideloading, and discovering in week 3 that the citation model doesn't work. Week 1 kills both. The skeleton proves the *whole* value chain end-to-end with zero external services, so every later week is an upgrade to something already working rather than a bet.

**Deliverables** — `pyproject.toml`, `main.py`, `config.py` (fail-fast on missing keys), `logging_conf.py` (structlog JSON + secret scrubbing), `api/health.py` · `db/models.py` + first Alembic migration (`team`, `member`, `standup_cycle`, `update`, `update_item`, `digest`, `digest_claim`, `audit_log`) · `api/web_forms.py` (3-field HTML form) · `ingestion/{base,web_adapter,normalizer}.py` with **character-offset spans** · `summarize/{base,rules,render,service}.py` (`RulesSummarizer` v0; renderer handles **withheld claims** from day one) · `api/evidence.py`, `api/digests.py`, `scripts/seed_demo.py` · `tests/unit/test_normalizer.py`, `tests/e2e/test_smoke_cycle.py` · `docker-compose.yml`, `.env.example`

**In parallel, days 1–2 — hard timebox 6 hours:** Entra app (single-tenant) + Azure Bot (F0, free); **check Teams admin → "Upload custom apps" policy**; apply to M365 Developer Program (bonus, never the critical path); install Agents Toolkit + Playground. Record in `docs/TEAMS-READINESS.md`.

**Done when** — `docker compose up`; three browser submissions; build digest; **every blocker links to an evidence page showing the verbatim source**. Plus a written go/no-go on Teams.

**Shipped — verified against a running server, not only tests:**

- Submit → digest → evidence, with blockers ordered first and every line cited
- Validator V1–V6 and V8 (pulled forward from week 2), enforced in `service.py` after the summarizer
- Hash-chained audit log, chain verified intact across ingest / digest-build / evidence-view
- Alembic initial migration; Dockerfile (multi-stage, non-root, healthcheck); compose with Postgres
- 72 tests at the end of week 1, 95% coverage, ruff clean, both import-linter contracts kept

**Still open after week 1:** the Teams tenant go/no-go (check **Teams admin → Setup policies → Upload custom apps**), and a `docker build` — the image is written but unbuilt, since Docker Desktop was not running.

**Cut line:** Postgres — stay on SQLite.

### Week 2 — Teams adapter + faithfulness enforced in code

**Why.** Week 1 proved citations are *possible*; week 2 makes them **unfakeable**. The validator is the core differentiator — what separates this from "an AI summary you have to trust." It must exist before any AI does, and be provably impossible to bypass. Meanwhile the Teams adapter proves the ingestion seam holds under a second, messier source.

**Deliverables** — `api/teams_router.py` on `microsoft-agents-hosting-fastapi` · `ingestion/teams_adapter.py` to the **same** `RawSubmission` · Adaptive Card (prompt + consent) — *structured fields are what keep the rules summarizer faithful: you never infer "is this a blocker", the user said so* · `teams/manifest/` + `scripts/make_teams_zip.py`, `scripts/devtunnel.ps1` · `conversation_ref` + `consent` tables · `ingestion/permalink.py` with the honest `a:`-conversation null path · Playground-captured activity fixtures

> The validator was pulled forward into week 1 — it is only ~150 lines and having it early lets the end-to-end test assert zero violations rather than hand-wave. Week 2 therefore adds V7's groundwork and the Teams work, not the validator itself.

**Done when** — in Agents Playground: type `standup`, get a card, submit, digest updates with citations. And the validator rejects a fabricated-citation summarizer **100%** of the time.

**Shipped:** `api/teams_router.py` (bot route, mounted only when `STANDUP_TEAMS_ENABLED=true`) · the scope gate and Adaptive Card in `ingestion/teams_adapter.py` · Teams submissions through the same `ingest()` as the web form · account linking via `/me/teams` + `link <code>` · `ingestion/permalink.py` (deep link for `19:` threads, a stated reason for `a:` 1:1 chats) · `teams/manifest/` + `scripts/make_teams_zip.py` · the content-free `ingest_rejection` counter at `GET /scope` · an import-linter contract confining the SDK to two files. **Not yet:** a run in Agents Playground or a real tenant. The Teams tests use hand-written activity fixtures, not Playground recordings, and `scripts/devtunnel.ps1` and the consent card are not written.

**Cut line — enforce ruthlessly:** if real Teams is still blocked at end of week 2, **freeze it**. Ship the Playground demo + fixtures + documented blocker, and do not touch Teams in week 3.

### Week 3 — GitHub write-back + blocker lifecycle + scheduling

**Why.** This fixes the failure every incumbent shares. Turning a blocker into a GitHub Issue gives it the three things a chat message can never have: **an owner, a state, and a history.**

**Deliverables** — `tracker/{base,github,noop,idempotency,outbox,credentials}.py` · `tracker_link` + `tracker_outbox` tables · blocker-to-Issue mapping with body markers and labels · bidirectional digest/issue links · reconcile job · `scheduling/{tick,jobs,timezones}.py` with pure `tick()` and per-member IANA timezones · carry-over detection in `rules.py` · respx-mocked tracker tests + `tests/e2e/test_two_day_carryover.py`

**Done when** — simulate two days with an injected clock: day 1 creates two real issues in a scratch repo; day 2 the same blocker creates **no duplicate**, adds one "still blocked (day 2)" comment; the day-2 digest shows the carry-over **citing both days' sources**.

**Cut lines:** Projects v2 board sync, GitHub App auth, proactive scheduled prompts.

**Shipped so far:** `tracker/{base,github,noop,idempotency,outbox}.py` · `tracker_link` + `tracker_outbox` tables · blocker-to-Issue with body marker and label · links both ways (issue → evidence and digest; digest → issue with age) · background drain with backoff · respx-mocked tests including a two-day recurrence that comments instead of duplicating. **Also shipped:** `scheduling/{tick,jobs}.py` with a pure `tick()`, the in-app loop and `scripts/tick.py`, and Teams "digest ready" notices sent through the stored 1:1 conversation reference. **Not yet:** proactive "time to file" prompts (cut line), the reconcile job, carry-over detection in `rules.py`, and a run against a real scratch repo (a read-only live test exists and is skipped without credentials).

### Week 4 — Privacy, deployment, docs, and the LLM seam

**Why.** Two of the three "enterprise-grade" requirements land here, plus production deployment. Privacy is the subsystem that makes "not surveillance" *true rather than aspirational* — and the one architectural commitment guaranteeing it is that **there is no manager role and no manager-only view.**

**Deliverables** — `privacy/{consent,visibility,redaction,retention,audit,export}.py` · `api/privacy.py` for `/consent`, `/me/data`, `/me/export`, `/me/delete`, plus **contest/correct** · redaction running **before** `SourceDoc` construction, so the LLM seam can never receive a secret even by accident · hash-chained audit log + "who read your updates" · retention purge (default 30d) leaving digests renderable · `summarize/llm.py` + `prompts.py` (stub + `FakeLLMSummarizer`) + import-linter contract · **deployment** to Azure Container Apps (Fly.io fallback), managed Postgres, platform secrets, Alembic on release, probes wired to `/healthz` + `/readyz` · **CI/CD** via GitHub Actions (ruff, mypy, pytest, coverage >=90% on `summarize/` and `privacy/`, import-linter, build+push, deploy on tag) · **docs** — `PRIVACY.md`, `docs/{ARCHITECTURE.md,LIA.md,TEAMS-READINESS.md,DEMO.md}`, ADRs

**Done when — the 10-minute scripted demo against the deployed instance:** enroll with consent, submit via card, digest with citations, GitHub issue created, click a blocker's evidence link, **show the audit-log row that click just produced**, run "delete my data", digest re-renders with the item withheld and the issue gets a removal comment, then run the golden set against `FakeLLMSummarizer` and watch the **same** validator reject its hallucinated citation.

**Cut line:** the LLM stub may ship as interface + fake + tests with no real provider call. That is the *correct* scope — the seam is the deliverable, not the model.

### Global cut-line ordering

Drop in this order: (1) Projects v2 board sync, (2) GitHub App auth (keep fine-grained PAT), (3) proactive scheduled Teams messages (keep user-initiated `standup`), (4) managed Postgres, (5) real Teams tenant (ship the Playground demo), (6) carry-over detection, (7) channel-scope ingestion.

**Never cut:** the citation contract · the faithfulness validator · the consent/retention/audit privacy core · the web-form adapter · the test suite.

> **Scoping note.** "Production-ready" here means deployed, containerized, migrated, health-checked, CI-gated, secret-managed, and documented — usable by a real team. It does **not** mean multi-tenant onboarding, SSO, an SLA, or horizontal scale. Those are future work rather than half-built.

---

## Testing

Layout today: `tests/{unit,integration,e2e}/`. Stack: pytest · FastAPI `TestClient` · **Hypothesis** · injected `Clock` protocol (not freezegun). `tests/fixtures/` and **respx** arrive with the work that needs them. The integration and e2e tests also run against Postgres in CI when `STANDUP_TEST_DATABASE_URL` is set.

| What | Status | How |
|---|---|---|
| **Teams bot, no tenant** | built | Hand-written activity fixtures in `tests/fixtures/teams/` (not yet recorded from Playground) drive the scope gate and `StandupAgent.on_turn` with a `FakeTurnContext` that records replies, against a real database. The HTTP route is exercised in anonymous mode. A manifest test asserts zero Graph permissions, and an SDK-compat test builds real replies. |
| **Faithfulness** | partial | Negation and misfiled-blocker cases are parametrized tests in `tests/unit/test_rules_summarizer.py`. Planned: a `tests/fixtures/golden/*.yaml` set parametrized over `[RulesSummarizer, FakeLLMSummarizer]`, adding sarcasm, a number appearing nowhere, near-identical text from two members, and a **prompt-injection** string. |
| **Validator** | built | `HallucinatingSummarizer` double, assert 100% rejection. Hypothesis mutation properties (flip a digit, swap a `source_id`, shift an offset by 1) and example tests for paraphrase-as-quote and cross-attribution, each asserting the mutation is rejected. |
| **GitHub** | built (no reconcile yet) | respx-mocked API (`tests/unit/test_github_tracker.py`, `tests/integration/test_tracker_writeback.py`). A blocker gives exactly one POST; a rebuild adds nothing; the next day adds one comment; a lost link is recovered from the issue marker with no POST; a 403 rate limit schedules a retry and leaves the digest unaffected; a 401 fails the row; no tracker or no repo skips with a reason. One read-only `@pytest.mark.live_github` test, skipped without credentials. |
| **Privacy** | partial | Built: audit-chain integrity (in the e2e smoke test) and a test asserting a known secret never appears in captured logs. Planned (week 4): retention purge leaves digests renderable; `/me/delete` marks claims withheld. |
| **E2E smoke** (<10s) | built | Three submissions, digest, validator passes, evidence link returns exact source text, `audit_log` has the expected rows in an intact chain. Advancing the clock past a cutoff arrives with scheduling. **The regression net and the demo script simultaneously.** |

Run them:

```bash
pytest                      # everything (215 tests, a few seconds)
pytest tests/unit           # fast unit pass
pytest tests/e2e -v         # end-to-end smoke
pytest --cov=standup --cov-report=term-missing
ruff check .                # lint
lint-imports                # enforce the dependency rule
mypy src                    # strict type check
python -m scripts.verify_integrity   # audit chain + stored-text hashes
```

CI (`.github/workflows/ci.yml`) runs all of the above with `STANDUP_VALIDATOR_STRICT=true`, gates `summarize/` and `privacy/` at 90% coverage, runs migrations plus the integration and e2e tests against Postgres 16, and builds the Docker image.

Current: **215 passing, 97% coverage overall.** The gate that matters is `summarize/` and `privacy/` at >=90% — those are the modules where a silent regression is a correctness or compliance failure rather than a bug. `normalizer.py`, `summarize/base.py`, `logging_conf.py` and `main.py` sit at 100%; `validator.py` at 99%.

> `lint-imports` must be run as the console script. `python -m importlinter.cli` exits 0 *without reading* `pyproject.toml`, so it reports success while enforcing nothing — confirmed by adding a deliberate boundary violation and watching it pass.

Week 1 covers: normalizer span round-tripping (including a Hypothesis property over arbitrary text), the rules summarizer with its negation and prompt-injection cases, all implemented validator rules with a `HallucinatingSummarizer` double and mutation properties, and the end-to-end cycle with audit-chain verification.

---

## Getting started

```bash
git clone https://github.com/RitGos28/status-unblocked.git
cd status-unblocked
cp .env.example .env
# set STANDUP_SECRET_KEY in .env (required, 32+ chars):
python -c "import secrets; print(secrets.token_urlsafe(48))"

# local (SQLite, no containers)
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed_demo --days 2   # two days of made-up updates; prints a login link per member
uvicorn standup.main:app --reload

# or containerised (Postgres + the API); reads STANDUP_SECRET_KEY from your shell
export STANDUP_SECRET_KEY=...
docker compose up --build          # the seed's links appear in the logs
```

Open a member's login link to sign in as them, then use **Submit update** and **Digests**. `python -m scripts.issue_links` prints fresh links at any time.

**The full demo is [`docs/DEMO.md`](docs/DEMO.md)**, and `scripts/demo_check.sh` runs it end to end (also in CI). The short version:

### A two-minute walkthrough

1. **Open Ada's link and submit** — Progress `Shipped the retry logic. Reviewed #214.`, Blockers `Waiting on staging credentials from infra.`, Today `Finish the migration.`
2. **Open Bruno's link and submit**, putting `No blockers today.` in the Blockers box.
3. **Open Chen's link and submit**, typing `Stuck on the deploy pipeline.` into **Progress** — deliberately the wrong box.
4. Go to **Digests** and press **Build digest**.

What you should see, and why each part matters:

| Observation | What it demonstrates |
|---|---|
| Blockers section comes first | The digest is ordered by what needs attention, not by who submitted |
| Bruno's "No blockers today" is absent | Negation handling — the commonest false positive in this category |
| Chen's line appears **under Blockers**, with "Moved to Blockers … it says “stuck”" beneath it | Misfiled blockers are promoted, and the reason (`promoted:marker:stuck`) is stored and shown |
| Every line has a **source** link | No claim ships uncited |
| The evidence page highlights the exact span | The citation is a real offset into stored text, not a vague pointer |
| "No platform link: webform…" on that page | Missing permalinks state their reason instead of being a silent null |

Then check the digest's `validator_report_json` — `checked: 8, passed: 8, withheld: 0`. Every line was verified against its source before the page rendered.

| Endpoint | Purpose |
|---|---|
| `GET /healthz` `GET /readyz` `GET /version` | Liveness, readiness, build info |
| `GET POST /submit` | Web-form ingestion adapter |
| `GET /digests` `GET /digest/{id}` | Build and read digests |
| `GET /evidence/{item_id}` | Citation target — verbatim source with the quoted span highlighted |

---

## Verify during implementation

Do not trust these from memory — confirm each at build time:

- Exact Teams extension package name: `microsoft-agents-hosting-msteams` vs `microsoft-agents-hosting-teams` — Microsoft's repo and migration doc **disagree**; check with `pip index versions`
- ~~Agents SDK version pins and the exact `CloudAdapter` / `start_agent_process` signatures for FastAPI~~ Verified against the installed 1.5.0 source: `CloudAdapter(connection_manager=MsalConnectionManager(**load_configuration_from_env(os.environ)))`, then `adapter.process(request, agent)`. **Found:** the SDK needs pydantic >= 2.11 (it sets `validate_by_name`) although its metadata says >= 2.10.4; on 2.10 every reply fails to build. Pinned to 2.13.5, with a regression test.
- The `manifestVersion` / `$schema` pair your Teams client accepts. The manifest uses 1.17; the toolkit changelog says 1.23 is current. Not yet checked against a tenant.
- Whether your tenant surfaces a `19:`-form chat ID anywhere in a 1:1 bot payload (design assumes **no**; the fallback covers either)
- GitHub `/search/issues` current rate limit; whether issue `type` is enabled on your repo
- Config env-var shape: `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID` etc., and `...__ANONYMOUS_ALLOWED=True` for local

---

## References

**Product research** — [Geekbot reviews](https://www.capterra.com/p/148076/geekbot/reviews/) · [Async standup bots compared](https://www.standin.co/blog/async-standup-bots-compared) · [Geekbot alternatives for engineering teams](https://www.standin.co/blog/geekbot-alternatives) · [Async standups people actually read](https://pickuma.com/for-dev/async-standups-people-actually-read/) · [Async standups guide](https://www.vereda.ai/guides/async-standups)

**Summarization faithfulness** — [AI summaries are unreliable](https://www.baldurbjarnason.com/2023/ai-summaries-unreliable/) · [Avoiding hallucination in content extraction](https://madhudadi.in/blog/posts/ai-summaries-avoiding-hallucination-in-content-extraction)

**Privacy and compliance** — [GDPR employee monitoring](https://secureprivacy.ai/blog/employee-monitoring-gdpr-guide) · [GDPR-compliant monitoring checklist](https://gstride.ai/blog/gdpr-compliant-employee-monitoring/)

**Microsoft Teams** — [Bot Framework to M365 Agents SDK Python migration](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/bf-migration-python) · [botbuilder-python (archived)](https://github.com/microsoft/botbuilder-python) · [microsoft-agents-hosting-fastapi](https://pypi.org/project/microsoft-agents-hosting-fastapi/) · [Teams deep links](https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-teams) · [Manage custom app policies](https://learn.microsoft.com/en-us/microsoftteams/teams-custom-app-policies-and-settings) · [Agents Playground](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/debug-your-agents-playground) · [Proactive messages](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages) · [Azure Bot Service pricing](https://azure.microsoft.com/en-us/pricing/details/bot-services/)

**GitHub** — [Issues REST API](https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28) · [REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
