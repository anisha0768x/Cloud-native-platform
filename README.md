# Cloud-Native Intelligent Microservices Management Platform

An AIOps-style observability platform (comparable in scope to Datadog / New
Relic / Dynatrace) covering microservices, Kubernetes, Docker monitoring,
traffic + failure prediction, GenAI log analysis, and auto-scaling
recommendations.

Full architecture: see `docs/01-SYSTEM-ARCHITECTURE.md`.

**New here? Start with [`RUN-GUIDE.md`](./RUN-GUIDE.md)** — a complete,
step-by-step setup guide (what to install, how to run the whole stack,
troubleshooting) written for someone opening this project for the first
time. This README's per-service sections below assume you've already
got the basics running and want a specific service's details.

## Build Status

| Module | Status |
|---|---|
| 1. Shared Foundation (`platform_common` + local infra) | ✅ Done |
| 2. Authentication Service | ✅ Done |
| 3. API Gateway | ✅ Done |
| 4. Monitoring Service (service registry, heartbeats, alerts) | ✅ Done |
| 5. Metrics Service (TimescaleDB, Kafka ingestion) | ✅ Done |
| 6. Kubernetes Management Service (pluggable cluster provider) | ✅ Done |
| 7. Dashboard Service (BFF — Executive/Infrastructure/Kubernetes dashboards) | ✅ Done |
| 8. Traffic Prediction Service (LightGBM, quantile confidence intervals) | ✅ Done |
| 9. Predictive Maintenance Service (XGBoost, root-cause attribution) | ✅ Done |
| 10. GenAI Log Analysis Service (RAG + Claude, rule-based fallback) | ✅ Done |
| 11. Notification Service (webhook/Slack/email, escalation) | ✅ Done |
| 12. Cloud Storage Service (S3/MinIO) | ✅ Done — **all 12 backend services complete** |
| 13. Frontend (React + TS + Tailwind, 3 dashboards) | ✅ Done |
| 14. CI/CD, K8s manifests, Terraform | ✅ Done — **project complete** |

## Repository Layout

```
services/           One folder per microservice (added as each is built)
shared/libs/        platform_common — shared config/logging/db/security/events
shared/event-schemas/  Kafka event contract definitions
frontend/           React + TypeScript dashboards (added later)
infra/docker-compose.yml   Local dev infrastructure
infra/k8s/          Kubernetes manifests (kustomize base + overlays)
infra/terraform/    Cloud infrastructure as code
docs/               Architecture documentation
```

## Local Development Setup

**Prerequisites:** Docker + Docker Compose, Python 3.11+, Node 20+ (once frontend exists).

```bash
# 1. Start shared infrastructure (Postgres/Timescale, Redis, Kafka, OpenSearch, MinIO)
make infra-up

# 2. Install the shared library
make install-common

# 3. Verify it works
make test-common
```

Once running:
- Postgres/TimescaleDB: `localhost:5432` (user: `platform`, db: `platform`)
- Redis: `localhost:6379`
- Kafka: `localhost:9092` (UI at `localhost:8085`)
- OpenSearch: `localhost:9200`
- MinIO (S3-compatible): `localhost:9000` (console: `localhost:9001`)

Each service, once built, will have its own section here with its specific
run instructions.

## Auth Service — Run Instructions

**Local (no Docker), against the shared infra:**
```bash
cd services/auth-service
pip install -r requirements-dev.txt
python scripts/generate_keys.py          # writes keys/private_key.pem, keys/public_key.pem
# create .env from .env.example, pasting the two key files' contents in
# (or set JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH to the generated files instead)

alembic upgrade head                      # creates users/roles/permissions/refresh_tokens tables
PYTHONPATH=. python scripts/seed_rbac.py  # seeds viewer/operator/admin roles

uvicorn app.main:app --reload --port 8001
# Swagger UI: http://localhost:8001/docs
```

**Via Docker (from repo root):**
```bash
python services/auth-service/scripts/generate_keys.py   # populates services/auth-service/keys/
make infra-up
docker compose -f infra/docker-compose.yml -f services/auth-service/docker-compose.yml up -d --build
```

**Tests** (spins nothing up itself — point it at a real Postgres, e.g. a
`auth_service_test` database with migrations applied):
```bash
cd services/auth-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`,
`POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`,
`GET /health`, `GET /ready`.

## API Gateway — Run Instructions

**Local (no Docker):**
```bash
cd services/api-gateway
pip install -r requirements-dev.txt
# create .env from .env.example — point JWT_PUBLIC_KEY_PATH at
# ../auth-service/keys/public_key.pem (generated when you ran Auth Service's setup)

uvicorn app.main:app --reload --port 8000
```

Then talk to Auth Service *through* the gateway instead of directly:
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"Str0ngPass"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"Str0ngPass"}'

# GET /api/v1/auth/me without a token → 401, rejected AT THE GATEWAY,
# auth-service never sees the request.
curl http://localhost:8000/api/v1/auth/me
```

**Via Docker (from repo root, all three services):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests** (spins up Redis + a real mock backend server internally — needs
a real Redis reachable at `redis://localhost:6379/1`):
```bash
cd services/api-gateway
PYTHONPATH=. python -m pytest tests/ -v
```

What it does: routes by path prefix (see `app/core/config.py`'s
`route_table` — add one line per new service as later modules are built),
rejects invalid/missing/expired JWTs before they reach a backend, rate
limits per authenticated user (or per IP for anonymous calls), generates/
propagates an `X-Trace-Id` for cross-service log correlation, and returns
a proper `503` (not a hang) when a backend is unreachable.

## Monitoring Service — Run Instructions

**Local (no Docker):**
```bash
cd services/monitoring-service
pip install -r requirements-dev.txt
# create .env from .env.example — JWT_PUBLIC_KEY_PATH should point at
# ../auth-service/keys/public_key.pem (same key Auth Service generated)

alembic upgrade head    # creates services / health_check_records / alerts tables

uvicorn app.main:app --reload --port 8002
```

**Via Docker (from repo root, all four services):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests:**
```bash
cd services/monitoring-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints (all behind the gateway once wired: `/api/v1/services/*`,
`/api/v1/alerts/*`):
- `POST /api/v1/services` (needs `service:create`) — register a service
- `GET /api/v1/services` / `GET /api/v1/services/{id}` (needs `service:read`)
- `DELETE /api/v1/services/{id}` (needs `service:delete`)
- `POST /api/v1/services/{id}/heartbeat` (needs `service:update`) — report
  health; 3 consecutive failures marks the service `down` and auto-creates
  a `CRITICAL` alert (deduplicated — won't spam on further failures)
- `GET /api/v1/services/{id}/health-summary` — uptime % over recent checks
- `GET /api/v1/alerts` (needs `alert:read`), filterable by `service_id`,
  `status`, `severity`
- `POST /api/v1/alerts/{id}/acknowledge` / `.../resolve` (needs `alert:acknowledge`)

## Metrics Service — Run Instructions

**Local (no Docker):**
```bash
cd services/metrics-service
pip install -r requirements-dev.txt
# create .env from .env.example — set ENABLE_KAFKA_CONSUMER=false if you
# don't have a local Kafka running and just want the REST ingestion path

alembic upgrade head    # creates the metrics table (hypertable IF the
                         # timescaledb extension is available; a plain,
                         # well-indexed table otherwise — see the migration)

uvicorn app.main:app --reload --port 8003
```

**Via Docker (from repo root, all five services — this is the first
compose stack where Kafka + the TimescaleDB image actually matter):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests:**
```bash
cd services/metrics-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints (behind the gateway at `/api/v1/metrics/*`):
- `POST /api/v1/metrics/ingest` (needs `metrics:write`) — REST fallback;
  the PRIMARY path is publishing to the `metrics.raw` Kafka topic, which
  the service's background consumer ingests automatically
- `GET /api/v1/metrics/query` (needs `metrics:read`) — time-bucketed
  aggregation: `?service_id=&metric_name=&start=&end=&aggregation=avg|min|max|sum|count|p95|p99&interval_seconds=60`
- `GET /api/v1/metrics/latest` (needs `metrics:read`) — most recent data point

Publishing to Kafka directly (what a real agent/sidecar would do, instead
of the REST fallback) — example using `platform_common`'s `EventProducer`:
```python
producer = EventProducer(bootstrap_servers="localhost:9092", service_name="checkout-api")
await producer.start()
await producer.publish(
    topic="metrics.raw",
    event_type="metric.recorded",
    payload={"service_id": "...", "metric_name": "cpu_usage", "value": 55.2},
)
```

## Kubernetes Management Service — Run Instructions

**Local (no Docker, no real cluster needed):**
```bash
cd services/k8s-management-service
pip install -r requirements-dev.txt
# create .env from .env.example — CLUSTER_MODE=demo works out of the box

alembic upgrade head    # creates scaling_history / cluster_snapshots tables

uvicorn app.main:app --reload --port 8004
```

**To point it at a REAL Kubernetes cluster instead of demo data:**
set `CLUSTER_MODE=kubernetes` and either run this service *inside* the
cluster (it auto-detects its ServiceAccount) or mount a working
`~/.kube/config` when running locally against a cluster like minikube/kind.

**Via Docker (from repo root, all five services):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests:**
```bash
cd services/k8s-management-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints (behind the gateway at `/api/v1/k8s/*`):
- `GET /api/v1/k8s/nodes` / `pods` / `deployments` (needs `service:read`)
  — `pods`/`deployments` accept `?namespace=`
- `POST /api/v1/k8s/deployments/{namespace}/{name}/scale` (needs
  `scaling:trigger`) — `{"replicas": N}`, records an audit entry in
  `scaling_history` with the accurate pre-scale replica count
- `GET /api/v1/k8s/scaling-history` — filterable by `namespace`,
  `deployment_name`
- `GET /api/v1/k8s/snapshots?start=&end=` — periodic point-in-time
  cluster counts (node/pod/deployment totals), captured every
  `SNAPSHOT_INTERVAL_SECONDS` by a background worker

Architecture note: this service talks to the cluster through a
`ClusterProvider` interface (`app/providers/`) with two implementations —
`DemoClusterProvider` (default, synthetic-but-consistent data, no cluster
needed) and `KubernetesClusterProvider` (real, via the official
`kubernetes` client). Every endpoint and the snapshot worker are written
against the interface, so switching `CLUSTER_MODE` is the only change
needed to go from demo to a real cluster.

## Dashboard Service — Run Instructions

**Local (no Docker; needs Monitoring + K8s Management Service reachable):**
```bash
cd services/dashboard-service
pip install -r requirements-dev.txt
# create .env from .env.example

uvicorn app.main:app --reload --port 8005
```

**Via Docker (from repo root, all six services):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/dashboard-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests** (spins up real mock Monitoring/K8s backend servers + needs real
Redis reachable at `redis://localhost:6379/2`):
```bash
cd services/dashboard-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints (needs `dashboard:read`): `GET /api/v1/dashboards/executive`,
`GET /api/v1/dashboards/infrastructure`, `GET /api/v1/dashboards/kubernetes`.

Each aggregates 3-5 backend calls (Monitoring + K8s Management) concurrently,
caches the result in Redis for `CACHE_TTL_SECONDS` (default 15s), and
degrades gracefully — if one backend call fails, the response still
returns `200` with whatever data succeeded, plus a `partial_errors` list
naming what didn't.

**Scope note:** 5 dashboards from the original architecture doc (Traffic,
AI, Security, Cloud Cost, Logs) aren't implemented yet — they depend on
services not yet built (Traffic Prediction, Predictive Maintenance,
GenAI, Notification, Cloud Storage). Each gets added to this service as
its backing service is built in a later module.






## Traffic Prediction Service — Run Instructions

**Local (no Docker):**
```bash
cd services/traffic-prediction-service
pip install -r requirements-dev.txt
# create .env from .env.example

alembic upgrade head   # creates the predictions table

uvicorn app.main:app --reload --port 8006
```

**Via Docker (from repo root, all seven services):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/dashboard-service/docker-compose.yml \
  -f services/traffic-prediction-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests** (spins up a real mock Metrics Service backend + real Postgres;
also directly exercises the LightGBM model, not just the API):
```bash
cd services/traffic-prediction-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints (needs `metrics:read`):
- `GET /api/v1/predictions/traffic/{service_id}?horizon_hours=1` — forecast
  expected requests for `horizon_hours` from now (1-168), with a 10th/90th
  percentile confidence interval and a scaling recommendation
  (`ceil(expected_requests / REQUESTS_PER_POD_CAPACITY)`)
- `GET /api/v1/predictions/traffic/{service_id}/history` — every past
  forecast served for that service, for future accuracy-tracking

**How it actually works:** on first request for a service, it fetches
historical `request_count` data from Metrics Service; if there are fewer
than `MIN_TRAINING_POINTS` real data points (a fresh deployment has none),
it trains on a realistic **synthetic** traffic series instead — and every
response honestly reports which (`data_source: "historical"` |
`"synthetic"`) was used. The trained model (3 LightGBM quantile
regressors — 10th/50th/90th percentile) is cached in-memory per service
for `MODEL_CACHE_TTL_SECONDS` before retraining. Verified in tests that
the model actually learned the seasonal pattern (predicts higher traffic
at 1pm than 3am on the same synthetic series) rather than just running
without error.

## Predictive Maintenance Service — Run Instructions

**Local (no Docker):**
```bash
cd services/predictive-maintenance-service
pip install -r requirements-dev.txt
# create .env from .env.example

alembic upgrade head   # creates the maintenance_predictions table

uvicorn app.main:app --reload --port 8007
```

**Via Docker (from repo root, all eight services):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/dashboard-service/docker-compose.yml \
  -f services/traffic-prediction-service/docker-compose.yml \
  -f services/predictive-maintenance-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests** (spins up real mock Metrics + K8s Management backends, real
Postgres; also directly exercises the XGBoost model):
```bash
cd services/predictive-maintenance-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints (needs `metrics:read`):
- `GET /api/v1/predictions/maintenance/{service_id}?service_name=X` —
  failure-risk prediction: probability, root cause, recommendation
- `GET /api/v1/predictions/maintenance/{service_id}/history`

**Honest design note (more important here than in most modules):** unlike
Traffic Prediction Service, this classifier's TRAINING data is always
synthetic — there's no real failure history anywhere in this platform to
learn from, and there structurally can't be until real incidents happen.
The synthetic dataset is deliberately structured (high+rising CPU, memory
near capacity, and climbing restart counts correlate with the failure
label) rather than random noise, and tests verify the trained model
actually learned that structure (e.g. predicts monotonically higher risk
as CPU rises, and correctly attributes root cause to whichever input
deviates most from a learned healthy baseline). What IS real: the feature
values run through the model at inference time — live CPU/memory trends
from Metrics Service and actual pod restart counts from K8s Management
Service.

## GenAI Log Analysis Service — Run Instructions

**Local (no Docker, no OpenSearch required):**
```bash
cd services/genai-log-analysis-service
pip install -r requirements-dev.txt
# create .env from .env.example — leave ANTHROPIC_API_KEY blank to run
# in fallback-only mode (fully supported and tested), or set a real key

alembic upgrade head   # creates the log_analyses table

uvicorn app.main:app --reload --port 8008
```

**Via Docker (from repo root, all nine services):**
```bash
export ANTHROPIC_API_KEY=sk-ant-...   # optional — omit to run fallback-only
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/dashboard-service/docker-compose.yml \
  -f services/traffic-prediction-service/docker-compose.yml \
  -f services/predictive-maintenance-service/docker-compose.yml \
  -f services/genai-log-analysis-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests** (spins up real mock Anthropic + Metrics backends, real Postgres,
real Redis — no OpenSearch needed since tests run against `InMemoryLogStore`):
```bash
cd services/genai-log-analysis-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints:
- `POST /api/v1/logs/ingest` (needs `logs:write`) — fallback log ingestion
  (Kafka topic `logs.raw` is the primary path, mirrors Metrics Service)
- `GET /api/v1/logs/search?service_id=&level=&query=&start=&end=` (needs `logs:read`)
- `GET /api/v1/genai/analyze/{service_id}` (needs `logs:read`) — the RAG
  analysis: root cause, human explanation, suggested fix
- `GET /api/v1/genai/history/{service_id}`

**Two honest environment limitations, both handled the same way this
platform has handled similar gaps before (Kafka in Module 5, a real K8s
cluster in Module 6):**
1. **No Anthropic API key is configured in this sandbox.** The real LLM
   call path (`api.anthropic.com`) is genuine working code — every
   failure mode (timeout, malformed response, HTTP error, missing key)
   is tested and correctly falls back to a rule-based summary, so the
   dashboard never shows a blank AI panel. What isn't tested here is a
   real Claude response, since no key is available in this environment.
2. **OpenSearch isn't installable in this sandbox** (JVM-based, not on
   the allowed package mirrors). A `LogStore` interface (same pattern as
   Module 6's `ClusterProvider`) has a real `OpenSearchLogStore`
   (matches `infra/docker-compose.yml`'s OpenSearch container, correct
   but untested live here) and an `InMemoryLogStore` (the default —
   what the test suite and local dev actually run against).

## Notification Service — Run Instructions

**Local (no Docker, no channels needed to start):**
```bash
cd services/notification-service
pip install -r requirements-dev.txt
# create .env from .env.example — leave WEBHOOK_URL/SLACK_WEBHOOK_URL/SMTP_HOST
# blank to run with zero channels (notifications still record, 0 delivery attempts)

alembic upgrade head   # creates notifications / delivery_attempts tables

uvicorn app.main:app --reload --port 8009
```

**Via Docker (from repo root, all ten services):**
```bash
export NOTIFICATION_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...   # optional
export NOTIFICATION_SMTP_HOST=smtp.example.com                              # optional
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/dashboard-service/docker-compose.yml \
  -f services/traffic-prediction-service/docker-compose.yml \
  -f services/predictive-maintenance-service/docker-compose.yml \
  -f services/genai-log-analysis-service/docker-compose.yml \
  -f services/notification-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests** (real infrastructure throughout — a real local SMTP server via
`aiosmtpd` receives actual emails, real mock HTTP servers receive actual
webhook/Slack payloads, real Postgres):
```bash
cd services/notification-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints:
- `POST /api/v1/notifications` (needs `notifications:send`) — dispatches
  to every configured channel concurrently; partial failures (e.g.
  webhook down, Slack/email fine) still return `201` with per-channel
  results, not an overall failure
- `POST /api/v1/notifications/{id}/acknowledge` (needs `alert:acknowledge`)
- `GET /api/v1/notifications?service_id=&status=` (needs `alert:read`)

**Escalation:** a background worker re-sends any notification still
`pending` (unacknowledged) after `ESCALATION_WINDOW_MINUTES` through the
same channels, marked `[ESCALATED]`, then flips its status so it isn't
re-escalated every poll cycle. Acknowledged notifications are never
escalated — verified directly against the repository logic in tests
(escalation worker's LOOP is trivial; its LOGIC — find-overdue,
re-dispatch, mark-escalated — is what's actually tested).

**Scope note:** routing WHICH alerts trigger a notification (e.g. wiring
Monitoring Service's alert-creation directly to this service) isn't
built yet — this service's `POST /notifications` is currently
manually/externally triggered. A real deployment would have Monitoring
Service publish an alert-created event to Kafka for this service to
consume, the same pattern Metrics Service and GenAI Log Analysis Service
already use for their primary ingestion path; wiring that up is a
natural next increment now that both sides of that event flow exist.

## Cloud Storage Service — Run Instructions

**Local (no Docker) — needs MinIO running:**
```bash
make infra-up   # provisions MinIO among the shared infra

cd services/cloud-storage-service
pip install -r requirements-dev.txt
# create .env from .env.example

uvicorn app.main:app --reload --port 8010
```

**Via Docker (from repo root — the full, final stack, all 12 backend services):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/dashboard-service/docker-compose.yml \
  -f services/traffic-prediction-service/docker-compose.yml \
  -f services/predictive-maintenance-service/docker-compose.yml \
  -f services/genai-log-analysis-service/docker-compose.yml \
  -f services/notification-service/docker-compose.yml \
  -f services/cloud-storage-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  up -d --build
```

**Tests** (real S3 API surface via `moto`'s mock — genuine `boto3` calls
against a real-behaving S3 implementation, not mocked internals; no MinIO
needed to run tests):
```bash
cd services/cloud-storage-service
PYTHONPATH=. python -m pytest tests/ -v
```

Endpoints:
- `PUT /api/v1/storage/objects/{key}` (needs `storage:write`) — multipart
  file upload; rejects path-traversal keys and oversized files
- `GET /api/v1/storage/objects/{key}` (needs `storage:read`) — raw download
- `DELETE /api/v1/storage/objects/{key}` (needs `storage:write`)
- `GET /api/v1/storage/objects?prefix=&limit=` (needs `storage:read`)
- `GET /api/v1/storage/objects/{key}/presigned-url` (needs `storage:read`)
  — temporary signed download link, no auth needed to use the link itself

**Architecture note:** unlike most modules, there's only ONE
`StorageProvider` implementation (`S3StorageProvider`), not a real/demo
split — object storage's API surface (put/get/delete/list) is
essentially identical across AWS S3, MinIO, and GCS's S3-compatibility
mode, so `S3_ENDPOINT_URL` is the only thing that changes between MinIO
(local dev) and real AWS S3 (production); no second implementation adds
anything a config value doesn't already cover.

**A real bug this test suite caught:** the initial route ordering had
`GET /objects/{key:path}` (generic download) registered before
`GET /objects/{key:path}/presigned-url` — since `{key:path}` matches
greedily, every presigned-url request was being swallowed by the download
route (returning 404 for a nonexistent key named `.../presigned-url`
instead of hitting the intended handler). Fixed by registering the more
specific route first; caught immediately by
`test_presigned_url_endpoint`, not discovered later via a confused user
report.

---

**With this module, all 12 backend services from the master architecture
document are complete: 177 tests passing across the platform.** What's
left is the frontend (Module 13 — the 3 dashboards Dashboard Service
already serves data for) and CI/CD + Kubernetes manifests (Module 14).

## Frontend — Run Instructions

**Local dev (hot reload) — needs the API Gateway + backend services running:**
```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000

npm run dev             # http://localhost:5173
```

**Verify without a browser** (what was actually run to confirm this
module works, since this environment has no browser):
```bash
cd frontend
npm run lint       # oxlint — 0 warnings, 0 errors
npx tsc --noEmit    # strict type-check — 0 errors
npm run build       # real production build via Vite
npm run preview     # serves the actual dist/ output; verified via curl
                     # that index.html, the JS bundle, and CSS all return 200
```

**Via Docker (from repo root — the complete stack, all 12 backend
services plus this):**
```bash
make infra-up
docker compose \
  -f infra/docker-compose.yml \
  -f services/auth-service/docker-compose.yml \
  -f services/monitoring-service/docker-compose.yml \
  -f services/metrics-service/docker-compose.yml \
  -f services/k8s-management-service/docker-compose.yml \
  -f services/dashboard-service/docker-compose.yml \
  -f services/traffic-prediction-service/docker-compose.yml \
  -f services/predictive-maintenance-service/docker-compose.yml \
  -f services/genai-log-analysis-service/docker-compose.yml \
  -f services/notification-service/docker-compose.yml \
  -f services/cloud-storage-service/docker-compose.yml \
  -f services/api-gateway/docker-compose.yml \
  -f frontend/docker-compose.yml \
  up -d --build
# http://localhost:3000
```

### What's built

3 dashboards, each consuming Dashboard Service (Module 7) directly:
**Executive** (health %, open alerts, cluster summary), **Infrastructure**
(nodes, service health table, 24h cluster trend chart), **Kubernetes**
(deployments, pods, recent scaling actions). Plus a real login flow
against Auth Service (Module 2) with automatic token refresh — the HTTP
client coalesces concurrent 401s into a single refresh call rather than
racing multiple refresh-token rotations (Module 2 rotates on every use,
so a naive per-request retry would invalidate its own new token).

**Design:** dark "command console" theme — deliberately not the generic
AI-dashboard look (see `src/index.css` for the full token rationale):
near-black surfaces, a teal accent (not the common terracotta/vermilion
default), JetBrains Mono for all numeric data to visually separate "live
values" from labels, and a single deliberate motion element (a live pulse
indicator in the top bar) rather than animation scattered throughout.

**Real-time model:** polling, not WebSockets — `refetchInterval` is set
to match Dashboard Service's own 15s cache TTL exactly (Module 7), so the
frontend never polls faster than the backend's cache actually refreshes.

**Graceful degradation carried through to the UI:** Dashboard Service's
`partial_errors` field (Module 7) renders as an inline notice rather than
either being ignored or blocking the whole page — matching the backend's
own "partial data beats no data" design all the way to the screen.

### Honest limitations

- **Only 3 of the architecture doc's 10 dashboards** — the same scope
  boundary as Module 7, since the other 7 need dashboard-aggregation
  endpoints that don't exist yet.
- **No browser was available to visually verify this** in the sandbox
  that built it — correctness was verified via a real type-check, a real
  lint pass (which caught one genuine bug — see below), a real production
  build, and serving that real build's output via `curl` to confirm the
  HTML/JS/CSS all load. Visual QA in an actual browser is still worth
  doing before treating this as done-done.
- **Bundle size**: `oxlint`'s build output warns the main JS bundle is
  ~680KB — route-based code-splitting (dynamic `import()` per dashboard
  page) would address this; not done here since it's a performance
  polish item, not a correctness one.

**A real bug the linter caught:** `ProtectedRoute` originally called
`useAuthStore((s) => s.accessToken) && useAuthStore((s) => s.user)` —
the `&&` short-circuits, so the second hook call was conditionally
skipped, violating React's Rules of Hooks (hook call order must be
identical on every render). `npm run lint` caught it immediately; fixed
by calling both hooks unconditionally and combining the results after.

## Module 14 — CI/CD, Kubernetes Manifests, Terraform

### Kubernetes manifests

`infra/k8s/services.yaml` is the single source of truth — a registry of
every service's port, replica count, resource limits, and dependencies
(DB/Redis/Kafka). `infra/k8s/generate_manifests.py` reads it and generates
Deployment/Service/ConfigMap/HPA/Kustomization YAML for all 12 backend
services + frontend, plus the `dev`/`staging`/`prod` overlay
kustomizations. Regenerate after any registry change:

```bash
python3 infra/k8s/generate_manifests.py
```

CI enforces this stays in sync — `.github/workflows/ci.yml`'s
`k8s-manifests` job regenerates and fails the build if the committed
output differs (the same "generated code must match its generator"
check as Alembic migrations being reviewed alongside model changes).

**Two real design bugs caught and fixed while building this, both worth
naming since they're genuine Kubernetes/Terraform gotchas, not typos:**

1. **`$(VAR)` substitution doesn't work for `envFrom`-sourced values.**
   The first draft put `DATABASE_URL: "...$(DB_PASSWORD)@..."` in a
   ConfigMap, assuming Kubernetes would interpolate the password from the
   paired Secret. It doesn't — `$(VAR)` expansion only applies to a
   container's explicit `env:` list, not values arriving via
   `envFrom.configMapRef`/`secretRef` ([kubernetes/kubernetes#69113](https://github.com/kubernetes/kubernetes/issues/69113)).
   Fixed by moving `DATABASE_URL` into an explicit `env:` entry, which
   *can* reference the `envFrom`-sourced `DB_PASSWORD`.
2. **A kustomize `namespace:` transformer would have collapsed 6
   deliberately-separate namespaces into one.** The dev overlay's first
   draft set `namespace: dev` to scope resources per-environment — but
   that transformer overrides *every* resource's namespace, which would
   have destroyed the `auth`/`monitoring`/`data`/`ai`/`platform`/`frontend`
   split `base/namespaces.yaml` defines. Removed; overlays assume
   dev/staging/prod are separate clusters instead (each keeping the same
   6-namespace structure), which is what actually lets that split survive
   across environments.
3. (Caught before writing any file, not after) **Ingress backends must be
   in the same namespace as the Ingress resource** — a single Ingress
   trying to route to both `api-gateway` (namespace `platform`) and
   `frontend` (namespace `frontend`) simply doesn't work. Fixed with two
   Ingress objects for the same host; NGINX merges path rules across them.

**Validation actually performed** (no `kubectl`/`kustomize` binary
available in the sandbox that built this — documented honestly, not
glossed over): every generated file parsed with `yaml.safe_load` (64
valid documents) and passed `yamllint` with zero issues. This catches
structural/syntax errors, not semantic ones a real `kubectl apply
--dry-run=server` or `kustomize build` would catch (e.g. a typo'd field
name that's still valid YAML) — worth running both before a real deploy.

### Terraform

`infra/terraform/` provisions AWS infrastructure: VPC (public/private
subnets across 3 AZs, one NAT gateway per AZ — not a shared single point
of failure), EKS (cluster + managed node group + IRSA OIDC provider), RDS
Postgres (one instance hosting all services' separate databases, mirroring
`infra/postgres-init/`'s local-dev pattern), ElastiCache Redis, MSK
Kafka, S3 (with lifecycle rules matching the architecture doc's log
hot/warm/archive tiers), and IAM roles for IRSA (K8s Management Service's
real-cluster access, Cloud Storage Service's scoped S3 access — Module
6/12's `CLUSTER_MODE=kubernetes`/real-S3 paths' production auth story).

**No `terraform` binary is reachable from this sandbox**
(`releases.hashicorp.com` isn't in the allowed egress list). Validated
instead with `terraform-config-inspect` (the same HCL-parsing library
Terraform itself uses for config loading) across the root module and all
7 submodules — confirms every file is syntactically valid HCL and every
module's variables/outputs/resources parse correctly, which is a real,
meaningful check, just not as strong as `terraform validate` or `plan`
would be. Run those before a real `apply`.

### CI/CD

Three GitHub Actions workflows:
- **`ci.yml`** — matrix over all 11 testable backend services (shared
  lib tested first, as a prerequisite job) against real Postgres/Redis
  service containers, plus frontend lint/typecheck/build, plus the
  generated-manifests-are-in-sync check.
- **`build-and-push.yml`** — builds and pushes every service's Docker
  image to GHCR on merge to `main`, tagged with the git SHA (traceability
  from a running image back to the exact commit).
- **`deploy.yml`** — staging deploys automatically after a successful
  build; production requires a GitHub Environment approval gate (a real
  reviewer must approve in the Actions UI before the `deploy-production`
  job runs) — matching the architecture doc's §12 CI/CD design exactly.

---

**This completes all 14 modules of the Cloud-Native Intelligent
Microservices Management Platform**: 12 independently-deployable backend
services (177 passing tests), a shared library, an API gateway, a React
frontend, Kubernetes manifests for the whole stack, Terraform for the
underlying AWS infrastructure, and a 3-workflow CI/CD pipeline with a
production approval gate — built module by module, each one tested
against real infrastructure wherever this sandbox environment allowed it,
with every honest limitation (no live Kafka broker, no real K8s cluster,
no Anthropic API key, no `terraform`/`kubectl` binaries) documented
rather than glossed over, and a graceful fallback built for each one.
#   c l o u d - n a t i v e - p l a t f o r m  
 #   C l o u d - n a t i v e - p l a t f o r m  
 