# --- Builder stage: install deps into an isolated location ---
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed only to BUILD python packages (e.g. asyncpg's C extension),
# not needed at runtime — kept out of the final image entirely.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the shared library first so it's installable, then this service's
# requirements — this ordering also means Docker's layer cache is only
# invalidated when platform_common's own source actually changes.
COPY shared/libs/platform_common /build/shared/libs/platform_common
COPY services/auth-service/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Runtime stage: slim image, no compilers, non-root user ---
FROM python:3.12-slim

# libpq5 (not libpq-dev) — the runtime shared lib asyncpg needs, without
# the full dev headers/compiler toolchain the builder stage required.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /install /usr/local

WORKDIR /app
COPY services/auth-service/app ./app
COPY services/auth-service/alembic ./alembic
COPY services/auth-service/alembic.ini .

RUN chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8001

# Matches the readiness dependency check registered in main.py (DB
# connectivity) — Kubernetes uses the same endpoint via its own probe
# config (see infra/k8s manifests, added in a later module), this
# HEALTHCHECK is for plain `docker run` / docker-compose parity.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
