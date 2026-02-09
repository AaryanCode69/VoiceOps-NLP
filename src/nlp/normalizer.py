"""
src/nlp/normalizer.py
======================
Text Normalizer — VoiceOps Phase 4

Responsibility:
    - Accept structured utterances from Phase 3 (utterance_structurer output)
    - Remove filler words (uh, um, hmm, etc.) without altering semantic meaning
    - Normalize common spoken contractions (gonna → going to, etc.)
    - Normalize whitespace (collapse runs, strip leading/trailing)
    - Preserve speaker labels, timing information, and original intent

Per RULES.md §6 — this is pipeline step 3 (text cleanup & normalization).

This module does NOT:
    - Perform PII redaction (handled by pii_redactor.py)
    - Perform intent, sentiment, obligation, or risk analysis
    - Call any LLM or external API
    - Generate summaries, scores, or identifiers
    - Modify speaker labels or timestamps
    - Store data or call RAG
"""

import logging
import re
from typing import Any

logger = logging.getLogger("voiceops.nlp.normalizer")


# ---------------------------------------------------------------------------
# Filler words — removed only when they appear as whole words
# ---------------------------------------------------------------------------

_FILLER_WORDS: list[str] = [
    "uh",
    "uhh",
    "uhhh",
    "um",
    "umm",
    "ummm",
    "hmm",
    "hmmm",
    "hmmmm",
    "er",
    "err",
    "ah",
    "ahh",
    "mhm",
    "uh-huh",
    "uh huh",
]

# Build a single compiled regex that matches any filler as a whole word.
# (?i) for case-insensitive; \b for word boundaries.
_FILLER_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:" + "|".join(re.escape(f) for f in _FILLER_WORDS) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Spoken-form → written-form normalization map
# ---------------------------------------------------------------------------
# Only safe, meaning-preserving substitutions are included.
# Each key is matched as a whole word (case-insensitive).

_SPOKEN_FORMS: dict[str, str] = {
    "gonna": "going to",
    "gotta": "got to",
    "wanna": "want to",
    "kinda": "kind of",
    "sorta": "sort of",
    "dunno": "do not know",
    "lemme": "let me",
    "gimme": "give me",
    "coulda": "could have",
    "shoulda": "should have",
    "woulda": "would have",
    "ain't": "is not",
    "y'all": "you all",
    "ima": "I am going to",
    "tryna": "trying to",
    "outta": "out of",
}

# Build pattern:  \b(gonna|gotta|...)\b  — case-insensitive
_SPOKEN_FORM_PATTERN: re.Pattern[str] = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _SPOKEN_FORMS) + r")\b",
    re.IGNORECASE,
)


def _replace_spoken_form(match: re.Match[str]) -> str:
    """Return the written form for a matched spoken variant."""
    return _SPOKEN_FORMS[match.group(0).lower()]


# ---------------------------------------------------------------------------
# Core normalization function (operates on a single text string)
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """
    Normalize a single text string.

    Steps (in order):
        1. Remove filler words
        2. Normalize spoken contractions to written form
        3. Collapse whitespace and strip

    Args:
        text: Raw utterance text from Phase 3.

    Returns:
        Normalized text with meaning preserved.
    """
    if not text or not text.strip():
        return text

    # Step 1: Remove fillers
    result = _FILLER_PATTERN.sub("", text)

    # Step 2: Normalize spoken forms
    result = _SPOKEN_FORM_PATTERN.sub(_replace_spoken_form, result)

    # Step 3: Collapse whitespace and strip
    result = re.sub(r"\s+", " ", result).strip()

    return result


# ---------------------------------------------------------------------------
# Public API — operates on the full utterance list
# ---------------------------------------------------------------------------


def normalize_utterances(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Normalize text in a list of structured utterances from Phase 3.

    Each utterance dict must have keys: speaker, text, start_time, end_time.
    Only the ``text`` field is modified. Speaker labels and timestamps are
    passed through unchanged. No utterances are added or dropped.

    Args:
        utterances: Phase 3 output — list of utterance dicts.

    Returns:
        New list of utterance dicts with normalized text.
    """
    if not utterances:
        logger.warning("Received empty utterance list — nothing to normalize.")
        return []

    normalized: list[dict[str, Any]] = []
    for utt in utterances:
        normalized.append({
            "speaker": utt["speaker"],
            "text": normalize_text(utt["text"]),
            "start_time": utt["start_time"],
            "end_time": utt["end_time"],
        })

    logger.info(
        "Text normalization complete for %d utterances.", len(normalized)
    )
    return normalized
