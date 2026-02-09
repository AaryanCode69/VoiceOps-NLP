"""
src/nlp/entity_extractor.py
=============================
Entity Extractor — VoiceOps Phase 6

Responsibility:
    - Accept Phase 4 output (normalized, PII-redacted utterances) and
      intent classification result from Phase 6
    - Extract structured entities: payment_commitment and amount_mentioned
    - Uses OpenAI API for extraction (per RULES.md §6 — LLMs may interpret)
    - Returns structured entity dict for final JSON assembly

Per RULES.md §11:
    - nlp_insights.entities is owned by Phase 6
    - Contains: payment_commitment (enum | null), amount_mentioned (number | null)

Per RULES.md §6:
    - LLMs MAY detect intent-related entities
    - LLMs MUST NOT assign risk, make legal assertions, or invent facts

This module does NOT:
    - Perform sentiment analysis or risk scoring
    - Generate summaries
    - Perform PII redaction (already done upstream)
    - Store data or generate identifiers
"""

import json
import logging
import os
from typing import Any, Optional

from src.openai_retry import chat_completions_with_retry

logger = logging.getLogger("voiceops.nlp.entity_extractor")


# ---------------------------------------------------------------------------
# Valid payment_commitment values
# ---------------------------------------------------------------------------

_VALID_PAYMENT_COMMITMENTS: set[str] = {
    "today",
    "tomorrow",
    "this_week",
    "next_week",
    "this_month",
    "next_month",
    "specific_date",
    "unspecified",
}


# ---------------------------------------------------------------------------
# OpenAI prompt — entity extraction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are a financial call entity extractor for an Indian financial services context. "
    "You analyze CUSTOMER speech from recorded financial calls "
    "(e.g., debt collection, loan inquiries, payment discussions, balance inquiries). "
    "You must extract two specific entities from the customer's speech.\n\n"
    "RULES:\n"
    "- You MUST return ONLY a valid JSON object with exactly two keys: "
    '"payment_commitment" and "amount_mentioned".\n'
    '- "payment_commitment" MUST be one of: "today", "tomorrow", '
    '"this_week", "next_week", "this_month", "next_month", '
    '"specific_date", "unspecified", or null.\n'
    "  - null means no payment timeline was mentioned at all.\n"
    '  - "unspecified" means a payment was promised but no timeframe given.\n'
    '- "amount_mentioned" MUST be a number (any monetary amount the customer '
    "mentions in the conversation) or null if no amount was mentioned.\n"
    "  - This includes: payment amounts, outstanding balances, loan amounts, "
    "EMI amounts, settlement amounts, dues, or any financial figure.\n"
    "  - Extract the numeric value only, no currency symbols or units.\n"
    "  - IMPORTANT: Convert Indian number words to their numeric values:\n"
    "    - 'lakh' or 'lac' = 100,000 (e.g., '4 lakh' = 400000)\n"
    "    - 'crore' = 10,000,000 (e.g., '1.5 crore' = 15000000)\n"
    "    - 'hazaar' or 'hazar' or 'thousand' = 1,000 (e.g., '50 hazaar' = 50000)\n"
    "    - Combinations like '2 lakh 50 thousand' = 250000\n"
    "  - If multiple amounts are mentioned, use the most recent or most "
    "specific one.\n\n"
    "CONTEXT:\n"
    "- This is an Indian financial services call. Amounts are typically in INR.\n"
    "- Customers may speak in English, Hindi, Hinglish, or other Indian languages "
    "(translated to English).\n"
    "- Extract amounts even if the customer is asking about a balance, disputing "
    "a charge, or discussing any financial figure — not only payment promises.\n"
    "- Do NOT include any other keys, explanations, reasoning, or text.\n"
    "- Do NOT infer risk, fraud, or sentiment.\n\n"
    "EXAMPLES:\n"
    'Customer says "I will pay 4 lakh next week":\n'
    '{"payment_commitment": "next_week", "amount_mentioned": 400000}\n\n'
    'Customer says "my outstanding is 2.5 lakh" (no commitment):\n'
    '{"payment_commitment": null, "amount_mentioned": 250000}\n\n'
    'Customer says "I can pay 50 thousand tomorrow":\n'
    '{"payment_commitment": "tomorrow", "amount_mentioned": 50000}\n\n'
    'Customer says "what is my balance?" (no amount, no commitment):\n'
    '{"payment_commitment": null, "amount_mentioned": null}\n'
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _filter_customer_utterances(
    utterances: list[dict[str, Any]],
) -> list[str]:
    """Extract text from CUSTOMER utterances only."""
    customer_texts: list[str] = []
    for utt in utterances:
        if utt.get("speaker", "").upper() == "CUSTOMER":
            text = utt.get("text", "").strip()
            if text:
                customer_texts.append(text)
    return customer_texts


def _parse_entity_response(raw: str) -> dict[str, Any]:
    """
    Parse and validate the OpenAI response into an entity dict.

    Returns:
        Validated entity dict with payment_commitment and amount_mentioned.

    Raises:
        ValueError: If response is not valid.
    """
    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI response is not valid JSON: {raw!r}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")

    payment = parsed.get("payment_commitment")
    amount = parsed.get("amount_mentioned")

    # Validate payment_commitment
    if payment is not None and payment not in _VALID_PAYMENT_COMMITMENTS:
        payment = None  # Graceful degradation for unexpected values

    # Validate amount_mentioned — accept int, float, or numeric strings
    if amount is not None:
        if isinstance(amount, (int, float)):
            amount = float(amount) if amount != 0 else None
        elif isinstance(amount, str):
            # Handle cases where LLM returns amount as a string
            cleaned = amount.replace(",", "").replace(" ", "").strip()
            try:
                amount = float(cleaned)
                if amount == 0:
                    amount = None
            except (ValueError, TypeError):
                logger.warning("Could not parse amount string: %r", amount)
                amount = None
        else:
            amount = None

    return {
        "payment_commitment": payment,
        "amount_mentioned": amount,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_entities(
    utterances: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Extract payment entities from CUSTOMER speech.

    Steps:
        1. Filter utterances to CUSTOMER speaker only
        2. Send to OpenAI for entity extraction
        3. Parse and validate response
        4. Return entity dict

    Args:
        utterances:
            Phase 4 output — list of utterance dicts (normalized, PII-redacted)
            with keys: speaker, text, start_time, end_time.

    Returns:
        Entity dict:
            {
                "payment_commitment": str | None,
                "amount_mentioned": float | None,
            }
    """
    _DEFAULT_ENTITIES = {
        "payment_commitment": None,
        "amount_mentioned": None,
    }

    customer_texts = _filter_customer_utterances(utterances)

    if not customer_texts:
        logger.warning(
            "No CUSTOMER utterances found — returning empty entities."
        )
        return dict(_DEFAULT_ENTITIES)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning(
            "OPENAI_API_KEY not set — returning empty entities."
        )
        return dict(_DEFAULT_ENTITIES)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        user_message = "CUSTOMER utterances from the call:\n" + "\n".join(
            f"[{i+1}] {text}" for i, text in enumerate(customer_texts)
        )

        response = chat_completions_with_retry(
            client,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=80,
        )

        raw_content = response.choices[0].message.content or ""

        logger.debug("OpenAI raw entity response: %s", raw_content)

        entities = _parse_entity_response(raw_content)

        logger.info("Entity extraction complete: %s", entities)
        return entities

    except Exception as exc:
        logger.warning(
            "Entity extraction failed: %s — returning empty entities.", exc
        )
        return dict(_DEFAULT_ENTITIES)
