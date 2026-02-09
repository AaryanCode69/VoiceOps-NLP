"""
src/stt/diarizer_validator.py
==============================
Speaker Diarization & Alignment — VoiceOps Phase 3 (PyAnnote)

Responsibility:
    - Accept timestamped transcript from Phase 2 (Deepgram STT, no speaker labels)
    - Accept raw audio bytes (original file)
    - Run PyAnnote speaker diarization on the RAW AUDIO (CUDA-enabled)
    - Align PyAnnote speaker segments with Deepgram transcript timestamps
    - Output utterances labeled as speaker_A / speaker_B with timestamps

Per updated Phase 3 spec:
    - PyAnnote MUST be used for speaker segmentation
    - CUDA MUST be enabled (GPU if available)
    - Diarization is AUDIO-based, not text-based
    - Deepgram diarization is NOT used
    - Output is speaker_A / speaker_B (role classification is separate)

Per RULES.md §5:
    - Only two logical speakers: AGENT and CUSTOMER
    - Role assignment happens in role_classifier.py (downstream)

This module does NOT:
    - Perform STT (handled by Phase 2)
    - Assign AGENT / CUSTOMER roles (handled by role_classifier.py)
    - Translate text (handled by translator.py)
    - Perform PII redaction
    - Perform intent, sentiment, obligation, or risk analysis
    - Generate summaries, scores, or identifiers
    - Store data or call RAG
"""

import io
import logging
import os
import wave
from typing import Any

import torch

logger = logging.getLogger("voiceops.stt.diarizer_validator")

# ---------------------------------------------------------------------------
# PyAnnote pipeline (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_pyannote_pipeline = None


def _get_pyannote_pipeline():
    """
    Lazily load the PyAnnote speaker diarization pipeline.

    Uses CUDA if available, otherwise falls back to CPU.
    Requires a HuggingFace token set as HUGGINGFACE_TOKEN env var.
    """
    global _pyannote_pipeline

    if _pyannote_pipeline is not None:
        return _pyannote_pipeline

    from pyannote.audio import Pipeline

    hf_token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    if not hf_token:
        raise RuntimeError(
            "HUGGINGFACE_TOKEN (or HF_TOKEN) environment variable is required "
            "for PyAnnote speaker diarization. Get a token from "
            "https://huggingface.co/settings/tokens and accept the model "
            "license at https://huggingface.co/pyannote/speaker-diarization-3.1"
        )

    logger.info("Loading PyAnnote speaker-diarization-3.1 pipeline...")

    _pyannote_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )

    # Use CUDA if available, else CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _pyannote_pipeline = _pyannote_pipeline.to(device)

    logger.info(
        "PyAnnote pipeline loaded on device: %s (CUDA available: %s)",
        device, torch.cuda.is_available(),
    )

    return _pyannote_pipeline


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diarize_audio(audio_bytes: bytes) -> list[dict[str, Any]]:
    """
    Run PyAnnote speaker diarization on raw audio bytes.

    Uses the PyAnnote speaker-diarization-3.1 model on GPU (CUDA)
    when available.

    Args:
        audio_bytes: Normalized audio from Phase 1 (mono 16 kHz WAV bytes).

    Returns:
        List of speaker segment dicts:
            [{"speaker": "speaker_A", "start_time": float, "end_time": float}, ...]

    Raises:
        RuntimeError: If PyAnnote pipeline cannot be loaded.
    """
    pipeline = _get_pyannote_pipeline()

    # PyAnnote expects a dict with "waveform" and "sample_rate", or a file path.
    # We'll provide an in-memory waveform tensor.
    waveform, sample_rate = _wav_bytes_to_tensor(audio_bytes)

    logger.info(
        "Running PyAnnote diarization on %.1fs of audio (sample_rate=%d)...",
        waveform.shape[1] / sample_rate, sample_rate,
    )

    # Run diarization
    diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate})

    # Convert PyAnnote output to our segment format
    # PyAnnote yields (segment, track, speaker_label)
    raw_segments: list[dict[str, Any]] = []
    for segment, _track, speaker_label in diarization.itertracks(yield_label=True):
        raw_segments.append({
            "speaker": speaker_label,
            "start_time": round(segment.start, 3),
            "end_time": round(segment.end, 3),
        })

    # Normalize PyAnnote speaker labels to speaker_A / speaker_B
    # PyAnnote uses labels like "SPEAKER_00", "SPEAKER_01", etc.
    speaker_label_map = _build_speaker_label_map(raw_segments)
    segments = []
    for seg in raw_segments:
        segments.append({
            "speaker": speaker_label_map.get(seg["speaker"], "speaker_A"),
            "start_time": seg["start_time"],
            "end_time": seg["end_time"],
        })

    logger.info(
        "PyAnnote diarization complete: %d segments, %d unique speakers.",
        len(segments), len(speaker_label_map),
    )

    return segments


def align_transcript_with_speakers(
    transcript: list[dict[str, Any]],
    speaker_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Align Deepgram transcript timestamps with PyAnnote speaker segments.

    For each transcript segment, find the PyAnnote speaker segment with the
    greatest time overlap and assign that speaker label.

    Args:
        transcript: Phase 2 output — list of dicts with keys:
            chunk_id, start_time, end_time, text.
        speaker_segments: PyAnnote output — list of dicts with keys:
            speaker (speaker_A/speaker_B), start_time, end_time.

    Returns:
        List of aligned utterance dicts:
            [{"speaker": "speaker_A"|"speaker_B", "text": str,
              "start_time": float, "end_time": float}]
    """
    if not transcript:
        logger.warning("Empty transcript — nothing to align.")
        return []

    if not speaker_segments:
        logger.warning(
            "No speaker segments from PyAnnote — assigning all to speaker_A."
        )
        return [
            {
                "speaker": "speaker_A",
                "text": seg["text"].strip(),
                "start_time": float(seg["start_time"]),
                "end_time": float(seg["end_time"]),
            }
            for seg in transcript
            if seg.get("text", "").strip()
        ]

    aligned: list[dict[str, Any]] = []

    for seg in transcript:
        text = seg.get("text", "").strip()
        if not text:
            continue

        seg_start = float(seg["start_time"])
        seg_end = float(seg["end_time"])

        # Find the speaker segment with maximum overlap
        best_speaker = "speaker_A"
        best_overlap = 0.0

        for spk_seg in speaker_segments:
            overlap_start = max(seg_start, spk_seg["start_time"])
            overlap_end = min(seg_end, spk_seg["end_time"])
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = spk_seg["speaker"]

        aligned.append({
            "speaker": best_speaker,
            "text": text,
            "start_time": seg_start,
            "end_time": seg_end,
        })

    logger.info(
        "Alignment complete: %d transcript segments aligned with speaker labels.",
        len(aligned),
    )

    return aligned


def diarize_and_align(
    audio_bytes: bytes,
    transcript: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Full Phase 3 Step 1–3: Diarize audio with PyAnnote, then align with
    Deepgram transcript.

    This is the primary entry point for Phase 3 diarization.

    Args:
        audio_bytes: Raw audio bytes (mono 16 kHz WAV from Phase 1).
        transcript: Phase 2 output (timestamped text, no speaker labels).

    Returns:
        List of speaker-labeled utterance dicts with speaker_A/speaker_B.
    """
    # Step 1: PyAnnote speaker segmentation on raw audio
    speaker_segments = diarize_audio(audio_bytes)

    # Step 2: Align transcript timestamps with speaker segments
    aligned_utterances = align_transcript_with_speakers(transcript, speaker_segments)

    return aligned_utterances


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wav_bytes_to_tensor(audio_bytes: bytes) -> tuple:
    """
    Convert WAV bytes to a PyTorch tensor suitable for PyAnnote.

    Returns:
        Tuple of (waveform_tensor, sample_rate) where waveform_tensor
        has shape (1, num_samples) — mono channel.
    """
    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    import numpy as np

    # Convert raw bytes to numpy array
    if sample_width == 2:
        dtype = np.int16
    elif sample_width == 4:
        dtype = np.int32
    else:
        dtype = np.int16

    audio_np = np.frombuffer(raw_data, dtype=dtype).astype(np.float32)

    # If stereo, take first channel
    if n_channels > 1:
        audio_np = audio_np[::n_channels]

    # Normalize to [-1.0, 1.0]
    max_val = float(np.iinfo(dtype).max)
    audio_np = audio_np / max_val

    # Convert to torch tensor with shape (1, num_samples)
    waveform = torch.from_numpy(audio_np).unsqueeze(0)

    return waveform, sample_rate


def _build_speaker_label_map(
    raw_segments: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Map PyAnnote raw speaker labels (e.g. SPEAKER_00, SPEAKER_01)
    to normalized speaker_A / speaker_B labels.

    The speaker who appears first chronologically becomes speaker_A.
    """
    label_map: dict[str, str] = {}
    label_counter = 0
    suffixes = ["A", "B", "C", "D", "E"]  # Support up to 5 speakers

    for seg in sorted(raw_segments, key=lambda s: s["start_time"]):
        raw_label = seg["speaker"]
        if raw_label not in label_map:
            if label_counter < len(suffixes):
                label_map[raw_label] = f"speaker_{suffixes[label_counter]}"
            else:
                label_map[raw_label] = f"speaker_{label_counter}"
            label_counter += 1

    logger.debug("PyAnnote label map: %s", label_map)
    return label_map
