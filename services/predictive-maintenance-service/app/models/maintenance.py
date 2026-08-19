from sqlalchemy import Float, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_common.db import TimestampedModel


class MaintenancePrediction(TimestampedModel):
    """
    Audit history of every failure-risk prediction served — same
    reasoning as Traffic Prediction Service's `predictions` table: this
    is what a future "prediction accuracy over time" view needs (compare
    predicted risk against whether the service actually failed
    afterward), which requires having recorded the prediction in advance.
    """

    __tablename__ = "maintenance_predictions"

    service_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    failure_probability: Mapped[float] = mapped_column(Float, nullable=False)
    root_cause: Mapped[str] = mapped_column(String(255), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(500), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
