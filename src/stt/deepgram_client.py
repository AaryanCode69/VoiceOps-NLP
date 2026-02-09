"""
src/stt/deepgram_client.py
===========================
Deepgram STT Client — VoiceOps Phase 2 (Updated: Diarization-Agnostic)

Responsibility:
    - Transcribe a single audio chunk using Deepgram Nova-3
    - Return timestamped transcript text (no speaker labels)
    - Auto-detect the spoken language (metadata only)

Per updated Phase 2 spec:
    - Deepgram Nova-3 is the DEFAULT STT engine
    - Deepgram SDK MUST be used
    - Diarization MUST be DISABLED (diarize=False)
    - Output is text + timestamps only — no speaker labels

This module does NOT:
    - Perform speaker diarization or role classification
    - Translate text
    - Chunk audio (handled by src.audio.chunker)
    - Merge or flatten chunks (handled by stt_pipeline)
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Store data
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("voiceops.stt.deepgram_client")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe_chunk(audio_bytes: bytes) -> dict | None:
    """
    Transcribe a single audio chunk using Deepgram Nova-3.

    Diarization is DISABLED. Returns a single transcript dict for the
    entire chunk with word-level timestamp boundaries.

    Args:
        audio_bytes: WAV audio bytes for a single chunk.

    Returns:
        A dict containing:
            - text       (str):   Full transcribed text for this chunk
            - start_time (float): Start time of first word (seconds, chunk-relative)
            - end_time   (float): End time of last word (seconds, chunk-relative)

        Returns None if Deepgram produces no transcript.

    Raises:
        RuntimeError: If the Deepgram API call fails or API key is missing.
    """
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY environment variable is not set.")

    try:
        from deepgram import DeepgramClient
    except ImportError as exc:
        raise RuntimeError(
            "Deepgram SDK is required. Install with: pip install deepgram-sdk"
        ) from exc

    # ------------------------------------------------------------------
    # Build Deepgram client and call API
    # ------------------------------------------------------------------
    client = DeepgramClient(api_key=api_key)

    try:
        logger.debug("Sending chunk (%d bytes) to Deepgram Nova-3...", len(audio_bytes))
        response = client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model="nova-3",
            diarize=False,          # Diarization DISABLED per Phase 2 spec
            utterances=False,       # Not needed without diarization
            smart_format=True,
            punctuate=True,
            detect_language=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Deepgram transcription failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Log response metadata
    # ------------------------------------------------------------------
    _log_response_metadata(response, len(audio_bytes))

    # ------------------------------------------------------------------
    # Extract transcript from channels[0].alternatives[0]
    # ------------------------------------------------------------------
    transcript_text, start_time, end_time = _extract_transcript(response)

    if not transcript_text:
        logger.warning(
            "Deepgram returned no transcript for chunk (%d bytes). "
            "Possible cause: background noise, very short speech, or "
            "chunk split mid-utterance.",
            len(audio_bytes),
        )
        return None

    logger.debug(
        "Deepgram transcript: %.1fs–%.1fs, %d chars.",
        start_time, end_time, len(transcript_text),
    )

    return {
        "text": transcript_text,
        "start_time": round(start_time, 2),
        "end_time": round(end_time, 2),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_transcript(response) -> tuple[str, float, float]:
    """
    Extract the full transcript text and word-level time boundaries from
    a Deepgram PrerecordedResponse (channels → alternatives → words).

    Returns:
        (transcript_text, start_time, end_time)
        If no transcript is found, returns ("", 0.0, 0.0).
    """
    results = getattr(response, "results", None)
    if results is None and isinstance(response, dict):
        results = response.get("results")

    if results is None:
        return ("", 0.0, 0.0)

    channels = getattr(results, "channels", None)
    if channels is None and isinstance(results, dict):
        channels = results.get("channels", [])

    if not channels:
        return ("", 0.0, 0.0)

    ch0 = channels[0]
    alternatives = getattr(ch0, "alternatives", None)
    if alternatives is None and isinstance(ch0, dict):
        alternatives = ch0.get("alternatives", [])

    if not alternatives:
        return ("", 0.0, 0.0)

    alt0 = alternatives[0]

    # Get transcript text
    transcript = _get_attr(alt0, "transcript", "").strip()

    # Get word-level timestamps for precise boundaries
    words = getattr(alt0, "words", None)
    if words is None and isinstance(alt0, dict):
        words = alt0.get("words", [])

    if words:
        first_word = words[0]
        last_word = words[-1]
        start_time = float(_get_attr(first_word, "start", 0.0))
        end_time = float(_get_attr(last_word, "end", 0.0))
    else:
        start_time = 0.0
        end_time = 0.0

    return (transcript, start_time, end_time)


def _log_response_metadata(response, audio_size: int) -> None:
    """Log Deepgram response metadata for debugging."""
    try:
        results = getattr(response, "results", None)
        if results is None and isinstance(response, dict):
            results = response.get("results")

        if results is None:
            logger.warning("Deepgram response has no 'results' field.")
            return

        # Duration
        metadata = getattr(response, "metadata", None)
        if metadata is None and isinstance(response, dict):
            metadata = response.get("metadata")
        duration = None
        if metadata is not None:
            duration = (
                getattr(metadata, "duration", None)
                or (metadata.get("duration") if isinstance(metadata, dict) else None)
            )

        # Channels info
        channels = getattr(results, "channels", None)
        if channels is None and isinstance(results, dict):
            channels = results.get("channels", [])
        n_channels = len(channels) if channels else 0

        # Word count from first channel
        n_words = 0
        if channels and n_channels > 0:
            ch0 = channels[0]
            alternatives = getattr(ch0, "alternatives", None)
            if alternatives is None and isinstance(ch0, dict):
                alternatives = ch0.get("alternatives", [])
            if alternatives:
                alt0 = alternatives[0]
                words = getattr(alt0, "words", None)
                if words is None and isinstance(alt0, dict):
                    words = alt0.get("words", [])
                n_words = len(words) if words else 0

        # Detected language from first channel
        detected_lang = None
        if channels and n_channels > 0:
            ch0 = channels[0]
            det = getattr(ch0, "detected_language", None)
            if det is None and isinstance(ch0, dict):
                det = ch0.get("detected_language")
            if det is None:
                alternatives = getattr(ch0, "alternatives", None)
                if alternatives is None and isinstance(ch0, dict):
                    alternatives = ch0.get("alternatives", [])
                if alternatives:
                    alt0 = alternatives[0]
                    det = getattr(alt0, "detected_language", None)
                    if det is None and isinstance(alt0, dict):
                        det = alt0.get("detected_language")
                detected_lang = det

        logger.info(
            "Deepgram response: audio_size=%d bytes, duration=%.2fs, "
            "channels=%d, words=%d, language=%s",
            audio_size,
            duration if duration else 0.0,
            n_channels,
            n_words,
            detected_lang or "unknown",
        )

        if duration and duration < 5.0 and audio_size > 100_000:
            logger.warning(
                "Deepgram reported only %.2fs duration for %d bytes of audio. "
                "This suggests audio may be truncated or malformed.",
                duration, audio_size,
            )

    except Exception as exc:
        logger.debug("Failed to log Deepgram response metadata: %s", exc)


def _get_attr(obj, name: str, default):
    """Get an attribute from an SDK object or dict key, with a default."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
