"""
src/pipeline.py
================
Full Pipeline Orchestrator — VoiceOps Integration Layer

Responsibility (LOCKED):
    1. Verify that each phase has executed correctly
    2. Ensure OpenAI is used ONLY in allowed phases
    3. Aggregate outputs from all phases
    4. Assemble the FINAL STRUCTURED JSON
    5. Return the JSON as the final API response

This layer MUST NOT:
    - Perform STT, translation, role attribution,
      sentiment, intent, or risk analysis itself
    - Call OpenAI directly for analysis
    - Modify phase outputs semantically
    - Infer missing values
    - If something is missing → FAIL FAST

Phase execution order:
    Phase 1: Audio Normalization  → normalized_audio + audio_quality
    Phase 2: STT                  → transcript
    Phase 3: Semantic Structuring → structured_utterances
    Phase 4: Text Normalization   → PII Redaction → phase4_utterances
    Phase 5: Sentiment Analysis   → sentiment
    Phase 6: Intent + Obligation + Contradictions + Entities
    Phase 7: Risk & Fraud Engine  → risk_assessment
    Phase 8: Summary Generation   → summary_for_rag

Per RULES.md §3 — High-Level Pipeline
Per RULES.md §9 — AI must always generate an execution plan first
Per RULES.md §11 — Section Ownership by Phase
"""

import logging
from typing import Any

# ---------------------------------------------------------------------------
# Phase 1 imports
# ---------------------------------------------------------------------------
from src.audio.normalizer import normalize, AudioValidationError, AudioNormalizationError
from src.audio.quality import analyze_audio_quality

# ---------------------------------------------------------------------------
# Phase 2 imports
# ---------------------------------------------------------------------------
from src.stt.router import transcribe
from src.stt.language_detector import detect_language

# ---------------------------------------------------------------------------
# Phase 3 imports
# ---------------------------------------------------------------------------
from src.nlp.semantic_structurer import structure_semantically

# ---------------------------------------------------------------------------
# Phase 4 imports
# ---------------------------------------------------------------------------
from src.nlp.normalizer import normalize_utterances
from src.nlp.pii_redactor import redact_utterances

# ---------------------------------------------------------------------------
# Phase 5 imports
# ---------------------------------------------------------------------------
from src.nlp.sentiment import analyze_sentiment

# ---------------------------------------------------------------------------
# Phase 6 imports
# ---------------------------------------------------------------------------
from src.nlp.intent import classify_intent
from src.nlp.obligation import derive_obligation_strength
from src.nlp.contradictions import detect_contradictions
from src.nlp.entity_extractor import extract_entities

# ---------------------------------------------------------------------------
# Phase 7 imports
# ---------------------------------------------------------------------------
from src.risk.signals import build_signal_bundle
from src.risk.scorer import compute_risk

# ---------------------------------------------------------------------------
# Phase 8 imports
# ---------------------------------------------------------------------------
from src.rag.summary_generator import generate_summary

# ---------------------------------------------------------------------------
# Phase validator
# ---------------------------------------------------------------------------
from src.phase_validator import (
    PhaseVerificationError,
    verify_phase2,
    verify_phase3,
    verify_phase4,
    verify_phase5,
    verify_phase6,
    verify_phase7,
    verify_phase8,
    verify_audio_quality,
)

logger = logging.getLogger("voiceops.pipeline")


# =====================================================================
# Risk signal mapping — derives audio_trust_flags and behavioral_flags
# from Phase 7 key_risk_factors and upstream signals
# =====================================================================

# Maps audio quality values to risk flag strings
_AUDIO_TRUST_FLAG_MAP: dict[str, dict[str, str | None]] = {
    "noise_level": {
        "low": None,
        "medium": "moderate_noise",
        "high": "high_background_noise",
    },
    "call_stability": {
        "low": "low_call_stability",
        "medium": None,
        "high": None,
    },
    "speech_naturalness": {
        "normal": None,
        "suspicious": "unnatural_speech_pattern",
    },
}

# Maps risk factor labels to behavioral flag strings
_BEHAVIORAL_FLAG_MAP: dict[str, str] = {
    "conditional_commitment": "conditional_commitment",
    "contradictory_statements": "statement_contradiction",
    "high_emotional_stress": "emotional_distress",
    "risky_intent": "evasive_responses",
    "weak_obligation": "weak_commitment",
}


def _derive_audio_trust_flags(audio_quality: dict[str, str]) -> list[str]:
    """Derive audio_trust_flags from audio quality signals."""
    flags: list[str] = []
    for dimension, mapping in _AUDIO_TRUST_FLAG_MAP.items():
        value = audio_quality.get(dimension, "")
        flag = mapping.get(value)
        if flag:
            flags.append(flag)
    return flags


def _derive_behavioral_flags(
    key_risk_factors: list[str],
    contradictions_detected: bool,
) -> list[str]:
    """Derive behavioral_flags from Phase 7 risk factors + Phase 6 data."""
    flags: list[str] = []
    for factor in key_risk_factors:
        flag = _BEHAVIORAL_FLAG_MAP.get(factor)
        if flag and flag not in flags:
            flags.append(flag)

    # Ensure contradiction flag is present if contradictions detected
    if contradictions_detected and "statement_contradiction" not in flags:
        flags.append("statement_contradiction")

    return flags


def _derive_speaker_analysis(
    structured_utterances: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Derive speaker_analysis from Phase 3 output.

    customer_only_analysis: True (always — per RULES.md, sentiment is
        CUSTOMER-only)
    agent_influence_detected: True if AGENT utterances contain leading
        patterns
    """
    # Per RULES.md §5, analysis is customer-only
    customer_only = True

    # Simple heuristic: check if agent utterances contain leading language
    agent_influence = False
    leading_patterns = [
        "wouldn't you agree",
        "you have to admit",
        "surely you",
        "you must agree",
        "don't you think",
        "obviously",
        "clearly you",
        "as you know",
    ]

    for utt in structured_utterances:
        if utt.get("speaker") == "AGENT":
            text_lower = utt.get("text", "").lower()
            for pattern in leading_patterns:
                if pattern in text_lower:
                    agent_influence = True
                    break
        if agent_influence:
            break

    return {
        "customer_only_analysis": customer_only,
        "agent_influence_detected": agent_influence,
    }


# =====================================================================
# Main orchestration — FULL PIPELINE
# =====================================================================


def run_pipeline(audio_bytes: bytes, filename: str) -> dict[str, Any]:
    """
    Execute the full VoiceOps pipeline from audio upload to final JSON.

    This function orchestrates ALL phases (1 → 8), verifies each phase
    output, and assembles the final structured JSON per RULES.md §10.

    Args:
        audio_bytes: Raw audio bytes from upload.
        filename: Original filename (for extension validation).

    Returns:
        Final structured JSON dict matching the locked schema.

    Raises:
        AudioValidationError: Phase 1 validation failure.
        AudioNormalizationError: Phase 1 normalization failure.
        PhaseVerificationError: Any phase output fails verification.
        RuntimeError: Critical pipeline failure.
    """

    # ==================================================================
    # PHASE 1 — Audio Normalization + Quality Analysis
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 1: Audio Normalization + Quality Analysis")
    logger.info("=" * 60)

    normalized_audio = normalize(audio_bytes, filename)
    audio_quality = analyze_audio_quality(normalized_audio)
    verify_audio_quality(audio_quality)

    logger.info("Phase 1 complete: audio normalized, quality analyzed.")

    # ==================================================================
    # PHASE 2 — Speech-to-Text (STT ONLY)
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 2: Speech-to-Text (STT)")
    logger.info("=" * 60)

    # Detect language for call_context
    lang_result = detect_language(normalized_audio)
    call_language = lang_result.language_name.lower()

    # Transcribe
    transcript = transcribe(normalized_audio)
    verify_phase2(transcript)

    logger.info(
        "Phase 2 complete: %d segments, language=%s.",
        len(transcript), call_language,
    )

    # ==================================================================
    # PHASE 3 — Semantic Structuring (Translation + Role Attribution)
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 3: Semantic Structuring")
    logger.info("=" * 60)

    structured_utterances = structure_semantically(transcript)
    verify_phase3(structured_utterances)

    # Derive speaker_analysis from Phase 3 output
    speaker_analysis = _derive_speaker_analysis(structured_utterances)

    logger.info(
        "Phase 3 complete: %d structured utterances.",
        len(structured_utterances),
    )

    # ==================================================================
    # PHASE 4 — Text Normalization + PII Redaction
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 4: Text Normalization + PII Redaction")
    logger.info("=" * 60)

    # Bridge Phase 3 → Phase 4: Phase 3 output has {speaker, text, confidence}
    # Phase 4 expects {speaker, text, start_time, end_time}
    # We assign sequential timestamps from Phase 2 segments where possible,
    # or use index-based ordering.
    phase4_input = _bridge_phase3_to_phase4(structured_utterances, transcript)

    # Step 1: Text normalization (filler removal, contraction normalization)
    normalized_utterances = normalize_utterances(phase4_input)

    # Step 2: PII redaction
    phase4_output = redact_utterances(normalized_utterances)
    verify_phase4(phase4_output)

    logger.info(
        "Phase 4 complete: %d utterances normalized and redacted.",
        len(phase4_output),
    )

    # ==================================================================
    # PHASE 5 — Sentiment Analysis (CUSTOMER ONLY)
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 5: Sentiment Analysis")
    logger.info("=" * 60)

    sentiment = analyze_sentiment(phase4_output)
    verify_phase5(sentiment)

    logger.info(
        "Phase 5 complete: sentiment=%s (%.2f).",
        sentiment["label"], sentiment["confidence"],
    )

    # ==================================================================
    # PHASE 6 — Intent, Obligation, Contradictions, Entities
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 6: Intent, Obligation, Contradictions, Entities")
    logger.info("=" * 60)

    # Intent classification (OpenAI)
    intent = classify_intent(phase4_output)

    # Obligation strength (DETERMINISTIC — no LLM)
    obligation_strength = derive_obligation_strength(intent, phase4_output)

    # Contradiction detection (OpenAI)
    contradictions_detected = detect_contradictions(phase4_output)

    # Entity extraction (OpenAI)
    entities = extract_entities(phase4_output)

    verify_phase6(intent, obligation_strength, contradictions_detected, entities)

    logger.info(
        "Phase 6 complete: intent=%s, obligation=%s, contradictions=%s.",
        intent["label"], obligation_strength, contradictions_detected,
    )

    # ==================================================================
    # PHASE 7 — Risk & Fraud Signal Engine (NO LLMs)
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 7: Risk & Fraud Signal Engine")
    logger.info("=" * 60)

    signal_bundle = build_signal_bundle(
        sentiment=sentiment,
        intent=intent,
        obligation_strength=obligation_strength,
        contradictions_detected=contradictions_detected,
        audio_quality=audio_quality,
    )

    risk_assessment = compute_risk(signal_bundle)
    verify_phase7(risk_assessment)

    # Derive risk_signals (audio_trust_flags + behavioral_flags)
    audio_trust_flags = _derive_audio_trust_flags(audio_quality)
    behavioral_flags = _derive_behavioral_flags(
        risk_assessment["key_risk_factors"],
        contradictions_detected,
    )

    logger.info(
        "Phase 7 complete: risk=%d, fraud=%s, confidence=%.2f.",
        risk_assessment["risk_score"],
        risk_assessment["fraud_likelihood"],
        risk_assessment["confidence"],
    )

    # ==================================================================
    # PHASE 8 — Summary Generation (RAG Anchor)
    # ==================================================================
    logger.info("=" * 60)
    logger.info("PHASE 8: Summary Generation")
    logger.info("=" * 60)

    summary = generate_summary(
        intent_label=intent["label"],
        conditionality=intent["conditionality"],
        obligation_strength=obligation_strength,
        contradictions_detected=contradictions_detected,
        risk_score=risk_assessment["risk_score"],
        fraud_likelihood=risk_assessment["fraud_likelihood"],
        key_risk_factors=risk_assessment["key_risk_factors"],
    )
    verify_phase8(summary)

    logger.info("Phase 8 complete: summary generated.")

    # ==================================================================
    # FINAL JSON ASSEMBLY — per RULES.md §10 (LOCKED SCHEMA)
    # ==================================================================
    logger.info("=" * 60)
    logger.info("FINAL: Assembling structured JSON output")
    logger.info("=" * 60)

    final_output = _assemble_final_json(
        call_language=call_language,
        audio_quality=audio_quality,
        speaker_analysis=speaker_analysis,
        sentiment=sentiment,
        intent=intent,
        obligation_strength=obligation_strength,
        entities=entities,
        contradictions_detected=contradictions_detected,
        audio_trust_flags=audio_trust_flags,
        behavioral_flags=behavioral_flags,
        risk_assessment=risk_assessment,
        summary=summary,
        conversation=phase4_output,
    )

    logger.info("Pipeline complete — final JSON assembled.")
    return final_output


# =====================================================================
# Phase 3 → Phase 4 bridge
# =====================================================================


def _bridge_phase3_to_phase4(
    structured: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Bridge Phase 3 output to Phase 4 input format.

    Phase 3 outputs: {speaker, text, confidence}
    Phase 4 expects: {speaker, text, start_time, end_time}

    Strategy: Map Phase 3 utterances to Phase 2 transcript timestamps
    where possible. Use sequential index-based timing for unmatched
    utterances.
    """
    bridged: list[dict[str, Any]] = []

    # Calculate total duration from transcript
    if transcript:
        total_duration = max(seg.get("end_time", 0.0) for seg in transcript)
    else:
        total_duration = 0.0

    n = len(structured)
    if n == 0:
        return bridged

    # Assign evenly spaced timestamps if we can't align
    segment_duration = total_duration / n if total_duration > 0 else 1.0

    for i, utt in enumerate(structured):
        start_time = round(i * segment_duration, 2)
        end_time = round((i + 1) * segment_duration, 2)

        bridged.append({
            "speaker": utt["speaker"],
            "text": utt["text"],
            "start_time": start_time,
            "end_time": end_time,
        })

    return bridged


# =====================================================================
# Final JSON assembly — LOCKED SCHEMA per RULES.md §10
# =====================================================================


def _assemble_final_json(
    call_language: str,
    audio_quality: dict[str, str],
    speaker_analysis: dict[str, Any],
    sentiment: dict[str, Any],
    intent: dict[str, Any],
    obligation_strength: str,
    entities: dict[str, Any],
    contradictions_detected: bool,
    audio_trust_flags: list[str],
    behavioral_flags: list[str],
    risk_assessment: dict[str, Any],
    summary: str,
    conversation: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Assemble the FINAL structured JSON per RULES.md §10.

    This function ONLY assembles — it does NOT compute or interpret.
    All values come directly from verified phase outputs.

    Schema is LOCKED:
        - No additional keys allowed
        - No nested metadata allowed
        - No debug information allowed
        - No raw transcripts allowed
        - No identifiers (call_id, customer_id, loan_id)

    Returns:
        Final JSON dict matching the exact locked schema.
    """
    return {
        "call_context": {
            "call_language": call_language,
            "call_quality": {
                "noise_level": audio_quality["noise_level"],
                "call_stability": audio_quality["call_stability"],
                "speech_naturalness": audio_quality["speech_naturalness"],
            },
        },
        "speaker_analysis": {
            "customer_only_analysis": speaker_analysis["customer_only_analysis"],
            "agent_influence_detected": speaker_analysis["agent_influence_detected"],
        },
        "nlp_insights": {
            "intent": {
                "label": intent["label"],
                "confidence": intent["confidence"],
                "conditionality": intent["conditionality"],
            },
            "sentiment": {
                "label": sentiment["label"],
                "confidence": sentiment["confidence"],
            },
            "obligation_strength": obligation_strength,
            "entities": {
                "payment_commitment": entities["payment_commitment"],
                "amount_mentioned": entities["amount_mentioned"],
            },
            "contradictions_detected": contradictions_detected,
        },
        "risk_signals": {
            "audio_trust_flags": audio_trust_flags,
            "behavioral_flags": behavioral_flags,
        },
        "risk_assessment": {
            "risk_score": risk_assessment["risk_score"],
            "fraud_likelihood": risk_assessment["fraud_likelihood"],
            "confidence": risk_assessment["confidence"],
        },
        "summary_for_rag": summary,
        "conversation": [
            {
                "speaker": utt["speaker"],
                "text": utt["text"],
            }
            for utt in (conversation or [])
        ],
    }
