from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_common.db import TimestampedModel


class Notification(TimestampedModel):
    __tablename__ = "notifications"

    alert_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    service_id: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # "pending" (sent, awaiting ack) -> "acknowledged" | "escalated"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    delivery_attempts: Mapped[list["DeliveryAttempt"]] = relationship(
        "DeliveryAttempt", back_populates="notification", cascade="all, delete-orphan", lazy="selectin"
    )


class DeliveryAttempt(TimestampedModel):
    __tablename__ = "delivery_attempts"

    notification_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # "webhook" | "slack" | "email"
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    notification: Mapped["Notification"] = relationship("Notification", back_populates="delivery_attempts")
