import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_common.db import Base, TimestampedModel


class ScalingHistory(TimestampedModel):
    """
    Audit trail of every scaling action, regardless of source — this
    `trigger_source` column is what lets the Dashboard later distinguish
    "an operator clicked scale" from "the Traffic Prediction Service
    triggered this automatically" (a later module), without needing a
    second table.
    """

    __tablename__ = "scaling_history"

    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    deployment_name: Mapped[str] = mapped_column(String(150), nullable=False)
    from_replicas: Mapped[int] = mapped_column(Integer, nullable=False)
    to_replicas: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False)  # user id (JWT sub) or system name
    trigger_source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")  # manual|auto


class ClusterSnapshot(Base):
    """
    Append-only periodic point-in-time cluster counts (see
    app/workers/snapshot_worker.py), used for trend charts on the
    Infrastructure/Kubernetes dashboards — "pod count over the last 24h",
    not a live query on every dashboard refresh.

    Not TimestampedModel: same reasoning as the Metrics Service's `Metric`
    model — `time` IS the meaningful timestamp here, an `updated_at` would
    be meaningless since these rows are never updated.
    """

    __tablename__ = "cluster_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pod_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pods_running: Mapped[int] = mapped_column(Integer, nullable=False)
    pods_pending: Mapped[int] = mapped_column(Integer, nullable=False)
    pods_failed: Mapped[int] = mapped_column(Integer, nullable=False)
    deployment_count: Mapped[int] = mapped_column(Integer, nullable=False)
