import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LogIngestRequest(BaseModel):
    service_id: uuid.UUID
    level: str = Field(pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    message: str = Field(min_length=1)
    trace_id: str | None = None
    pod_id: str | None = None
    timestamp: datetime | None = None


class LogEntryResponse(BaseModel):
    service_id: str
    level: str
    message: str
    timestamp: datetime
    trace_id: str | None
    pod_id: str | None


class AnalysisRequest(BaseModel):
    service_id: uuid.UUID


class AnalysisResponse(BaseModel):
    service_id: uuid.UUID
    root_cause_summary: str
    human_explanation: str
    suggested_fix: str
    source: str = Field(description="'llm' if Claude answered, 'fallback' if a rule-based summary was used")
    logs_analyzed: int
    cached: bool = False


class AnalysisHistoryEntry(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    root_cause_summary: str
    human_explanation: str
    suggested_fix: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}
