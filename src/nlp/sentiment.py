"""
src/nlp/sentiment.py
=====================
Sentiment Analyzer — VoiceOps Phase 5

Responsibility:
    - Accept Phase 4 output (normalized, PII-redacted utterances)
    - Filter to CUSTOMER utterances only (per RULES.md §5)
    - Classify sentiment in a financial-call context using OpenAI API
    - Return a single sentiment object with label and confidence

Per RULES.md §8.2 — Financial-context sentiment detection with confidence.

Allowed sentiment labels (enum):
    calm, neutral, stressed, anxious, frustrated, evasive

This module does NOT:
    - Perform intent detection, obligation analysis, or contradiction detection
    - Compute risk or fraud scores
    - Generate summaries or explanations
    - Perform PII redaction or text normalization
    - Analyze AGENT speech
    - Call RAG or store data
    - Generate identifiers
"""

import json
import logging
import os
from enum import Enum
from typing import Any

from openai import OpenAI

from src.openai_retry import chat_completions_with_retry

logger = logging.getLogger("voiceops.nlp.sentiment")


# ---------------------------------------------------------------------------
# Sentiment label enum — locked per Phase 5 specification
# ---------------------------------------------------------------------------


class SentimentLabel(str, Enum):
    """Allowed financial-context sentiment labels."""

    CALM = "calm"
    NEUTRAL = "neutral"
    STRESSED = "stressed"
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    EVASIVE = "evasive"


_VALID_LABELS: set[str] = {member.value for member in SentimentLabel}

# Default sentiment returned when there are no CUSTOMER utterances
_DEFAULT_SENTIMENT: dict[str, Any] = {
    "label": SentimentLabel.NEUTRAL.value,
    "confidence": 0.0,
}


# ---------------------------------------------------------------------------
# OpenAI prompt — financial-context sentiment classification
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are a financial call sentiment classifier. "
    "You analyze CUSTOMER speech from recorded financial calls "
    "(e.g., debt collection, loan inquiries, payment discussions). "
    "You must classify the overall sentiment of the customer's speech.\n\n"
    "RULES:\n"
    "- You MUST return ONLY a valid JSON object with exactly two keys: "
    '"label" and "confidence".\n'
    '- "label" MUST be one of: "calm", "neutral", "stressed", "anxious", '
    '"frustrated", "evasive".\n'
    '- "confidence" MUST be a float between 0.0 and 1.0 (inclusive), '
    "representing how confident you are in the label.\n"
    "- Interpret sentiment in the context of financial conversations "
    "(e.g., payment pressure, debt stress, evasive answers about obligations).\n"
    "- Do NOT include any other keys, explanations, reasoning, or text.\n"
    "- Do NOT infer intent, risk, or fraud.\n\n"
    "EXAMPLE OUTPUT:\n"
    '{"label": "stressed", "confidence": 0.82}\n'
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
    Build the user message containing all CUSTOMER speech for analysis.

    Args:
        customer_texts: List of non-empty customer text strings.

    Returns:
        Concatenated customer speech as a single user message.
    """
    return "\n".join(customer_texts)


def _parse_sentiment_response(raw: str) -> dict[str, Any]:
    """
    Parse and validate the OpenAI response into a sentiment object.

    Args:
        raw: Raw JSON string from OpenAI completion.

    Returns:
        Validated sentiment dict with "label" and "confidence".

    Raises:
        ValueError: If response is not valid or contains disallowed values.
    """
    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Sentiment response is not valid JSON: {raw!r}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")

    label = parsed.get("label")
    confidence = parsed.get("confidence")

    if label not in _VALID_LABELS:
        raise ValueError(
            f"Invalid sentiment label: {label!r}. "
            f"Must be one of {sorted(_VALID_LABELS)}"
        )

    if not isinstance(confidence, (int, float)):
        raise ValueError(
            f"Confidence must be a number, got {type(confidence).__name__}"
        )

    confidence = float(confidence)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(
            f"Confidence must be between 0.0 and 1.0, got {confidence}"
        )

    return {
        "label": label,
        "confidence": round(confidence, 2),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_sentiment(
    utterances: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Analyze sentiment of CUSTOMER speech from Phase 4 output.

    Steps:
        1. Filter utterances to CUSTOMER speaker only
        2. Concatenate customer text
        3. Send to OpenAI API for financial-context sentiment classification
        4. Parse and validate response
        5. Return sentiment object with label and confidence

    Args:
        utterances:
            Phase 4 output — list of utterance dicts (normalized, PII-redacted)
            with keys: speaker, text, start_time, end_time.

    Returns:
        Sentiment result dict:
            {
                "label": "calm" | "neutral" | "stressed" | "anxious" | "frustrated" | "evasive",
                "confidence": float  # 0.0–1.0
            }

    Raises:
        ValueError: If OpenAI returns an invalid or unparseable response.
        openai.OpenAIError: If the OpenAI API call fails.
    """
    # Step 1: Filter to CUSTOMER utterances only (per RULES.md §5)
    customer_texts = _filter_customer_utterances(utterances)

    if not customer_texts:
        logger.warning(
            "No CUSTOMER utterances found — returning default neutral sentiment."
        )
        return dict(_DEFAULT_SENTIMENT)

    # Step 2: Build user message
    user_message = _build_user_message(customer_texts)

    logger.info(
        "Analyzing sentiment for %d CUSTOMER utterance(s).",
        len(customer_texts),
    )

    # Step 3: Call OpenAI API
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    response = chat_completions_with_retry(
        client,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,  # Deterministic output for identical inputs
        max_tokens=60,
    )

    raw_content = response.choices[0].message.content or ""

    logger.debug("Raw sentiment response: %s", raw_content)

    # Step 4: Parse and validate
    sentiment = _parse_sentiment_response(raw_content)

    logger.info(
        "Sentiment analysis complete: label=%s, confidence=%.2f",
        sentiment["label"],
        sentiment["confidence"],
    )

    # Step 5: Return sentiment object
    return sentiment
