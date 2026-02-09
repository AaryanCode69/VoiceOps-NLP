"""
src/stt/diarizer_validator.py
==============================
Diarization Validator — VoiceOps Phase 3

Responsibility:
    - Validate raw diarized transcript output from Phase 2
    - Ensure every utterance has a valid speaker label, timestamps, and text
    - Normalize speaker labels strictly to AGENT or CUSTOMER
    - Reject malformed utterances (missing fields, empty text, bad timestamps)

Per RULES.md §5:
    - Only AGENT and CUSTOMER labels are permitted
    - Both speakers are preserved (AGENT speech is not discarded)

This module does NOT:
    - Perform STT, language detection, or text normalization
    - Perform PII redaction
    - Perform intent, sentiment, obligation, or risk analysis
    - Call any LLM or external API
    - Generate summaries, scores, or identifiers
    - Store data
"""

import logging
from typing import Any

logger = logging.getLogger("voiceops.stt.diarizer_validator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SPEAKERS = {"AGENT", "CUSTOMER"}

# Known raw speaker label aliases that can be safely mapped
_SPEAKER_ALIAS_MAP: dict[str, str] = {
    "agent": "AGENT",
    "AGENT": "AGENT",
    "Agent": "AGENT",
    "customer": "CUSTOMER",
    "CUSTOMER": "CUSTOMER",
    "Customer": "CUSTOMER",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_diarized_transcript(
    raw_utterances: list[dict[str, Any]],
    *,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """
    Validate and normalize a raw diarized transcript from Phase 2.

    Each utterance dict is expected to have:
        - "speaker":    str   → must resolve to AGENT or CUSTOMER
        - "text":       str   → must be non-empty after stripping whitespace
        - "start_time": float → must be >= 0
        - "end_time":   float → must be > start_time

    Utterances that fail validation are logged and dropped (default) or
    cause a ``ValueError`` if *strict* mode is enabled.

    Args:
        raw_utterances: List of dicts from Phase 2 diarizer output.
        strict:         If True, raise on the first invalid utterance
                        instead of dropping it silently.

    Returns:
        List of validated utterance dicts with normalized speaker labels.

    Raises:
        TypeError:  If *raw_utterances* is not a list.
        ValueError: If *strict* is True and an invalid utterance is found.
    """
    if not isinstance(raw_utterances, list):
        raise TypeError(
            f"Expected list of utterance dicts, got {type(raw_utterances).__name__}"
        )

    if not raw_utterances:
        logger.warning("Received empty utterance list — nothing to validate.")
        return []

    validated: list[dict[str, Any]] = []

    for idx, utt in enumerate(raw_utterances):
        issues = _validate_single_utterance(utt, idx)

        if issues:
            msg = (
                f"Utterance [{idx}] validation failed: "
                + "; ".join(issues)
                + f" — raw value: {utt!r}"
            )
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            continue

        # Normalize speaker label
        normalized_speaker = _normalize_speaker_label(utt["speaker"])

        validated.append({
            "speaker": normalized_speaker,
            "text": utt["text"].strip(),
            "start_time": float(utt["start_time"]),
            "end_time": float(utt["end_time"]),
        })

    dropped = len(raw_utterances) - len(validated)
    if dropped > 0:
        logger.info(
            "Validation complete: %d/%d utterances kept (%d dropped).",
            len(validated), len(raw_utterances), dropped,
        )
    else:
        logger.info(
            "Validation complete: all %d utterances passed.", len(validated),
        )

    return validated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_single_utterance(utt: Any, idx: int) -> list[str]:
    """
    Check a single utterance dict for structural issues.

    Returns a list of human-readable issue strings (empty = valid).
    """
    issues: list[str] = []

    if not isinstance(utt, dict):
        issues.append(f"expected dict, got {type(utt).__name__}")
        return issues  # cannot check further

    # --- speaker ---
    speaker = utt.get("speaker")
    if speaker is None:
        issues.append("missing 'speaker' key")
    elif not isinstance(speaker, str):
        issues.append(f"'speaker' must be str, got {type(speaker).__name__}")
    elif _normalize_speaker_label(speaker) is None:
        issues.append(
            f"unrecognized speaker label '{speaker}' "
            f"(expected AGENT or CUSTOMER)"
        )

    # --- text ---
    text = utt.get("text")
    if text is None:
        issues.append("missing 'text' key")
    elif not isinstance(text, str):
        issues.append(f"'text' must be str, got {type(text).__name__}")
    elif not text.strip():
        issues.append("'text' is empty or whitespace-only")

    # --- start_time ---
    start = utt.get("start_time")
    if start is None:
        issues.append("missing 'start_time' key")
    elif not isinstance(start, (int, float)):
        issues.append(f"'start_time' must be numeric, got {type(start).__name__}")
    elif start < 0:
        issues.append(f"'start_time' is negative ({start})")

    # --- end_time ---
    end = utt.get("end_time")
    if end is None:
        issues.append("missing 'end_time' key")
    elif not isinstance(end, (int, float)):
        issues.append(f"'end_time' must be numeric, got {type(end).__name__}")
    elif isinstance(start, (int, float)) and start >= 0:
        if end <= start:
            issues.append(
                f"'end_time' ({end}) must be greater than 'start_time' ({start})"
            )

    return issues


def _normalize_speaker_label(raw_label: str) -> str | None:
    """
    Map a raw speaker label to a canonical AGENT or CUSTOMER label.

    Returns None if the label cannot be mapped.
    """
    if not isinstance(raw_label, str):
        return None

    # Direct alias lookup (covers common casing variants)
    mapped = _SPEAKER_ALIAS_MAP.get(raw_label)
    if mapped is not None:
        return mapped

    # Case-insensitive fallback
    lowered = raw_label.strip().lower()
    if lowered == "agent":
        return "AGENT"
    if lowered == "customer":
        return "CUSTOMER"

    return None
