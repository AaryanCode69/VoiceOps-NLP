"""
src/risk/scorer.py
===================
Deterministic Risk Scorer — VoiceOps Phase 7

Responsibility:
    - Accept a validated RiskSignalBundle (from signals.py)
    - Compute a numerical risk score (0–100) using weighted signal contributions
    - Classify fraud likelihood (low | medium | high) from fixed thresholds
    - Compute overall confidence from input signal confidence values
    - Identify key contributing risk factors traceable to input signals

Per RULES.md §9 — Risk must be computed using multiple signals, not a single factor.

Scoring philosophy:
    - Each signal dimension is scored independently (0–100 sub-score)
    - Sub-scores are combined via configurable weights (must sum to 1.0)
    - Final risk score = weighted sum, clamped to [0, 100]
    - Fraud likelihood is derived from fixed score thresholds
    - A risk factor is flagged when its sub-score exceeds a configurable threshold

This module does NOT:
    - Call any LLM or external API
    - Perform NLP analysis, intent detection, or sentiment classification
    - Generate summaries or explanations
    - Inspect raw transcript text
    - Store data or generate identifiers
    - Make downstream business decisions
    - Call RAG
"""

import logging
from typing import Any

from src.risk.signals import RiskSignalBundle

logger = logging.getLogger("voiceops.risk.scorer")


# ---------------------------------------------------------------------------
# Configurable weights — must sum to 1.0
# Each weight controls how much that signal dimension contributes to the
# final risk score. Adjust these to change risk sensitivity.
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "sentiment":      0.20,
    "intent":         0.20,
    "conditionality": 0.15,
    "obligation":     0.15,
    "contradictions": 0.15,
    "audio_trust":    0.15,
}

# Fraud likelihood thresholds (applied to the final 0–100 risk score)
FRAUD_THRESHOLD_HIGH: float = 65.0
FRAUD_THRESHOLD_MEDIUM: float = 35.0

# Sub-score threshold for flagging a dimension as a key risk factor
RISK_FACTOR_THRESHOLD: float = 50.0


# ---------------------------------------------------------------------------
# Signal-dimension scorers — each returns a sub-score in [0, 100]
# ---------------------------------------------------------------------------


def _score_sentiment(bundle: RiskSignalBundle) -> float:
    """
    Score sentiment risk contribution.

    Higher-risk sentiments (stressed, frustrated, evasive, anxious) produce
    higher sub-scores. Calm/neutral produce low sub-scores. Confidence
    scales the magnitude.

    Returns:
        Sub-score in [0, 100].
    """
    base_scores: dict[str, float] = {
        "calm":       0.0,
        "neutral":    10.0,
        "anxious":    55.0,
        "stressed":   70.0,
        "frustrated": 60.0,
        "evasive":    85.0,
    }
    base = base_scores.get(bundle.sentiment_label, 10.0)
    # Scale by confidence — low confidence dampens the signal
    return round(base * bundle.sentiment_confidence, 2)


def _score_intent(bundle: RiskSignalBundle) -> float:
    """
    Score intent risk contribution.

    Intents like refusal, deflection, and dispute carry higher inherent risk.
    Repayment promises are low risk. Confidence scales the result.

    Returns:
        Sub-score in [0, 100].
    """
    base_scores: dict[str, float] = {
        "repayment_promise":   5.0,
        "repayment_delay":    40.0,
        "refusal":            80.0,
        "deflection":         75.0,
        "information_seeking": 15.0,
        "dispute":            65.0,
        "unknown":            50.0,
    }
    base = base_scores.get(bundle.intent_label, 50.0)
    return round(base * bundle.intent_confidence, 2)


def _score_conditionality(bundle: RiskSignalBundle) -> float:
    """
    Score conditionality risk contribution.

    High conditionality means the customer's statements are heavily hedged
    or dependent on external factors — higher risk. Low conditionality
    means direct, unconditional statements — lower risk.

    Returns:
        Sub-score in [0, 100].
    """
    level_scores: dict[str, float] = {
        "low":    10.0,
        "medium": 50.0,
        "high":   85.0,
    }
    return level_scores.get(bundle.conditionality, 50.0)


def _score_obligation(bundle: RiskSignalBundle) -> float:
    """
    Score obligation strength risk contribution.

    Weaker obligations indicate less reliable commitments — higher risk.
    Strong obligations are lower risk.

    Returns:
        Sub-score in [0, 100].
    """
    strength_scores: dict[str, float] = {
        "strong":      5.0,
        "weak":        45.0,
        "conditional": 65.0,
        "none":        80.0,
    }
    return strength_scores.get(bundle.obligation_strength, 50.0)


def _score_contradictions(bundle: RiskSignalBundle) -> float:
    """
    Score contradiction risk contribution.

    Contradictions detected = high risk signal.
    No contradictions = minimal risk contribution.

    Returns:
        Sub-score in [0, 100].
    """
    return 90.0 if bundle.contradictions_detected else 5.0


def _score_audio_trust(bundle: RiskSignalBundle) -> float:
    """
    Score audio trust risk contribution.

    Combines noise level, call stability, and speech naturalness into
    a single audio trust sub-score. Suspicious naturalness is the
    strongest audio risk indicator.

    Returns:
        Sub-score in [0, 100].
    """
    noise_scores: dict[str, float] = {
        "low":    0.0,
        "medium": 25.0,
        "high":   55.0,
    }

    stability_scores: dict[str, float] = {
        "high":   0.0,
        "medium": 25.0,
        "low":    55.0,
    }

    naturalness_scores: dict[str, float] = {
        "normal":     0.0,
        "suspicious": 80.0,
    }

    noise = noise_scores.get(bundle.noise_level, 25.0)
    stability = stability_scores.get(bundle.call_stability, 25.0)
    naturalness = naturalness_scores.get(bundle.speech_naturalness, 0.0)

    # Naturalness is the dominant audio signal; noise and stability are secondary
    combined = (naturalness * 0.50) + (noise * 0.25) + (stability * 0.25)
    return round(combined, 2)


# ---------------------------------------------------------------------------
# Risk factor label mapping — traceable to input signals
# ---------------------------------------------------------------------------

_FACTOR_LABELS: dict[str, str] = {
    "sentiment":      "high_emotional_stress",
    "intent":         "risky_intent",
    "conditionality": "conditional_commitment",
    "obligation":     "weak_obligation",
    "contradictions": "contradictory_statements",
    "audio_trust":    "suspicious_audio_signals",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_risk(
    bundle: RiskSignalBundle,
    weights: dict[str, float] | None = None,
    fraud_threshold_high: float = FRAUD_THRESHOLD_HIGH,
    fraud_threshold_medium: float = FRAUD_THRESHOLD_MEDIUM,
    risk_factor_threshold: float = RISK_FACTOR_THRESHOLD,
) -> dict[str, Any]:
    """
    Compute deterministic risk assessment from a validated signal bundle.

    Steps:
        1. Score each signal dimension independently (0–100)
        2. Compute weighted sum using configurable weights
        3. Clamp final risk score to [0, 100]
        4. Classify fraud likelihood from fixed thresholds
        5. Compute confidence from input signal quality
        6. Collect key risk factors from elevated sub-scores

    Args:
        bundle:
            Validated RiskSignalBundle containing all upstream signals.
        weights:
            Optional custom weight dictionary. Keys must match DEFAULT_WEIGHTS.
            Values must sum to 1.0. If None, DEFAULT_WEIGHTS are used.
        fraud_threshold_high:
            Risk score at or above which fraud_likelihood = "high".
        fraud_threshold_medium:
            Risk score at or above which fraud_likelihood = "medium".
        risk_factor_threshold:
            Sub-score threshold for flagging a dimension as a key risk factor.

    Returns:
        Risk assessment dict:
            {
                "risk_score": int (0–100),
                "fraud_likelihood": "low" | "medium" | "high",
                "confidence": float (0.0–1.0),
                "key_risk_factors": list[str]
            }

    Raises:
        ValueError: If custom weights are invalid.
    """
    # --- Resolve weights ---
    active_weights = _validate_weights(weights or DEFAULT_WEIGHTS)

    # --- Score each dimension ---
    sub_scores: dict[str, float] = {
        "sentiment":      _score_sentiment(bundle),
        "intent":         _score_intent(bundle),
        "conditionality": _score_conditionality(bundle),
        "obligation":     _score_obligation(bundle),
        "contradictions": _score_contradictions(bundle),
        "audio_trust":    _score_audio_trust(bundle),
    }

    logger.info("Sub-scores: %s", sub_scores)

    # --- Weighted aggregation ---
    raw_score = sum(
        sub_scores[dim] * active_weights[dim] for dim in active_weights
    )
    risk_score = int(round(min(max(raw_score, 0.0), 100.0)))

    # --- Fraud likelihood classification ---
    if risk_score >= fraud_threshold_high:
        fraud_likelihood = "high"
    elif risk_score >= fraud_threshold_medium:
        fraud_likelihood = "medium"
    else:
        fraud_likelihood = "low"

    # --- Confidence ---
    # Confidence reflects how much information the upstream phases provided.
    # Higher upstream confidence = higher scorer confidence.
    # Contradictions and audio trust have no upstream confidence — they
    # contribute a fixed base confidence.
    confidence = _compute_confidence(bundle)

    # --- Key risk factors ---
    key_risk_factors: list[str] = [
        _FACTOR_LABELS[dim]
        for dim in sub_scores
        if sub_scores[dim] >= risk_factor_threshold
    ]

    result: dict[str, Any] = {
        "risk_score": risk_score,
        "fraud_likelihood": fraud_likelihood,
        "confidence": confidence,
        "key_risk_factors": key_risk_factors,
    }

    logger.info("Risk assessment: %s", result)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_weights(weights: dict[str, float]) -> dict[str, float]:
    """
    Validate that weights have the correct keys and sum to 1.0.

    Args:
        weights: Weight dictionary to validate.

    Returns:
        The validated weight dictionary (unchanged).

    Raises:
        ValueError: If keys are wrong or weights don't sum to ~1.0.
    """
    expected_keys = set(DEFAULT_WEIGHTS.keys())
    actual_keys = set(weights.keys())

    if actual_keys != expected_keys:
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        raise ValueError(
            f"Invalid weight keys. Missing: {missing}, Extra: {extra}"
        )

    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise ValueError(
            f"Weights must sum to 1.0, got {total:.4f}"
        )

    return weights


def _compute_confidence(bundle: RiskSignalBundle) -> float:
    """
    Compute overall risk assessment confidence from input signal quality.

    Combines sentiment confidence and intent confidence (the two signals
    with upstream confidence values). Contradictions, conditionality,
    obligation, and audio trust are deterministic / categorical —
    they contribute a fixed baseline.

    Returns:
        Confidence float in [0.0, 1.0], rounded to 2 decimal places.
    """
    # Weighted combination of upstream confidences
    # Sentiment and intent each contribute proportionally
    upstream_confidence = (
        bundle.sentiment_confidence * 0.40
        + bundle.intent_confidence * 0.40
    )

    # Deterministic signals provide a fixed confidence floor
    deterministic_base = 0.20

    confidence = upstream_confidence + deterministic_base
    # Clamp to [0.0, 1.0]
    confidence = min(max(confidence, 0.0), 1.0)
    return round(confidence, 2)
