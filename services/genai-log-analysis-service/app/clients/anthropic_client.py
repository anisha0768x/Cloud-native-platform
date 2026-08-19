"""
Calls the Anthropic API directly via httpx (not the SDK — this service's
only interaction is a single structured JSON-generating call, and adding
the full SDK dependency for that is unnecessary weight).

WHY this raises a specific exception rather than returning None on
failure (unlike this platform's other "graceful degradation" clients,
e.g. Dashboard Service's BackendClient): the caller (GenAiAnalysisService)
needs to distinguish "LLM unavailable, use the rule-based fallback" from
"LLM answered but the response was malformed" for logging/observability
purposes — a bare None loses that distinction. Both cases still result in
the same fallback behavior, just with different log detail.
"""

import json

import httpx

from platform_common.logging import get_logger

logger = get_logger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LlmUnavailableError(Exception):
    pass


class AnthropicClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        api_key: str | None,
        model: str,
        timeout: float,
        api_url: str = ANTHROPIC_API_URL,
    ):
        self._client = http_client
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._api_url = api_url

    async def summarize_incident(self, *, prompt: str) -> dict:
        """
        Returns {"root_cause_summary": str, "human_explanation": str,
        "suggested_fix": str}. Raises LlmUnavailableError on ANY failure
        (no API key configured, network error, timeout, malformed
        response) — the caller is expected to catch this and fall back.
        """
        if not self._api_key:
            raise LlmUnavailableError("ANTHROPIC_API_KEY not configured")

        try:
            resp = await self._client.post(
                self._api_url,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            body = resp.json()
            text = "".join(block.get("text", "") for block in body.get("content", []) if block.get("type") == "text")
            parsed = json.loads(text)
            for required_key in ("root_cause_summary", "human_explanation", "suggested_fix"):
                if required_key not in parsed:
                    raise ValueError(f"LLM response missing required key: {required_key}")
            return parsed
        except LlmUnavailableError:
            raise
        except Exception as exc:
            logger.warning("LLM call failed, caller will fall back", extra={"error": str(exc)})
            raise LlmUnavailableError(str(exc)) from exc
