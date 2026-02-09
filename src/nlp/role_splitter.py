"""
src/nlp/role_splitter.py
=========================
Semantic Role Splitter — VoiceOps Phase 3

Responsibility:
    - Accept English-translated transcript segments (no speaker labels)
    - Use OpenAI to semantically attribute each utterance to
      AGENT, CUSTOMER, or unknown
    - Attach a confidence score (0.0–1.0) per utterance
    - Return structured role-labeled utterances

Per docs/RULES.md §4 Phase 3:
    - OpenAI APIs for semantic role attribution
    - "speaker": "unknown" is allowed if confidence is low
    - No forced speaker assignment
    - No diarization models

Per docs/RULES.md §6:
    - LLMs MAY attribute roles
    - LLMs MUST NOT assign risk, make legal assertions, or invent facts

This module does NOT:
    - Perform STT or audio processing
    - Perform acoustic diarization
    - Translate text (handled upstream by translator.py)
    - Perform PII redaction
    - Perform sentiment, intent, obligation, or risk analysis
    - Generate summaries, scores, or identifiers
    - Store data or call RAG
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger("voiceops.nlp.role_splitter")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SPEAKERS = {"AGENT", "CUSTOMER", "unknown"}

# Maximum number of utterances to send in a single OpenAI call
# to avoid token limits. Larger conversations are batched.
_MAX_BATCH_SIZE = 40


# ---------------------------------------------------------------------------
# OpenAI prompt — semantic role attribution
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are analyzing a financial phone call transcript. "
    "The call is between a collection AGENT from a financial institution "
    "and a CUSTOMER. The transcript has been split into numbered utterances "
    "but has NO speaker labels.\n\n"
    "Your task is to determine who is speaking in each utterance based on "
    "semantic content and conversational patterns:\n"
    "- AGENT: The caller from the financial institution (introduces themselves, "
    "asks structured questions, references account/loan/payment details, "
    "reads from scripts, states call recording notices).\n"
    "- CUSTOMER: The called party (responds to questions, makes commitments, "
    "expresses confusion, asks why they are being called, discusses personal "
    "financial situation).\n"
    "- unknown: Use this when you genuinely cannot determine the speaker "
    "from the content alone.\n\n"
    "RULES:\n"
    "- Return ONLY a valid JSON array with one object per utterance.\n"
    "- Each object MUST have exactly three keys: "
    '"speaker", "text", "confidence".\n'
    '- "speaker" MUST be one of: "AGENT", "CUSTOMER", "unknown".\n'
    '- "text" MUST be the exact text from the input (do not modify it).\n'
    '- "confidence" MUST be a float between 0.0 and 1.0 indicating how '
    "confident you are in the speaker attribution.\n"
    "- If confidence would be below 0.4, set speaker to \"unknown\".\n"
    "- Do NOT infer intent, sentiment, risk, or any other analysis.\n"
    "- Do NOT add any explanation, reasoning, or extra keys.\n"
    "- The output array MUST have the same number of elements as the input.\n\n"
    "EXAMPLE INPUT:\n"
    "[1] This call may be recorded for quality purposes\n"
    "[2] Hello? Who is this?\n"
    "[3] I am calling from XYZ Bank regarding your loan\n\n"
    "EXAMPLE OUTPUT:\n"
    '[{"speaker": "AGENT", "text": "This call may be recorded for quality purposes", "confidence": 0.95},\n'
    ' {"speaker": "CUSTOMER", "text": "Hello? Who is this?", "confidence": 0.90},\n'
    ' {"speaker": "AGENT", "text": "I am calling from XYZ Bank regarding your loan", "confidence": 0.97}]'
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def attribute_roles(
    english_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Attribute AGENT / CUSTOMER / unknown to each transcript segment
    using OpenAI semantic reasoning.

    Args:
        english_segments: English-translated transcript segments with keys:
            start_time, end_time, text.

    Returns:
        List of structured utterance dicts:
            [{"speaker": str, "text": str, "confidence": float}]
    """
    if not english_segments:
        logger.warning("Empty segments — nothing to attribute.")
        return []

    texts = [seg["text"].strip() for seg in english_segments]

    # Process in batches if needed
    all_results: list[dict[str, Any]] = []
    for batch_start in range(0, len(texts), _MAX_BATCH_SIZE):
        batch = texts[batch_start : batch_start + _MAX_BATCH_SIZE]
        batch_result = _attribute_batch(batch)
        all_results.extend(batch_result)

    logger.info(
        "Role attribution complete: %d utterances processed.",
        len(all_results),
    )
    return all_results


# ---------------------------------------------------------------------------
# OpenAI role attribution
# ---------------------------------------------------------------------------


def _attribute_batch(texts: list[str]) -> list[dict[str, Any]]:
    """
    Send a batch of texts to OpenAI for semantic role attribution.

    Falls back to "unknown" with confidence 0.0 if API is unavailable.

    Args:
        texts: List of English text strings (one per utterance).

    Returns:
        List of dicts with speaker, text, confidence.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning(
            "OPENAI_API_KEY not set — returning all utterances as 'unknown'."
        )
        return [
            {"speaker": "unknown", "text": t, "confidence": 0.0}
            for t in texts
        ]

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        # Build numbered utterance list for the prompt
        numbered_lines = "\n".join(
            f"[{i+1}] {text}" for i, text in enumerate(texts)
        )

        user_message = (
            f"Analyze this financial call transcript and attribute speaker roles.\n\n"
            f"{numbered_lines}"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=4096,
        )

        raw_output = response.choices[0].message.content.strip()
        parsed = _parse_role_response(raw_output, texts)

        if len(parsed) == len(texts):
            logger.info("OpenAI role attribution successful: %d utterances.", len(parsed))
            return parsed
        else:
            logger.warning(
                "Role attribution count mismatch (expected %d, got %d). "
                "Filling missing with 'unknown'.",
                len(texts), len(parsed),
            )
            return _fill_missing(parsed, texts)

    except Exception as exc:
        logger.warning(
            "OpenAI role attribution failed: %s. Returning all as 'unknown'.",
            exc,
        )
        return [
            {"speaker": "unknown", "text": t, "confidence": 0.0}
            for t in texts
        ]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_role_response(
    raw_output: str,
    original_texts: list[str],
) -> list[dict[str, Any]]:
    """
    Parse and validate the OpenAI JSON array response.

    Args:
        raw_output: Raw response string from OpenAI.
        original_texts: Original texts (used to enforce text preservation).

    Returns:
        List of validated utterance dicts.
    """
    # Strip markdown code fences if present
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[: -3]
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse role attribution JSON: %s", exc)
        return []

    if not isinstance(parsed, list):
        logger.warning("Expected JSON array, got %s", type(parsed).__name__)
        return []

    results: list[dict[str, Any]] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            continue

        speaker = item.get("speaker", "unknown")
        if speaker not in VALID_SPEAKERS:
            speaker = "unknown"

        # Use original text to prevent any LLM modification
        text = original_texts[i] if i < len(original_texts) else item.get("text", "")

        confidence = item.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        confidence = max(0.0, min(1.0, float(confidence)))

        # If confidence is too low, force "unknown"
        if confidence < 0.4:
            speaker = "unknown"

        results.append({
            "speaker": speaker,
            "text": text,
            "confidence": round(confidence, 2),
        })

    return results


def _fill_missing(
    parsed: list[dict[str, Any]],
    original_texts: list[str],
) -> list[dict[str, Any]]:
    """
    Fill in missing utterances when the parsed result is shorter than expected.
    Missing entries get speaker="unknown" and confidence=0.0.
    """
    result = list(parsed)
    for i in range(len(parsed), len(original_texts)):
        result.append({
            "speaker": "unknown",
            "text": original_texts[i],
            "confidence": 0.0,
        })
    return result
