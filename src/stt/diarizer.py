"""
src/stt/diarizer.py
====================
Speaker Diarization — VoiceOps Phase 2

Responsibility:
    - Identify distinct speakers in the audio
    - Map speakers to AGENT / CUSTOMER labels (per RULES.md §4)
    - Merge diarization output with STT transcript segments
    - Produce the final raw diarized transcript

Speaker labelling heuristic:
    In call-center audio the first speaker is typically the AGENT
    (initiating the call). The second unique speaker is the CUSTOMER.

This module does NOT:
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Filter or remove any speaker's text (both AGENT and CUSTOMER preserved)
    - Store or embed data
"""

import io
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from src.stt.language_detector import TranscriptSegment

load_dotenv()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeakerTurn:
    """A single speaker turn from diarization."""

    speaker: str        # Raw label from diarizer (e.g. "SPEAKER_00")
    start_time: float
    end_time: float


@dataclass(frozen=True)
class DiarizedUtterance:
    """A transcript segment enriched with speaker label and timestamps."""

    speaker: str        # "AGENT" or "CUSTOMER"
    text: str
    start_time: float
    end_time: float

    def to_dict(self) -> dict:
        """Serialize to the Phase 2 output format."""
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


# ---------------------------------------------------------------------------
# Speaker label constants
# ---------------------------------------------------------------------------

SPEAKER_AGENT = "AGENT"
SPEAKER_CUSTOMER = "CUSTOMER"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diarize_and_merge(
    audio_bytes: bytes,
    transcript_segments: list[TranscriptSegment],
) -> list[DiarizedUtterance]:
    """
    Run speaker diarization on the audio and merge with transcript segments.

    Steps:
        1. Run pyannote.audio diarization pipeline on the audio
        2. Map raw speaker labels to AGENT / CUSTOMER
        3. Assign a speaker to each transcript segment via time overlap
        4. Return merged diarized utterances

    Args:
        audio_bytes:         Normalized audio (mono 16 kHz WAV bytes).
        transcript_segments: Time-aligned text segments from the STT provider.

    Returns:
        List of DiarizedUtterance ordered by start_time.

    Raises:
        RuntimeError: If diarization fails.
    """
    speaker_turns = _run_diarization(audio_bytes)

    if not speaker_turns:
        # Fallback: if diarization produces no speaker turns, label all AGENT
        return [
            DiarizedUtterance(
                speaker=SPEAKER_AGENT,
                text=seg.text,
                start_time=seg.start_time,
                end_time=seg.end_time,
            )
            for seg in transcript_segments
            if seg.text.strip()
        ]

    # Build speaker label map: first unique speaker → AGENT, rest → CUSTOMER
    label_map = _build_speaker_label_map(speaker_turns)

    # Merge transcript segments with speaker labels
    utterances = _merge_segments_with_speakers(
        transcript_segments, speaker_turns, label_map
    )

    return utterances


# ---------------------------------------------------------------------------
# Diarization pipeline
# ---------------------------------------------------------------------------


def _run_diarization(audio_bytes: bytes) -> list[SpeakerTurn]:
    """
    Run pyannote.audio speaker-diarization pipeline on in-memory audio.

    Requires:
        - torch and torchaudio installed
        - pyannote.audio installed
        - HF_AUTH_TOKEN environment variable set (HuggingFace model access)

    Returns:
        List of SpeakerTurn ordered by start_time.
    """
    try:
        import torch          # noqa: F401
        import torchaudio
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError(
            "Speaker diarization requires 'torch', 'torchaudio', and "
            "'pyannote.audio'. Install them with: "
            "pip install torch torchaudio pyannote.audio"
        ) from exc

    hf_token = os.environ.get("HF_AUTH_TOKEN")
    if not hf_token:
        raise RuntimeError("HF_AUTH_TOKEN environment variable is not set.")

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to load diarization model: {exc}") from exc

    # Load audio from bytes into a tensor
    try:
        waveform, sample_rate = torchaudio.load(io.BytesIO(audio_bytes))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to decode audio for diarization: {exc}"
        ) from exc

    # Run the diarization pipeline
    try:
        result = pipeline({"waveform": waveform, "sample_rate": sample_rate})
    except Exception as exc:
        raise RuntimeError(f"Diarization pipeline failed: {exc}") from exc

    # New pyannote versions return a DiarizeOutput object;
    # the Annotation with itertracks() lives on .speaker_diarization.
    # Legacy versions return the Annotation directly.
    if hasattr(result, "speaker_diarization"):
        diarization = result.speaker_diarization
    else:
        diarization = result

    # Collect speaker turns
    turns: list[SpeakerTurn] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append(
            SpeakerTurn(
                speaker=speaker,
                start_time=round(turn.start, 2),
                end_time=round(turn.end, 2),
            )
        )

    turns.sort(key=lambda t: t.start_time)
    return turns


# ---------------------------------------------------------------------------
# Speaker label mapping
# ---------------------------------------------------------------------------


def _build_speaker_label_map(turns: list[SpeakerTurn]) -> dict[str, str]:
    """
    Map raw speaker labels to AGENT / CUSTOMER.

    Heuristic: In call-center audio, the first speaker is typically the
    AGENT (initiating the call). The second unique speaker is the CUSTOMER.
    Any additional speakers are mapped to CUSTOMER by default.

    Args:
        turns: Ordered list of SpeakerTurn.

    Returns:
        Dict mapping a raw label (e.g. "SPEAKER_00") to "AGENT" or "CUSTOMER".
    """
    seen_order: list[str] = []
    for t in turns:
        if t.speaker not in seen_order:
            seen_order.append(t.speaker)

    label_map: dict[str, str] = {}
    for i, raw_label in enumerate(seen_order):
        if i == 0:
            label_map[raw_label] = SPEAKER_AGENT
        else:
            label_map[raw_label] = SPEAKER_CUSTOMER

    return label_map


# ---------------------------------------------------------------------------
# Merging logic
# ---------------------------------------------------------------------------


def _merge_segments_with_speakers(
    transcript_segments: list[TranscriptSegment],
    speaker_turns: list[SpeakerTurn],
    label_map: dict[str, str],
) -> list[DiarizedUtterance]:
    """
    Assign a speaker label to each transcript segment by time overlap.

    For each transcript segment, the speaker turn with the greatest
    temporal overlap determines the speaker label.

    Args:
        transcript_segments: Timestamped text from the STT provider.
        speaker_turns:       Speaker turns from diarization.
        label_map:           Raw label → AGENT/CUSTOMER mapping.

    Returns:
        List of DiarizedUtterance ordered by start_time.
    """
    utterances: list[DiarizedUtterance] = []

    for seg in transcript_segments:
        if not seg.text.strip():
            continue

        best_speaker = _find_best_speaker(seg, speaker_turns, label_map)
        utterances.append(
            DiarizedUtterance(
                speaker=best_speaker,
                text=seg.text,
                start_time=seg.start_time,
                end_time=seg.end_time,
            )
        )

    utterances.sort(key=lambda u: u.start_time)
    return utterances


def _find_best_speaker(
    segment: TranscriptSegment,
    speaker_turns: list[SpeakerTurn],
    label_map: dict[str, str],
) -> str:
    """
    Find the speaker with the greatest time overlap for a transcript segment.

    Returns AGENT as the default if no overlap is found.
    """
    best_label = SPEAKER_AGENT
    best_overlap = 0.0

    for turn in speaker_turns:
        overlap_start = max(segment.start_time, turn.start_time)
        overlap_end = min(segment.end_time, turn.end_time)
        overlap = max(0.0, overlap_end - overlap_start)

        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label_map.get(turn.speaker, SPEAKER_CUSTOMER)

    return best_label
