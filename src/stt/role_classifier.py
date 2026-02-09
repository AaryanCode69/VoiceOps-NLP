"""
src/stt/role_classifier.py
===========================
Role Classifier — VoiceOps Phase 3

Responsibility:
    - Accept speaker_A / speaker_B labeled utterances from diarizer_validator
    - Classify speakers into AGENT vs CUSTOMER using deterministic heuristics
    - Use optional lightweight OpenAI call ONLY if heuristics are inconclusive
    - Output utterances with AGENT / CUSTOMER labels

Classification signals (deterministic heuristics):
    - Linguistic patterns (agent-indicative vs customer-indicative phrases)
    - Turn-taking dominance (agents initiate more, follow scripts)
    - Question frequency (agents ask structured questions)
    - Word count in opening utterances (agents read from scripts)

Per RULES.md §5:
    - Only AGENT and CUSTOMER labels are permitted
    - Do NOT assume first speaker is customer
    - Do NOT assume longer speaker is customer
    - ALL downstream NLP must be derived from CUSTOMER speech only

This module does NOT:
    - Perform STT or speaker diarization
    - Translate text
    - Perform PII redaction
    - Perform intent, sentiment, obligation, or risk analysis
    - Generate summaries, scores, or identifiers
    - Store data or call RAG
"""

import logging
import os
import re
from typing import Any

logger = logging.getLogger("voiceops.stt.role_classifier")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ROLES = {"AGENT", "CUSTOMER"}

# How many utterances per speaker to analyze for role detection
_ROLE_DETECTION_WINDOW = 8

# Minimum confidence threshold for heuristic classification.
# If below this, the optional OpenAI fallback is triggered.
_HEURISTIC_CONFIDENCE_THRESHOLD = 1.0

# ---------------------------------------------------------------------------
# Linguistic patterns (deterministic heuristics)
# ---------------------------------------------------------------------------

# Phrases strongly indicating the speaker is an AGENT (outbound caller)
_AGENT_PHRASES = [
    r"\bcalling\s+(you\s+)?(back\s+)?regarding\b",
    r"\bcalling\s+(you\s+)?(back\s+)?about\b",
    r"\bcalling\s+from\b",
    r"\bthis\s+is\s+\w+\s+from\b",
    r"\bmy\s+name\s+is\s+\w+.*\bfrom\b",
    r"\bon\s+behalf\s+of\b",
    r"\bfor\s+verification\b",
    r"\bmay\s+i\s+speak\s+to\b",
    r"\bam\s+i\s+speaking\s+(to|with)\b",
    r"\bis\s+this\s+(mr|mrs|ms|miss|sir|madam)\b",
    r"\bi\s+am\s+calling\b",
    r"\bwe\s+are\s+calling\b",
    r"\byour\s+(account|loan|payment|emi|policy|application|form)\b",
    r"\bpending\s+(payment|amount|dues|emi)\b",
    r"\brecord(ing)?\s+(this\s+)?call\b",
    r"\bquality\s+(and\s+)?training\s+purposes\b",
    r"\byou\s+filled\s+out\b",
    r"\byou\s+(had\s+)?(applied|registered|submitted)\b",
    r"\bfollow\s*-?\s*up\b",
    r"\bcan\s+you\s+confirm\b",
    r"\blet\s+me\s+(explain|tell\s+you|inform)\b",
    r"\bplease\s+verify\b",
]

# Phrases strongly indicating the speaker is a CUSTOMER (called party)
_CUSTOMER_PHRASES = [
    r"\bwho\s+is\s+(this|calling)\b",
    r"\bwhy\s+are\s+you\s+calling\b",
    r"\bi\s+don'?t\s+understand\b",
    r"\bspeak\s+(a\s+little\s+)?slower\b",
    r"\bwhat\s+is\s+this\s+(about|regarding|call)\b",
    r"\bi\s+already\s+paid\b",
    r"\bi\s+didn'?t\s+(apply|register|fill)\b",
    r"\bstop\s+calling\b",
    r"\bdon'?t\s+call\s+me\b",
    r"\bi\s+(am\s+)?not\s+interested\b",
    r"\bhello\?",
    r"\byes\?$",
    r"\bwho\s+are\s+you\b",
    r"\bwhat\s+do\s+you\s+want\b",
    r"\bi\s+will\s+pay\b",
    r"\bgive\s+me\s+(some\s+)?(more\s+)?time\b",
    r"\bmy\s+salary\b",
]

_AGENT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _AGENT_PHRASES]
_CUSTOMER_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _CUSTOMER_PHRASES]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_roles(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Classify speaker_A / speaker_B into AGENT vs CUSTOMER.

    Uses deterministic heuristics first. Falls back to a lightweight
    OpenAI call ONLY if heuristics are inconclusive.

    Args:
        utterances: List of utterance dicts with keys:
            speaker (speaker_A/speaker_B), text, start_time, end_time.

    Returns:
        Same list with speaker labels replaced by AGENT / CUSTOMER.
    """
    if not utterances:
        logger.warning("Empty utterance list — nothing to classify.")
        return []

    # Collect unique speaker labels
    unique_speakers = list(dict.fromkeys(u["speaker"] for u in utterances))

    if len(unique_speakers) == 1:
        # Single speaker — default to CUSTOMER per RULES.md §5
        logger.info(
            "Single speaker '%s' detected. Mapping to CUSTOMER.",
            unique_speakers[0],
        )
        role_map = {unique_speakers[0]: "CUSTOMER"}
        return _apply_role_map(utterances, role_map)

    # --- Deterministic heuristic classification ---
    role_map, confidence = _heuristic_classify(utterances, unique_speakers)

    if confidence >= _HEURISTIC_CONFIDENCE_THRESHOLD:
        logger.info(
            "Heuristic classification confident (score=%.2f): %s",
            confidence, role_map,
        )
        return _apply_role_map(utterances, role_map)

    # --- Optional OpenAI fallback (only if heuristics are inconclusive) ---
    logger.info(
        "Heuristic classification inconclusive (score=%.2f). "
        "Attempting OpenAI fallback...",
        confidence,
    )
    llm_role_map = _openai_classify_fallback(utterances, unique_speakers)

    if llm_role_map is not None:
        logger.info("OpenAI role classification: %s", llm_role_map)
        return _apply_role_map(utterances, llm_role_map)

    # If OpenAI also fails, use the heuristic result anyway
    logger.warning(
        "OpenAI fallback failed. Using heuristic result: %s", role_map,
    )
    return _apply_role_map(utterances, role_map)


# ---------------------------------------------------------------------------
# Heuristic classification
# ---------------------------------------------------------------------------


def _heuristic_classify(
    utterances: list[dict[str, Any]],
    speakers: list[str],
) -> tuple[dict[str, str], float]:
    """
    Classify speakers using deterministic linguistic and structural signals.

    Returns:
        Tuple of (role_map, confidence_score).
        role_map: dict mapping each speaker label to AGENT or CUSTOMER.
        confidence_score: float indicating how confident the classification is.
    """
    speaker_scores: dict[str, dict[str, float]] = {}

    for spk in speakers:
        spk_utts = [u for u in utterances if u["speaker"] == spk]
        window = spk_utts[:_ROLE_DETECTION_WINDOW]

        agent_score = 0.0
        customer_score = 0.0

        # Signal 1: Linguistic pattern matching
        for utt in window:
            text = utt.get("text", "")
            if not text:
                continue
            for pattern in _AGENT_PATTERNS:
                if pattern.search(text):
                    agent_score += 1.0
            for pattern in _CUSTOMER_PATTERNS:
                if pattern.search(text):
                    customer_score += 1.0

        # Signal 2: Question frequency (agents ask structured questions)
        question_count = sum(
            1 for u in window if u.get("text", "").strip().endswith("?")
        )
        # High question rate suggests AGENT
        if len(window) > 0 and question_count / len(window) > 0.4:
            agent_score += 0.5

        # Signal 3: Turn-taking — who initiates the conversation
        all_sorted = sorted(utterances, key=lambda u: u["start_time"])
        if all_sorted and all_sorted[0]["speaker"] == spk:
            # First speaker gets a small agent boost (agents initiate calls)
            agent_score += 0.3

        # Signal 4: Word count in opening utterances
        # (agents read from scripts → longer opening statements)
        total_words = sum(len(u.get("text", "").split()) for u in window)
        speaker_scores[spk] = {
            "agent_score": agent_score,
            "customer_score": customer_score,
            "total_words": total_words,
        }

    logger.debug("Speaker role scores: %s", speaker_scores)

    # Determine roles: speaker with highest net AGENT score → AGENT
    best_agent = None
    best_net = -999.0

    for spk, scores in speaker_scores.items():
        net = scores["agent_score"] - scores["customer_score"]
        if net > best_net:
            best_net = net
            best_agent = spk

    # Tiebreaker: if scores are equal/zero → speaker with more words
    # in opening utterances is AGENT (agents read from scripts)
    if best_net == 0:
        logger.debug("Role scores tied at zero. Using word-count tiebreaker.")
        best_agent = max(
            speaker_scores,
            key=lambda s: speaker_scores[s]["total_words"],
        )

    # Build role map
    role_map: dict[str, str] = {}
    for spk in speakers:
        role_map[spk] = "AGENT" if spk == best_agent else "CUSTOMER"

    # Confidence = absolute value of the net score difference
    confidence = abs(best_net)

    logger.info(
        "Heuristic role map: %s (confidence=%.2f)", role_map, confidence,
    )

    return role_map, confidence


# ---------------------------------------------------------------------------
# Optional OpenAI fallback (lightweight)
# ---------------------------------------------------------------------------


def _openai_classify_fallback(
    utterances: list[dict[str, Any]],
    speakers: list[str],
) -> dict[str, str] | None:
    """
    Use a lightweight OpenAI call to classify speaker roles.

    Only called when deterministic heuristics are inconclusive.
    Sends only a small sample of utterances (no PII, no full transcript).

    Returns:
        Role map dict, or None if the call fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — skipping LLM role classification.")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        # Build a small sample of the conversation (first 6 turns)
        sample_turns = []
        sorted_utts = sorted(utterances, key=lambda u: u["start_time"])
        for utt in sorted_utts[:6]:
            sample_turns.append(f"{utt['speaker']}: {utt['text'][:100]}")

        conversation_sample = "\n".join(sample_turns)

        prompt = (
            "You are analyzing a financial phone call between two speakers. "
            "One is a collection AGENT from a financial institution, "
            "and the other is a CUSTOMER.\n\n"
            f"The speakers are labeled: {', '.join(speakers)}\n\n"
            "Here is a sample of the conversation:\n"
            f"{conversation_sample}\n\n"
            "Based on the conversation patterns, which speaker is the AGENT "
            "and which is the CUSTOMER?\n\n"
            "Respond with ONLY a JSON object like:\n"
            f'{{"{ speakers[0]}": "AGENT", "{speakers[1]}": "CUSTOMER"}}\n'
            "or\n"
            f'{{"{ speakers[0]}": "CUSTOMER", "{speakers[1]}": "AGENT"}}'
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )

        import json

        content = response.choices[0].message.content.strip()
        role_map = json.loads(content)

        # Validate the response
        if not isinstance(role_map, dict):
            logger.warning("OpenAI returned non-dict: %s", content)
            return None

        for spk in speakers:
            if spk not in role_map:
                logger.warning("OpenAI response missing speaker '%s'", spk)
                return None
            if role_map[spk] not in VALID_ROLES:
                logger.warning(
                    "OpenAI returned invalid role '%s' for '%s'",
                    role_map[spk], spk,
                )
                return None

        return role_map

    except Exception as exc:
        logger.warning("OpenAI role classification failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_role_map(
    utterances: list[dict[str, Any]],
    role_map: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Apply a role mapping to utterances, replacing speaker_A/speaker_B
    with AGENT/CUSTOMER.

    Returns a new list (does not mutate input).
    """
    result = []
    for utt in utterances:
        role = role_map.get(utt["speaker"], "CUSTOMER")
        result.append({
            "speaker": role,
            "text": utt["text"],
            "start_time": utt["start_time"],
            "end_time": utt["end_time"],
        })
    return result
