"""
src/stt/utterance_structurer.py
================================
Utterance Structurer — VoiceOps Phase 3 (Updated for PyAnnote)

Responsibility:
    - Accept translated, role-classified utterances from Phase 3 pipeline
      (PyAnnote diarization → role classification → translation)
    - Merge consecutive same-speaker utterances separated by trivial gaps
      (diarization artifacts from chunked output)
    - Drop extremely short fragments that carry no meaningful speech
    - Sort utterances chronologically by start_time
    - Produce the final clean, ordered utterance list for downstream use
      (Phase 4: text normalization → PII redaction)

Phase 3 output contract:
    Each utterance has:
        - speaker:         "AGENT" or "CUSTOMER"
        - original_text:   original transcribed text (always present)
        - translated_text: English translation (CUSTOMER only, None for AGENT)
        - start_time:      float >= 0
        - end_time:        float > start_time

Per RULES.md §5:
    - Both AGENT and CUSTOMER utterances are preserved
    - Text content is NOT modified semantically
    - No NLP interpretation is applied

This module does NOT:
    - Perform STT, language detection, or text normalization
    - Perform PII redaction
    - Perform intent, sentiment, obligation, or risk analysis
    - Call any LLM or external API
    - Run any diarization model
    - Generate summaries, scores, or identifiers
    - Store data
"""

import logging
from typing import Any

logger = logging.getLogger("voiceops.stt.utterance_structurer")


# ---------------------------------------------------------------------------
# Configuration — thresholds for artifact cleanup
# ---------------------------------------------------------------------------

# Maximum gap (seconds) between two consecutive same-speaker utterances
# below which they are merged into a single utterance.
MERGE_GAP_THRESHOLD_SEC: float = 0.3

# Minimum duration (seconds) for a standalone utterance to be kept.
# Fragments shorter than this that cannot be merged are dropped.
MIN_UTTERANCE_DURATION_SEC: float = 0.1

# Minimum character count for text to be considered non-trivial.
# Utterances with stripped text shorter than this are dropped.
MIN_TEXT_LENGTH: int = 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def structure_utterances(
    translated_utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Clean and structure translated utterances into the final Phase 3 output.

    Steps:
        1. Sort utterances by start_time
        2. Merge consecutive same-speaker utterances separated by a small gap
        3. Drop fragments that are too short in duration or text length
        4. Re-sort and return

    Args:
        translated_utterances:
            List of utterance dicts from the Phase 3 pipeline
            (after diarization, role classification, and translation).
            Each dict must have keys:
                speaker, original_text, translated_text, start_time, end_time.

    Returns:
        Cleaned and ordered list of utterance dicts:
            [{
                "speaker": str,
                "original_text": str,
                "translated_text": str | None,
                "start_time": float,
                "end_time": float
            }]
    """
    if not translated_utterances:
        logger.warning("Received empty utterance list — nothing to structure.")
        return []

    # Step 1: Sort by start_time for chronological processing
    sorted_utts = sorted(translated_utterances, key=lambda u: u["start_time"])

    # Step 2: Merge consecutive same-speaker fragments
    merged = _merge_consecutive_same_speaker(sorted_utts)

    # Step 3: Drop trivially short fragments
    cleaned = _drop_short_fragments(merged)

    # Step 4: Final sort (should already be sorted, but guarantee it)
    cleaned.sort(key=lambda u: u["start_time"])

    logger.info(
        "Structuring complete: %d → %d utterances (merged %d, dropped %d).",
        len(translated_utterances),
        len(cleaned),
        len(sorted_utts) - len(merged),
        len(merged) - len(cleaned),
    )

    return cleaned


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _merge_consecutive_same_speaker(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge consecutive utterances from the same speaker when the gap between
    them is smaller than ``MERGE_GAP_THRESHOLD_SEC``.

    Merging rules:
        - Speaker labels must match exactly
        - Gap = next.start_time - current.end_time
        - Merged original_text is joined with a single space
        - Merged translated_text is joined with a single space (if both non-None)
        - Merged start_time = earliest start, end_time = latest end
        - Text is NOT modified semantically (only concatenated)
    """
    if not utterances:
        return []

    result: list[dict[str, Any]] = []
    current = _copy_utterance(utterances[0])

    for utt in utterances[1:]:
        gap = utt["start_time"] - current["end_time"]
        same_speaker = utt["speaker"] == current["speaker"]

        if same_speaker and gap <= MERGE_GAP_THRESHOLD_SEC:
            # Merge: extend current utterance
            current["original_text"] = (
                current["original_text"] + " " + utt["original_text"]
            )
            # Merge translated_text only if both are non-None
            if current["translated_text"] is not None and utt["translated_text"] is not None:
                current["translated_text"] = (
                    current["translated_text"] + " " + utt["translated_text"]
                )
            elif utt["translated_text"] is not None:
                current["translated_text"] = utt["translated_text"]
            # If current has translated_text but utt doesn't, keep current's

            current["end_time"] = max(current["end_time"], utt["end_time"])
        else:
            # Flush current, start new
            result.append(current)
            current = _copy_utterance(utt)

    # Flush the last accumulated utterance
    result.append(current)

    merged_count = len(utterances) - len(result)
    if merged_count > 0:
        logger.debug(
            "Merged %d consecutive same-speaker fragments.", merged_count,
        )

    return result


def _drop_short_fragments(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Remove utterances that are too short in duration or have trivially
    short text, as these are likely diarization artifacts.

    An utterance is dropped if:
        - Its duration (end_time - start_time) < MIN_UTTERANCE_DURATION_SEC
        - AND its stripped original_text length < MIN_TEXT_LENGTH

    Note: We only drop when BOTH conditions hold so that very short but
    meaningful single-word responses (e.g. "yes", "no") are preserved.
    """
    kept: list[dict[str, Any]] = []

    for utt in utterances:
        duration = utt["end_time"] - utt["start_time"]
        text_len = len(utt["original_text"].strip())

        if duration < MIN_UTTERANCE_DURATION_SEC and text_len < MIN_TEXT_LENGTH:
            logger.debug(
                "Dropping short fragment: %.2fs, %d chars, speaker=%s",
                duration, text_len, utt["speaker"],
            )
            continue

        kept.append(utt)

    return kept


def _copy_utterance(utt: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of an utterance dict (avoids mutation)."""
    return {
        "speaker": utt["speaker"],
        "original_text": utt["original_text"],
        "translated_text": utt.get("translated_text"),
        "start_time": utt["start_time"],
        "end_time": utt["end_time"],
    }
