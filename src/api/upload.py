"""
src/api/upload.py
==================
API Upload Endpoint — VoiceOps Full Pipeline (Phase 1 → Phase 8)

Responsibility:
    - Expose POST /analyze-call
    - Accept a single audio file (.wav, .mp3, or .m4a) via multipart/form-data
    - Reject requests missing an audio file
    - Reject disallowed file types
    - Delegate full pipeline execution to src.pipeline.run_pipeline
    - Return the FINAL STRUCTURED JSON per RULES.md §10

Per RULES.md §3:
    - No customer_id, loan_id, or call_id is accepted or generated.
    - No metadata is required.

Per RULES.md §10:
    - The final JSON is the ONLY valid endpoint response
    - No additional keys, nested metadata, debug info, raw transcripts
    - No identifiers (call_id, customer_id, loan_id)
"""

import asyncio
import logging

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger("voiceops.api")

from src.audio.normalizer import AudioValidationError, AudioNormalizationError
from src.pipeline import run_pipeline
from src.phase_validator import PhaseVerificationError


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VoiceOps",
    description="Call-centric risk & fraud intelligence — audio analysis endpoint.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@app.post("/analyze-call")
async def analyze_call(audio_file: UploadFile = File(...)):
    """
    Accept an audio file and run the full VoiceOps pipeline
    (Phase 1 → Phase 8).

    Returns the FINAL STRUCTURED JSON per RULES.md §10.

    Args:
        audio_file: Uploaded audio file (.wav, .mp3, or .m4a).

    Returns:
        Final structured JSON with call_context, speaker_analysis,
        nlp_insights, risk_signals, risk_assessment, summary_for_rag.
    """

    # Guard: file must be provided
    if audio_file is None or audio_file.filename is None:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    logger.info("Audio file received: %s", audio_file.filename)

    # Read raw bytes
    try:
        audio_bytes = await audio_file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read uploaded file.")

    logger.info("File size: %.2f KB", len(audio_bytes) / 1024)

    # Run full pipeline (Phase 1 → Phase 8)
    try:
        final_output = await asyncio.to_thread(
            run_pipeline, audio_bytes, audio_file.filename
        )
    except AudioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AudioNormalizationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except PhaseVerificationError as exc:
        logger.error("Phase verification failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline verification error in Phase {exc.phase}: {exc.message}",
        )
    except RuntimeError as exc:
        logger.error("Pipeline runtime error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.error("Pipeline unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {exc}",
        )

    logger.info("Full pipeline complete — returning final structured JSON.")

    return JSONResponse(status_code=200, content=final_output)
