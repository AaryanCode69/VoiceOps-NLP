"""
src/nlp/intent.py
==================
Intent Classifier — VoiceOps Phase 6

Responsibility:
    - Accept Phase 4 output (normalized, PII-redacted utterances)
    - Filter to CUSTOMER utterances only (per RULES.md §5)
    - Classify customer intent in a financial-call context using OpenAI API
    - Return intent label, confidence (0–1), and conditionality level

Per RULES.md §8.1 — Enum-based intent detection with confidence and conditionality.

Allowed intent labels (enum):
    repayment_promise, repayment_delay, refusal, deflection,
    information_seeking, dispute, unknown

Allowed conditionality levels (enum):
    low, medium, high

This module does NOT:
    - Perform sentiment analysis (already done in Phase 5)
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

logger = logging.getLogger("voiceops.nlp.intent")


# ---------------------------------------------------------------------------
# Intent label enum — locked per Phase 6 specification
# ---------------------------------------------------------------------------


class IntentLabel(str, Enum):
    """Allowed financial-context intent labels."""

    REPAYMENT_PROMISE = "repayment_promise"
    REPAYMENT_DELAY = "repayment_delay"
    REFUSAL = "refusal"
    DEFLECTION = "deflection"
    INFORMATION_SEEKING = "information_seeking"
    DISPUTE = "dispute"
    UNKNOWN = "unknown"


class Conditionality(str, Enum):
    """Conditionality levels for customer intent."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_VALID_INTENT_LABELS: set[str] = {member.value for member in IntentLabel}
_VALID_CONDITIONALITY: set[str] = {member.value for member in Conditionality}

# Default intent returned when there are no CUSTOMER utterances
_DEFAULT_INTENT: dict[str, Any] = {
    "label": IntentLabel.UNKNOWN.value,
    "confidence": 0.0,
    "conditionality": Conditionality.LOW.value,
}


# ---------------------------------------------------------------------------
# OpenAI prompt — financial-context intent classification
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are a financial call intent classifier. "
    "You analyze CUSTOMER speech from recorded financial calls "
    "(e.g., debt collection, loan inquiries, payment discussions). "
    "You must classify the primary intent of the customer's speech "
    "and assess how conditional their statements are.\n\n"
    "RULES:\n"
    "- You MUST return ONLY a valid JSON object with exactly three keys: "
    '"label", "confidence", and "conditionality".\n'
    '- "label" MUST be one of: "repayment_promise", "repayment_delay", '
    '"refusal", "deflection", "information_seeking", "dispute", "unknown".\n'
    '- "confidence" MUST be a float between 0.0 and 1.0 (inclusive), '
    "representing how confident you are in the intent label.\n"
    '- "conditionality" MUST be one of: "low", "medium", "high".\n'
    "  - \"low\" means the customer's statement is unconditional and direct "
    '(e.g., "I will pay tomorrow").\n'
    '  - "medium" means the statement has some conditions or hedging '
    '(e.g., "I should be able to pay by Friday").\n'
    '  - "high" means the statement is heavily conditional, vague, or dependent '
    'on external factors (e.g., "If my salary comes, maybe I can pay").\n\n'
    "INTENT DEFINITIONS:\n"
    '- "repayment_promise": Customer explicitly commits to making a payment.\n'
    '- "repayment_delay": Customer acknowledges debt but requests more time.\n'
    '- "refusal": Customer refuses to pay or denies the obligation.\n'
    '- "deflection": Customer avoids answering directly, changes topic, '
    "or gives evasive responses.\n"
    '- "information_seeking": Customer asks questions about the debt, '
    "account details, or process.\n"
    '- "dispute": Customer challenges the validity of the debt or charges.\n'
    '- "unknown": Intent cannot be determined from the speech.\n\n'
    "CONTEXT:\n"
    "- Interpret intent in the context of financial conversations "
    "(e.g., payment pressure, debt recovery, loan discussions).\n"
    "- Do NOT include any other keys, explanations, reasoning, or text.\n"
    "- Do NOT infer risk, fraud, or sentiment.\n\n"
    "EXAMPLE OUTPUT:\n"
    '{"label": "repayment_delay", "confidence": 0.85, "conditionality": "medium"}\n'
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


def _parse_intent_response(raw: str) -> dict[str, Any]:
    """
    Parse and validate the OpenAI response into an intent object.

    Args:
        raw: Raw JSON string from OpenAI completion.

    Returns:
        Validated intent dict with "label", "confidence", and "conditionality".

    Raises:
        ValueError: If response is not valid or contains disallowed values.
    """
    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI response is not valid JSON: {raw!r}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")

    label = parsed.get("label")
    confidence = parsed.get("confidence")
    conditionality = parsed.get("conditionality")

    # Validate label
    if label not in _VALID_INTENT_LABELS:
        raise ValueError(
            f"Invalid intent label: {label!r}. "
            f"Must be one of {sorted(_VALID_INTENT_LABELS)}"
        )

    # Validate confidence
    if not isinstance(confidence, (int, float)):
        raise ValueError(
            f"Confidence must be a number, got {type(confidence).__name__}"
        )

    confidence = float(confidence)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(
            f"Confidence must be between 0.0 and 1.0, got {confidence}"
        )

    # Validate conditionality
    if conditionality not in _VALID_CONDITIONALITY:
        raise ValueError(
            f"Invalid conditionality: {conditionality!r}. "
            f"Must be one of {sorted(_VALID_CONDITIONALITY)}"
        )

    return {
        "label": label,
        "confidence": round(confidence, 2),
        "conditionality": conditionality,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_intent(
    utterances: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Classify intent of CUSTOMER speech from Phase 4 output.

    Steps:
        1. Filter utterances to CUSTOMER speaker only
        2. Concatenate customer text
        3. Send to OpenAI API for financial-context intent classification
        4. Parse and validate response
        5. Return intent object with label, confidence, and conditionality

    Args:
        utterances:
            Phase 4 output — list of utterance dicts (normalized, PII-redacted)
            with keys: speaker, text, start_time, end_time.

    Returns:
        Intent result dict:
            {
                "label": "repayment_promise" | "repayment_delay" | "refusal"
                         | "deflection" | "information_seeking" | "dispute"
                         | "unknown",
                "confidence": float,        # 0.0–1.0
                "conditionality": "low" | "medium" | "high"
            }

    Raises:
        ValueError: If OpenAI returns an invalid or unparseable response.
        openai.OpenAIError: If the OpenAI API call fails.
    """
    # Step 1: Filter to CUSTOMER utterances only (per RULES.md §5)
    customer_texts = _filter_customer_utterances(utterances)

    if not customer_texts:
        logger.warning(
            "No CUSTOMER utterances found — returning default unknown intent."
        )
        return dict(_DEFAULT_INTENT)

    # Step 2: Build user message
    user_message = _build_user_message(customer_texts)

    logger.info(
        "Classifying intent for %d CUSTOMER utterance(s) via OpenAI.",
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
        max_tokens=80,
    )

    raw_content = response.choices[0].message.content or ""

    logger.debug("OpenAI raw intent response: %s", raw_content)

    # Step 4: Parse and validate
    intent = _parse_intent_response(raw_content)

    logger.info(
        "Intent classification complete: label=%s, confidence=%.2f, conditionality=%s",
        intent["label"],
        intent["confidence"],
        intent["conditionality"],
    )

    # Step 5: Return intent object
    return intent
