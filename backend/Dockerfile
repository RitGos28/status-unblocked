# Multi-stage: wheels are built once, the runtime image carries no toolchain.
FROM python:3.13-slim AS builder

WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --upgrade pip setuptools wheel \
 && pip wheel --wheel-dir /wheels ".[postgres]"


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    STANDUP_LOG_JSON=true

# Runs as a non-root user: a container that only serves HTTP has no business
# owning its own filesystem.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels "status-unblocked[postgres]" \
 && rm -rf /wheels

# Migrations and the alembic config are not part of the wheel, but a release
# needs them to run "alembic upgrade head" before serving.
COPY alembic.ini ./
COPY src/standup/migrations ./src/standup/migrations
COPY scripts/ ./scripts/

RUN mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser

ENV STANDUP_DATABASE_URL=sqlite:////data/standup.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status==200 else 1)"

CMD ["uvicorn", "standup.main:app", "--host", "0.0.0.0", "--port", "8000"]
