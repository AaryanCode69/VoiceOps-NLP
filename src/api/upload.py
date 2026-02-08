"""
src/api/upload.py
==================
API Upload Endpoint — VoiceOps Phase 1 + Phase 2

Responsibility:
    - Expose POST /analyze-call
    - Accept a single audio file (.wav or .mp3) via multipart/form-data
    - Reject requests missing an audio file
    - Reject disallowed file types
    - Delegate audio validation and normalization to src.audio.normalizer (Phase 1)
    - Delegate language detection, STT routing, and diarization to src.stt (Phase 2)
    - Return raw diarized transcript (no analysis, no IDs)

Per RULES.md §3:
    - No customer_id, loan_id, or call_id is accepted or generated.
    - No metadata is required.
"""

import asyncio
import logging

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger("voiceops.api")

from src.audio.normalizer import (
    normalize,
    AudioValidationError,
    AudioNormalizationError,
)
from src.stt.router import transcribe_and_diarize


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VoiceOps",
    description="Call-centric risk & fraud intelligence — audio ingestion endpoint.",
    version="0.2.0",
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@app.post("/analyze-call")
async def analyze_call(audio_file: UploadFile = File(...)):
    """
    Accept an audio file, validate & normalize it (Phase 1), then detect
    language, transcribe, and diarize (Phase 2).

    Args:
        audio_file: Uploaded audio file (.wav or .mp3).

    Returns:
        JSON with raw diarized transcript.
    """

    # Guard: file must be provided (FastAPI enforces via File(...), but
    # double-check for safety).
    if audio_file is None or audio_file.filename is None:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    logger.info("Audio file received: %s", audio_file.filename)

    # Read raw bytes
    try:
        audio_bytes = await audio_file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read uploaded file.")

    logger.info("File size: %.2f KB", len(audio_bytes) / 1024)

    # Phase 1: Validate & normalize
    logger.info("Phase 1: Validating and normalizing audio...")
    try:
        normalized_audio = normalize(audio_bytes, audio_file.filename)
    except AudioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AudioNormalizationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Phase 2: Language detection → STT routing → diarization
    logger.info("Phase 2: Starting language detection, STT routing, and diarization...")
    try:
        transcript = await asyncio.to_thread(
            transcribe_and_diarize, normalized_audio
        )
    except RuntimeError as exc:
        logger.error("Phase 2 failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    logger.info("Phase 2 complete — %d utterances in transcript.", len(transcript))

    return JSONResponse(
        status_code=200,
        content={
            "status": "transcription_complete",
            "transcript": transcript,
        },
    )
