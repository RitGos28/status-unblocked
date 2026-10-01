# Demo

Everything below runs locally with **no accounts**: no GitHub, no Teams tenant,
no Docker. `scripts/demo_check.sh` runs this exact script against a real server
and asserts every step; run it to prove the demo still works.

```bash
scripts/demo_check.sh          # about 10 seconds; prints one line per step
```

## Setup (once per demo)

```bash
export STANDUP_DATABASE_URL=sqlite:///./demo.db
export STANDUP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
export STANDUP_BASE_URL=http://127.0.0.1:8000
alembic upgrade head
python -m scripts.seed_demo --days 2      # two days of made-up updates; prints a login link per person
uvicorn standup.main:app --port 8000
```

`./run.sh` does the same with today's updates only.

## 1. Sign-in and team boundaries
- Open `/digests` without signing in: **401**, "Sign in with your personal link".
- Open **Ada's** link from the seed output: you land on Core Platform's digests. Mobile's are not listed.
- Later (step 6), open **Dana's** link (team Mobile) and paste a Core Platform digest or evidence URL: **404**. Another team's pages are not just forbidden; they do not exist for her.

## 2. Submit, and resubmit
- As Ada, **Submit update**. Submit again with a change: the second replaces the first in the digest (the first is kept unedited, because stored text is never rewritten).

## 3. The daily digest, built by the scheduler
The digest builds itself at each team's cutoff (11:00 UTC for the demo teams). To show it at any hour, run one scheduler pass on a demo clock:

```bash
python -m scripts.tick --at 2026-10-01T11:06:00Z     # today's date, just after the cutoff
```

It reports `built 2 digest(s)`: yesterday's and today's. Then open **Digests** and today's digest.

## 4. What the digest shows
- **Blockers come first.** Ada: "Waiting on staging credentials from infra."
- **Chen's misfiled blocker:** he typed "Stuck on the deploy pipeline." under Progress; it is under Blockers with "Moved to Blockers: the author filed it elsewhere, but it says 'stuck'". The text itself is unchanged.
- **Negation:** Bruno wrote "No blockers today." It is not reported as a blocker.
- Every line has a **source** link. The **Markdown** link at the bottom gives the same digest as text.

## 5. Evidence, and proving nothing was edited
- Click a **source** link: the stored update, with the cited words highlighted and their character offsets.
- `python -m scripts.verify_integrity` → "audit chain intact; every stored update matches its pinned hash".
- Edit any stored update in a *copy* of the database and run it against the copy: it names the tampered update and exits 1. (`scripts/demo_check.sh` does exactly this.)

## 6. Ops
- `/scope`: how many out-of-scope Teams messages were refused (counts only; nothing about them is stored).
- `/healthz`, `/readyz`.
- Any error opened in a browser is an HTML page; API clients get `application/problem+json`.

## Optional: needs your accounts or tools
- **GitHub Issues write-back against a real repo:** `STANDUP_TRACKER=github`, `STANDUP_GITHUB_TOKEN` (fine-grained, Issues read/write on one repo), `python -m scripts.set_github_repo --team core --repo owner/name`, then build a digest.
- **Teams in a real client:** Agents Playground or a tenant; see README "Teams".
- **Postgres via Docker:** `export STANDUP_SECRET_KEY=...; docker compose up --build` (needs the Docker daemon running).
