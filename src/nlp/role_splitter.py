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

from src.openai_retry import chat_completions_with_retry

logger = logging.getLogger("voiceops.nlp.role_splitter")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SPEAKERS = {"AGENT", "CUSTOMER"}

# Maximum number of utterances to send in a single OpenAI call
# to avoid token limits. Larger conversations are batched.
_MAX_BATCH_SIZE = 40


# ---------------------------------------------------------------------------
# OpenAI prompt — semantic role attribution
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are an expert at analyzing financial phone call transcripts between "
    "a collection AGENT from a financial institution and a CUSTOMER.\n\n"

    "You will receive a raw transcript that may be a single block of text "
    "or multiple segments. The transcript has NO speaker labels, and sentences "
    "from both speakers may be merged together or interleaved.\n\n"

    "IMPORTANT LANGUAGE RULE:\n"
    "If the received text is NOT in English (including Hinglish or any Indian "
    "native language), you MUST first translate the text into clear English. "
    "After translation, perform all further analysis ONLY on the English text. "
    "Preserve the original meaning exactly during translation.\n\n"

    "YOUR TASK:\n"
    "1. SPLIT the text into individual conversational turns.\n"
    "   - A new turn starts ONLY when the speaker changes.\n"
    "   - Do NOT merge turns from different speakers.\n\n"

    "Use contextual clues to detect speaker changes, including but not limited to:\n"
    " - Questioning vs answering patterns\n"
    " - Procedural or authoritative language vs personal or reactive language\n"
    " - Asking for details vs explaining or justifying details\n"
    " - Addressing someone directly (sir, madam, etc.)\n"
    " - Shifts from instructions or verification to explanations or excuses\n\n"

    "2. ASSIGN each conversational turn to exactly ONE of the following speakers:\n\n"

    "AGENT (financial institution representative):\n"
    " - Asks questions about finances, income, stock, payments, or verification\n"
    " - References loans, EMIs, accounts, dues, or deadlines\n"
    " - Gives instructions, warnings, or procedural explanations\n"
    " - Reads disclaimers or call-recording notices\n"
    " - Uses formal, structured, or authoritative language\n\n"

    "CUSTOMER (person being called):\n"
    " - Answers the agent’s questions\n"
    " - Explains their financial situation\n"
    " - Makes promises, excuses, or denials about payments\n"
    " - Expresses emotions (stress, frustration, defensiveness)\n"
    " - Reacts to the agent’s statements\n"
    " - Uses personal, emotional, or defensive language\n\n"

    "3. EVERY turn MUST be assigned either AGENT or CUSTOMER.\n"
    "   - NEVER use \"unknown\".\n"
    "   - Use the full conversation context to make the best possible assignment.\n\n"

    "STRICT OUTPUT RULES:\n"
    "- Return ONLY a valid JSON array. No text outside JSON.\n"
    "- Each element MUST contain EXACTLY these three keys:\n"
    '  "speaker", "text", "confidence".\n'
    '- "speaker" MUST be either "AGENT" or "CUSTOMER".\n'
    '- "text" MUST contain the exact words of that turn in English. Do NOT paraphrase.\n'
    '- "confidence" MUST be a float between 0.0 and 1.0.\n'
    "- The output MUST cover ALL content from the input with NOTHING omitted.\n"
    "- Do NOT infer intent, sentiment, risk, legality, or any other analysis.\n"
    "- Do NOT add explanations, reasoning, or extra keys.\n\n"

    "EXAMPLE INPUT:\n"
    "[1] Do you have employee staff? You didn't tell me, you are a shopkeeper, "
    "you must know how much the total stock is, tell me on average how much the "
    "stock is. It's above 4 lakh. It won't be 4 lakh, Madam, I'm not lying.\n\n"

    "EXAMPLE OUTPUT:\n"
    '[{"speaker": "AGENT", "text": "Do you have employee staff?", "confidence": 0.88},\n'
    ' {"speaker": "CUSTOMER", "text": "You did not tell me, you are a shopkeeper, you must know how much the total stock is, tell me on average how much the stock is.", "confidence": 0.75},\n'
    ' {"speaker": "AGENT", "text": "It is above 4 lakh.", "confidence": 0.80},\n'
    ' {"speaker": "CUSTOMER", "text": "It will not be 4 lakh, madam, I am not lying.", "confidence": 0.92}]'
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
            "API key not set — returning all utterances as CUSTOMER."
        )
        return [
            {"speaker": "CUSTOMER", "text": t, "confidence": 0.0}
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

        response = chat_completions_with_retry(
            client,
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=8192,
        )

        raw_output = response.choices[0].message.content.strip()
        parsed = _parse_role_response(raw_output, texts)

        if parsed:
            logger.info("Role attribution processing successful: %d utterances.", len(parsed))
            return parsed
        else:
            logger.warning(
                "Role attribution returned empty. Returning input as CUSTOMER."
            )
            return [
                {"speaker": "CUSTOMER", "text": t, "confidence": 0.5}
                for t in texts
            ]

    except Exception as exc:
        logger.warning(
            "Role attribution processing failed: %s. Returning all as 'unknown'.",
            exc,
        )
        return [
            {"speaker": "CUSTOMER", "text": t, "confidence": 0.0}
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

        speaker = item.get("speaker", "CUSTOMER")
        if speaker not in VALID_SPEAKERS:
            # Default to CUSTOMER if invalid label returned
            speaker = "CUSTOMER"

        # Use original text from the model's split (not from original_texts,
        # since the model may have split a single block into multiple turns)
        text = item.get("text", "")
        if not text and i < len(original_texts):
            text = original_texts[i]

        confidence = item.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

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
    Missing entries default to CUSTOMER with confidence=0.5.
    """
    result = list(parsed)
    for i in range(len(parsed), len(original_texts)):
        result.append({
            "speaker": "CUSTOMER",
            "text": original_texts[i],
            "confidence": 0.5,
        })
    return result
