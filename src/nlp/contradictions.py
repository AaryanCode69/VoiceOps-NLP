"""
src/nlp/contradictions.py
==========================
Contradiction Detector — VoiceOps Phase 6

Responsibility:
    - Accept Phase 4 output (normalized, PII-redacted utterances)
    - Filter to CUSTOMER utterances only (per RULES.md §5)
    - Detect contradictions within the same call using OpenAI API
    - Return a boolean: true if contradictions detected, false otherwise

Per RULES.md §8.4 — Contradiction detection with binary output (true / false).

This module does NOT:
    - Perform sentiment analysis (already done in Phase 5)
    - Perform intent classification (handled by intent.py)
    - Compute risk or fraud scores
    - Generate summaries or explanations
    - Perform PII redaction or text normalization
    - Analyze AGENT speech
    - Call RAG or store data
    - Generate identifiers
    - Track customers over time
"""

import json
import logging
import os
import threading
import time
from typing import Any

from openai import OpenAI

from src.openai_retry import chat_completions_with_retry

logger = logging.getLogger("voiceops.nlp.contradictions")


# ---------------------------------------------------------------------------
# Adaptive Token-Bucket Rate Limiter (module-scoped, thread-safe)
# ---------------------------------------------------------------------------
# Prevents 429 errors by proactively throttling OpenAI calls.
# - Only sleeps when the bucket is empty (zero overhead otherwise).
# - If a 429 *still* leaks through, the limiter halves its rate
#   temporarily and recovers over time.
# ---------------------------------------------------------------------------

class _AdaptiveRateLimiter:
    """
    Token-bucket rate limiter with adaptive back-off.

    Parameters
    ----------
    max_rpm : int
        Baseline requests-per-minute budget for this module.
    burst : int
        Maximum tokens that can accumulate (allows short bursts).
    cooldown_factor : float
        Multiplier applied to the refill interval on a 429 hit
        (e.g. 2.0 → halve the effective RPM).
    recovery_calls : int
        Number of successful calls before the cooldown fully resets.
    """

    def __init__(
        self,
        max_rpm: int = 30,
        burst: int = 5,
        cooldown_factor: float = 2.0,
        recovery_calls: int = 10,
    ) -> None:
        self._lock = threading.Lock()

        # --- bucket state ---
        self._burst = burst
        self._tokens = float(burst)          # start with full burst
        self._base_interval = 60.0 / max_rpm  # seconds between refills
        self._interval = self._base_interval
        self._last_refill = time.monotonic()

        # --- adaptive state ---
        self._cooldown_factor = cooldown_factor
        self._recovery_calls = recovery_calls
        self._success_streak = 0

    # ---- internal helpers ------------------------------------------------

    def _refill(self) -> None:
        """Add tokens that have accrued since the last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed / self._interval
        if new_tokens > 0:
            self._tokens = min(self._tokens + new_tokens, float(self._burst))
            self._last_refill = now

    # ---- public API ------------------------------------------------------

    def acquire(self) -> None:
        """
        Block (if necessary) until a token is available, then consume one.

        In the common case (tokens > 0) this returns **immediately**
        with no sleep, so throughput is unaffected when the call rate
        is well within budget.
        """
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return  # fast path — no wait
            # Calculate how long until the next token is available
            deficit = 1.0 - self._tokens
            wait = deficit * self._interval

        # Sleep *outside* the lock so other threads aren't blocked
        logger.debug(
            "Rate limiter: waiting %.2fs for token (interval=%.2fs).",
            wait, self._interval,
        )
        time.sleep(wait)

        with self._lock:
            self._refill()
            self._tokens = max(self._tokens - 1.0, 0.0)

    def report_success(self) -> None:
        """Signal a successful API call; gradually recover the rate."""
        with self._lock:
            self._success_streak += 1
            if (
                self._interval > self._base_interval
                and self._success_streak >= self._recovery_calls
            ):
                self._interval = self._base_interval
                self._success_streak = 0
                logger.info(
                    "Rate limiter: recovered to base interval (%.2fs).",
                    self._interval,
                )

    def report_rate_limit(self) -> None:
        """Signal a 429 hit; immediately tighten the rate."""
        with self._lock:
            self._interval = min(
                self._interval * self._cooldown_factor,
                60.0,  # never slower than 1 req / min
            )
            self._success_streak = 0
            logger.warning(
                "Rate limiter: 429 detected — interval raised to %.2fs.",
                self._interval,
            )


# Module-level singleton — shared across all calls in this process.
# Conservative baseline: 30 RPM with burst of 5.  Tune via env vars
# CONTRADICTION_MAX_RPM / CONTRADICTION_BURST if needed.
_rate_limiter = _AdaptiveRateLimiter(
    max_rpm=int(os.environ.get("CONTRADICTION_MAX_RPM", "30")),
    burst=int(os.environ.get("CONTRADICTION_BURST", "5")),
)


# ---------------------------------------------------------------------------
# OpenAI prompt — within-call contradiction detection
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are a contradiction detector for financial call transcripts. "
    "You analyze CUSTOMER speech from a single recorded financial call "
    "(e.g., debt collection, loan inquiries, payment discussions). "
    "You must determine whether the customer has made contradictory "
    "statements within this same call.\n\n"
    "RULES:\n"
    "- You MUST return ONLY a valid JSON object with exactly one key: "
    '"contradictions_detected".\n'
    '- "contradictions_detected" MUST be a boolean: true or false.\n'
    "- A contradiction exists when the customer makes statements that "
    "are logically inconsistent with each other within the same call.\n\n"
    "EXAMPLES OF CONTRADICTIONS:\n"
    '- "I never received any loan" followed by "I already paid part of it"\n'
    '- "I will pay tomorrow" followed by "I have no money at all"\n'
    '- "I do not owe anything" followed by "The amount seems too high"\n'
    '- "I was not contacted before" followed by "I told the last agent I would pay"\n\n'
    "EXAMPLES OF NON-CONTRADICTIONS:\n"
    '- Changing topic or asking different questions\n'
    '- Expressing frustration alongside a payment promise\n'
    '- Providing additional details that refine earlier statements\n\n'
    "CONTEXT:\n"
    "- Analyze ONLY within-call consistency; there is no call history.\n"
    "- Interpret statements in the context of financial conversations.\n"
    "- Do NOT include any other keys, explanations, reasoning, or text.\n"
    "- Do NOT infer risk, fraud, sentiment, or intent.\n\n"
    "EXAMPLE OUTPUT:\n"
    '{"contradictions_detected": true}\n'
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _filter_customer_utterances(
    utterances: list[dict[str, Any]],
) -> list[str]:
    """
    Extract text from CUSTOMER utterances only.

    Args:
        utterances: Phase 4 output — list of utterance dicts with keys:
            speaker, text, start_time, end_time.

    Returns:
        List of customer text strings (non-empty only).
    """
    customer_texts: list[str] = []
    for utt in utterances:
        if utt.get("speaker", "").upper() == "CUSTOMER":
            text = utt.get("text", "").strip()
            if text:
                customer_texts.append(text)
    return customer_texts


def _build_user_message(customer_texts: list[str]) -> str:
    """
    Build the user message containing numbered CUSTOMER utterances.

    Numbering preserves chronological order and helps the model
    identify which statements may contradict each other.

    Args:
        customer_texts: List of non-empty customer text strings.

    Returns:
        Numbered customer speech as a single user message.
    """
    numbered = [
        f"{i}. {text}" for i, text in enumerate(customer_texts, start=1)
    ]
    return "\n".join(numbered)


def _parse_contradiction_response(raw: str) -> bool:
    """
    Parse and validate the OpenAI response into a boolean.

    Args:
        raw: Raw JSON string from OpenAI completion.

    Returns:
        True if contradictions detected, False otherwise.

    Raises:
        ValueError: If response is not valid or contains disallowed values.
    """
    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Contradiction response is not valid JSON: {raw!r}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")

    value = parsed.get("contradictions_detected")

    if not isinstance(value, bool):
        raise ValueError(
            f"'contradictions_detected' must be a boolean, "
            f"got {type(value).__name__}: {value!r}"
        )

    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_contradictions(
    utterances: list[dict[str, Any]],
) -> bool:
    """
    Detect contradictions in CUSTOMER speech within a single call.

    Steps:
        1. Filter utterances to CUSTOMER speaker only
        2. Build numbered chronological user message
        3. Send to OpenAI API for within-call contradiction detection
        4. Parse and validate response
        5. Return boolean result

    Args:
        utterances:
            Phase 4 output — list of utterance dicts (normalized, PII-redacted)
            with keys: speaker, text, start_time, end_time.

    Returns:
        True if contradictions are detected within the call, False otherwise.

    Raises:
        ValueError: If OpenAI returns an invalid or unparseable response.
        openai.OpenAIError: If the OpenAI API call fails.
    """
    # Step 1: Filter to CUSTOMER utterances only (per RULES.md §5)
    customer_texts = _filter_customer_utterances(utterances)

    if not customer_texts:
        logger.warning(
            "No CUSTOMER utterances found — no contradictions possible."
        )
        return False

    if len(customer_texts) < 2:
        logger.info(
            "Only 1 CUSTOMER utterance — contradictions require at least 2."
        )
        return False

    # Step 2: Build user message with numbered utterances
    user_message = _build_user_message(customer_texts)

    logger.info(
        "Detecting contradictions across %d CUSTOMER utterance(s).",
        len(customer_texts),
    )

    # Step 3: Call OpenAI API (with proactive rate limiting)
    _rate_limiter.acquire()

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    try:
        response = chat_completions_with_retry(
            client,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,  # Deterministic output for identical inputs
            max_tokens=30,
        )
        _rate_limiter.report_success()
    except Exception as exc:
        # If a 429 leaked through the proactive limiter, tighten the rate
        # so subsequent calls are safer — then let openai_retry handle it.
        exc_type = type(exc).__name__
        status = getattr(exc, "status_code", None)
        if exc_type == "RateLimitError" or status == 429:
            _rate_limiter.report_rate_limit()
        raise

    raw_content = response.choices[0].message.content or ""

    logger.debug("Raw contradiction response: %s", raw_content)

    # Step 4: Parse and validate
    result = _parse_contradiction_response(raw_content)

    logger.info("Contradiction detection complete: %s", result)

    # Step 5: Return boolean
    return result
