"""
src/openai_retry.py
====================
Shared OpenAI API retry utility — VoiceOps

Provides a thin wrapper around ``client.chat.completions.create`` that
automatically retries on transient failures (429 rate-limit, 5xx server
errors, and connection timeouts) with exponential back-off.

Usage in any phase module::

    from src.openai_retry import chat_completions_with_retry

    response = chat_completions_with_retry(
        client,
        model="gpt-4o-mini",
        messages=[...],
        temperature=0.0,
        max_tokens=80,
    )

This module does NOT:
    - Create or manage OpenAI client instances
    - Change any analytical behaviour of the pipeline
    - Store data or generate identifiers
"""

import logging
import time
from typing import Any

logger = logging.getLogger("voiceops.openai_retry")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_RETRIES: int = 4          # total attempts = MAX_RETRIES + 1 (initial)
BASE_DELAY: float = 1.0       # seconds — first back-off delay
MAX_DELAY: float = 30.0       # cap so we don't wait forever
BACKOFF_FACTOR: float = 2.0   # exponential multiplier

# HTTP status codes worth retrying on
_RETRYABLE_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception is a transient OpenAI error."""
    exc_str = str(exc)

    # openai.RateLimitError, openai.APIStatusError with retryable codes
    exc_type = type(exc).__name__
    if exc_type in ("RateLimitError", "APITimeoutError", "APIConnectionError"):
        return True

    # Generic APIStatusError — check for retryable status codes
    if hasattr(exc, "status_code"):
        return getattr(exc, "status_code") in _RETRYABLE_STATUS_CODES

    # Fallback: look for status code patterns in the message
    for code in _RETRYABLE_STATUS_CODES:
        if str(code) in exc_str:
            return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chat_completions_with_retry(
    client: Any,
    **kwargs: Any,
) -> Any:
    """
    Call ``client.chat.completions.create(**kwargs)`` with automatic retry.

    Retries up to ``MAX_RETRIES`` times on rate-limit (429) and server
    errors (5xx) using exponential back-off.  Non-retryable errors are
    re-raised immediately.

    Args:
        client:  An instantiated ``openai.OpenAI`` client.
        **kwargs: Passed directly to ``client.chat.completions.create()``.

    Returns:
        The OpenAI ChatCompletion response object.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc: Exception | None = None
    delay = BASE_DELAY

    for attempt in range(MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            last_exc = exc

            if not _is_retryable(exc):
                logger.warning(
                    "OpenAI call failed with non-retryable error: %s", exc,
                )
                raise

            if attempt < MAX_RETRIES:
                logger.warning(
                    "OpenAI call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * BACKOFF_FACTOR, MAX_DELAY)
            else:
                logger.error(
                    "OpenAI call failed after %d attempts: %s",
                    MAX_RETRIES + 1,
                    exc,
                )

    # All retries exhausted
    raise last_exc  # type: ignore[misc]
