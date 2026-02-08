"""
src/audio/normalizer.py
========================
Audio Normalizer — VoiceOps Phase 1

Responsibility:
    - Validate audio file format (.wav, .mp3)
    - Validate audio is non-empty and within duration limits
    - Convert audio to mono channel
    - Resample audio to 16kHz sample rate
    - Return normalized audio as an in-memory bytes object

This module implements pipeline step 1 (Audio normalization) per RULES.md §6.
No storage, embedding, or downstream processing occurs here.

--- Phase 2 begins after this module's output is passed downstream ---
"""

import io

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".wav", ".mp3"}
TARGET_SAMPLE_RATE = 16000  # Hz
TARGET_CHANNELS = 1  # mono
MAX_DURATION_SECONDS = 1800  # 30 minutes — safety limit
OUTPUT_FORMAT = "wav"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AudioValidationError(Exception):
    """Raised when the uploaded audio file fails validation."""
    pass


class AudioNormalizationError(Exception):
    """Raised when audio normalization fails unexpectedly."""
    pass


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_extension(filename: str) -> None:
    """
    Check that the file extension is .wav or .mp3.

    Raises:
        AudioValidationError: If the extension is not allowed.
    """
    if not filename:
        raise AudioValidationError("Filename is missing.")

    ext = _extract_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )


def validate_not_empty(audio_bytes: bytes) -> None:
    """
    Check that the uploaded file is not empty (zero bytes).

    Raises:
        AudioValidationError: If the file has no content.
    """
    if not audio_bytes or len(audio_bytes) == 0:
        raise AudioValidationError("Audio file is empty.")


def validate_duration(audio: AudioSegment) -> None:
    """
    Check that audio duration does not exceed the safety limit.

    Raises:
        AudioValidationError: If duration exceeds MAX_DURATION_SECONDS.
    """
    duration_seconds = len(audio) / 1000.0
    if duration_seconds > MAX_DURATION_SECONDS:
        raise AudioValidationError(
            f"Audio duration ({duration_seconds:.1f}s) exceeds the "
            f"maximum allowed ({MAX_DURATION_SECONDS}s)."
        )
    if duration_seconds == 0:
        raise AudioValidationError("Audio file has zero duration.")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize(audio_bytes: bytes, filename: str) -> bytes:
    """
    Full validation + normalization pipeline for a single audio file.

    Steps:
        1. Validate file extension
        2. Validate file is non-empty
        3. Decode audio
        4. Validate duration
        5. Convert to mono
        6. Resample to 16 kHz
        7. Export as WAV bytes

    Args:
        audio_bytes: Raw bytes of the uploaded audio file.
        filename:    Original filename (used for extension check).

    Returns:
        Normalized audio as WAV bytes (mono, 16 kHz).

    Raises:
        AudioValidationError:    On any validation failure.
        AudioNormalizationError: On unexpected processing failure.
    """
    # 1. Extension check
    validate_extension(filename)

    # 2. Empty-file check
    validate_not_empty(audio_bytes)

    # 3. Decode
    ext = _extract_extension(filename)
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=ext.lstrip("."))
    except CouldntDecodeError:
        raise AudioValidationError("Audio file is corrupt or could not be decoded.")
    except Exception as exc:
        raise AudioNormalizationError(f"Unexpected error decoding audio: {exc}")

    # 4. Duration check
    validate_duration(audio)

    # 5. Convert to mono
    if audio.channels != TARGET_CHANNELS:
        audio = audio.set_channels(TARGET_CHANNELS)

    # 6. Resample to target rate
    if audio.frame_rate != TARGET_SAMPLE_RATE:
        audio = audio.set_frame_rate(TARGET_SAMPLE_RATE)

    # 7. Export as WAV bytes
    try:
        buffer = io.BytesIO()
        audio.export(buffer, format=OUTPUT_FORMAT)
        return buffer.getvalue()
    except Exception as exc:
        raise AudioNormalizationError(f"Failed to export normalized audio: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_extension(filename: str) -> str:
    """Return lowercase file extension including the dot, e.g. '.wav'."""
    dot_index = filename.rfind(".")
    if dot_index == -1:
        return ""
    return filename[dot_index:].lower()
