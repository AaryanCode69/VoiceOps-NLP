"""
src/risk/signals.py
====================
Risk Signal Definitions — VoiceOps Phase 7

Responsibility:
    - Define typed structures for all input signals consumed by the risk scorer
    - Provide enums for audio trust signal categories
    - Validate and normalize raw upstream outputs into a unified signal bundle

Phase 7 inputs (per specification):
    - Sentiment output from Phase 5 (label + confidence)
    - Intent + conditionality + obligation strength from Phase 6
    - Contradiction flag from Phase 6
    - Audio trust signals (noise_level, call_stability, speech_naturalness)

This module does NOT:
    - Call any LLM or external API
    - Perform NLP analysis or text processing
    - Compute risk scores (that is scorer.py)
    - Generate summaries or explanations
    - Store data or generate identifiers
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger("voiceops.risk.signals")


# ---------------------------------------------------------------------------
# Audio trust signal enums — per RULES.md §11
# ---------------------------------------------------------------------------


class NoiseLevel(str, Enum):
    """Audio noise level classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CallStability(str, Enum):
    """Call connection stability classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SpeechNaturalness(str, Enum):
    """Speech naturalness classification."""

    NORMAL = "normal"
    SUSPICIOUS = "suspicious"


# ---------------------------------------------------------------------------
# Valid value sets for validation
# ---------------------------------------------------------------------------

_VALID_SENTIMENT_LABELS: set[str] = {
    "calm", "neutral", "stressed", "anxious", "frustrated", "evasive",
}

_VALID_INTENT_LABELS: set[str] = {
    "repayment_promise", "repayment_delay", "refusal", "deflection",
    "information_seeking", "dispute", "unknown",
}

_VALID_CONDITIONALITY: set[str] = {"low", "medium", "high"}

_VALID_OBLIGATION: set[str] = {"strong", "weak", "conditional", "none"}

_VALID_NOISE: set[str] = {e.value for e in NoiseLevel}
_VALID_STABILITY: set[str] = {e.value for e in CallStability}
_VALID_NATURALNESS: set[str] = {e.value for e in SpeechNaturalness}


# ---------------------------------------------------------------------------
# Signal bundle — typed dict holding all risk inputs
# ---------------------------------------------------------------------------


class RiskSignalBundle:
    """
    Immutable container for all input signals consumed by the risk scorer.

    Attributes:
        sentiment_label:        Sentiment classification (Phase 5)
        sentiment_confidence:   Confidence of sentiment classification (0–1)
        intent_label:           Intent classification (Phase 6)
        intent_confidence:      Confidence of intent classification (0–1)
        conditionality:         Conditionality level (Phase 6)
        obligation_strength:    Obligation strength (Phase 6)
        contradictions_detected: Within-call contradiction flag (Phase 6)
        noise_level:            Audio noise level
        call_stability:         Call connection stability
        speech_naturalness:     Speech naturalness classification
    """

    __slots__ = (
        "sentiment_label",
        "sentiment_confidence",
        "intent_label",
        "intent_confidence",
        "conditionality",
        "obligation_strength",
        "contradictions_detected",
        "noise_level",
        "call_stability",
        "speech_naturalness",
    )

    def __init__(
        self,
        sentiment_label: str,
        sentiment_confidence: float,
        intent_label: str,
        intent_confidence: float,
        conditionality: str,
        obligation_strength: str,
        contradictions_detected: bool,
        noise_level: str,
        call_stability: str,
        speech_naturalness: str,
    ) -> None:
        self.sentiment_label = sentiment_label
        self.sentiment_confidence = sentiment_confidence
        self.intent_label = intent_label
        self.intent_confidence = intent_confidence
        self.conditionality = conditionality
        self.obligation_strength = obligation_strength
        self.contradictions_detected = contradictions_detected
        self.noise_level = noise_level
        self.call_stability = call_stability
        self.speech_naturalness = speech_naturalness

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RiskSignalBundle):
            return NotImplemented
        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in self.__slots__
        )

    def __repr__(self) -> str:
        fields = ", ".join(
            f"{attr}={getattr(self, attr)!r}" for attr in self.__slots__
        )
        return f"RiskSignalBundle({fields})"


# ---------------------------------------------------------------------------
# Factory / validator — builds a validated RiskSignalBundle from raw dicts
# ---------------------------------------------------------------------------


def build_signal_bundle(
    sentiment: dict[str, Any],
    intent: dict[str, Any],
    obligation_strength: str,
    contradictions_detected: bool,
    audio_quality: dict[str, Any],
) -> RiskSignalBundle:
    """
    Build a validated RiskSignalBundle from upstream phase outputs.

    Args:
        sentiment:
            Phase 5 output — {"label": str, "confidence": float}
        intent:
            Phase 6 intent output — {"label": str, "confidence": float,
            "conditionality": str}
        obligation_strength:
            Phase 6 obligation output — "strong" | "weak" | "conditional" | "none"
        contradictions_detected:
            Phase 6 contradiction output — bool
        audio_quality:
            Audio trust signals — {"noise_level": str, "call_stability": str,
            "speech_naturalness": str}

    Returns:
        Validated RiskSignalBundle ready for risk scoring.

    Raises:
        ValueError: If any input value is invalid or missing.
    """
    # --- Sentiment validation ---
    s_label = sentiment.get("label", "")
    if s_label not in _VALID_SENTIMENT_LABELS:
        raise ValueError(
            f"Invalid sentiment label: {s_label!r}. "
            f"Must be one of {sorted(_VALID_SENTIMENT_LABELS)}"
        )

    s_conf = sentiment.get("confidence")
    if not isinstance(s_conf, (int, float)):
        raise ValueError(
            f"Sentiment confidence must be a number, got {type(s_conf).__name__}"
        )
    s_conf = float(s_conf)
    if s_conf < 0.0 or s_conf > 1.0:
        raise ValueError(f"Sentiment confidence out of range: {s_conf}")

    # --- Intent validation ---
    i_label = intent.get("label", "")
    if i_label not in _VALID_INTENT_LABELS:
        raise ValueError(
            f"Invalid intent label: {i_label!r}. "
            f"Must be one of {sorted(_VALID_INTENT_LABELS)}"
        )

    i_conf = intent.get("confidence")
    if not isinstance(i_conf, (int, float)):
        raise ValueError(
            f"Intent confidence must be a number, got {type(i_conf).__name__}"
        )
    i_conf = float(i_conf)
    if i_conf < 0.0 or i_conf > 1.0:
        raise ValueError(f"Intent confidence out of range: {i_conf}")

    cond = intent.get("conditionality", "")
    if cond not in _VALID_CONDITIONALITY:
        raise ValueError(
            f"Invalid conditionality: {cond!r}. "
            f"Must be one of {sorted(_VALID_CONDITIONALITY)}"
        )

    # --- Obligation validation ---
    if obligation_strength not in _VALID_OBLIGATION:
        raise ValueError(
            f"Invalid obligation strength: {obligation_strength!r}. "
            f"Must be one of {sorted(_VALID_OBLIGATION)}"
        )

    # --- Contradiction validation ---
    if not isinstance(contradictions_detected, bool):
        raise ValueError(
            f"contradictions_detected must be bool, "
            f"got {type(contradictions_detected).__name__}"
        )

    # --- Audio quality validation ---
    noise = audio_quality.get("noise_level", "")
    if noise not in _VALID_NOISE:
        raise ValueError(
            f"Invalid noise_level: {noise!r}. "
            f"Must be one of {sorted(_VALID_NOISE)}"
        )

    stability = audio_quality.get("call_stability", "")
    if stability not in _VALID_STABILITY:
        raise ValueError(
            f"Invalid call_stability: {stability!r}. "
            f"Must be one of {sorted(_VALID_STABILITY)}"
        )

    naturalness = audio_quality.get("speech_naturalness", "")
    if naturalness not in _VALID_NATURALNESS:
        raise ValueError(
            f"Invalid speech_naturalness: {naturalness!r}. "
            f"Must be one of {sorted(_VALID_NATURALNESS)}"
        )

    bundle = RiskSignalBundle(
        sentiment_label=s_label,
        sentiment_confidence=s_conf,
        intent_label=i_label,
        intent_confidence=i_conf,
        conditionality=cond,
        obligation_strength=obligation_strength,
        contradictions_detected=contradictions_detected,
        noise_level=noise,
        call_stability=stability,
        speech_naturalness=naturalness,
    )

    logger.info("RiskSignalBundle built: %s", bundle)
    return bundle
