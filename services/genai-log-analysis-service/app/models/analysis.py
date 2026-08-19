from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_common.db import TimestampedModel


class LogAnalysis(TimestampedModel):
    __tablename__ = "log_analyses"

    service_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    root_cause_summary: Mapped[str] = mapped_column(Text, nullable=False)
    human_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_fix: Mapped[str] = mapped_column(Text, nullable=False)
    # "llm" if the Anthropic API answered successfully, "fallback" if a
    # rule-based summary was used instead — always reported honestly.
    source: Mapped[str] = mapped_column(String(20), nullable=False)
