"""
src/rag/summary_generator.py
=============================
RAG Summary Generator — VoiceOps Phase 8

Responsibility:
    - Accept structured outputs from Phase 6 (intent, conditionality,
      obligation strength, contradictions) and Phase 7 (risk score,
      fraud likelihood, key risk factors)
    - Generate a single-sentence, neutral, embedding-safe summary
    - Ensure the summary contains no PII, identifiers, accusations,
      raw numbers, or new facts

Per RULES.md §11 — The "summary_for_rag" field is a string in the final JSON.
Per RULES.md §10 — RAG must not re-extract intent, re-score risk, or make
accusations.

Model usage:
    - OpenAI (gpt-4o-mini, temperature=0.0) MAY be used for controlled
      summary generation
    - Input to OpenAI is ONLY structured signal data, never raw transcript
    - If OpenAI is unavailable or fails, a deterministic template-based
      fallback is used

Summary constraints:
    - Exactly ONE sentence
    - Factual and neutral
    - No banned words (fraudster, lied, scam, etc.)
    - No PII, identifiers, or numeric scores
    - Consistent for identical inputs

This module does NOT:
    - Analyze raw transcript text
    - Perform sentiment, intent, or risk detection
    - Modify risk scores or fraud likelihood
    - Generate explanations or recommendations for users
    - Store or embed data
    - Call RAG
    - Generate identifiers
    - Introduce new facts
"""

import json
import logging
import os
from typing import Any

from src.openai_retry import chat_completions_with_retry

logger = logging.getLogger("voiceops.rag.summary_generator")


# ---------------------------------------------------------------------------
# Valid input value sets — must match Phase 6 / Phase 7 output contracts
# ---------------------------------------------------------------------------

_VALID_INTENT_LABELS: set[str] = {
    "repayment_promise", "repayment_delay", "refusal", "deflection",
    "information_seeking", "dispute", "unknown",
}

_VALID_CONDITIONALITY: set[str] = {"low", "medium", "high"}

_VALID_OBLIGATION: set[str] = {"strong", "weak", "conditional", "none"}

_VALID_FRAUD_LIKELIHOOD: set[str] = {"low", "medium", "high"}

_VALID_RISK_FACTORS: set[str] = {
    "high_emotional_stress",
    "risky_intent",
    "conditional_commitment",
    "weak_obligation",
    "contradictory_statements",
    "suspicious_audio_signals",
}

# ---------------------------------------------------------------------------
# Banned words — summaries must never use accusatory language
# ---------------------------------------------------------------------------

_BANNED_WORDS: set[str] = {
    "fraudster", "fraud", "lied", "lying", "scam", "scammer",
    "criminal", "guilty", "dishonest", "cheat", "cheating",
    "thief", "steal", "stealing", "deceive", "deceiving",
    "deceptive", "malicious",
}


# ---------------------------------------------------------------------------
# Human-readable label mappings for template-based summary
# ---------------------------------------------------------------------------

_INTENT_PHRASES: dict[str, str] = {
    "repayment_promise": "a repayment promise",
    "repayment_delay": "a request to delay repayment",
    "refusal": "a refusal to pay",
    "deflection": "deflective responses",
    "information_seeking": "information-seeking behavior",
    "dispute": "a dispute regarding the obligation",
    "unknown": "unclear intent",
}

_OBLIGATION_PHRASES: dict[str, str] = {
    "strong": "strong commitment",
    "weak": "weak commitment",
    "conditional": "conditional commitment",
    "none": "no discernible commitment",
}

_CONDITIONALITY_PHRASES: dict[str, str] = {
    "low": "low conditionality",
    "medium": "moderate conditionality",
    "high": "high conditionality",
}

_FRAUD_PHRASES: dict[str, str] = {
    "low": "low risk",
    "medium": "moderate risk",
    "high": "elevated risk",
}

_RISK_FACTOR_PHRASES: dict[str, str] = {
    "high_emotional_stress": "elevated stress",
    "risky_intent": "risky intent signals",
    "conditional_commitment": "conditional commitment patterns",
    "weak_obligation": "unreliable commitment",
    "contradictory_statements": "contradictions",
    "suspicious_audio_signals": "suspicious audio characteristics",
}


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _validate_inputs(
    intent_label: str,
    conditionality: str,
    obligation_strength: str,
    contradictions_detected: bool,
    risk_score: int,
    fraud_likelihood: str,
    key_risk_factors: list[str],
) -> None:
    """
    Validate all structured inputs against known Phase 6 / Phase 7 contracts.

    Raises:
        ValueError: If any input value is invalid.
    """
    if intent_label not in _VALID_INTENT_LABELS:
        raise ValueError(
            f"Invalid intent_label: {intent_label!r}. "
            f"Must be one of {sorted(_VALID_INTENT_LABELS)}"
        )

    if conditionality not in _VALID_CONDITIONALITY:
        raise ValueError(
            f"Invalid conditionality: {conditionality!r}. "
            f"Must be one of {sorted(_VALID_CONDITIONALITY)}"
        )

    if obligation_strength not in _VALID_OBLIGATION:
        raise ValueError(
            f"Invalid obligation_strength: {obligation_strength!r}. "
            f"Must be one of {sorted(_VALID_OBLIGATION)}"
        )

    if not isinstance(contradictions_detected, bool):
        raise ValueError(
            f"contradictions_detected must be bool, "
            f"got {type(contradictions_detected).__name__}"
        )

    if not isinstance(risk_score, int):
        raise ValueError(
            f"risk_score must be int, got {type(risk_score).__name__}"
        )
    if risk_score < 0 or risk_score > 100:
        raise ValueError(f"risk_score out of range [0, 100]: {risk_score}")

    if fraud_likelihood not in _VALID_FRAUD_LIKELIHOOD:
        raise ValueError(
            f"Invalid fraud_likelihood: {fraud_likelihood!r}. "
            f"Must be one of {sorted(_VALID_FRAUD_LIKELIHOOD)}"
        )

    if not isinstance(key_risk_factors, list):
        raise ValueError(
            f"key_risk_factors must be a list, "
            f"got {type(key_risk_factors).__name__}"
        )

    for factor in key_risk_factors:
        if factor not in _VALID_RISK_FACTORS:
            raise ValueError(
                f"Invalid risk factor: {factor!r}. "
                f"Must be one of {sorted(_VALID_RISK_FACTORS)}"
            )


# ---------------------------------------------------------------------------
# Template-based deterministic fallback
# ---------------------------------------------------------------------------


def _generate_template_summary(
    intent_label: str,
    conditionality: str,
    obligation_strength: str,
    contradictions_detected: bool,
    fraud_likelihood: str,
    key_risk_factors: list[str],
) -> str:
    """
    Generate a deterministic, template-based single-sentence summary.

    This fallback is always available and produces identical output for
    identical inputs. It never introduces new facts.

    Args:
        intent_label: Phase 6 intent classification.
        conditionality: Phase 6 conditionality level.
        obligation_strength: Phase 6 obligation strength.
        contradictions_detected: Phase 6 contradiction flag.
        fraud_likelihood: Phase 7 fraud likelihood.
        key_risk_factors: Phase 7 key risk factor labels.

    Returns:
        A single-sentence summary string safe for embedding.
    """
    intent_phrase = _INTENT_PHRASES.get(intent_label, "unclear intent")
    obligation_phrase = _OBLIGATION_PHRASES.get(
        obligation_strength, "uncertain commitment"
    )
    fraud_phrase = _FRAUD_PHRASES.get(fraud_likelihood, "uncertain risk")

    # Build the middle qualifiers
    qualifiers: list[str] = []

    qualifiers.append(
        _CONDITIONALITY_PHRASES.get(conditionality, "uncertain conditionality")
    )

    if contradictions_detected:
        qualifiers.append("contradictions in statements")

    # Add up to two risk factor phrases for conciseness
    factor_phrases = [
        _RISK_FACTOR_PHRASES[f]
        for f in key_risk_factors
        if f in _RISK_FACTOR_PHRASES
    ]
    # Limit to avoid overly long summaries
    for phrase in factor_phrases[:2]:
        if phrase not in qualifiers:
            qualifiers.append(phrase)

    qualifier_str = " and ".join(qualifiers) if qualifiers else "noted signals"

    # Determine the closing action phrase based on risk
    if fraud_likelihood == "high":
        action = "requiring further review"
    elif fraud_likelihood == "medium":
        action = "warranting closer attention"
    else:
        action = "within normal parameters"

    summary = (
        f"Customer expressed {intent_phrase} with {obligation_phrase}, "
        f"showing {qualifier_str}, indicating {fraud_phrase} and {action}."
    )

    return summary


# ---------------------------------------------------------------------------
# OpenAI-based controlled summary generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are a neutral financial call summary generator. "
    "You receive structured analysis signals from a financial call "
    "and produce EXACTLY one sentence summarizing the call for "
    "semantic embedding.\n\n"
    "RULES:\n"
    "- Output MUST be EXACTLY one sentence (one period at the end).\n"
    "- Output MUST be neutral and non-accusatory.\n"
    "- Do NOT use words like: fraudster, lied, lying, scam, scammer, "
    "criminal, guilty, dishonest, cheat, thief, steal, deceive, "
    "deceptive, malicious.\n"
    "- Do NOT introduce any new facts not present in the input.\n"
    "- Do NOT include any numbers, scores, percentages, or identifiers.\n"
    "- Do NOT include PII, names, account numbers, or phone numbers.\n"
    "- Do NOT include explanations, recommendations, or action items.\n"
    "- Use neutral phrasing like: 'indicates elevated risk', "
    "'shows unreliable commitment', 'requires further review'.\n"
    "- Return ONLY the summary sentence as plain text, nothing else.\n"
)


def _build_openai_input(
    intent_label: str,
    conditionality: str,
    obligation_strength: str,
    contradictions_detected: bool,
    fraud_likelihood: str,
    key_risk_factors: list[str],
) -> str:
    """
    Build the structured user message for OpenAI.

    Only structured signal data is included — never raw transcript.

    Returns:
        JSON-formatted string of structured signals.
    """
    signals = {
        "intent": intent_label,
        "conditionality": conditionality,
        "obligation_strength": obligation_strength,
        "contradictions_detected": contradictions_detected,
        "fraud_likelihood": fraud_likelihood,
        "key_risk_factors": key_risk_factors,
    }
    return json.dumps(signals)


def _call_openai(user_message: str) -> str:
    """
    Call OpenAI API with constrained prompt for summary generation.

    Args:
        user_message: JSON-formatted structured signals.

    Returns:
        Raw response text from OpenAI.

    Raises:
        Exception: If OpenAI call fails for any reason.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)

    response = chat_completions_with_retry(
        client,
        model="gpt-4o-mini",
        temperature=0.0,
        max_tokens=150,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("OpenAI returned empty response")

    return content.strip()


def _validate_summary(summary: str) -> str:
    """
    Validate that a generated summary meets all constraints.

    Checks:
        - Non-empty
        - Exactly one sentence (one terminal period, no multiple sentences)
        - No banned words
        - No numeric scores

    Args:
        summary: The summary string to validate.

    Returns:
        The validated summary.

    Raises:
        ValueError: If the summary violates any constraint.
    """
    if not summary:
        raise ValueError("Summary is empty")

    # Check for banned words (case-insensitive)
    summary_lower = summary.lower()
    for word in _BANNED_WORDS:
        # Check as whole word to avoid false positives
        # (e.g., "defraud" matching "fraud")
        if word in summary_lower.split():
            raise ValueError(
                f"Summary contains banned word: {word!r}"
            )

    # Check for numeric scores (digits that look like scores)
    import re
    if re.search(r'\b\d{1,3}\b', summary):
        raise ValueError(
            "Summary contains numeric values, which are not allowed"
        )

    # Check it's approximately one sentence — must end with a period
    # and not contain multiple sentence-ending punctuation
    stripped = summary.strip()
    if not stripped.endswith("."):
        raise ValueError("Summary must end with a period")

    # Count sentence-ending punctuation (rough check)
    sentence_endings = len(re.findall(r'[.!?]', stripped))
    if sentence_endings > 1:
        # Allow one period at end — if more, may be multiple sentences
        # But also allow abbreviations / common patterns
        # Count actual periods not inside common abbreviations
        period_count = stripped.count(".")
        if period_count > 1:
            raise ValueError(
                "Summary must be exactly one sentence "
                f"(detected {period_count} periods)"
            )

    return stripped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_summary(
    intent_label: str,
    conditionality: str,
    obligation_strength: str,
    contradictions_detected: bool,
    risk_score: int,
    fraud_likelihood: str,
    key_risk_factors: list[str],
) -> str:
    """
    Generate a single-sentence summary for RAG embedding.

    Accepts structured outputs from Phase 6 and Phase 7 ONLY.
    Tries OpenAI first for natural language generation; falls back
    to a deterministic template if OpenAI is unavailable or returns
    an invalid summary.

    Args:
        intent_label:
            Phase 6 intent classification (enum string).
        conditionality:
            Phase 6 conditionality level ("low" | "medium" | "high").
        obligation_strength:
            Phase 6 obligation strength ("strong" | "weak" | "conditional" | "none").
        contradictions_detected:
            Phase 6 contradiction flag (bool).
        risk_score:
            Phase 7 numerical risk score (0–100). Used for validation
            only — not included verbatim in the summary.
        fraud_likelihood:
            Phase 7 fraud likelihood ("low" | "medium" | "high").
        key_risk_factors:
            Phase 7 key contributing risk factor labels.

    Returns:
        A single-sentence summary string safe for semantic embedding.

    Raises:
        ValueError: If any input is invalid per Phase 6 / Phase 7 contracts.
    """
    # --- Input validation ---
    _validate_inputs(
        intent_label=intent_label,
        conditionality=conditionality,
        obligation_strength=obligation_strength,
        contradictions_detected=contradictions_detected,
        risk_score=risk_score,
        fraud_likelihood=fraud_likelihood,
        key_risk_factors=key_risk_factors,
    )

    logger.info(
        "Generating summary — intent=%s, conditionality=%s, "
        "obligation=%s, contradictions=%s, fraud_likelihood=%s, "
        "risk_factors=%s",
        intent_label, conditionality, obligation_strength,
        contradictions_detected, fraud_likelihood, key_risk_factors,
    )

    # --- Try OpenAI-based summary generation ---
    try:
        user_message = _build_openai_input(
            intent_label=intent_label,
            conditionality=conditionality,
            obligation_strength=obligation_strength,
            contradictions_detected=contradictions_detected,
            fraud_likelihood=fraud_likelihood,
            key_risk_factors=key_risk_factors,
        )

        raw_summary = _call_openai(user_message)
        summary = _validate_summary(raw_summary)

        logger.info("OpenAI summary generated: %s", summary)
        return summary

    except Exception as exc:
        logger.warning(
            "OpenAI summary generation failed (%s), "
            "falling back to template-based summary",
            exc,
        )

    # --- Deterministic template fallback ---
    summary = _generate_template_summary(
        intent_label=intent_label,
        conditionality=conditionality,
        obligation_strength=obligation_strength,
        contradictions_detected=contradictions_detected,
        fraud_likelihood=fraud_likelihood,
        key_risk_factors=key_risk_factors,
    )

    logger.info("Template summary generated: %s", summary)
    return summary
