"""
Scrubs likely secrets/PII from log text before it leaves the platform's
boundary to the LLM provider — required by the master architecture doc's
§4.2 GenAI design ("log content is scrubbed for PII/secrets patterns
before leaving the cluster boundary"). This is pattern-based, not a
proper PII-detection model — deliberately: a false positive here just
over-redacts a log line (annoying but safe); a false negative leaks a
secret (unsafe). Bias toward over-redaction is the correct trade-off.
"""

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    # Generic long alphanumeric tokens (API keys, JWTs, bearer tokens) —
    # deliberately broad: 20+ chars of mixed alnum/./_/- with no spaces.
    ("TOKEN", re.compile(r"\b[A-Za-z0-9_\-\.]{20,}\b")),
    ("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]


def scrub(text: str) -> str:
    scrubbed = text
    for label, pattern in _PATTERNS:
        scrubbed = pattern.sub(f"[REDACTED_{label}]", scrubbed)
    return scrubbed
