# Status Unblocked — Backend Service

Python 3.13 FastAPI backend powering Status Unblocked.

## Architecture

- **FastAPI**: REST API + Server-side fallback endpoints, OpenAPI schemas, async background tasks.
- **SQLAlchemy 2.0 & Alembic**: SQLite for development and PostgreSQL 16 for production with migrations.
- **Extractive Summarizer**: Faithful rule-based extraction ensuring claims are verbatim source spans.
- **Audit Logging**: Cryptographically hash-chained audit log guaranteeing non-repudiation.
- **Microsoft 365 Agents SDK**: Optional Teams bot connector (`POST /api/messages`).

## Running Locally

```bash
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export STANDUP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
alembic upgrade head
python -m scripts.seed_demo --days 2
uvicorn standup.main:app --reload
```

## Running Tests

```bash
pytest                                    # full test suite (266 tests)
pytest --cov=standup --cov-report=term-missing
ruff check .
mypy src
lint-imports
backend/scripts/demo_check.sh
```
