"""
src/audio/vad.py
=================
Voice Activity Detection — VoiceOps (Phase 1 support)

Responsibility:
    - Detect speech vs silence regions in normalized audio
    - Provide silence gap locations for intelligent chunk boundary selection
    - Pre-filter chunks that contain no meaningful speech
    - Uses Silero VAD (lightweight, no GPU required)

Per RULES.md §3.1:
    - Audio MUST be chunked BEFORE STT
    - Chunks should contain meaningful speech to avoid empty Deepgram results

This module does NOT:
    - Perform STT, diarization, or any NLP
    - Modify the audio content
    - Perform speaker identification
    - Store data
"""

import logging
from typing import List, Tuple

import numpy as np

logger = logging.getLogger("voiceops.audio.vad")

# ---------------------------------------------------------------------------
# Module-level model cache (singleton — avoids reloading on every request)
# ---------------------------------------------------------------------------

_vad_model = None
_get_speech_timestamps_fn = None


def _load_vad_model():
    """Lazy-load and cache Silero VAD model."""
    global _vad_model, _get_speech_timestamps_fn

    if _vad_model is not None:
        return _vad_model, _get_speech_timestamps_fn

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "torch is required for VAD. Install with: pip install torch"
        ) from exc

    logger.info("Loading Silero VAD model (first request, will be cached)...")

    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )

    get_speech_timestamps = utils[0]

    _vad_model = model
    _get_speech_timestamps_fn = get_speech_timestamps

    logger.info("Silero VAD model loaded and cached.")
    return _vad_model, _get_speech_timestamps_fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_speech_segments(
    pcm_samples: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = 0.35,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 300,
) -> List[dict]:
    """
    Detect speech segments in audio using Silero VAD.

    Args:
        pcm_samples:             1-D float32 numpy array of audio samples
                                 normalized to [-1.0, 1.0].
        sample_rate:             Sample rate (must be 8000 or 16000).
        threshold:               VAD probability threshold.
        min_speech_duration_ms:  Ignore speech shorter than this.
        min_silence_duration_ms: Minimum silence gap to qualify as a boundary.

    Returns:
        List of dicts with ``start`` and ``end`` keys (in sample indices).
    """
    import torch

    model, get_speech_timestamps = _load_vad_model()

    tensor = torch.from_numpy(pcm_samples).float()

    speech_timestamps = get_speech_timestamps(
        tensor,
        model,
        sampling_rate=sample_rate,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
    )

    logger.debug("VAD detected %d speech segments.", len(speech_timestamps))
    return speech_timestamps


def find_silence_gaps(
    pcm_samples: np.ndarray,
    sample_rate: int = 16000,
    min_silence_duration_ms: int = 300,
) -> List[Tuple[int, int]]:
    """
    Find silence gaps (non-speech regions) in audio.

    Args:
        pcm_samples:             1-D float32 numpy array, normalized.
        sample_rate:             Sample rate.
        min_silence_duration_ms: Minimum gap duration to report.

    Returns:
        List of ``(start_sample, end_sample)`` tuples for each silence gap,
        ordered chronologically.
    """
    speech_segments = detect_speech_segments(
        pcm_samples,
        sample_rate=sample_rate,
        min_silence_duration_ms=min_silence_duration_ms,
    )

    total_samples = len(pcm_samples)
    gaps: List[Tuple[int, int]] = []

    if not speech_segments:
        # Entire audio is silence
        return [(0, total_samples)]

    # Gap before first speech
    if speech_segments[0]["start"] > 0:
        gaps.append((0, speech_segments[0]["start"]))

    # Gaps between speech segments
    for i in range(len(speech_segments) - 1):
        gap_start = speech_segments[i]["end"]
        gap_end = speech_segments[i + 1]["start"]
        if gap_end > gap_start:
            gaps.append((gap_start, gap_end))

    # Gap after last speech
    if speech_segments[-1]["end"] < total_samples:
        gaps.append((speech_segments[-1]["end"], total_samples))

    logger.debug("Found %d silence gaps.", len(gaps))
    return gaps


def chunk_has_speech(
    pcm_samples: np.ndarray,
    sample_rate: int = 16000,
    min_speech_duration_ms: int = 500,
) -> bool:
    """
    Check if an audio chunk contains meaningful speech.

    Args:
        pcm_samples:             1-D float32 numpy array (chunk only).
        sample_rate:             Sample rate.
        min_speech_duration_ms:  Minimum total speech to qualify.

    Returns:
        True if the chunk has speech above the threshold duration.
    """
    segments = detect_speech_segments(
        pcm_samples,
        sample_rate=sample_rate,
        min_speech_duration_ms=min_speech_duration_ms,
    )

    total_speech_samples = sum(s["end"] - s["start"] for s in segments)
    total_speech_ms = (total_speech_samples / sample_rate) * 1000

    has = total_speech_ms >= min_speech_duration_ms

    if not has:
        logger.debug(
            "Chunk has only %.0fms of speech (threshold: %dms) — marking as silent.",
            total_speech_ms,
            min_speech_duration_ms,
        )

    return has
