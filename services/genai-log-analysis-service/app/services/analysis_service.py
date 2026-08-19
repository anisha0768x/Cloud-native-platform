"""
GenAiAnalysisService: the RAG pipeline. Order of operations, matching the
architecture doc's §4.2 design:
  1. Check Redis cache by fingerprint (dedupe repeated identical issues)
  2. Retrieve context: recent ERROR logs (LogStore) + a correlated metric
     (Metrics Service) — the "before calling the LLM" retrieval step
  3. Scrub PII/secrets from log content
  4. Build the prompt, call the LLM
  5. On ANY LLM failure, fall back to a rule-based summary — the dashboard
     must never show a blank AI panel (§4.2's explicit design goal)
  6. Persist + cache the result
"""

import hashlib
import json
import uuid

from app.clients.anthropic_client import AnthropicClient, LlmUnavailableError
from app.clients.metrics_client import MetricsClient
from app.logstore.base import LogEntry, LogStore
from app.repositories.analysis_repository import AnalysisRepository
from app.services.scrubber import scrub


def _fingerprint(service_id: str, error_messages: list[str]) -> str:
    """
    Identifies "the same underlying issue" for cache dedup: same service +
    same TOP error message. Using only the top message (not the whole log
    set) means minor variation in a secondary log line doesn't bust the
    cache for what's fundamentally the same incident.
    """
    top = error_messages[0] if error_messages else "no-errors"
    raw = f"{service_id}:{top}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_prompt(service_id: str, logs: list[LogEntry], avg_latency: float | None) -> str:
    scrubbed_lines = [f"[{log.level}] {scrub(log.message)}" for log in logs]
    log_block = "\n".join(scrubbed_lines) if scrubbed_lines else "(no recent error logs)"
    metric_line = f"Average latency (last 30 min): {avg_latency:.1f}ms" if avg_latency is not None else "(no metrics available)"

    return f"""You are an SRE assistant analyzing an incident for service '{service_id}'.

Recent error logs:
{log_block}

Correlated metrics:
{metric_line}

Respond with ONLY a JSON object (no markdown, no preamble) with exactly these keys:
"root_cause_summary": a one-sentence technical root cause,
"human_explanation": a 2-3 sentence plain-language explanation for a non-expert,
"suggested_fix": a concrete, actionable next step.
"""


def _fallback_summary(service_id: str, logs: list[LogEntry], avg_latency: float | None) -> dict:
    """
    Rule-based fallback when the LLM is unavailable — deliberately simple
    pattern matching, not a second ML model. Good enough to answer "is
    something actually wrong" without ever showing a blank panel.
    """
    error_count = len(logs)
    if error_count == 0:
        return {
            "root_cause_summary": "No recent error logs found for this service.",
            "human_explanation": "The system did not find any ERROR-level log entries in the recent window, so no incident is currently indicated.",
            "suggested_fix": "No action needed.",
        }

    latency_note = f" alongside elevated average latency ({avg_latency:.0f}ms)" if avg_latency and avg_latency > 500 else ""
    return {
        "root_cause_summary": f"{error_count} error log(s) detected for this service{latency_note}.",
        "human_explanation": (
            f"The system observed {error_count} error-level log entries for this service in the recent "
            f"window{latency_note}. This is a pattern-based summary (the AI analysis service was unavailable), "
            "so review the raw logs for full detail."
        ),
        "suggested_fix": "Review recent error logs and any recent deployments to this service for correlation.",
    }


class GenAiAnalysisService:
    def __init__(
        self,
        log_store: LogStore,
        metrics_client: MetricsClient,
        llm_client: AnthropicClient,
        repo: AnalysisRepository,
        redis_client,
        *,
        recent_error_limit: int,
        cache_ttl_seconds: int,
    ):
        self._logs = log_store
        self._metrics = metrics_client
        self._llm = llm_client
        self._repo = repo
        self._redis = redis_client
        self._error_limit = recent_error_limit
        self._cache_ttl = cache_ttl_seconds

    async def analyze(self, *, service_id: uuid.UUID, authorization: str) -> dict:
        logs = await self._logs.recent_errors(service_id=str(service_id), limit=self._error_limit)
        error_messages = [log.message for log in logs]
        fingerprint = _fingerprint(str(service_id), error_messages)
        cache_key = f"genai:analysis:{fingerprint}"

        cached = await self._redis.get(cache_key)
        if cached:
            result = json.loads(cached)
            result["cached"] = True
            result["service_id"] = str(service_id)
            return result

        avg_latency = await self._metrics.get_recent_average(
            service_id=str(service_id), metric_name="latency_ms", authorization=authorization
        )

        prompt = _build_prompt(str(service_id), logs, avg_latency)

        try:
            llm_result = await self._llm.summarize_incident(prompt=prompt)
            source = "llm"
            summary = llm_result
        except LlmUnavailableError:
            source = "fallback"
            summary = _fallback_summary(str(service_id), logs, avg_latency)

        await self._repo.record(
            service_id=service_id,
            root_cause_summary=summary["root_cause_summary"],
            human_explanation=summary["human_explanation"],
            suggested_fix=summary["suggested_fix"],
            source=source,
        )

        response = {
            "service_id": service_id,
            "root_cause_summary": summary["root_cause_summary"],
            "human_explanation": summary["human_explanation"],
            "suggested_fix": summary["suggested_fix"],
            "source": source,
            "logs_analyzed": len(logs),
            "cached": False,
        }

        await self._redis.set(
            cache_key,
            json.dumps({k: v for k, v in response.items() if k != "service_id"}),
            ex=self._cache_ttl,
        )

        return response

    async def history(self, *, service_id: uuid.UUID, limit: int = 50):
        return await self._repo.history(service_id=service_id, limit=limit)
