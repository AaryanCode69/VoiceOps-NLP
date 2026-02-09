"""
src/nlp/translator.py
======================
Translator — VoiceOps Phase 3 (Transcript Translation)

Responsibility:
    - Accept raw timestamped transcript from Phase 2 (no speaker labels)
    - Translate ALL text to English using OpenAI (if not already English)
    - Preserve meaning exactly — no interpretation, no role inference
    - Return English-only transcript segments

Per docs/RULES.md §4 Phase 3:
    - Translation is handled by OpenAI APIs
    - Translation occurs as part of Phase 3 semantic structuring
    - No language assumptions — detect and translate as needed

Per docs/RULES.md §6:
    - LLMs MAY translate
    - LLMs MUST NOT assign risk, make legal assertions, or invent facts

This module does NOT:
    - Perform STT or audio processing
    - Perform acoustic diarization
    - Perform role classification or speaker attribution
    - Perform PII redaction
    - Perform intent, sentiment, obligation, or risk analysis
    - Generate summaries, scores, or identifiers
    - Store data or call RAG
"""

import logging
import os
import re
from typing import Any

from src.openai_retry import chat_completions_with_retry

logger = logging.getLogger("voiceops.nlp.translator")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def translate_transcript(
    transcript: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Translate all transcript segments to English.

    For each segment the original text is replaced with English text.
    If text is already in English, it is returned unchanged.

    Args:
        transcript: Phase 2 output — list of dicts with keys:
            start_time, end_time, text.

    Returns:
        List of dicts with the same structure, text now in English:
            [{"start_time": float, "end_time": float, "text": str}]
    """
    if not transcript:
        logger.warning("Empty transcript — nothing to translate.")
        return []

    texts = [seg["text"] for seg in transcript]

    # Batch translate all texts in a single OpenAI call
    translated_texts = _batch_translate(texts)

    # Build output preserving timestamps
    result: list[dict[str, Any]] = []
    for i, seg in enumerate(transcript):
        result.append({
            "start_time": seg["start_time"],
            "end_time": seg["end_time"],
            "text": translated_texts[i] if i < len(translated_texts) else seg["text"],
        })

    logger.info(
        "Translation complete: %d segments processed.",
        len(result),
    )
    return result


# ---------------------------------------------------------------------------
# Translation engine (OpenAI)
# ---------------------------------------------------------------------------


def _batch_translate(
    texts: list[str],
    target_language: str = "English",
) -> list[str]:
    """
    Translate a batch of texts to the target language using OpenAI.

    If OPENAI_API_KEY is not set or the API call fails, returns the
    original texts unchanged (graceful degradation).

    Args:
        texts: List of text strings to translate.
        target_language: Target language for translation.

    Returns:
        List of translated text strings (same length as input).
    """
    if not texts:
        return []

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning(
            "OPENAI_API_KEY not set — returning original texts without translation."
        )
        return list(texts)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        # Batch all texts into a single prompt with numbered lines
        numbered_lines = "\n".join(
            f"[{i+1}] {text}" for i, text in enumerate(texts)
        )

        prompt = (
            f"Translate each of the following numbered lines to {target_language}. "
            "If a line is already in English, return it unchanged. "
            "Preserve the meaning exactly — do not add, remove, or interpret anything. "
            "Do not infer speaker roles, sentiment, or intent. "
            "Return ONLY the translations, one per line, with the same numbering format:\n\n"
            f"{numbered_lines}"
        )

        response = chat_completions_with_retry(
            client,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4096,
        )

        raw_output = response.choices[0].message.content.strip()
        translated = _parse_numbered_response(raw_output, len(texts))

        if len(translated) == len(texts):
            logger.info("Batch translation successful: %d texts.", len(texts))
            return translated
        else:
            logger.warning(
                "Translation output count mismatch (expected %d, got %d). "
                "Falling back to original texts.",
                len(texts), len(translated),
            )
            return list(texts)

    except Exception as exc:
        logger.warning(
            "OpenAI translation failed: %s. Returning original texts.", exc,
        )
        return list(texts)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parse_numbered_response(
    raw_output: str,
    expected_count: int,
) -> list[str]:
    """
    Parse a numbered response like:
        [1] translated text one
        [2] translated text two

    Returns list of translated strings.
    """
    lines = raw_output.strip().split("\n")
    results: dict[int, str] = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match patterns like [1] text, 1. text, 1) text
        match = re.match(r"^\[?(\d+)\]?[.):]?\s*(.+)$", line)
        if match:
            idx = int(match.group(1))
            text = match.group(2).strip()
            results[idx] = text

    # Build ordered list
    translated = []
    for i in range(1, expected_count + 1):
        if i in results:
            translated.append(results[i])
        else:
            # Missing translation — will trigger fallback in caller
            break

    return translated
