"""
WHY this model does NOT inherit platform_common's TimestampedModel: that
base gives every table a UUID `id` PK plus `created_at`/`updated_at`. For
an append-only time-series row, `updated_at` is meaningless (metrics are
never updated, only inserted) and having both `time` (when the metric was
observed) and `created_at` (when the row was written) invites confusion
about which one queries should filter on. This model defines its own
minimal shape instead of forcing every table in the platform through one
base class regardless of fit.

WHY a composite (time, id) primary key instead of a plain `id` PK:
TimescaleDB requires that any UNIQUE/PRIMARY KEY constraint on a
hypertable include the partitioning column. Using `id` alone as the PK
would make `create_hypertable()` fail in a real TimescaleDB deployment —
better to design the table correctly for its target engine now than
discover this the first time it runs against real Timescale.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_common.db import Base


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        Index("ix_metrics_service_name_time", "service_id", "metric_name", "time"),
    )

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
