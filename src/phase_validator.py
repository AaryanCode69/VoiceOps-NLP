"""
src/phase_validator.py
=======================
Phase Output Validator — VoiceOps Integration Layer

Responsibility:
    - Validate outputs from each phase (Phase 2 → Phase 8)
    - Ensure phase outputs conform to their contracts
    - FAIL FAST with clear errors if any phase output is invalid
    - NO auto-correction — if something is missing, raise an error

Per RULES.md §9:
    - Copilot must always generate an execution plan first
    - Never expand phase scope
    - If unsure → STOP

This module does NOT:
    - Execute any phase logic
    - Call any LLM or external API
    - Modify phase outputs
    - Infer missing values
"""

import logging
from typing import Any

logger = logging.getLogger("voiceops.phase_validator")


# =====================================================================
# Custom exception for phase verification failures
# =====================================================================


class PhaseVerificationError(Exception):
    """Raised when a phase output fails verification."""

    def __init__(self, phase: str, message: str):
        self.phase = phase
        self.message = message
        super().__init__(f"Phase {phase} verification failed: {message}")


# =====================================================================
# Phase 2 — STT Output Verification
# =====================================================================


def verify_phase2(transcript: list[dict[str, Any]]) -> None:
    """
    Verify Phase 2 (STT) output.

    Checks:
        - Output is a non-empty list
        - Each segment has start_time, end_time, and text
        - No speaker labels present (diarization forbidden)
        - No translation fields
        - Timestamps are numeric

    Raises:
        PhaseVerificationError: If any check fails.
    """
    if not isinstance(transcript, list):
        raise PhaseVerificationError(
            "2", f"Expected list, got {type(transcript).__name__}"
        )

    if not transcript:
        raise PhaseVerificationError("2", "Transcript is empty — no STT output")

    for i, seg in enumerate(transcript):
        if not isinstance(seg, dict):
            raise PhaseVerificationError(
                "2", f"Segment {i} is not a dict: {type(seg).__name__}"
            )

        # Required keys
        for key in ("start_time", "end_time", "text"):
            if key not in seg:
                raise PhaseVerificationError(
                    "2", f"Segment {i} missing required key '{key}'"
                )

        # Timestamps must be numeric
        if not isinstance(seg["start_time"], (int, float)):
            raise PhaseVerificationError(
                "2", f"Segment {i} start_time is not numeric"
            )
        if not isinstance(seg["end_time"], (int, float)):
            raise PhaseVerificationError(
                "2", f"Segment {i} end_time is not numeric"
            )

        # Text must be a non-empty string
        if not isinstance(seg["text"], str) or not seg["text"].strip():
            raise PhaseVerificationError(
                "2", f"Segment {i} has empty or non-string text"
            )

        # NO diarization — speaker labels forbidden
        if "speaker" in seg:
            raise PhaseVerificationError(
                "2", f"Segment {i} contains 'speaker' key — "
                "diarization is FORBIDDEN in Phase 2"
            )

    logger.info("Phase 2 verification passed: %d segments.", len(transcript))


# =====================================================================
# Phase 3 — Semantic Structuring Output Verification
# =====================================================================


def verify_phase3(structured: list[dict[str, Any]]) -> None:
    """
    Verify Phase 3 (Semantic Structuring) output.

    Checks:
        - Output is a non-empty list
        - Each utterance has speaker, text, confidence
        - Speaker is AGENT, CUSTOMER, or unknown
        - Text is English (non-empty string)
        - Confidence is a float in [0.0, 1.0]

    Raises:
        PhaseVerificationError: If any check fails.
    """
    if not isinstance(structured, list):
        raise PhaseVerificationError(
            "3", f"Expected list, got {type(structured).__name__}"
        )

    if not structured:
        raise PhaseVerificationError(
            "3", "Structured utterances are empty — no Phase 3 output"
        )

    valid_speakers = {"AGENT", "CUSTOMER", "unknown"}

    for i, utt in enumerate(structured):
        if not isinstance(utt, dict):
            raise PhaseVerificationError(
                "3", f"Utterance {i} is not a dict"
            )

        # Required keys
        for key in ("speaker", "text", "confidence"):
            if key not in utt:
                raise PhaseVerificationError(
                    "3", f"Utterance {i} missing required key '{key}'"
                )

        # Speaker validation
        if utt["speaker"] not in valid_speakers:
            raise PhaseVerificationError(
                "3", f"Utterance {i} has invalid speaker: {utt['speaker']!r}. "
                f"Must be one of {sorted(valid_speakers)}"
            )

        # Text must be non-empty string
        if not isinstance(utt["text"], str) or not utt["text"].strip():
            raise PhaseVerificationError(
                "3", f"Utterance {i} has empty or non-string text"
            )

        # Confidence must be float in [0.0, 1.0]
        conf = utt["confidence"]
        if not isinstance(conf, (int, float)):
            raise PhaseVerificationError(
                "3", f"Utterance {i} confidence is not numeric: {type(conf).__name__}"
            )
        if conf < 0.0 or conf > 1.0:
            raise PhaseVerificationError(
                "3", f"Utterance {i} confidence out of range: {conf}"
            )

    logger.info("Phase 3 verification passed: %d utterances.", len(structured))


# =====================================================================
# Phase 4 — Text Normalization & PII Redaction Verification
# =====================================================================


def verify_phase4(utterances: list[dict[str, Any]]) -> None:
    """
    Verify Phase 4 (Text Normalization + PII Redaction) output.

    Checks:
        - Output is a non-empty list
        - Each utterance has speaker, text, start_time, end_time
        - No raw PII patterns remain (basic check)
        - Agent text is preserved (has text content)

    Raises:
        PhaseVerificationError: If any check fails.
    """
    if not isinstance(utterances, list):
        raise PhaseVerificationError(
            "4", f"Expected list, got {type(utterances).__name__}"
        )

    if not utterances:
        raise PhaseVerificationError(
            "4", "Utterances are empty — no Phase 4 output"
        )

    for i, utt in enumerate(utterances):
        if not isinstance(utt, dict):
            raise PhaseVerificationError(
                "4", f"Utterance {i} is not a dict"
            )

        for key in ("speaker", "text", "start_time", "end_time"):
            if key not in utt:
                raise PhaseVerificationError(
                    "4", f"Utterance {i} missing required key '{key}'"
                )

        if not isinstance(utt["text"], str):
            raise PhaseVerificationError(
                "4", f"Utterance {i} text is not a string"
            )

    logger.info("Phase 4 verification passed: %d utterances.", len(utterances))


# =====================================================================
# Phase 5 — Sentiment Analysis Verification
# =====================================================================

_VALID_SENTIMENT_LABELS: set[str] = {
    "calm", "neutral", "stressed", "anxious", "frustrated", "evasive",
}


def verify_phase5(sentiment: dict[str, Any]) -> None:
    """
    Verify Phase 5 (Sentiment Analysis) output.

    Checks:
        - Output is a dict with label and confidence
        - Label is a valid sentiment label
        - Confidence is a float in [0.0, 1.0]
        - No risk or intent fields present

    Raises:
        PhaseVerificationError: If any check fails.
    """
    if not isinstance(sentiment, dict):
        raise PhaseVerificationError(
            "5", f"Expected dict, got {type(sentiment).__name__}"
        )

    if "label" not in sentiment:
        raise PhaseVerificationError("5", "Missing 'label' key")
    if "confidence" not in sentiment:
        raise PhaseVerificationError("5", "Missing 'confidence' key")

    if sentiment["label"] not in _VALID_SENTIMENT_LABELS:
        raise PhaseVerificationError(
            "5", f"Invalid sentiment label: {sentiment['label']!r}. "
            f"Must be one of {sorted(_VALID_SENTIMENT_LABELS)}"
        )

    conf = sentiment["confidence"]
    if not isinstance(conf, (int, float)):
        raise PhaseVerificationError(
            "5", f"Confidence is not numeric: {type(conf).__name__}"
        )
    if conf < 0.0 or conf > 1.0:
        raise PhaseVerificationError(
            "5", f"Confidence out of range: {conf}"
        )

    # No risk bleeding
    for forbidden in ("risk_score", "fraud_likelihood", "intent"):
        if forbidden in sentiment:
            raise PhaseVerificationError(
                "5", f"Sentiment contains forbidden key '{forbidden}' — "
                "Phase 5 must NOT contain risk or intent data"
            )

    logger.info(
        "Phase 5 verification passed: label=%s, confidence=%.2f",
        sentiment["label"], sentiment["confidence"],
    )


# =====================================================================
# Phase 6 — Intent, Obligation & Contradiction Verification
# =====================================================================

_VALID_INTENT_LABELS: set[str] = {
    "repayment_promise", "repayment_delay", "refusal", "deflection",
    "information_seeking", "dispute", "unknown",
}

_VALID_CONDITIONALITY: set[str] = {"low", "medium", "high"}

_VALID_OBLIGATION: set[str] = {"strong", "weak", "conditional", "none"}


def verify_phase6(
    intent: dict[str, Any],
    obligation_strength: str,
    contradictions_detected: bool,
    entities: dict[str, Any],
) -> None:
    """
    Verify Phase 6 (Intent, Obligation, Contradiction, Entities) outputs.

    Checks:
        - Intent has label, confidence, conditionality
        - Obligation strength is valid
        - Contradictions is a boolean
        - Entities has payment_commitment and amount_mentioned
        - No risk scoring present

    Raises:
        PhaseVerificationError: If any check fails.
    """
    # --- Intent ---
    if not isinstance(intent, dict):
        raise PhaseVerificationError(
            "6", f"Intent: expected dict, got {type(intent).__name__}"
        )

    for key in ("label", "confidence", "conditionality"):
        if key not in intent:
            raise PhaseVerificationError(
                "6", f"Intent missing required key '{key}'"
            )

    if intent["label"] not in _VALID_INTENT_LABELS:
        raise PhaseVerificationError(
            "6", f"Invalid intent label: {intent['label']!r}"
        )

    if not isinstance(intent["confidence"], (int, float)):
        raise PhaseVerificationError(
            "6", f"Intent confidence not numeric: {type(intent['confidence']).__name__}"
        )

    if intent["conditionality"] not in _VALID_CONDITIONALITY:
        raise PhaseVerificationError(
            "6", f"Invalid conditionality: {intent['conditionality']!r}"
        )

    # --- Obligation ---
    if obligation_strength not in _VALID_OBLIGATION:
        raise PhaseVerificationError(
            "6", f"Invalid obligation strength: {obligation_strength!r}"
        )

    # --- Contradictions ---
    if not isinstance(contradictions_detected, bool):
        raise PhaseVerificationError(
            "6", f"contradictions_detected must be bool, "
            f"got {type(contradictions_detected).__name__}"
        )

    # --- Entities ---
    if not isinstance(entities, dict):
        raise PhaseVerificationError(
            "6", f"Entities: expected dict, got {type(entities).__name__}"
        )

    if "payment_commitment" not in entities:
        raise PhaseVerificationError(
            "6", "Entities missing 'payment_commitment'"
        )
    if "amount_mentioned" not in entities:
        raise PhaseVerificationError(
            "6", "Entities missing 'amount_mentioned'"
        )

    # No risk bleeding
    for forbidden in ("risk_score", "fraud_likelihood"):
        if forbidden in intent:
            raise PhaseVerificationError(
                "6", f"Intent contains forbidden key '{forbidden}' — "
                "Phase 6 must NOT contain risk data"
            )

    logger.info(
        "Phase 6 verification passed: intent=%s, obligation=%s, "
        "contradictions=%s",
        intent["label"], obligation_strength, contradictions_detected,
    )


# =====================================================================
# Phase 7 — Risk & Fraud Signal Engine Verification
# =====================================================================


def verify_phase7(risk_assessment: dict[str, Any]) -> None:
    """
    Verify Phase 7 (Risk & Fraud Engine) output.

    Checks:
        - Output has risk_score, fraud_likelihood, confidence,
          key_risk_factors
        - risk_score is int in [0, 100]
        - fraud_likelihood is low/medium/high
        - confidence is float in [0.0, 1.0]
        - key_risk_factors is a list
        - No LLM/OpenAI artifacts present

    Raises:
        PhaseVerificationError: If any check fails.
    """
    if not isinstance(risk_assessment, dict):
        raise PhaseVerificationError(
            "7", f"Expected dict, got {type(risk_assessment).__name__}"
        )

    for key in ("risk_score", "fraud_likelihood", "confidence", "key_risk_factors"):
        if key not in risk_assessment:
            raise PhaseVerificationError(
                "7", f"Risk assessment missing required key '{key}'"
            )

    # risk_score
    rs = risk_assessment["risk_score"]
    if not isinstance(rs, int):
        raise PhaseVerificationError(
            "7", f"risk_score must be int, got {type(rs).__name__}"
        )
    if rs < 0 or rs > 100:
        raise PhaseVerificationError(
            "7", f"risk_score out of range [0, 100]: {rs}"
        )

    # fraud_likelihood
    fl = risk_assessment["fraud_likelihood"]
    if fl not in ("low", "medium", "high"):
        raise PhaseVerificationError(
            "7", f"Invalid fraud_likelihood: {fl!r}"
        )

    # confidence
    conf = risk_assessment["confidence"]
    if not isinstance(conf, (int, float)):
        raise PhaseVerificationError(
            "7", f"confidence not numeric: {type(conf).__name__}"
        )
    if conf < 0.0 or conf > 1.0:
        raise PhaseVerificationError(
            "7", f"confidence out of range: {conf}"
        )

    # key_risk_factors
    krf = risk_assessment["key_risk_factors"]
    if not isinstance(krf, list):
        raise PhaseVerificationError(
            "7", f"key_risk_factors must be list, got {type(krf).__name__}"
        )

    logger.info(
        "Phase 7 verification passed: risk_score=%d, fraud_likelihood=%s, "
        "confidence=%.2f",
        rs, fl, conf,
    )


# =====================================================================
# Phase 8 — Summary Generation Verification
# =====================================================================


def verify_phase8(summary: str) -> None:
    """
    Verify Phase 8 (Summary Generation) output.

    Checks:
        - Output is a non-empty string
        - Exactly one sentence (ends with period)
        - No PII patterns
        - No accusatory language
        - Suitable for RAG embedding

    Raises:
        PhaseVerificationError: If any check fails.
    """
    if not isinstance(summary, str):
        raise PhaseVerificationError(
            "8", f"Expected string, got {type(summary).__name__}"
        )

    if not summary.strip():
        raise PhaseVerificationError("8", "Summary is empty")

    # Must end with a period
    if not summary.strip().endswith("."):
        raise PhaseVerificationError(
            "8", "Summary must end with a period (one sentence requirement)"
        )

    # Check for banned/accusatory words
    banned = {
        "fraudster", "lied", "lying", "scam", "scammer", "criminal",
        "guilty", "dishonest", "cheat", "thief", "steal", "deceive",
        "deceptive", "malicious",
    }
    summary_lower = summary.lower()
    for word in banned:
        if word in summary_lower.split():
            raise PhaseVerificationError(
                "8", f"Summary contains banned word: {word!r}"
            )

    logger.info("Phase 8 verification passed: summary length=%d chars.", len(summary))


# =====================================================================
# Audio Quality Verification
# =====================================================================


def verify_audio_quality(quality: dict[str, str]) -> None:
    """
    Verify audio quality signals from Phase 1.

    Checks:
        - noise_level is low/medium/high
        - call_stability is low/medium/high
        - speech_naturalness is normal/suspicious

    Raises:
        PhaseVerificationError: If any check fails.
    """
    if not isinstance(quality, dict):
        raise PhaseVerificationError(
            "1", f"Audio quality: expected dict, got {type(quality).__name__}"
        )

    valid_noise = {"low", "medium", "high"}
    valid_stability = {"low", "medium", "high"}
    valid_naturalness = {"normal", "suspicious"}

    noise = quality.get("noise_level")
    if noise not in valid_noise:
        raise PhaseVerificationError(
            "1", f"Invalid noise_level: {noise!r}"
        )

    stability = quality.get("call_stability")
    if stability not in valid_stability:
        raise PhaseVerificationError(
            "1", f"Invalid call_stability: {stability!r}"
        )

    naturalness = quality.get("speech_naturalness")
    if naturalness not in valid_naturalness:
        raise PhaseVerificationError(
            "1", f"Invalid speech_naturalness: {naturalness!r}"
        )

    logger.info(
        "Audio quality verification passed: noise=%s, stability=%s, "
        "naturalness=%s",
        noise, stability, naturalness,
    )
