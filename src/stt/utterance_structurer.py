"""
src/stt/utterance_structurer.py
================================
Utterance Structurer — VoiceOps Phase 3

Responsibility:
    - Accept validated utterances from diarizer_validator
    - Merge consecutive same-speaker utterances separated by trivial gaps
      (diarization artifacts)
    - Drop extremely short fragments that carry no meaningful speech
    - Sort utterances chronologically by start_time
    - Produce the final clean, ordered utterance list for downstream use

Per RULES.md §5:
    - Both AGENT and CUSTOMER utterances are preserved
    - Text content is NOT modified semantically
    - No NLP interpretation is applied

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
    validated_utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Clean and structure validated utterances into the final Phase 3 output.

    Steps:
        1. Sort utterances by start_time
        2. Merge consecutive same-speaker utterances separated by a small gap
        3. Drop fragments that are too short in duration or text length
        4. Re-sort and return

    Args:
        validated_utterances:
            List of utterance dicts already validated by
            ``diarizer_validator.validate_diarized_transcript``.
            Each dict must have keys: speaker, text, start_time, end_time.

    Returns:
        Cleaned and ordered list of utterance dicts:
            [{ "speaker": str, "text": str, "start_time": float, "end_time": float }]
    """
    if not validated_utterances:
        logger.warning("Received empty utterance list — nothing to structure.")
        return []

    # Step 1: Sort by start_time for chronological processing
    sorted_utts = sorted(validated_utterances, key=lambda u: u["start_time"])

    # Step 2: Merge consecutive same-speaker fragments
    merged = _merge_consecutive_same_speaker(sorted_utts)

    # Step 3: Drop trivially short fragments
    cleaned = _drop_short_fragments(merged)

    # Step 4: Final sort (should already be sorted, but guarantee it)
    cleaned.sort(key=lambda u: u["start_time"])

    logger.info(
        "Structuring complete: %d → %d utterances (merged %d, dropped %d).",
        len(validated_utterances),
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
        - Merged text is joined with a single space
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
            current["text"] = current["text"] + " " + utt["text"]
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
        - AND its stripped text length < MIN_TEXT_LENGTH

    Note: We only drop when BOTH conditions hold so that very short but
    meaningful single-word responses (e.g. "yes", "no") are preserved.
    """
    kept: list[dict[str, Any]] = []

    for utt in utterances:
        duration = utt["end_time"] - utt["start_time"]
        text_len = len(utt["text"].strip())

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
        "text": utt["text"],
        "start_time": utt["start_time"],
        "end_time": utt["end_time"],
    }
