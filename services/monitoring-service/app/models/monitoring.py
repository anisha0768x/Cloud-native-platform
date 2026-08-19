"""
WHY status is a plain string column with an enum validated at the Pydantic
layer (not a Postgres ENUM type): adding a new status later (e.g.
"degraded_partial") is a code-only change with a plain string column;
with a native Postgres ENUM it requires an ALTER TYPE migration. At this
table's scale that migration cost isn't worth the marginal type-safety
gain — Pydantic already guards every write path.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_common.db import TimestampedModel


class ServiceStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class Service(TimestampedModel):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "microservice", "database", "cache"
    namespace: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    owner_team: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[ServiceStatus] = mapped_column(
        SAEnum(ServiceStatus, native_enum=False, length=20), default=ServiceStatus.UNKNOWN, nullable=False
    )
    consecutive_failed_heartbeats: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    health_checks: Mapped[list["HealthCheckRecord"]] = relationship(
        "HealthCheckRecord", back_populates="service", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="service", cascade="all, delete-orphan"
    )


class HealthCheckRecord(TimestampedModel):
    """
    Append-only heartbeat history. WHY not just overwrite one row on
    Service: uptime % and the health-summary trend both need history, not
    just current state. This is deliberately in Postgres for now (simple,
    and volume is low — one row per heartbeat per service, not per raw
    metric); if heartbeat frequency ever grows into true metrics territory,
    this is the natural table to migrate into the Metrics Service's
    TimescaleDB instead — a boundary worth naming now even though we're
    not crossing it yet.
    """

    __tablename__ = "health_check_records"
    __table_args__ = (Index("ix_health_check_service_created", "service_id", "created_at"),)

    service_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    healthy: Mapped[bool] = mapped_column(nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    service: Mapped["Service"] = relationship("Service", back_populates="health_checks")


class Alert(TimestampedModel):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_service_status", "service_id", "status"),)

    service_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        SAEnum(AlertSeverity, native_enum=False, length=20), nullable=False
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "service_down", "high_latency"
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(AlertStatus, native_enum=False, length=20), default=AlertStatus.OPEN, nullable=False
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    service: Mapped["Service"] = relationship("Service", back_populates="alerts")
