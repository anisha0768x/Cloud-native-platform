"""
Structured JSON logging.

WHY structured (JSON) logs instead of plain text:
  The GenAI Log Analysis Service and the Logs Dashboard both need to filter
  and correlate logs by fields (service, level, trace_id, pod_id) at query
  time in OpenSearch. Plain-text logs would force regex parsing at ingest
  time, which is fragile and slow. Every service emitting the *same* JSON
  shape means one Fluent Bit config can ship all 12 services' logs
  correctly with zero per-service special-casing.

Every log line includes: timestamp, level, service, message, plus any
extra structured fields passed via `logger.info(..., extra={...})`, and a
request-scoped trace_id when available (set via `bind_trace_id`).
"""

import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

# Request-scoped trace id, set by the tracing middleware per incoming request
# so every log line emitted while handling that request can be correlated
# back to it in OpenSearch/Jaeger.
_trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)


def bind_trace_id(trace_id: str) -> None:
    _trace_id_ctx.set(trace_id)


class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_ctx.get()
        return True


class _ServiceContextFormatter(jsonlogger.JsonFormatter):
    def __init__(self, service_name: str, service_version: str, environment: str, **kwargs):
        super().__init__(**kwargs)
        self._service_name = service_name
        self._service_version = service_version
        self._environment = environment

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["service"] = self._service_name
        log_record["service_version"] = self._service_version
        log_record["environment"] = self._environment
        log_record["level"] = record.levelname
        if not log_record.get("trace_id"):
            log_record["trace_id"] = getattr(record, "trace_id", None)


def configure_logging(
    service_name: str,
    service_version: str = "0.1.0",
    environment: str = "local",
    log_level: str = "INFO",
) -> None:
    """
    Call once at service startup (in main.py, before the app is created).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_TraceIdFilter())
    formatter = _ServiceContextFormatter(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        fmt="%(timestamp)s %(level)s %(name)s %(message)s %(trace_id)s",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Quiet noisy third-party loggers unless we're actively debugging.
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "aiokafka"):
        logging.getLogger(noisy).setLevel("WARNING" if log_level != "DEBUG" else "DEBUG")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
