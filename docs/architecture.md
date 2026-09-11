# Helio Operations — Architecture Decision Record

## Why this architecture

An operations platform must keep the request path for live monitoring predictable even while analytics and AI work are slow. The target production design therefore separates command/query APIs from asynchronous event processing. This repository implements the same public boundaries as a compact, locally runnable product slice, enabling the entire experience to work without cloud accounts or a cluster.

## High-level design

```text
Browser → API Gateway → Auth / Dashboard BFF
                          ├─ Monitoring & Metrics
                          ├─ Kubernetes Management
                          ├─ Traffic + Maintenance ML
                          ├─ Log Analysis / GenAI
                          └─ Notification + Storage
                                  ↓
                          Kafka event bus → specialized workers
                                  ↓
                    PostgreSQL/Timescale, Redis, OpenSearch, S3
```

The local server presents this through versionable `/api/*` contracts and a SQLite persistence adapter. In production, each bounded context becomes an independently deployed FastAPI service; the gateway validates JWTs, forwards trace IDs and applies rate limits.

## Service boundaries

| Service | Responsibility | Storage / communication |
|---|---|---|
| Auth | users, RBAC, token issuing | PostgreSQL; JWT |
| Gateway | routing, rate limits, trace propagation | Redis |
| Monitoring | service registry, health and alerts | PostgreSQL; `health.changed` |
| Metrics | ingest and aggregate telemetry | TimescaleDB; `metrics.raw` |
| Kubernetes | clusters, workload state, scaling commands | Kubernetes API; `scaling.executed` |
| Dashboard | read-model aggregation for UI | Redis cache |
| Traffic prediction | quantile demand forecast | model store; `forecast.ready` |
| Predictive maintenance | failure likelihood and attribution | model store; `risk.detected` |
| Log analysis | retrieval, summary and remediation | OpenSearch/S3 |
| Notifications | policy, escalation, delivery | Kafka; provider APIs |
| Cloud storage | evidence and report objects | S3 |

## Data and security

Production tables are normalized around tenants, users/roles/permissions, registered services, metric points, alerts, deployments, pods, forecasts, incident summaries, notifications and immutable audit logs. Tenant IDs exist on every business record; metric/event tables use time partitioning. API access uses short-lived signed access tokens and rotating refresh tokens, least-privilege service identities, KMS-encrypted secrets, TLS everywhere, audit events, request validation and OPA/RBAC authorization. Never put cluster credentials or provider keys in the browser.

## Delivery, observability and scale

Images are built once, SBOM/scanned, signed and promoted through staging to an approval-gated production environment. CI runs unit, contract, integration, UI and load tests; deployment uses progressive rollout with automatic rollback on SLO burn. Kubernetes runs services in separate namespaces with resource limits, probes, HPA/KEDA and network policies. OpenTelemetry traces, structured logs and RED/USE metrics make the platform observable itself. Kafka partitions and consumer groups scale ingestion; read models are cached; Timescale retention/compression and S3 lifecycle rules control cost.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Alert storms | deduplication, grouping, escalation policy and suppression windows |
| Bad automated scaling | confidence thresholds, rate limits, audit trail and manual approval option |
| AI hallucination | grounded retrieval, source links, confidence labels and human review |
| Noisy telemetry / cost | sampling, cardinality limits and retention tiers |
| Cross-service failure | timeouts, retries with jitter, circuit breakers and graceful partial responses |
