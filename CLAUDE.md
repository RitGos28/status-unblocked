# CLAUDE.md

Working agreement for this repo. Read before making changes.

Project background, competitive analysis, and the 4-week roadmap live in [`README.md`](./README.md). This file is the operating rules.

---

## Commit convention

**Do not add attribution trailers to commits or PRs.** Specifically, never include:

- `Co-Authored-By:` lines of any kind
- `Claude-Session:` links
- "Generated with Claude Code" or similar footers

Plain commit messages only. This overrides the default Claude Code attribution behaviour and applies to every commit in this repo, starting from the first.

```
# good
feat(ingestion): add character-offset spans to normalizer

# bad
feat(ingestion): add character-offset spans to normalizer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

Other commit rules: conventional-commit prefixes (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`), imperative mood, scope by module (`ingestion`, `summarize`, `tracker`, `privacy`, `db`, `api`).

## Push cadence

**Push after every meaningful change, and update the docs before pushing.**

A "meaningful change" is a coherent unit that leaves the tree working — a module plus its tests, a completed vertical slice, a bug fix. Not every file save, and not a week's work in one drop.

Before each push:

1. Update `README.md` if behaviour, endpoints, setup, or roadmap status changed
2. Update `CLAUDE.md` if a convention, invariant, or command changed
3. Update `.env.example` if a setting was added
4. Run `pytest` and `ruff check .` — do not push a red tree
5. Commit with no attribution trailer (see above), then `git push`

---

## Layout

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
tests/        unit/ integration/ e2e/ fixtures/
```

---

## The dependency rule

This is the constraint that keeps the summarizer seam honest. Enforced by import-linter in CI.

| Layer | May import |
|---|---|
| `domain/` | **nothing from this project** — pure dataclasses, enums, errors |
| `summarize/{base,rules,validator,render}.py` | `domain/` only — this is the prompt boundary |
| `summarize/service.py` | anything — it is the orchestrator, and does the I/O the pure modules must not |
| `scheduling/tick.py` | `domain/` only (the `tick` function is pure) |
| `ingestion/`, `tracker/`, `privacy/`, `db/`, `api/` | anything — these are the I/O layers |

If you find yourself wanting to import a SQLAlchemy model into `summarize/`, that is the signal you are about to break the seam. Map it to a `domain` dataclass in `service.py` instead.

---

## Invariants — do not break these

1. **The validator runs after the summarizer, never inside one.** `summarize/service.py` calls `summarize()` then `validate()`. A summarizer must never call the validator itself, or the check becomes bypassable by the next implementation.

2. **`update.raw_text` and `update.raw_payload_json` are immutable.** Written once at ingestion, never updated. Retention nulls them; nothing else touches them. Every citation's verifiability depends on this.

3. **Character offsets are real offsets.** `update_item.span_start/span_end` must satisfy `raw_text[start:end] == item.text`. If you normalize or strip text, adjust the offsets — do not silently drift. There is a test for this.

4. **A summarizer receives no ORM objects, no DB session, no email addresses, and no unredacted text.** `SummaryRequest` is the whole input surface. This is the prompt boundary: when the LLM implementation lands, whatever crosses this line is what leaves the building.

5. **Redaction runs before `SourceDoc` construction**, so a secret cannot reach a third-party model even by accident.

6. **No manager role.** There is no role hierarchy, no manager-only view, and no per-person metric. Digests are team-scoped and visible to every member equally. If a requested feature needs "so the lead can see who didn't submit", that is the surveillance anti-pattern — push back and refer to `PRIVACY.md`.

7. **External writes go through the outbox.** `tracker/` never blocks ingestion or digest generation. A GitHub outage must never lose a standup update.

8. **All Microsoft Agents SDK imports stay inside `api/teams_router.py` and `ingestion/teams_adapter.py`.** The SDK surface is young and still moving; keep the blast radius of a breaking change to two files.

---

## Commands

```bash
pip install -e ".[dev]"      # install with dev extras

pytest                       # full suite
pytest tests/unit            # fast pass
pytest tests/e2e -v          # end-to-end smoke
pytest --cov=standup --cov-report=term-missing

ruff check .
mypy src

# import-linter. Use the console script: `python -m importlinter.cli` exits 0
# without reading pyproject.toml, so it silently "passes" even when a contract
# is broken. Verified by adding a deliberate violation.
lint-imports

alembic revision --autogenerate -m "description"
alembic upgrade head

uvicorn standup.main:app --reload
docker compose up --build
```

**Coverage gate: >=90% on `summarize/` and `privacy/`.** Those are the two modules where a silent regression is a correctness or compliance failure rather than a bug.

---

## Testing conventions

- **Injected `Clock` protocol, never `freezegun`.** Time comes from `deps.get_clock()`. Tests pass a `FakeClock`. No `sleep` anywhere in the suite.
- **No network in tests.** `respx` mocks httpx. The one exception is `@pytest.mark.live_github`, excluded from CI by default.
- **Teams is tested from recorded fixtures** in `tests/fixtures/teams_activities/`, captured once from Agents Playground. The Teams path stays CI-testable with no tenant, forever.
- **The validator suite is parametrized over every summarizer implementation**, so a future LLM must clear the identical bar as the rules engine. When you add an implementation, add it to that parametrize list — do not write it a softer test.
- `tests/e2e/test_smoke_cycle.py` is both the regression net and the demo script. Keep it under 10 seconds.

---

## Secrets and config

- `pydantic-settings` in `config.py`, `SecretStr` for every credential, fail-fast at startup listing all missing keys.
- `.env` is gitignored. **`.env.example` must stay complete** — every key present, no values. Adding a setting means updating it in the same commit.
- Secrets never reach logs; `logging_conf.py` has a scrubbing processor and there is a test asserting a known secret value never appears in captured output.

---

## Style

- Python 3.13, full type annotations, `from __future__ import annotations` not needed.
- `ruff` for lint and format — do not hand-format.
- Frozen dataclasses for domain types; `Protocol` for seams, not ABCs.
- Structured logging with stable event names (`update.ingested`, `digest.built`, `claim.rejected`, `tracker.issue.created`) — not f-string prose.
- Errors surface as RFC-9457 `application/problem+json`.

---

## When in doubt

The three graded requirements are **faithful citations**, **structured write-back**, and **privacy boundaries**. If a change trades one of those for convenience, it is the wrong change. The cut-line ordering in `README.md` says what may be dropped under time pressure; the "never cut" list says what may not.
