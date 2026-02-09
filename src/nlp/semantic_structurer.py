"""
src/nlp/semantic_structurer.py
===============================
Semantic Structurer — VoiceOps Phase 3 Orchestrator

Responsibility (LOCKED — Phase 3 ONLY):
    1. Accept timestamped transcript from Phase 2 (no speaker labels)
    2. Translate text to English if required (via translator.py)
    3. Split conversation into AGENT vs CUSTOMER using semantic reasoning
       (via role_splitter.py)
    4. Return structured, role-labeled utterances with confidence scores

Per docs/RULES.md §4 Phase 3:
    - Translation + role attribution via OpenAI
    - No audio processing, no diarization models
    - No forced speaker assignment
    - "speaker": "unknown" is allowed if confidence is low
    - No sentiment, intent, risk, PII, or summary logic

Per docs/RULES.md §6:
    - LLMs translate, attribute roles
    - LLMs do NOT assign risk or make decisions

This module does NOT:
    - Perform STT or audio processing
    - Perform acoustic diarization
    - Perform PII redaction
    - Perform sentiment, intent, obligation, or risk analysis
    - Generate summaries, scores, or identifiers
    - Store data or call RAG
"""

import logging
from typing import Any

from src.nlp.translator import translate_transcript
from src.nlp.role_splitter import attribute_roles

logger = logging.getLogger("voiceops.nlp.semantic_structurer")


# ---------------------------------------------------------------------------
# Public API — Phase 3 entry point
# ---------------------------------------------------------------------------


def structure_semantically(
    transcript: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Phase 3 pipeline: translate → attribute roles → return structured output.

    Accepts Phase 2 output (timestamped text segments, NO speaker labels)
    and returns a list of structured utterances with AGENT/CUSTOMER/unknown
    labels and confidence scores.

    Steps:
        1. Translate all transcript text to English (if not already English).
        2. Attribute AGENT / CUSTOMER / unknown roles via semantic reasoning.
        3. Return structured utterances matching the Phase 3 output contract.

    Args:
        transcript: Phase 2 output — list of dicts with keys:
            - "start_time": float
            - "end_time":   float
            - "text":       str (raw transcribed text, any language)

    Returns:
        List of structured utterance dicts:
            [{
                "speaker":    "AGENT" | "CUSTOMER" | "unknown",
                "text":       str (English),
                "confidence": float (0.0–1.0)
            }]

    Raises:
        ValueError: If transcript is empty or malformed.
    """
    if not transcript:
        logger.warning("Empty transcript received — returning empty list.")
        return []

    # Validate input shape
    _validate_transcript(transcript)

    # ------------------------------------------------------------------
    # Step 1: Translate to English if required
    # ------------------------------------------------------------------
    english_segments = translate_transcript(transcript)
    logger.info(
        "Phase 3 Step 1 complete: %d segments translated to English.",
        len(english_segments),
    )

    # ------------------------------------------------------------------
    # Step 2: Semantic role attribution (AGENT / CUSTOMER / unknown)
    # ------------------------------------------------------------------
    structured = attribute_roles(english_segments)
    logger.info(
        "Phase 3 Step 2 complete: %d utterances with role attribution.",
        len(structured),
    )

    # ------------------------------------------------------------------
    # Step 3: Final validation and cleanup
    # ------------------------------------------------------------------
    output = _finalize_output(structured)

    role_counts = {}
    for utt in output:
        role_counts[utt["speaker"]] = role_counts.get(utt["speaker"], 0) + 1
    logger.info(
        "Phase 3 complete: %d utterances — %s",
        len(output), role_counts,
    )

    return output


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_transcript(transcript: list[dict[str, Any]]) -> None:
    """Validate that transcript segments have required keys."""
    for i, seg in enumerate(transcript):
        if "text" not in seg:
            raise ValueError(
                f"Transcript segment {i} missing required key 'text'."
            )
        if "start_time" not in seg or "end_time" not in seg:
            raise ValueError(
                f"Transcript segment {i} missing timestamp keys "
                "('start_time' and/or 'end_time')."
            )


def _finalize_output(
    structured: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Ensure every utterance conforms to the Phase 3 output contract.

    Output contract:
        - "speaker" ∈ {"AGENT", "CUSTOMER", "unknown"}
        - "text" is a non-empty English string
        - "confidence" is a float in [0.0, 1.0]
        - No extra keys (no metadata leakage)
    """
    valid_speakers = {"AGENT", "CUSTOMER", "unknown"}
    output: list[dict[str, Any]] = []

    for utt in structured:
        speaker = utt.get("speaker", "unknown")
        if speaker not in valid_speakers:
            speaker = "unknown"

        text = utt.get("text", "").strip()
        if not text:
            continue  # Drop empty utterances

        confidence = utt.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        confidence = max(0.0, min(1.0, float(confidence)))

        output.append({
            "speaker": speaker,
            "text": text,
            "confidence": round(confidence, 2),
        })

    return output
