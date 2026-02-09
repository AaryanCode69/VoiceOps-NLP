"""
src/nlp/pii_redactor.py
========================
PII Redactor — VoiceOps Phase 4

Responsibility:
    - Detect and redact personally identifiable information (PII) from text
    - Replace detected PII with safe tokens per RULES.md §7
    - Ensure no raw PII appears in any output

Per RULES.md §7 — PII redaction is MANDATORY before any storage, embedding,
or RAG use.

Redaction tokens:
    <CREDIT_CARD>   — Credit / debit card numbers
    <BANK_ACCOUNT>  — Bank account numbers
    <GOVT_ID>       — Aadhaar / SSN
    <OTP>           — One-time passwords / verification codes
    <PHONE_NUMBER>  — Phone numbers
    <EMAIL>         — Email addresses

This module does NOT:
    - Perform text normalization (handled by normalizer.py)
    - Perform intent, sentiment, obligation, or risk analysis
    - Call any LLM or external API
    - Generate summaries, scores, or identifiers
    - Modify speaker labels or timestamps
    - Store data or call RAG
"""

import logging
import re
from typing import Any

logger = logging.getLogger("voiceops.nlp.pii_redactor")


# ---------------------------------------------------------------------------
# PII detection patterns
# ---------------------------------------------------------------------------
# Patterns are applied in a specific order: more specific patterns first to
# avoid partial matches by broader patterns.

# Email — standard email regex; applied first since it contains digits that
# could otherwise match phone/OTP patterns.
_EMAIL_PATTERN: re.Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

# Credit / Debit card numbers:
#   - 13–19 digits, optionally separated by spaces or hyphens in groups
#   - Common formats: 4 groups of 4, or variations
_CREDIT_CARD_PATTERN: re.Pattern[str] = re.compile(
    r"\b"
    r"(?:\d[\s\-]?){12,18}\d"  # 13–19 digits with optional separators
    r"\b",
)

# Aadhaar number: 12 digits, optionally separated by spaces or hyphens
# in groups of 4 (e.g., 1234 5678 9012)
_AADHAAR_PATTERN: re.Pattern[str] = re.compile(
    r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
)

# SSN: 9 digits in format XXX-XX-XXXX or XXX XX XXXX
_SSN_PATTERN: re.Pattern[str] = re.compile(
    r"\b\d{3}[\s\-]\d{2}[\s\-]\d{4}\b",
)

# Phone numbers — broad patterns covering:
#   - International: +91 98765 43210, +1-555-123-4567
#   - Domestic: (555) 123-4567, 555-123-4567, 98765 43210
#   - 10-digit Indian numbers: 10 consecutive digits starting with 6-9
_PHONE_PATTERNS: list[re.Pattern[str]] = [
    # International format with country code
    re.compile(
        r"\+\d{1,3}[\s\-]?\(?\d{1,5}\)?[\s\-]?\d{1,5}[\s\-]?\d{1,5}"
    ),
    # Parenthesized area code: (555) 123-4567
    re.compile(
        r"\(\d{3,5}\)[\s\-]?\d{3,5}[\s\-]?\d{3,5}"
    ),
    # 10-digit Indian mobile: starts with 6-9
    re.compile(
        r"\b[6-9]\d{4}[\s\-]?\d{5}\b"
    ),
    # Hyphenated / spaced 10-digit: 555-123-4567
    re.compile(
        r"\b\d{3}[\s\-]\d{3}[\s\-]\d{4}\b"
    ),
]

# Bank account numbers: 9–18 digits (most Indian bank accounts are 9–18 digits)
# Context-aware: look for keywords like "account", "a/c", "acct" nearby
_BANK_ACCOUNT_CONTEXT_PATTERN: re.Pattern[str] = re.compile(
    r"(?:account|a/c|acct|acc)[\s\-.:;#]*(?:number|no|num|#)?[\s\-.:;#]*"
    r"(?:is|was|:)?\s*"
    r"(\d[\d\s\-]{7,17}\d)",
    re.IGNORECASE,
)

# OTP: 4-6 digit code with contextual keywords
_OTP_CONTEXT_PATTERN: re.Pattern[str] = re.compile(
    r"(?:otp|one[\s\-]?time[\s\-]?password|verification[\s\-]?code|"
    r"pin|code|cvv)[\s\-.:;#]*(?:is|was|:)?\s*(\d{4,6})\b",
    re.IGNORECASE,
)

# Reverse OTP: digit first, then context keyword
_OTP_REVERSE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(\d{4,6})\s+(?:is|was)\s+(?:the\s+)?(?:otp|one[\s\-]?time[\s\-]?password|"
    r"verification[\s\-]?code|pin|code)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Redaction logic
# ---------------------------------------------------------------------------


def redact_pii(text: str) -> str:
    """
    Detect and redact PII from a text string.

    Applies redaction patterns in a specific order to avoid conflicts:
        1. Email addresses
        2. OTPs (context-dependent, before generic digit patterns)
        3. Credit/debit card numbers (longest digit sequences)
        4. SSN
        5. Aadhaar
        6. Bank account numbers (context-dependent)
        7. Phone numbers

    Args:
        text: Input text, potentially containing PII.

    Returns:
        Text with all detected PII replaced by redaction tokens.
        Deterministic: same input always produces same output.
    """
    if not text or not text.strip():
        return text

    # 1. Emails
    result = _EMAIL_PATTERN.sub("<EMAIL>", text)

    # 2. OTPs (context-aware — must run before generic digit patterns)
    result = _OTP_CONTEXT_PATTERN.sub(
        lambda m: m.group(0)[: m.start(1) - m.start(0)] + "<OTP>",
        result,
    )
    result = _OTP_REVERSE_PATTERN.sub(
        lambda m: "<OTP>" + m.group(0)[m.end(1) - m.start(0) :],
        result,
    )

    # 3. Bank account numbers (context-dependent — before generic digit patterns)
    result = _BANK_ACCOUNT_CONTEXT_PATTERN.sub(
        lambda m: m.group(0)[: m.start(1) - m.start(0)] + "<BANK_ACCOUNT>",
        result,
    )

    # 4. Credit / debit card numbers (13–19 digits)
    result = _CREDIT_CARD_PATTERN.sub("<CREDIT_CARD>", result)

    # 5. SSN (XXX-XX-XXXX)
    result = _SSN_PATTERN.sub("<GOVT_ID>", result)

    # 6. Aadhaar (12 digits in groups of 4)
    result = _AADHAAR_PATTERN.sub("<GOVT_ID>", result)

    # 7. Phone numbers (multiple patterns, applied sequentially)
    for pattern in _PHONE_PATTERNS:
        result = pattern.sub("<PHONE_NUMBER>", result)

    return result


# ---------------------------------------------------------------------------
# Public API — operates on the full utterance list
# ---------------------------------------------------------------------------


def redact_utterances(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Redact PII from a list of structured utterances.

    Each utterance dict must have keys: speaker, text, start_time, end_time.
    Only the ``text`` field is modified. Speaker labels and timestamps are
    passed through unchanged. No utterances are added or dropped.

    Args:
        utterances: List of utterance dicts (typically from normalizer output).

    Returns:
        New list of utterance dicts with all PII redacted.
    """
    if not utterances:
        logger.warning("Received empty utterance list — nothing to redact.")
        return []

    redacted: list[dict[str, Any]] = []
    for utt in utterances:
        redacted.append({
            "speaker": utt["speaker"],
            "text": redact_pii(utt["text"]),
            "start_time": utt["start_time"],
            "end_time": utt["end_time"],
        })

    logger.info(
        "PII redaction complete for %d utterances.", len(redacted)
    )
    return redacted
