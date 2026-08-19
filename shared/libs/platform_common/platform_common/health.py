"""
Standard /health (liveness) and /ready (readiness) endpoints.

WHY: Kubernetes liveness/readiness probes need a fast, unauthenticated
endpoint. Liveness answers "is the process alive" (cheap, no dependency
checks — if this fails, k8s kills the pod). Readiness answers "can this
pod serve traffic right now" (checks DB/Kafka connectivity — if this
fails, k8s stops routing traffic to the pod but does NOT restart it,
since the dependency, not the process, is the problem).
Conflating the two (a common mistake) causes restart storms when a
downstream DB has a brief blip — the pod is fine, only its dependency
is down, so it should be marked not-ready, not killed.
"""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter

DependencyCheck = Callable[[], Awaitable[bool]]


def build_health_router(
    service_name: str,
    version: str,
    dependency_checks: dict[str, DependencyCheck] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["health"])
    checks = dependency_checks or {}

    @router.get("/health")
    async def liveness():
        return {"status": "alive", "service": service_name, "version": version}

    @router.get("/ready")
    async def readiness():
        results = {name: await check() for name, check in checks.items()}
        healthy = all(results.values())
        return {
            "status": "ready" if healthy else "not_ready",
            "service": service_name,
            "dependencies": results,
        }

    return router
