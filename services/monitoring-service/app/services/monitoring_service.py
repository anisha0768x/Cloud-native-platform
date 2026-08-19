"""
Core business logic. The heartbeat state machine is the centerpiece:

    healthy heartbeat  -> status=HEALTHY, failure counter resets to 0
    failed heartbeat   -> failure counter += 1
                           counter == 1           -> status=DEGRADED
                           counter >= threshold    -> status=DOWN, alert created (once)

This is intentionally a simple, explainable state machine — exactly the
kind of deterministic logic the Predictive Maintenance Service (a later
module) will eventually complement with a probabilistic model, but a
platform shouldn't need ML just to notice "this thing stopped responding
three times in a row."
"""

import uuid
from datetime import datetime, timezone

from platform_common.exceptions import ConflictError, NotFoundError

from app.models.monitoring import Alert, AlertSeverity, Service, ServiceStatus
from app.repositories.alert_repository import AlertRepository
from app.repositories.service_repository import ServiceRepository
from app.schemas.monitoring import HealthSummaryResponse, HeartbeatResponse


class MonitoringService:
    def __init__(
        self,
        service_repo: ServiceRepository,
        alert_repo: AlertRepository,
        *,
        consecutive_failures_before_down: int,
        health_summary_window_size: int,
    ):
        self._services = service_repo
        self._alerts = alert_repo
        self._down_threshold = consecutive_failures_before_down
        self._summary_window = health_summary_window_size

    async def register_service(
        self, *, name: str, type: str, namespace: str, owner_team: str | None
    ) -> Service:
        existing = await self._services.get_by_name(name)
        if existing:
            raise ConflictError(f"Service '{name}' is already registered")
        return await self._services.create(name=name, type=type, namespace=namespace, owner_team=owner_team)

    async def list_services(self, *, status: str | None = None, namespace: str | None = None) -> list[Service]:
        return await self._services.list_all(status=status, namespace=namespace)

    async def get_service_or_404(self, service_id: uuid.UUID) -> Service:
        service = await self._services.get_by_id(service_id)
        if service is None:
            raise NotFoundError(f"Service '{service_id}' not found")
        return service

    async def delete_service(self, service_id: uuid.UUID) -> None:
        service = await self.get_service_or_404(service_id)
        await self._services.delete(service)

    async def record_heartbeat(
        self, service_id: uuid.UUID, *, healthy: bool, latency_ms: int | None, detail: str | None
    ) -> HeartbeatResponse:
        service = await self.get_service_or_404(service_id)

        await self._services.add_health_check(
            service_id=service_id, healthy=healthy, latency_ms=latency_ms, detail=detail
        )
        service.last_heartbeat_at = datetime.now(timezone.utc)

        alert_created = False

        if healthy:
            service.consecutive_failed_heartbeats = 0
            service.status = ServiceStatus.HEALTHY
        else:
            service.consecutive_failed_heartbeats += 1
            if service.consecutive_failed_heartbeats >= self._down_threshold:
                service.status = ServiceStatus.DOWN
                alert_created = await self._maybe_create_down_alert(service, detail)
            else:
                service.status = ServiceStatus.DEGRADED

        return HeartbeatResponse(
            service_status=service.status,
            consecutive_failed_heartbeats=service.consecutive_failed_heartbeats,
            alert_created=alert_created,
        )

    async def _maybe_create_down_alert(self, service: Service, detail: str | None) -> bool:
        if await self._alerts.has_open_alert_of_type(service.id, "service_down"):
            return False  # already alerted; don't spam on every subsequent failed heartbeat

        await self._alerts.create(
            service_id=service.id,
            severity=AlertSeverity.CRITICAL,
            type="service_down",
            message=(
                f"Service '{service.name}' has failed {service.consecutive_failed_heartbeats} "
                f"consecutive heartbeats and is considered DOWN."
                + (f" Last detail: {detail}" if detail else "")
            ),
        )
        return True

    async def health_summary(self, service_id: uuid.UUID) -> HealthSummaryResponse:
        service = await self.get_service_or_404(service_id)
        checks = await self._services.recent_health_checks(service_id, limit=self._summary_window)

        if checks:
            healthy_count = sum(1 for c in checks if c.healthy)
            uptime_pct = round((healthy_count / len(checks)) * 100, 2)
        else:
            uptime_pct = 0.0

        return HealthSummaryResponse(
            service_id=service.id,
            current_status=service.status,
            uptime_percentage=uptime_pct,
            checks_considered=len(checks),
            last_heartbeat_at=service.last_heartbeat_at,
        )

    async def list_alerts(
        self, *, service_id: uuid.UUID | None = None, status: str | None = None, severity: str | None = None
    ) -> list[Alert]:
        return await self._alerts.list_all(service_id=service_id, status=status, severity=severity)

    async def acknowledge_alert(self, alert_id: uuid.UUID, *, acknowledged_by: str) -> Alert:
        alert = await self._alerts.get_by_id(alert_id)
        if alert is None:
            raise NotFoundError(f"Alert '{alert_id}' not found")
        return await self._alerts.acknowledge(alert, acknowledged_by=acknowledged_by)

    async def resolve_alert(self, alert_id: uuid.UUID) -> Alert:
        alert = await self._alerts.get_by_id(alert_id)
        if alert is None:
            raise NotFoundError(f"Alert '{alert_id}' not found")
        return await self._alerts.resolve(alert)
