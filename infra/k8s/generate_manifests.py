#!/usr/bin/env python3
"""
Generates infra/k8s/base/<service>/{deployment,service,configmap,hpa,
kustomization}.yaml for every entry in services.yaml.

Run: python3 infra/k8s/generate_manifests.py
Re-run whenever services.yaml changes — generated files are checked into
the repo (not generated at deploy time) so `kubectl diff`/code review can
see exactly what changes, same reasoning as committing Alembic migrations
rather than diffing live schema at deploy time.
"""

import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "base"
REGISTRY_PATH = BASE_DIR / "services.yaml"

DEPLOYMENT_TEMPLATE = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {namespace}
  labels:
    app: {name}
    part-of: cloud-native-platform
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
{service_account_line}      containers:
        - name: {name}
          image: {name}:latest  # replaced by CI with the built image digest — see .github/workflows/deploy.yml
          ports:
            - containerPort: {port}
          envFrom:
            - configMapRef:
                name: {name}-config
            - secretRef:
                name: {name}-secrets
{explicit_env_block}          resources:
            requests:
              cpu: {req_cpu}
              memory: {req_mem}
            limits:
              cpu: {lim_cpu}
              memory: {lim_mem}
          livenessProbe:
            httpGet:
              path: {liveness_path}
              port: {port}
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: {readiness_path}
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 10
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
"""

SERVICE_TEMPLATE = """apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {namespace}
  labels:
    app: {name}
spec:
  selector:
    app: {name}
  ports:
    - port: {port}
      targetPort: {port}
  type: {service_type}
"""

CONFIGMAP_TEMPLATE = """apiVersion: v1
kind: ConfigMap
metadata:
  name: {name}-config
  namespace: {namespace}
data:
  SERVICE_NAME: "{name}"
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  PORT: "{port}"
{extra_config}"""

HPA_TEMPLATE = """apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {name}
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {name}
  minReplicas: {min_replicas}
  maxReplicas: {max_replicas}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {target_cpu_percent}
"""

KUSTOMIZATION_TEMPLATE = """apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml
{hpa_resource}"""


def render_deployment(svc: dict) -> str:
    port = svc["port"]
    resources = svc.get("resources", {})
    requests = resources.get("requests", {"cpu": "100m", "memory": "128Mi"})
    limits = resources.get("limits", {"cpu": "500m", "memory": "256Mi"})

    is_frontend = svc.get("is_frontend", False)
    liveness_path = "/" if is_frontend else "/health"
    readiness_path = "/" if is_frontend else "/ready"

    service_account_line = ""
    if svc.get("service_account"):
        service_account_line = f"      serviceAccountName: {svc['service_account']}\n"

    # WHY an explicit `env:` block instead of putting DATABASE_URL in the
    # ConfigMap: Kubernetes' $(VAR_NAME) substitution ONLY expands
    # references within the same container's explicit `env:` list — it
    # does NOT expand values sourced from envFrom (ConfigMap/Secret), a
    # well-documented gotcha (kubernetes/kubernetes#69113). Putting
    # `$(DB_PASSWORD)` inside a ConfigMap `data` value would ship that
    # literal, unexpanded string to the app. The fix: DB_PASSWORD arrives
    # via envFrom's secretRef (as it already did), and DATABASE_URL is
    # built in an explicit `env:` entry that references it — env entries
    # CAN reference envFrom-sourced variables, since envFrom is merged
    # into the container's environment before explicit `env:` entries are
    # evaluated.
    explicit_env_block = ""
    if svc.get("needs_db"):
        db_name = svc["name"].replace("-", "_")
        explicit_env_block = (
            "          env:\n"
            "            - name: DATABASE_URL\n"
            f'              value: "postgresql+asyncpg://platform:$(DB_PASSWORD)@postgres:5432/{db_name}"\n'
        )

    return DEPLOYMENT_TEMPLATE.format(
        name=svc["name"],
        namespace=svc["namespace"],
        replicas=svc["replicas"],
        port=port,
        req_cpu=requests["cpu"],
        req_mem=requests["memory"],
        lim_cpu=limits["cpu"],
        lim_mem=limits["memory"],
        liveness_path=liveness_path,
        readiness_path=readiness_path,
        service_account_line=service_account_line,
        explicit_env_block=explicit_env_block,
    )


def render_service(svc: dict) -> str:
    # Only the gateway and frontend get a LoadBalancer-facing type here;
    # everything else is ClusterIP — internal-only, reached through the
    # gateway, matching the platform's own "gateway is the one edge"
    # design from Module 3. Real external exposure still goes through the
    # Ingress (base/ingress.yaml), this just controls in-cluster reachability.
    service_type = "ClusterIP"
    return SERVICE_TEMPLATE.format(
        name=svc["name"], namespace=svc["namespace"], port=svc["port"], service_type=service_type
    )


def render_configmap(svc: dict) -> str:
    extra_lines = []
    name = svc["name"]
    # DATABASE_URL deliberately NOT here — see render_deployment()'s
    # explicit_env_block docstring for why it must live in the
    # Deployment's `env:` list instead of a ConfigMap value.
    if svc.get("needs_redis"):
        extra_lines.append('  REDIS_URL: "redis://redis:6379/0"')
    if svc.get("needs_kafka"):
        extra_lines.append('  KAFKA_BOOTSTRAP_SERVERS: "kafka:9092"')
    if not svc.get("is_frontend"):
        extra_lines.append('  JWT_PUBLIC_KEY_PATH: "/run/secrets/jwt/public_key.pem"')

    extra_config = "\n".join(extra_lines) + ("\n" if extra_lines else "")
    return CONFIGMAP_TEMPLATE.format(name=name, namespace=svc["namespace"], port=svc["port"], extra_config=extra_config)


def render_hpa(svc: dict) -> str | None:
    hpa = svc.get("hpa")
    if not hpa:
        return None
    return HPA_TEMPLATE.format(
        name=svc["name"],
        namespace=svc["namespace"],
        min_replicas=hpa["min_replicas"],
        max_replicas=hpa["max_replicas"],
        target_cpu_percent=hpa["target_cpu_percent"],
    )


def render_kustomization(svc: dict, has_hpa: bool) -> str:
    hpa_resource = "  - hpa.yaml\n" if has_hpa else ""
    return KUSTOMIZATION_TEMPLATE.format(hpa_resource=hpa_resource)


def generate_service_manifests(svc: dict) -> None:
    service_dir = OUTPUT_DIR / svc["name"]
    service_dir.mkdir(parents=True, exist_ok=True)

    (service_dir / "deployment.yaml").write_text(render_deployment(svc))
    (service_dir / "service.yaml").write_text(render_service(svc))
    (service_dir / "configmap.yaml").write_text(render_configmap(svc))

    hpa_yaml = render_hpa(svc)
    if hpa_yaml:
        (service_dir / "hpa.yaml").write_text(hpa_yaml)

    (service_dir / "kustomization.yaml").write_text(render_kustomization(svc, has_hpa=bool(hpa_yaml)))


def generate_root_kustomization(services: list[dict]) -> None:
    resources = "\n".join(f"  - {svc['name']}" for svc in services)
    content = f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespaces.yaml
  - ingress.yaml
{resources}
"""
    (OUTPUT_DIR / "kustomization.yaml").write_text(content)


def _images_block(services: list[dict], tag: str) -> str:
    lines = [f"  - name: {svc['name']}\n    newTag: {tag}" for svc in services]
    return "\n".join(lines)


def generate_overlays(services: list[dict]) -> None:
    overlays_dir = BASE_DIR / "overlays"

    dev_content = f"""# Dev overlay: single replica everywhere (fast iteration, low cost).
# Assumes dev/staging/prod are SEPARATE clusters (a common pattern, and
# what lets base/ keep its deliberate 6-namespace split — see
# base/namespaces.yaml — without a kustomize `namespace:` transformer
# collapsing all of them into one "dev" namespace).
#
# Generated from services.yaml by generate_manifests.py — the `images:`
# list below must name every service exactly (kustomize's images
# transformer does NOT support wildcard names), so it's generated here
# rather than hand-maintained across 3 overlay files with drift risk.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

patches:
  - patch: |-
      - op: replace
        path: /spec/replicas
        value: 1
    target:
      kind: Deployment
  # HPAs removed entirely in dev — a Deployment pinned to 1 replica above
  # would otherwise fight an HPA still targeting minReplicas: 2/3.
  - patch: |-
      $patch: delete
      apiVersion: autoscaling/v2
      kind: HorizontalPodAutoscaler
      metadata:
        name: placeholder
    target:
      kind: HorizontalPodAutoscaler

images:
{_images_block(services, "dev")}
"""
    (overlays_dir / "dev" / "kustomization.yaml").write_text(dev_content)

    staging_content = f"""# Staging overlay: production-shaped (base's own replica counts/HPAs
# apply unchanged), but a distinct image tag so staging never accidentally
# runs an untagged/`latest` image that hasn't passed the staging
# promotion gate (see .github/workflows/deploy.yml).
#
# Generated from services.yaml by generate_manifests.py — see dev
# overlay's comment for why.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

images:
{_images_block(services, "staging")}
"""
    (overlays_dir / "staging" / "kustomization.yaml").write_text(staging_content)

    prod_content = f"""# Prod overlay: base's replica counts/HPAs are already production-sized
# (see services.yaml — that's WHY they're the base, not staging/dev-sized
# with prod as the exception). Only the image tag changes here.
#
# Generated from services.yaml by generate_manifests.py — see dev
# overlay's comment for why.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

images:
{_images_block(services, "stable")}
"""
    (overlays_dir / "prod" / "kustomization.yaml").write_text(prod_content)


def main() -> None:
    registry = yaml.safe_load(REGISTRY_PATH.read_text())
    services = registry["services"]

    for svc in services:
        generate_service_manifests(svc)

    generate_root_kustomization(services)
    generate_overlays(services)

    print(f"Generated manifests for {len(services)} services into {OUTPUT_DIR}/")
    print("Generated dev/staging/prod overlay kustomizations into overlays/")


if __name__ == "__main__":
    sys.exit(main())
