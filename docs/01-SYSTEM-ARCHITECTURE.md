# Cloud-Native Intelligent Microservices Management Platform
## Master Architecture Document — v1.0

**Positioning:** An internal Datadog/New Relic/Dynatrace-class observability + AIOps platform. Not a CRUD app — this is a real-time telemetry ingestion, analytics, prediction, and control-plane system.

---

## 1. Architectural Philosophy (Read First)

Three decisions drive everything else. I'll justify each because they cascade into every service, table, and API below.

**1.1 — Event-driven core, REST edge.**
Monitoring platforms are fundamentally *write-heavy, high-cardinality, time-series* systems on the ingestion side, and *read-heavy, aggregation-heavy* on the query side. If every metric/log write went through synchronous REST → DB, we'd bottleneck at the DB and couple ingestion uptime to every consumer's uptime. So: telemetry producers publish to a message broker (Kafka), and REST is reserved for control-plane operations (CRUD on services, users, config) and dashboard queries. This is the same pattern Datadog, Prometheus remote-write, and CloudWatch use internally.

**1.2 — Polyglot persistence, not one database for everything.**
A relational DB is wrong for time-series metrics (write amplification, index bloat) and wrong for logs (unstructured, high volume, short retention). Using Postgres for *everything* would work at demo scale and fall over at "industry-grade" scale — and since this project's stated goal is to demonstrate real cloud-computing concepts, using the wrong DB for the job would undermine the credibility of the whole design. So:
- **PostgreSQL (Cloud SQL)** — relational/control-plane data: users, roles, services, deployments, alerts, config, audit logs.
- **TimescaleDB (Postgres extension)** — metrics time-series (keeps SQL ergonomics, gets time-series performance — better fit than standing up a second DB engine like InfluxDB for a project already running Postgres).
- **Elasticsearch/OpenSearch** — logs (full-text search, GenAI log analysis needs fast semantic + keyword search over unstructured text).
- **Redis** — cache, rate limiting, pub/sub for real-time dashboard pushes, short-lived session/JWT blacklist.
- **Object Storage (S3/Cloud Storage)** — raw log archives, ML model artifacts, exported reports.

**1.3 — Kubernetes-native from day one, not "dockerized later."**
Because K8s concepts (HPA, ConfigMaps, Services) are graded/demonstrated deliverables, the platform's *own* deployment must exercise them for real — this doubles as the "Infrastructure Dashboard" data source (the platform monitors itself, like Datadog dogfoods Datadog).

---

## 2. High-Level Architecture (HLD)

```
                                   ┌────────────────────────┐
                                   │   React + TS Frontend   │
                                   │  (10 dashboards, WS)    │
                                   └───────────┬─────────────┘
                                               │ HTTPS/WSS
                                   ┌───────────▼─────────────┐
                                   │   API Gateway (Kong/     │
                                   │   Nginx Ingress + custom)│
                                   │  AuthN check, rate-limit,│
                                   │  routing, LB             │
                                   └───────────┬─────────────┘
        ┌───────────────┬───────────────┬──────┴───────┬───────────────┬───────────────┐
        ▼               ▼               ▼               ▼               ▼               ▼
 ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ ┌────────────┐  ┌────────────┐
 │   Auth     │  │ Dashboard  │  │ Monitoring │  │  Metrics   │ │ K8s Mgmt   │  │Notification│
 │  Service   │  │  Service   │  │  Service   │  │  Service   │ │  Service   │  │  Service   │
 └────────────┘  └────────────┘  └────────────┘  └────────────┘ └────────────┘  └────────────┘
                                        │                │
                                        │        ┌───────▼────────┐
                                        │        │  Kafka (event   │
                                        │        │  backbone)      │
                                        │        └───────┬────────┘
                       ┌────────────────┬──────────────┬─┴───────────────┐
                       ▼                ▼               ▼                ▼
               ┌───────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────────┐
               │Traffic Predict│ │ Predictive  │ │ GenAI Log   │ │ Cloud Storage/ │
               │   Service     │ │ Maintenance │ │  Analysis   │ │  SQL Services  │
               └───────────────┘ └─────────────┘ └─────────────┘ └───────────────┘

 Data Layer:  PostgreSQL(Cloud SQL) | TimescaleDB | OpenSearch | Redis | S3/GCS | MLflow registry
 Platform:    Kubernetes (EKS/GKE) | Prometheus+Grafana (infra self-monitoring) | GitHub Actions CI/CD
```

**Why an API Gateway instead of each service exposed directly?** Centralizes AuthN token validation, rate limiting, and TLS termination once instead of 11 times; gives us a single ingress point for the LB and a single place to enforce RBAC before a request even reaches a service (defense in depth).

**Why Kafka instead of direct service-to-service REST calls for telemetry?** Metrics/logs/events arrive at high, bursty volume from many agents. REST calls are synchronous and would let a slow downstream service (e.g., GenAI analysis) apply backpressure all the way to the metrics agent. Kafka decouples producer rate from consumer rate, gives replay for late-joining consumers (e.g., a new prediction model), and gives natural fan-out (Metrics Service, Predictive Maintenance, and GenAI can all consume the same event stream independently).

---

## 3. Microservice Inventory

| # | Service | Core Responsibility | Own DB |
|---|---|---|---|
| 1 | Authentication Service | Login, JWT issuance/refresh, RBAC, MFA | PostgreSQL (users, roles, permissions) |
| 2 | API Gateway | Routing, authN passthrough, rate limit, LB | Redis (rate-limit counters) |
| 3 | Monitoring Service | Health checks, uptime, service registry, SLA tracking | PostgreSQL |
| 4 | Metrics Service | Ingest/aggregate/query time-series metrics | TimescaleDB |
| 5 | Traffic Prediction Service | Forecast API traffic, recommend scaling | PostgreSQL + model artifacts (S3) |
| 6 | Predictive Maintenance Service | Failure probability, root cause, recs | PostgreSQL + model artifacts (S3) |
| 7 | GenAI Log Analysis Service | Summarize logs, RCA, suggested fixes | OpenSearch (read) + PostgreSQL (results) |
| 8 | Notification Service | Alert routing (email/Slack/webhook), escalation | PostgreSQL |
| 9 | Dashboard Service | Aggregation/BFF layer for all 10 dashboards | Redis (cache) — reads from others |
| 10 | Kubernetes Management Service | Cluster/pod/node state via K8s API, scaling actions | PostgreSQL (snapshot history) |
| 11 | Cloud Storage Service | Manage log archives, reports, exports | S3/GCS (no relational DB) |
| 12 | Cloud SQL Service | Config/audit-log CRUD abstraction over Postgres | PostgreSQL |

Each service owns its schema exclusively — no cross-service DB joins (a core microservices tenet: shared databases recreate a monolith with extra network hops). Cross-service data needs go through REST (for control-plane, low-frequency) or Kafka events (for high-frequency/async).

---

## 4. Per-Service Deep Design (template applied to all 12)

I'll fully detail **Metrics Service** and **GenAI Log Analysis Service** as the representative pattern (highest architectural complexity), then table the rest so this stays usable rather than repeating boilerplate 12 times.

### 4.1 Metrics Service

- **Responsibilities:** Ingest metrics (CPU, memory, latency, request count, error rate) from K8s Management Service + custom agents; write to TimescaleDB; expose aggregation queries (avg/p95/p99 over time windows); downsample old data (continuous aggregates) for retention cost control.
- **REST API:**
  - `POST /v1/metrics/ingest` (internal, agent-authenticated) — usually bypassed in favor of Kafka in production; kept for agents that can't produce to Kafka directly.
  - `GET /v1/metrics/query?service=&metric=&from=&to=&agg=` — dashboard queries.
  - `GET /v1/metrics/health`
- **Events consumed:** `metrics.raw` (Kafka topic) — high-volume ingestion path.
- **Events produced:** `metrics.threshold_breached` — consumed by Notification Service.
- **Failure handling:** Kafka consumer group with at-least-once processing + idempotent upsert (metric_id + timestamp as dedupe key) so re-processing after a crash doesn't double count. Circuit breaker on TimescaleDB writes with local buffering (bounded queue → disk spillover) if DB is briefly unavailable.
- **Security:** mTLS between internal services; agent tokens scoped read-write to `metrics.raw` topic only (no admin access).
- **Docker:** Multi-stage Python build, non-root user, `HEALTHCHECK` hitting `/health`.
- **K8s:** Deployment with 3 replicas min, HPA on CPU + custom metric (Kafka consumer lag) — the classic "scale the scaler" pattern, appropriate here since this service's own load is bursty.
- **Scaling strategy:** Horizontal — stateless consumers, TimescaleDB does the heavy lifting via hypertables/chunking.
- **Health check:** Liveness = process up; Readiness = Kafka connection + DB connection both healthy.

### 4.2 GenAI Log Analysis Service

- **Responsibilities:** Consume error/warning logs and alert events; call an LLM (Claude via Anthropic API) with retrieved context (correlated metrics + recent deploys) to produce root-cause summary and suggested fix; store results for the AI Dashboard.
- **REST API:**
  - `GET /v1/genai/summary/{alert_id}`
  - `POST /v1/genai/analyze` (on-demand re-analysis)
- **Events consumed:** `logs.error`, `alerts.triggered`.
- **Events produced:** `genai.summary_ready` → Notification Service, Dashboard Service (via WebSocket push).
- **Design detail — RAG pattern:** Before calling the LLM, the service queries OpenSearch for the last N related log lines and Metrics Service for the correlated time-window's CPU/latency, and Cloud SQL Service for "was there a deploy in the last 30 min" — this context is what makes the summary *useful* rather than a generic log paraphrase. This is the difference between a gimmick AI feature and a real AIOps capability.
- **Failure handling:** LLM call timeout (8s) → fallback to a rule-based summary ("Error rate spike correlated with deploy at 14:02") so the dashboard never shows a blank AI panel.
- **Rate/cost control:** Redis-based dedupe — identical alert fingerprints within 10 minutes reuse the cached summary instead of re-calling the LLM.
- **Security:** LLM API key stored in K8s Secret, never logged; log content is scrubbed for PII/secrets patterns (regex for tokens/keys) before leaving the cluster boundary to the LLM provider.

### 4.3 Remaining Services (summary table — same 10-attribute template applies to all)

| Service | Key APIs | Key Events | Scaling |
|---|---|---|---|
| Authentication | `/auth/login`, `/auth/refresh`, `/auth/rbac/check` | `user.login`, `user.role_changed` | Horizontal, stateless (JWT), Redis session blacklist shared |
| API Gateway | routes all `/v1/*` | n/a (synchronous) | Horizontal behind cloud LB |
| Monitoring | `/monitor/services`, `/monitor/health-summary` | `service.down`, `service.recovered` | Horizontal, low load |
| Traffic Prediction | `/predict/traffic`, `/predict/scaling-recommendation` | consumes `metrics.raw`, produces `prediction.ready` | Vertical for training jobs (batch), horizontal for inference API |
| Predictive Maintenance | `/predict/failure`, `/predict/root-cause` | consumes `metrics.raw`, produces `maintenance.risk_detected` | Same pattern as above |
| Notification | `/notify/send`, `/notify/rules` | consumes `*.triggered`/`*_ready` topics | Horizontal |
| Dashboard (BFF) | `/dashboard/{name}` aggregation endpoints | WebSocket push channel | Horizontal, Redis cache-aside |
| K8s Management | `/k8s/pods`, `/k8s/nodes`, `/k8s/scale` | produces `k8s.state_snapshot` | Horizontal, talks to K8s API via ServiceAccount RBAC |
| Cloud Storage | `/storage/upload`, `/storage/export` | consumes `logs.archive_ready` | Horizontal, stateless |
| Cloud SQL (config) | `/config/*`, `/audit/*` | produces `audit.entry_created` | Horizontal |

---

## 5. Communication Patterns

| Pattern | When Used | Example |
|---|---|---|
| Synchronous REST | Control-plane, user-triggered, needs immediate response | Login, dashboard query, manual scaling trigger |
| Async event (Kafka) | High-volume telemetry, decoupled fan-out | Metric ingestion, log streaming, alert triggers |
| WebSocket (server push) | Live dashboard updates | Real-time chart ticks, new alert banner |
| gRPC (optional, phase 2) | Internal high-frequency service-to-service | K8s Management ↔ Metrics Service polling loop |

Justification for keeping REST as default over gRPC everywhere: REST/JSON keeps the API Gateway, Swagger docs, and frontend integration simple; gRPC is reserved for the one genuinely latency-sensitive internal path, not adopted uniformly just for novelty.

---

## 6. Database Architecture

### 6.1 PostgreSQL (Cloud SQL) — Control Plane Schema (core tables)

```
users (id, email, password_hash, mfa_enabled, status, created_at)
roles (id, name, description)
permissions (id, name, resource, action)
role_permissions (role_id, permission_id)
user_roles (user_id, role_id)

services (id, name, type, namespace, owner_team, created_at)
deployments (id, service_id, version, status, deployed_at, deployed_by)
nodes (id, name, cpu_capacity, memory_capacity, status, region)
pods (id, node_id, service_id, status, restart_count, created_at)

alerts (id, service_id, severity, type, status, triggered_at, resolved_at)
notifications (id, alert_id, channel, sent_at, status)
predictions (id, service_id, type, input_snapshot JSONB, output JSONB, confidence, created_at)
scaling_history (id, service_id, action, from_replicas, to_replicas, trigger_source, created_at)

cloud_costs (id, service_id, resource_type, cost_usd, billing_period)
audit_logs (id, user_id, action, resource, before JSONB, after JSONB, created_at)
configurations (id, service_id, key, value, updated_by, updated_at)
```

**Normalization:** 3NF for control-plane entities (users/roles/services) — this data is low-volume, integrity-critical, and benefits from update anomaly protection. `predictions.input_snapshot`/`output` are intentionally JSONB (denormalized) since prediction payload shape varies by model version — forcing 3NF here would mean a schema migration every time a model adds a feature.

**Key indexes:** `alerts(service_id, status, triggered_at)` composite (dashboard's most common filter), `audit_logs(user_id, created_at)`, `pods(service_id, status)`. Partial index on `alerts WHERE status = 'open'` since dashboards query open alerts far more than resolved history.

### 6.2 TimescaleDB — Metrics Hypertable

```
metrics (time TIMESTAMPTZ, service_id UUID, metric_name TEXT, value DOUBLE PRECISION, labels JSONB)
-- hypertable partitioned by time (1-day chunks), compressed after 7 days, retention 90 days raw / 1yr downsampled
```

Continuous aggregates pre-compute 1-min/1-hr rollups so dashboard queries over "last 30 days" don't scan raw rows.

### 6.3 OpenSearch — Logs Index

Daily indices (`logs-YYYY.MM.DD`) with ILM policy: hot (7 days) → warm (30 days) → cold/archived to S3 (beyond that). Fields: `timestamp, service, level, message, trace_id, pod_id`. This is why logs live outside Postgres — full-text + fast filtering at this volume needs an inverted-index engine, not row storage.

---

## 7. AI Module Design

### 7.1 Traffic Prediction Service
- **Inputs:** historical request counts (time-series), hour-of-day, day-of-week, holiday flag, recent latency, CPU utilization.
- **Model choice:** Start with **Prophet or a gradient-boosted model (LightGBM) with lag/seasonal features** rather than a deep model — traffic has strong daily/weekly seasonality that tree/statistical models capture well with far less data and training cost than an LSTM/Transformer. Upgrade path to a Temporal Fusion Transformer if multi-service cross-correlation is needed later.
- **Output:** `expected_requests`, `confidence_interval`, `scaling_recommendation` (target replica count derived from expected_requests / requests-per-pod-capacity).
- **Serving:** batch retrain nightly (K8s CronJob), inference served via FastAPI + cached predictions (5-min TTL) since near-real-time is sufficient — traffic forecasts don't need sub-second freshness.

### 7.2 Predictive Maintenance Service
- **Inputs:** CPU, memory, disk, network I/O, restart_count (time-windowed features: rolling mean/std/slope).
- **Model choice:** **Gradient-boosted classifier (XGBoost)** for failure probability — tabular, interpretable (feature importance doubles as "root cause" signal), and doesn't need GPU infra, keeping the platform's own infra cost-realistic. Anomaly detection (Isolation Forest) as a secondary signal for "this looks unusual" even without labeled failure history.
- **Output:** `failure_probability`, `root_cause` (top contributing features, e.g., "memory trending up 40% over 2h + restart spike"), `recommendation` ("restart pod" / "scale up" / "investigate memory leak").

### 7.3 GenAI Log Analysis
- **Inputs:** raw log lines, correlated metrics snapshot, active alert context.
- **Model:** Anthropic Claude API (already justified in §4.2's RAG design) rather than a self-hosted LLM — avoids GPU cluster ops overhead that would distract from the platform's core value, and log summarization doesn't require fine-tuning.
- **Output:** structured JSON — `root_cause_summary`, `human_explanation`, `suggested_fix`, `confidence`.

---

## 8. Kubernetes Architecture

- **Cluster:** managed (EKS/GKE) with 2 node pools — `general` (services) and `compute` (ML training jobs, tainted, avoids stealing CPU from serving pods).
- **Namespaces:** `auth`, `monitoring`, `ai`, `data`, `frontend`, `platform` (per bounded context — clean RBAC boundaries and blast-radius containment).
- **Deployments + ReplicaSets:** every service is a Deployment (declarative, rolling updates); ReplicaSets are the mechanism Deployments manage, not something we author directly.
- **Services:** ClusterIP internally, one Ingress (NGINX Ingress Controller) at the edge routing to the API Gateway.
- **HPA:** CPU/memory-based on stateless services; custom-metrics (Kafka lag, request queue depth) on Metrics/GenAI services via Prometheus Adapter — this is the concrete implementation of "auto scaling" the project must demonstrate.
- **ConfigMaps/Secrets:** ConfigMaps for non-sensitive service config (log level, feature flags); Secrets (backed by cloud KMS / External Secrets Operator) for DB creds, JWT signing key, LLM API key — never baked into images.
- **PV/PVC:** used only where genuinely stateful (Kafka brokers, if self-hosted rather than managed MSK/Confluent) — everything else is stateless by design so it never needs a PVC.

---

## 9. Docker Strategy

- Multi-stage builds (builder stage compiles/installs deps, runtime stage is slim/distroless) — smaller attack surface and faster pull times, both directly relevant when the platform itself claims to monitor container health.
- Non-root user in every image.
- `HEALTHCHECK` matching the K8s readiness probe so `docker run` alone still reflects real health during local dev.
- Env vars for all config (12-factor); no secrets in image layers.

---

## 10. Security Architecture

- **AuthN:** JWT (short-lived access token + refresh token), MFA optional at Auth Service.
- **AuthZ:** RBAC enforced at API Gateway (coarse) and re-checked at service layer (fine-grained, per-resource) — defense in depth, since a compromised gateway shouldn't mean full access.
- **Transport:** TLS everywhere externally; mTLS internally (or a service mesh like Linkerd if we want it managed rather than hand-rolled — worth a follow-up decision once we're at that module).
- **Secrets:** K8s Secrets + cloud KMS, rotated, never logged.
- **Audit:** every mutating action logged to `audit_logs` with before/after state.

---

## 11. Monitoring & Logging Strategy (the platform monitoring itself)

The platform's own services emit metrics/logs into the *same* pipeline they're built to monitor — Prometheus scrapes service `/metrics` endpoints, feeds Metrics Service; structured JSON logs ship to OpenSearch via Fluent Bit sidecar. This is intentional dogfooding: it proves the pipeline works and gives free demo data.

---

## 12. CI/CD Strategy

GitHub Actions per-service pipeline: lint → unit test → build image → push to registry (tagged with git SHA) → deploy to staging namespace → integration test → manual approval gate → production rollout (rolling update, automatic rollback on failed readiness probes).

---

## 13. Testing Strategy

Unit (per-service, mocked dependencies) → contract tests (API schema) → integration (docker-compose spins up real deps) → E2E (against staging cluster) → load testing (k6) for the metrics ingestion path specifically, since that's the throughput-critical component.

---

## 14. Technology Stack Summary

| Layer | Choice | Why (vs. alternative) |
|---|---|---|
| Backend | FastAPI (Python, async) | Native async, auto Swagger, strong typing via Pydantic — better fit than Flask for high-throughput async I/O |
| Frontend | React + TypeScript + Tailwind | Type safety at scale, component reuse across 10 dashboards |
| Message Broker | Kafka | Durable, replayable, high-throughput — vs RabbitMQ which is better for task queues, not firehose telemetry |
| Relational DB | PostgreSQL (Cloud SQL) | Strong consistency for control-plane, JSONB flexibility where needed |
| Time-series DB | TimescaleDB | SQL-native, avoids adding a second query language (vs InfluxDB/Flux) |
| Search/Logs | OpenSearch | Full-text + aggregation at log volume, open-source vs proprietary Splunk cost |
| Cache/PubSub | Redis | Sub-ms cache, native pub/sub for WebSocket fan-out |
| Container Orchestration | Kubernetes (EKS/GKE) | Project requirement; industry standard |
| CI/CD | GitHub Actions | Native GitHub integration, sufficient for this scale vs Jenkins overhead |
| ML Serving | FastAPI + MLflow registry | Lightweight vs standing up KServe/Seldon at this stage |
| GenAI | Anthropic Claude API | Avoids self-hosted LLM infra burden; strong structured-output support |

---

## 15. Repository & Folder Structure

**Decision: monorepo with per-service isolation**, not polyrepo — at this project's phase, a monorepo gives atomic cross-service commits (e.g., changing an event schema and its two consumers in one PR) and one CI pipeline to reason about, while still keeping deployability independent via per-service Dockerfiles/K8s manifests. Splitting into 12 repos is easy later if team-per-service ownership emerges; premature polyrepo just adds coordination overhead now.

```
cloud-native-platform/
├── services/
│   ├── auth-service/
│   │   ├── app/
│   │   │   ├── api/            # routers
│   │   │   ├── core/           # config, security
│   │   │   ├── models/         # SQLAlchemy models
│   │   │   ├── schemas/        # Pydantic DTOs
│   │   │   ├── repositories/   # data access layer
│   │   │   ├── services/       # business logic
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── alembic/            # migrations
│   ├── api-gateway/
│   ├── monitoring-service/
│   ├── metrics-service/
│   ├── traffic-prediction-service/
│   ├── predictive-maintenance-service/
│   ├── genai-log-analysis-service/
│   ├── notification-service/
│   ├── dashboard-service/
│   ├── k8s-management-service/
│   ├── cloud-storage-service/
│   └── cloud-sql-service/
├── frontend/
│   └── src/
│       ├── components/         # reusable UI
│       ├── pages/              # 10 dashboards
│       ├── hooks/
│       ├── store/              # state management
│       ├── api/                # typed API clients
│       └── types/
├── infra/
│   ├── k8s/
│   │   ├── base/               # kustomize base per service
│   │   └── overlays/{dev,staging,prod}/
│   ├── terraform/               # cloud infra (VPC, EKS/GKE, Cloud SQL, S3)
│   └── docker-compose.yml       # local dev
├── shared/
│   ├── proto/                   # if/when gRPC introduced
│   ├── event-schemas/           # Kafka topic JSON schemas
│   └── libs/                    # shared Python package (auth utils, logging)
├── .github/workflows/
├── docs/                        # this document lives here
└── README.md
```

---

## 16. Dashboard Design (summary — full widget specs delivered per-dashboard when we build the Dashboard Service module)

| Dashboard | Purpose | Core Widgets |
|---|---|---|
| Executive | Org-wide health at a glance | Uptime %, active incidents, cost trend, SLA compliance |
| API | Per-endpoint performance | Latency p50/p95/p99, error rate, request volume, top slow endpoints table |
| Traffic | Current + predicted load | Live request graph, forecast overlay, scaling recommendation banner |
| Infrastructure | Node/VM health | CPU/mem/disk per node, network I/O, capacity heatmap |
| Kubernetes | Cluster state | Pod status grid, deployment rollout status, HPA activity |
| Containers | Docker-level detail | Container resource usage, restart count, image versions |
| AI | Predictions + GenAI output | Failure risk list, root-cause summaries, model confidence |
| Security | AuthN/Z events | Failed logins, permission changes, audit log stream |
| Cloud Cost | Spend tracking | Cost by service, trend, budget alerts |
| Logs | Searchable log stream | Filterable table, level breakdown, trace correlation |
| Settings | Admin config | User/role management, alert rules, integrations |

Each has: filters (time range, service, severity), real-time updates via the WebSocket channel from Dashboard Service, and export actions (CSV/PDF via Cloud Storage Service).

---

## 17. Scalability, Risk & Future Path

**Scalability:** stateless services scale horizontally behind HPA; Kafka partitions scale ingestion throughput; TimescaleDB chunking + read replicas scale query load; Redis cache absorbs repeated dashboard queries.

**Key risks:**
- *Kafka operational complexity* — mitigate by using managed Kafka (MSK/Confluent Cloud) rather than self-hosting initially.
- *LLM cost/latency at scale* — mitigate via caching + fallback summaries (already in §4.2).
- *Schema drift across 12 independent DBs* — mitigate via shared event-schema registry and contract tests in CI.
- *Over-engineering risk* — this design intentionally defers gRPC, service mesh, and self-hosted LLM until a concrete need appears, rather than adopting everything on day one.

**Future scalability:** multi-region deployment, service mesh (Linkerd/Istio) for automatic mTLS + traffic shaping once service count grows, model registry maturation (MLflow → full feature store) if more ML models are added.

---

## Next Step

Per the coding rules: no code yet. The recommended build order (each module depends only on what's already built):

1. **Shared foundation** — repo scaffold, shared libs (logging, config, DB base classes), docker-compose for local dev infra (Postgres, Redis, Kafka, OpenSearch).
2. **Authentication Service** — everything else needs AuthN/RBAC to exist first.
3. **API Gateway** — needs Auth Service to validate against.
4. **Cloud SQL Service + Monitoring Service** — establish the service registry other services register into.
5. Then Metrics → K8s Management → Dashboard (BFF) → prediction/GenAI services → Notification → Frontend.

Tell me to proceed and I'll start Module 1 (Shared Foundation) with full WHY/WHAT/HOW/DEPENDENCIES/INPUTS/OUTPUTS reasoning before any code, as your rules specify.
