from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status

from platform_common.security import TokenPayload, require_permission

from app.logstore.base import LogEntry
from app.schemas.analysis import LogEntryResponse, LogIngestRequest

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_log(
    body: LogIngestRequest,
    request: Request,
    _: TokenPayload = Depends(require_permission("logs:write")),
):
    """Fallback REST ingestion path — the Kafka consumer (app/workers) is primary."""
    entry = LogEntry(
        service_id=str(body.service_id),
        level=body.level,
        message=body.message,
        timestamp=body.timestamp or datetime.now(),
        trace_id=body.trace_id,
        pod_id=body.pod_id,
    )
    await request.app.state.log_store.index(entry)
    return {"accepted": True}


@router.get("/search", response_model=list[LogEntryResponse])
async def search_logs(
    request: Request,
    service_id: str | None = Query(default=None),
    level: str | None = Query(default=None),
    query: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    _: TokenPayload = Depends(require_permission("logs:read")),
):
    return await request.app.state.log_store.search(
        service_id=service_id, level=level, query=query, start=start, end=end, limit=limit
    )
