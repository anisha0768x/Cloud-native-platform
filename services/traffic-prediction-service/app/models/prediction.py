from sqlalchemy import Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_common.db import TimestampedModel


class Prediction(TimestampedModel):
    """
    One row per forecast served. WHY store every prediction rather than
    just the live model: this table is the source of truth for the future
    AI Dashboard's "prediction accuracy over time" view — comparing
    predicted vs. actually-observed traffic requires having recorded the
    prediction BEFORE the outcome was known. `input_snapshot` is
    intentionally JSONB (denormalized), matching the same reasoning as the
    master architecture doc's §6.1 for this exact table: the feature set a
    model uses will evolve, and forcing 3NF here would mean a migration
    every time a feature is added.
    """

    __tablename__ = "predictions"

    service_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    expected_requests: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_upper: Mapped[float] = mapped_column(Float, nullable=False)

    recommended_replicas: Mapped[int] = mapped_column(Integer, nullable=False)
    data_source: Mapped[str] = mapped_column(String(20), nullable=False)  # "historical" | "synthetic"

    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
