# Architecture alignment

## Correction made

The initial local proof of concept (`app.py` + static browser client) is retained only as a zero-dependency UI prototype. It is **not** the master architecture implementation: it has one process, SQLite, neither Kafka nor service isolation, and no React build pipeline.

The authoritative implementation target is now the supplied *Master Architecture Document v1.0*. Work proceeds in its dependency order:

1. Shared foundation and local infrastructure
2. Authentication service and gateway
3. Cloud SQL, monitoring, metrics, Kubernetes management and dashboard BFF
4. Prediction, maintenance, GenAI, notification and storage services
5. React dashboards, Kubernetes, Terraform and CI/CD

## Non-negotiable architecture rules

- REST at the control-plane edge; Kafka for telemetry/event fan-out.
- Each of the 12 services owns its storage schema; no cross-service database joins.
- PostgreSQL controls relational state, TimescaleDB metrics, OpenSearch logs, Redis cache/rate limiting, and S3/GCS objects.
- Frontend talks only to the gateway/BFF, never directly to a database or cloud provider.
- Mutating actions require RBAC and create audit events.

## Current implementation status

| Area | Status |
|---|---|
| Master HLD, database, security, risk and delivery design | documented |
| Monorepo foundation and event contracts | in progress |
| Local UI prototype | runnable, not architecture-complete |
| Production microservices and cloud deployment | not yet complete |

This document exists to prevent a demo implementation from being misrepresented as the architecture in the supplied brief.
