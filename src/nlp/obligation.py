"""
src/nlp/obligation.py
======================
Obligation Strength Classifier — VoiceOps Phase 6

Responsibility:
    - Accept intent classification result (label + conditionality) and
      CUSTOMER utterances from Phase 4
    - Derive obligation strength DETERMINISTICALLY (no OpenAI, no LLM)
    - Based on intent label, conditionality level, and linguistic markers

Per RULES.md §8.3 — Classify commitment as: strong, weak, conditional, none.

Derivation logic:
    1. Intent label determines the BASE obligation category
    2. Conditionality adjusts strength within commitment-bearing intents
    3. Linguistic strength markers in customer text provide fine-grained
       adjustment for borderline cases

This module does NOT:
    - Call any LLM or external API
    - Perform sentiment analysis
    - Compute risk or fraud scores
    - Generate summaries or explanations
    - Perform PII redaction or text normalization
    - Analyze AGENT speech
    - Call RAG or store data
    - Generate identifiers
"""

import logging
import re
from enum import Enum
from typing import Any

logger = logging.getLogger("voiceops.nlp.obligation")


# ---------------------------------------------------------------------------
# Obligation strength enum — locked per RULES.md §8.3
# ---------------------------------------------------------------------------


class ObligationStrength(str, Enum):
    """Allowed obligation strength values."""

    STRONG = "strong"
    WEAK = "weak"
    CONDITIONAL = "conditional"
    NONE = "none"


# ---------------------------------------------------------------------------
# Linguistic markers — used for fine-grained strength adjustment
# ---------------------------------------------------------------------------

# Strong commitment markers: definite, unconditional language
_STRONG_MARKERS: list[str] = [
    r"\bI will pay\b",
    r"\bI am going to pay\b",
    r"\bI promise\b",
    r"\bguarantee\b",
    r"\bfor sure\b",
    r"\bdefinitely\b",
    r"\bcertainly\b",
    r"\babsolutely\b",
    r"\bwithout fail\b",
    r"\bI commit\b",
    r"\bI assure\b",
    r"\byou have my word\b",
    r"\bcount on it\b",
    r"\btomorrow I will\b",
    r"\bI will clear\b",
    r"\bI will settle\b",
    r"\bI will transfer\b",
]

# Weak commitment markers: hedging, uncertainty, softened language
_WEAK_MARKERS: list[str] = [
    r"\bI think I can\b",
    r"\bmaybe\b",
    r"\bprobably\b",
    r"\bpossibly\b",
    r"\bI might\b",
    r"\bI may\b",
    r"\bnot sure\b",
    r"\bI hope\b",
    r"\bI will try\b",
    r"\bI should be able\b",
    r"\blet me see\b",
    r"\blet me check\b",
    r"\bI need to check\b",
    r"\bI am not sure\b",
    r"\bI do not know\b",
    r"\bhard to say\b",
]

# Conditional markers: dependency on external factors
_CONDITIONAL_MARKERS: list[str] = [
    r"\bif\b",
    r"\bonce\b",
    r"\bwhen\b.*\b(?:comes|arrives|gets|receive|cleared)\b",
    r"\bdepends on\b",
    r"\bsubject to\b",
    r"\bprovided that\b",
    r"\bas soon as\b",
    r"\bafter\b.*\b(?:salary|money|payment|funds|cheque|check)\b",
    r"\bonly if\b",
    r"\bin case\b",
    r"\bassuming\b",
    r"\bcondition\b",
]

# Compile patterns for efficiency
_STRONG_PATTERN: re.Pattern[str] = re.compile(
    "|".join(_STRONG_MARKERS), re.IGNORECASE
)
_WEAK_PATTERN: re.Pattern[str] = re.compile(
    "|".join(_WEAK_MARKERS), re.IGNORECASE
)
_CONDITIONAL_PATTERN: re.Pattern[str] = re.compile(
    "|".join(_CONDITIONAL_MARKERS), re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Deterministic derivation logic
# ---------------------------------------------------------------------------

# Intent labels that inherently carry NO obligation
_NO_OBLIGATION_INTENTS: set[str] = {
    "refusal",
    "deflection",
    "information_seeking",
    "dispute",
    "unknown",
}

# Intent labels that carry a payment commitment (strength varies)
_COMMITMENT_INTENTS: set[str] = {
    "repayment_promise",
    "repayment_delay",
}


def _count_marker_matches(text: str, pattern: re.Pattern[str]) -> int:
    """Count the number of linguistic marker matches in text."""
    return len(pattern.findall(text))


def _derive_from_commitment_intent(
    intent_label: str,
    conditionality: str,
    customer_text: str,
) -> str:
    """
    Derive obligation strength for commitment-bearing intents.

    Logic:
        1. High conditionality → "conditional" (regardless of markers)
        2. repayment_promise + low conditionality + strong markers → "strong"
        3. repayment_promise + low conditionality (no strong markers) → "weak"
        4. repayment_promise + medium conditionality → check markers:
           - conditional markers present → "conditional"
           - strong markers > weak markers → "weak"
           - else → "conditional"
        5. repayment_delay + low conditionality → "weak"
        6. repayment_delay + medium conditionality → "conditional"
        7. repayment_delay + high conditionality → "conditional"

    Args:
        intent_label: The classified intent (must be a commitment intent).
        conditionality: The conditionality level (low/medium/high).
        customer_text: Concatenated customer utterances for marker analysis.

    Returns:
        Obligation strength value as string.
    """
    strong_count = _count_marker_matches(customer_text, _STRONG_PATTERN)
    weak_count = _count_marker_matches(customer_text, _WEAK_PATTERN)
    conditional_count = _count_marker_matches(customer_text, _CONDITIONAL_PATTERN)

    # High conditionality always maps to "conditional"
    if conditionality == "high":
        return ObligationStrength.CONDITIONAL.value

    if intent_label == "repayment_promise":
        if conditionality == "low":
            # Direct promise with low conditionality
            if strong_count > 0:
                return ObligationStrength.STRONG.value
            # No strong markers but still a direct promise
            return ObligationStrength.WEAK.value

        if conditionality == "medium":
            # Medium conditionality — markers determine outcome
            if conditional_count > 0:
                return ObligationStrength.CONDITIONAL.value
            if strong_count > weak_count:
                return ObligationStrength.WEAK.value
            return ObligationStrength.CONDITIONAL.value

    if intent_label == "repayment_delay":
        if conditionality == "low":
            # Acknowledges debt, requests time — weak commitment
            return ObligationStrength.WEAK.value

        # medium conditionality for delay → conditional
        return ObligationStrength.CONDITIONAL.value

    # Fallback for any unhandled combination (should not reach here)
    return ObligationStrength.NONE.value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_obligation_strength(
    intent_result: dict[str, Any],
    utterances: list[dict[str, Any]],
) -> str:
    """
    Derive obligation strength deterministically from intent classification
    and customer utterances.

    This function does NOT call any LLM or external API. The derivation
    is entirely rule-based, using:
        1. Intent label (from intent classifier)
        2. Conditionality level (from intent classifier)
        3. Linguistic commitment markers in customer text

    Args:
        intent_result:
            Output of classify_intent() — dict with keys:
            "label", "confidence", "conditionality".

        utterances:
            Phase 4 output — list of utterance dicts (normalized, PII-redacted)
            with keys: speaker, text, start_time, end_time.

    Returns:
        Obligation strength as string:
            "strong" | "weak" | "conditional" | "none"
    """
    intent_label = intent_result.get("label", "unknown")
    conditionality = intent_result.get("conditionality", "low")

    # Non-commitment intents always map to "none"
    if intent_label in _NO_OBLIGATION_INTENTS:
        logger.info(
            "Intent '%s' carries no obligation — returning 'none'.",
            intent_label,
        )
        return ObligationStrength.NONE.value

    # Commitment intents — analyze customer text for fine-grained strength
    if intent_label in _COMMITMENT_INTENTS:
        # Extract and concatenate customer text
        customer_texts: list[str] = []
        for utt in utterances:
            if utt.get("speaker", "").upper() == "CUSTOMER":
                text = utt.get("text", "").strip()
                if text:
                    customer_texts.append(text)

        combined_text = " ".join(customer_texts)

        strength = _derive_from_commitment_intent(
            intent_label, conditionality, combined_text
        )

        logger.info(
            "Obligation strength derived: intent=%s, conditionality=%s → %s",
            intent_label,
            conditionality,
            strength,
        )
        return strength

    # Unknown intent label — safe fallback
    logger.warning(
        "Unexpected intent label '%s' — defaulting obligation to 'none'.",
        intent_label,
    )
    return ObligationStrength.NONE.value
