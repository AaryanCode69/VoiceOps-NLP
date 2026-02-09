# src/nlp/__init__.py
# ====================
# NLP Extraction Layer — VoiceOps
#
# Phase 4 implements:
#   - Text cleanup & normalization (pipeline step 3, per RULES.md §6)
#   - PII redaction (mandatory, pipeline step 4, per RULES.md §7)
#
# Responsibility (future phases):
#   - Intent detection with confidence & conditionality (per RULES.md §8.1)
#   - Financial-context sentiment detection (per RULES.md §8.2)
#   - Obligation strength classification (per RULES.md §8.3)
#   - Contradiction detection (per RULES.md §8.4)
#
# CRITICAL: All NLP signals MUST be derived ONLY from CUSTOMER speech (per RULES.md §5)

import logging
from typing import Any

from src.nlp.normalizer import normalize_utterances
from src.nlp.pii_redactor import redact_utterances

logger = logging.getLogger("voiceops.nlp")


def normalize_and_redact(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Phase 4 pipeline: normalize text then redact PII.

    Accepts Phase 3 output (structured utterances) and returns
    compliance-safe text ready for downstream NLP, embedding, and storage.

    Steps (per RULES.md §6 ordering):
        1. Text normalization (filler removal, spoken-form expansion, whitespace)
        2. PII redaction (mandatory per RULES.md §7)

    Speaker labels and timestamps are never modified.
    No utterances are added or dropped.

    Args:
        utterances: Phase 3 output — list of utterance dicts with keys:
            speaker, text, start_time, end_time.

    Returns:
        Cleaned and PII-redacted utterance list, same structure.
    """
    normalized = normalize_utterances(utterances)
    redacted = redact_utterances(normalized)

    logger.info(
        "Phase 4 complete: %d utterances normalized and PII-redacted.",
        len(redacted),
    )
    return redacted
