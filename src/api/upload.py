"""
src/api/upload.py
==================
API Upload Endpoint — VoiceOps Full Pipeline (Phase 1 → Phase 8)

Responsibility:
    - Expose POST /api/v1/analyze-call
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
import json
import logging
import os

import aiohttp
from fastapi import FastAPI, File, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("voiceops.api")

from src.audio.normalizer import AudioValidationError, AudioNormalizationError
from src.pipeline import run_pipeline
from src.phase_validator import PhaseVerificationError

WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VoiceOps",
    description="Call-centric risk & fraud intelligence — audio analysis endpoint.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@app.post("/api/v1/analyze-call")
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

    # POST final JSON to the configured webhook endpoint
    webhook_response = None
    if WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    WEBHOOK_URL,
                    json=final_output,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    logger.info(
                        "Webhook POST to %s — status %d", WEBHOOK_URL, resp.status,
                    )
                    try:
                        webhook_response = await resp.json()
                    except Exception:
                        logger.warning("Webhook did not return valid JSON (status %d), skipping.", resp.status)
        except Exception as exc:
            logger.error("Webhook POST failed: %s", exc)
    else:
        logger.debug("WEBHOOK_URL not configured — skipping POST.")

    if webhook_response is not None:
        return JSONResponse(status_code=200, content=webhook_response)

    return JSONResponse(status_code=200, content=final_output)
