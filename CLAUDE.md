# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Problem framing, competitive analysis, and the 4-week roadmap live in [`README.md`](./README.md). This file is the operating rules and the architecture map. The original hackathon brief is in [`projectstatement.txt`](./projectstatement.txt); its three "enterprise-grade" bullets are the graded requirements named at the bottom of this file.

---

## Commit convention

**Do not add attribution trailers to commits or PRs.** Never include:

- `Co-Authored-By:` lines of any kind
- `Claude-Session:` links
- "Generated with Claude Code" or similar footers

Plain commit messages only. This overrides the default Claude Code attribution behaviour and applies to every commit in this repo.

Conventional-commit prefixes (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`), imperative mood, scope by module (`ingestion`, `summarize`, `tracker`, `privacy`, `db`, `api`).

Commit identity is set repo-locally (`git config --local user.name/user.email`). Do not override it with `-c` flags.

## Push cadence

**Push after every meaningful change, and update the docs before pushing.**

A meaningful change is a coherent unit that leaves the tree working — a module plus its tests, a completed vertical slice, a bug fix. Not every file save, and not a week's work in one drop.

Before each push:

1. Update `README.md` if behaviour, endpoints, setup, or roadmap status changed
2. Update this file if a convention, invariant, or command changed
3. Update `.env.example` if a setting was added
4. Run `pytest` and `ruff check .` — do not push a red tree
5. Commit with no attribution trailer, then `git push`

Docs must not claim more than the code does. If you write "there is a test for X", there must be a test for X.

---

## Commands

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                                    # full suite
pytest tests/unit                         # fast pass
pytest tests/e2e -v                       # end-to-end smoke
pytest tests/unit/test_validator.py       # one file
pytest tests/unit/test_validator.py::test_v3_paraphrase_presented_as_quote_is_dropped
pytest -k "negation"                      # by name substring
pytest --cov=standup --cov-report=term-missing

ruff check .
ruff check --fix .
mypy src                                  # strict; clean as of Phase 1, keep it that way
python -m scripts.verify_integrity        # audit chain + stored-text hashes; exits 1 on tampering

alembic revision --autogenerate -m "description"
alembic upgrade head
```

**Coverage gate: >=90% on `summarize/` and `privacy/`.** Those are the modules where a silent regression is a correctness or compliance failure rather than a bug. CI enforces it with `coverage report --fail-under=90 --include='src/standup/summarize/*,src/standup/privacy/*'`; `pyproject.toml` also sets an overall `fail_under = 90`.

### Running the app locally

`alembic upgrade head` and the seed are both required before `uvicorn`, or the submit page renders with no members and nothing can be filed:

```bash
alembic upgrade head
python -m scripts.seed_demo      # team "Core Platform", 3 members
uvicorn standup.main:app --reload
```

Then `/submit` to file an update, `/digests` to build and read one. `docker compose up --build` runs the same thing against Postgres.

### import-linter

This enforces the prompt boundary, so it is worth getting right:

```bash
lint-imports
```

Two traps, both hit during week 1:

- **`python -m importlinter.cli` exits 0 without reading `pyproject.toml`.** It reports success while enforcing nothing. Verified by adding a deliberate violation and watching it pass. Only the console script works.
- If `lint-imports` is "not found", the console script is not on PATH (on the original Windows setup it lived under `.../Python313/Scripts/lint-imports.exe`; in a venv it is `.venv/bin/lint-imports`). Use the full path rather than falling back to the module form.

---

## Architecture

One request path carries the whole design. Follow it once and the layering makes sense:

```
POST /submit                         api/web_forms.py
  -> WebFormAdapter.to_raw_submission()     ingestion/web_adapter.py
       produces RawSubmission               ingestion/base.py      <-- the source-agnostic seam
  -> normalize()                            ingestion/normalizer.py
       composes raw_text, splits into UpdateItems with char offsets
  -> persisted as Update + UpdateItem[]     db/models.py
  -> record_audit()                         privacy/audit.py

POST /digests/build/{cycle_id}       api/digests.py
  -> build_request()                        summarize/service.py
       maps ORM rows -> SourceDoc[]         <-- the prompt boundary; ORM stops here
  -> Summarizer.summarize()                 summarize/rules.py
       emits Claims whose text IS a verbatim span
  -> FaithfulnessValidator.validate()       summarize/validator.py
       failing claims are DROPPED, counted as withheld
  -> render_markdown() + persist Digest/DigestClaim
```

Teams enters at the same seam: `TeamsAdapter` (`ingestion/teams_adapter.py`) turns an `Action.Submit` activity into the same `RawSubmission`. No route calls it yet — `api/teams_router.py` is still to be written.

### Validator rules

Tests and invariants refer to these by number. Defined in the `validator.py` docstring; README has the full table.

| Rule | Rejects |
|---|---|
| V1 | claim with no citation |
| V2 | cited `source_id` not in the request |
| V3 | quote != `source.text[start:end]` (after NFKC + whitespace collapse) |
| V4 | number not in a cited quote and not a derived metric |
| V5 | entity ref (`#123`, URL, `@handle`, `ABC-12`) not in a cited quote |
| V6 | claim's member differs from a cited source's member |
| V7 | source outside consented/visible scope — **not implemented** (week 4) |
| V8 | abstractive claim >1.3x the length of its evidence |

`STANDUP_VALIDATOR_STRICT=true` makes a failing claim raise instead of being dropped. CI (`.github/workflows/ci.yml`) runs the suite strict. Its jobs: ruff, mypy, `lint-imports`, strict pytest plus the coverage gate; migrations and the integration/e2e tests against Postgres 16; and a Docker build.

### The two seams that matter

**`ingestion/base.py` — `RawSubmission`.** Every source normalises to this. The web form is one adapter; `TeamsAdapter` is the second (written, but no route serves it yet). Everything downstream is platform-agnostic, which is what makes Teams *optional* — if a tenant blocks sideloading, the web adapter still exercises the entire pipeline.

**`summarize/base.py` — `SummaryRequest`.** The entire input surface of any summarizer. No ORM objects, no session, no emails, no unredacted text. When the LLM implementation lands, whatever crosses this line is what leaves the building, so keeping it narrow is cheaper than auditing a prompt builder that can reach anywhere.

### Why extractive-first

Verbatim extraction has a near-zero hallucination rate; generative summarization fabricates in roughly 15% of outputs even under strong prompting. For a digest whose value *is* faithfulness, that rate on blockers is disqualifying. So `RulesSummarizer` emits claims that ARE the source span — faithful by construction — and the validator is built against output that is already correct. A future LLM then has to clear the same bar rather than a softer one written for it.

### Why citations point at an internal evidence view

Teams message deep links need a `19:`-form chat ID, but 1:1 bot payloads carry the conversation ID in `a:` form, so a true per-message permalink is not constructible for the primary collection path. Every citation therefore resolves to `GET /evidence/{item_id}`, which renders the stored text with the cited span highlighted. A native permalink is emitted *additionally* when one can be built. When there is none, `update.permalink_reason` records why rather than leaving a silent null.

---

## Layout

Files that exist today:

```
src/standup/
  main.py          app factory, lifespan, RFC-9457 error handler
  config.py        pydantic-settings, STANDUP_ prefix
  deps.py          DI: get_db, get_clock, get_summarizer; Jinja templates
  logging_conf.py  structlog + secret scrubbing
  api/             health, web_forms, evidence, digests
  domain/          enums, errors, models (Clock, SystemClock, FakeClock), timezones   (pure, zero I/O)
  ingestion/       base, web_adapter, teams_adapter, normalizer
  summarize/       base, rules, validator, render, service
  privacy/         audit  (hash-chained log)
  db/              models, session
  templates/       base, index, submit, digests, digest, evidence, error
  migrations/      alembic
```

Planned but **not yet written** — do not import these, and do not assume they exist:

`api/teams_router.py`, `api/privacy.py`, `api/admin.py`, `ingestion/permalink.py`, `summarize/llm.py`, `summarize/prompts.py`, all of `tracker/`, all of `scheduling/`, and `privacy/{consent,visibility,redaction,retention,export}.py`.

**There is no authentication or authorization yet.** `/digests` lists every team's cycles and `/evidence/{id}` opens for anyone; "team-scoped" is the design, not something the code enforces today. Do not describe it as enforced in docs.

---

## The dependency rule

Partly enforced by import-linter. `pyproject.toml` has exactly two contracts: `domain` is pure, and the summarizer core (`base/rules/validator/render`) is pure. The `scheduling/` row and invariant 9 (Agents SDK confinement) have no contract yet; add one when that code lands. Neither contract forbids `standup.deps`, `standup.main` or `standup.logging_conf`, so check those imports by eye.

| Layer | May import |
|---|---|
| `domain/` | **nothing from this project** |
| `summarize/{base,rules,validator,render}.py` | `domain/` only — the prompt boundary |
| `summarize/service.py` | anything — the orchestrator, does the I/O the pure modules must not |
| `scheduling/tick.py` (planned) | `domain/` only; `tick()` is a pure function |
| `ingestion/`, `tracker/`, `privacy/`, `db/`, `api/` | anything — the I/O layers |

Wanting to import a SQLAlchemy model into `summarize/` is the signal you are about to break the seam. Map it to a domain dataclass in `service.py` instead.

---

## Invariants — do not break these

1. **The validator runs after the summarizer, never inside one.** `service.py` calls `summarize()` then `validate()`. A summarizer must never call the validator itself, or the check becomes bypassable by the next implementation.

2. **`update.raw_text` and `raw_payload_json` are immutable.** Written once at ingestion. Retention nulls them; nothing else touches them. Every citation's verifiability rests on this.

3. **Character offsets are real offsets.** `raw_text[span_start:span_end] == item.text` must hold. If you normalize or strip text, adjust the offsets. There is a Hypothesis property over arbitrary text guarding this.

4. **Reclassifying a claim must never rewrite its text.** A misfiled blocker is promoted from Progress into Blockers, but the claim stays the verbatim span and records why in `matched_rule` (`promoted:marker:stuck`). The moment promotion edits text, V3 breaks and the citation stops resolving.

5. **Negation is checked before markers, always.** `no blockers` / `not blocked` / `no longer blocked` must never yield a blocker. This is the most common bug in this category of tool and has a parametrized test.

6. **Redaction runs before `SourceDoc` construction** (week 4), so a secret cannot reach a third-party model even by accident.

7. **No manager role.** No role hierarchy, no manager-only view, no per-person metrics. Digests are team-scoped and visible to every member equally. If a request needs "so the lead can see who didn't submit", that is the surveillance anti-pattern — push back rather than building it.

8. **External writes go through the outbox** (week 3). `tracker/` never blocks ingestion or digest generation.

9. **All Microsoft Agents SDK imports stay inside `api/teams_router.py` and `ingestion/teams_adapter.py`** (week 2). That SDK is about a year old and still moving; keep the blast radius of a breaking change to two files. Note `botbuilder-python` is archived and must not be used.

10. **Every ingestion path pins the content hash.** The `update.ingested` audit row's `object_ids` must carry `content_sha256`, or `verify_evidence` reports that update as tampered. Any new adapter route (Teams, CSV import) must record it the same way `api/web_forms.py` does.

11. **A cycle is the team's local date, never the UTC date.** Use `domain/timezones.local_cycle_date(now, team.tz_default)`; `now.date()` splits one working day across two cycles for teams far from UTC.

---

## Testing conventions

- **Injected `Clock`, never `freezegun`.** Time comes from `deps.get_clock()`; tests pass a `FakeClock`. No `sleep` anywhere.
- **No network.** `respx` will mock httpx once `tracker/` lands (it is not yet in `[dev]` — add it with the first tracker test). The one exception is `@pytest.mark.live_github`, excluded from CI.
- **Teams will be tested from recorded fixtures** captured once from Agents Playground, so the Teams path stays CI-testable with no tenant.
- **The validator suite is parametrized over every summarizer implementation.** When you add one, add it to that list — do not write it a softer test.
- Tests run on a throwaway SQLite file by default. Set `STANDUP_TEST_DATABASE_URL` to a Postgres URL to run them there (CI does, for `tests/integration` and `tests/e2e`); each test then creates and drops its tables.
- `tests/e2e/test_smoke_cycle.py` is both the regression net and the demo script. Keep it under 10 seconds.
- Two test doubles carry most of the weight: `HallucinatingSummarizer` (fluent, plausible, entirely unsourced — must be rejected 100%) and Hypothesis mutation properties (shift an offset by one, swap a source id, inject a digit — every mutation must be caught).

Ruff excludes `src/standup/migrations/versions/` — Alembic writes those.

---

## Secrets and config

- `SecretStr` for every credential, declared as a required field so startup fails naming all missing keys. Today `config.py` has no credentials and every setting has a default; the first secrets (Teams app ID/secret, GitHub token) must follow this rule.
- `.env` is gitignored; **`.env.example` must stay complete** — every key present, no values.
- `logging_conf.py` scrubs sensitive key names and secret-shaped values (GitHub tokens, AWS keys, JWTs) from every log line. `tests/unit/test_logging.py` asserts a known secret never reaches the stream.

---

## Style

- Python 3.13, full annotations. (`pyproject.toml` still says `requires-python >=3.11` and mypy `python_version = "3.11"` — do not use 3.12+-only syntax until those are raised.) `ruff` for lint and format — do not hand-format.
- Frozen dataclasses for domain types; `Protocol` for seams, not ABCs.
- Structured logging with stable event names (`update.ingested`, `digest.built`, `claim.rejected`), not f-string prose.
- Errors surface as RFC-9457 `application/problem+json` via the handler in `main.py`.

---

## When in doubt

The three graded requirements are **faithful citations**, **structured write-back**, and **privacy boundaries**. If a change trades one of those for convenience, it is the wrong change. README's cut-line ordering says what may be dropped under time pressure; the "never cut" list says what may not.
