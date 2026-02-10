"""
main.py
========
Central entry point for the VoiceOps application.

Run with:
    uvicorn main:app --reload
"""

import logging

from dotenv import load_dotenv

load_dotenv()  # Load .env before any module reads env vars

# Configure logging for the entire application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Suppress OpenAI SDK internal HTTP/transport logs so they never appear
# in pipeline output — only phase-specific logs are shown.
for _openai_logger_name in (
    "openai",
    "openai._base_client",
    "openai._client",
    "openai.api_requestor",
    "httpx",
    "httpcore",
    "httpcore.http11",
    "httpcore.connection",
):
    logging.getLogger(_openai_logger_name).setLevel(logging.CRITICAL)

from src.api.upload import app  # noqa: F401, E402

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
