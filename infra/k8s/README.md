# Kubernetes deployment plan

The production topology uses namespaces `auth`, `monitoring`, `ai`, `data`, `frontend`, and `platform`. Every service must have a Deployment, ClusterIP Service, resource requests/limits, liveness/readiness probes, ConfigMap-backed non-secret configuration and Secret-backed credentials. The API gateway is the sole ingress target; services are never externally exposed directly.

The first deployable runtime is `api-gateway`; other service manifests are introduced only with their service implementation so a manifest cannot claim a missing workload is production-ready.
