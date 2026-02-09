"""
src/audio/quality.py
=====================
Audio Quality Analyzer — VoiceOps Phase 1

Responsibility:
    - Analyze normalized audio for basic call quality signals
    - Produce noise_level, call_stability, and speech_naturalness ratings
    - Output contributes to call_context.call_quality in final JSON

Per RULES.md §4 Phase 1:
    - Detect basic call quality signals
    - Noise estimation
    - Call stability heuristics

This module does NOT:
    - Perform STT, translation, or NLP
    - Call LLMs or external APIs
    - Store data or generate identifiers
"""

import io
import logging
import wave

import numpy as np

logger = logging.getLogger("voiceops.audio.quality")


# ---------------------------------------------------------------------------
# Thresholds (empirically tuned for 16 kHz mono WAV)
# ---------------------------------------------------------------------------

# RMS energy thresholds for noise level classification
_NOISE_THRESHOLD_HIGH: float = 0.08
_NOISE_THRESHOLD_MEDIUM: float = 0.03

# Stability: ratio of zero-crossing rate variance to mean
_STABILITY_THRESHOLD_LOW: float = 1.5
_STABILITY_THRESHOLD_MEDIUM: float = 0.8

# Speech naturalness: based on pitch regularity heuristics
# High autocorrelation regularity → suspicious (robotic/TTS)
_NATURALNESS_REGULARITY_THRESHOLD: float = 0.92


def analyze_audio_quality(audio_bytes: bytes) -> dict[str, str]:
    """
    Analyze audio quality from normalized WAV bytes.

    Args:
        audio_bytes: Normalized audio (mono 16 kHz WAV bytes).

    Returns:
        Dict with keys:
            - noise_level: "low" | "medium" | "high"
            - call_stability: "low" | "medium" | "high"
            - speech_naturalness: "normal" | "suspicious"
    """
    try:
        pcm_float = _wav_to_float32(audio_bytes)
    except Exception as exc:
        logger.warning("Audio quality analysis failed: %s — returning defaults.", exc)
        return {
            "noise_level": "medium",
            "call_stability": "medium",
            "speech_naturalness": "normal",
        }

    noise_level = _estimate_noise_level(pcm_float)
    call_stability = _estimate_call_stability(pcm_float)
    speech_naturalness = _estimate_speech_naturalness(pcm_float)

    result = {
        "noise_level": noise_level,
        "call_stability": call_stability,
        "speech_naturalness": speech_naturalness,
    }

    logger.info("Audio quality analysis: %s", result)
    return result


# ---------------------------------------------------------------------------
# Internal analyzers
# ---------------------------------------------------------------------------


def _wav_to_float32(audio_bytes: bytes) -> np.ndarray:
    """Convert WAV bytes to float32 numpy array normalized to [-1.0, 1.0]."""
    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        n_frames = wf.getnframes()
        sampwidth = wf.getsampwidth()
        raw_pcm = wf.readframes(n_frames)

    dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
    np_dtype = dtype_map.get(sampwidth, np.int16)
    pcm = np.frombuffer(raw_pcm, dtype=np_dtype).astype(np.float32)

    norm_map = {1: 128.0, 2: 32768.0, 4: 2147483648.0}
    pcm = pcm / norm_map.get(sampwidth, 32768.0)
    return pcm


def _estimate_noise_level(pcm: np.ndarray) -> str:
    """
    Estimate background noise level using RMS energy of low-energy frames.

    Splits audio into short frames, takes the bottom 20% by energy as
    'silence/noise' frames, and classifies based on their RMS.
    """
    frame_size = 1600  # 100ms at 16kHz
    n_frames = len(pcm) // frame_size
    if n_frames < 2:
        return "medium"

    frame_energies = []
    for i in range(n_frames):
        frame = pcm[i * frame_size : (i + 1) * frame_size]
        rms = np.sqrt(np.mean(frame ** 2))
        frame_energies.append(rms)

    frame_energies.sort()
    # Bottom 20% of frames approximate noise floor
    noise_frames = frame_energies[: max(1, n_frames // 5)]
    avg_noise_rms = np.mean(noise_frames)

    if avg_noise_rms >= _NOISE_THRESHOLD_HIGH:
        return "high"
    elif avg_noise_rms >= _NOISE_THRESHOLD_MEDIUM:
        return "medium"
    return "low"


def _estimate_call_stability(pcm: np.ndarray) -> str:
    """
    Estimate call stability using zero-crossing rate variability.

    Unstable calls show high variance in ZCR across frames (dropouts,
    digital artifacts, codec glitches).
    """
    frame_size = 1600
    n_frames = len(pcm) // frame_size
    if n_frames < 3:
        return "medium"

    zcr_values = []
    for i in range(n_frames):
        frame = pcm[i * frame_size : (i + 1) * frame_size]
        zc = np.sum(np.abs(np.diff(np.sign(frame))) > 0)
        zcr = zc / len(frame)
        zcr_values.append(zcr)

    zcr_arr = np.array(zcr_values)
    mean_zcr = np.mean(zcr_arr)
    if mean_zcr == 0:
        return "low"

    cv = np.std(zcr_arr) / mean_zcr  # coefficient of variation

    if cv >= _STABILITY_THRESHOLD_LOW:
        return "low"
    elif cv >= _STABILITY_THRESHOLD_MEDIUM:
        return "medium"
    return "high"


def _estimate_speech_naturalness(pcm: np.ndarray) -> str:
    """
    Estimate speech naturalness using autocorrelation regularity.

    TTS or robotic speech tends to have unnaturally regular pitch patterns.
    Natural speech shows more variation in autocorrelation peaks.
    """
    # Use a longer analysis window (1 second)
    window_size = 16000
    n_windows = len(pcm) // window_size
    if n_windows < 2:
        return "normal"

    peak_positions = []
    for i in range(min(n_windows, 10)):  # Sample up to 10 windows
        window = pcm[i * window_size : (i + 1) * window_size]
        # Autocorrelation of the window
        autocorr = np.correlate(window, window, mode="full")
        autocorr = autocorr[len(autocorr) // 2 :]  # positive lags only

        # Normalize
        if autocorr[0] > 0:
            autocorr = autocorr / autocorr[0]

        # Find first peak after lag 0 (skip first 2ms = 32 samples)
        search_start = 32
        search_end = min(len(autocorr), 800)  # Max ~50ms (20 Hz)
        if search_end <= search_start:
            continue

        segment = autocorr[search_start:search_end]
        if len(segment) < 3:
            continue

        peak_idx = np.argmax(segment)
        peak_positions.append(peak_idx)

    if len(peak_positions) < 3:
        return "normal"

    # Check regularity of peak positions
    peak_arr = np.array(peak_positions, dtype=np.float64)
    mean_peak = np.mean(peak_arr)
    if mean_peak == 0:
        return "normal"

    regularity = 1.0 - (np.std(peak_arr) / mean_peak)

    if regularity >= _NATURALNESS_REGULARITY_THRESHOLD:
        return "suspicious"
    return "normal"
