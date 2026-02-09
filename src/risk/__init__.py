# src/risk/__init__.py
# =====================
# Risk & Fraud Signal Engine — VoiceOps Phase 7
#
# Responsibility:
#   - Compute risk score (0–100) from multiple signals (per RULES.md §9)
#   - Determine fraud likelihood (low | medium | high)
#   - Inputs: intent, sentiment, obligation strength,
#     contradictions, audio trust signals
#   - Output key contributing risk factors
#
# Public API:
#   - build_signal_bundle() — validate and bundle upstream signals
#   - compute_risk()        — deterministic risk scoring

from src.risk.signals import (  # noqa: F401
    RiskSignalBundle,
    NoiseLevel,
    CallStability,
    SpeechNaturalness,
    build_signal_bundle,
)
from src.risk.scorer import compute_risk  # noqa: F401
