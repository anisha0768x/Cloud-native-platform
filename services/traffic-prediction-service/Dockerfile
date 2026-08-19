FROM python:3.12-slim AS builder

WORKDIR /build

# libgomp1 is required at BUILD time too since lightgbm's wheel links
# against it during its own install-time verification on some platforms;
# safer to have the full toolchain available in the builder stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY shared/libs/platform_common /build/shared/libs/platform_common
COPY services/traffic-prediction-service/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

# libgomp1 is also required at RUNTIME — LightGBM's compiled core uses
# OpenMP for multi-threaded training/inference, and this shared library
# isn't part of python:3.12-slim by default.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /install /usr/local

WORKDIR /app
COPY services/traffic-prediction-service/app ./app
COPY services/traffic-prediction-service/alembic ./alembic
COPY services/traffic-prediction-service/alembic.ini .

RUN chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8006

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
