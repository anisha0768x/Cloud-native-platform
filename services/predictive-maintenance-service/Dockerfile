FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY shared/libs/platform_common /build/shared/libs/platform_common
COPY services/predictive-maintenance-service/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

# libgomp1 required at runtime — XGBoost's compiled core uses OpenMP,
# same reasoning as Traffic Prediction Service's Dockerfile (LightGBM).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /install /usr/local

WORKDIR /app
COPY services/predictive-maintenance-service/app ./app
COPY services/predictive-maintenance-service/alembic ./alembic
COPY services/predictive-maintenance-service/alembic.ini .

RUN chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8007

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
