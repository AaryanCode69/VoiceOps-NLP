"""
tests/test_integration.py
==========================
Integration Layer Tests — VoiceOps Pipeline Orchestrator

Tests verify:
    1. Phase validators correctly accept/reject outputs
    2. Final JSON assembly produces the locked schema
    3. Risk signal derivation (audio_trust_flags, behavioral_flags)
    4. Speaker analysis derivation
    5. Phase 3 → Phase 4 bridging
    6. Full pipeline mock integration (all phases mocked)

All tests are OFFLINE — no LLM, no API, no audio processing.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.phase_validator import (
    PhaseVerificationError,
    verify_phase2,
    verify_phase3,
    verify_phase4,
    verify_phase5,
    verify_phase6,
    verify_phase7,
    verify_phase8,
    verify_audio_quality,
)
from src.pipeline import (
    _assemble_final_json,
    _derive_audio_trust_flags,
    _derive_behavioral_flags,
    _derive_speaker_analysis,
    _bridge_phase3_to_phase4,
)


# ===================================================================
# Test fixtures
# ===================================================================

def _valid_transcript():
    """Valid Phase 2 output."""
    return [
        {"chunk_id": 0, "start_time": 0.0, "end_time": 4.2, "text": "Hello this is agent speaking"},
        {"chunk_id": 1, "start_time": 4.5, "end_time": 8.1, "text": "I need more time to pay"},
    ]


def _valid_structured():
    """Valid Phase 3 output."""
    return [
        {"speaker": "AGENT", "text": "Hello this is agent speaking", "confidence": 0.92},
        {"speaker": "CUSTOMER", "text": "I need more time to pay", "confidence": 0.88},
    ]


def _valid_phase4():
    """Valid Phase 4 output."""
    return [
        {"speaker": "AGENT", "text": "Hello this is agent speaking", "start_time": 0.0, "end_time": 4.2},
        {"speaker": "CUSTOMER", "text": "I need more time to pay", "start_time": 4.5, "end_time": 8.1},
    ]


def _valid_sentiment():
    """Valid Phase 5 output."""
    return {"label": "stressed", "confidence": 0.82}


def _valid_intent():
    """Valid Phase 6 intent output."""
    return {"label": "repayment_promise", "confidence": 0.6, "conditionality": "high"}


def _valid_entities():
    """Valid Phase 6 entities output."""
    return {"payment_commitment": "next_week", "amount_mentioned": None}


def _valid_risk():
    """Valid Phase 7 output."""
    return {
        "risk_score": 78,
        "fraud_likelihood": "high",
        "confidence": 0.81,
        "key_risk_factors": [
            "conditional_commitment",
            "contradictory_statements",
            "high_emotional_stress",
        ],
    }


def _valid_audio_quality():
    """Valid audio quality signals."""
    return {
        "noise_level": "medium",
        "call_stability": "low",
        "speech_naturalness": "suspicious",
    }


# ===================================================================
# Phase 2 Validator Tests
# ===================================================================


class TestVerifyPhase2(unittest.TestCase):

    def test_valid_transcript(self):
        verify_phase2(_valid_transcript())

    def test_empty_list_fails(self):
        with self.assertRaises(PhaseVerificationError) as ctx:
            verify_phase2([])
        self.assertIn("empty", ctx.exception.message.lower())

    def test_not_a_list_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase2("not a list")

    def test_missing_text_fails(self):
        bad = [{"start_time": 0.0, "end_time": 1.0}]
        with self.assertRaises(PhaseVerificationError):
            verify_phase2(bad)

    def test_speaker_key_forbidden(self):
        bad = [{"start_time": 0.0, "end_time": 1.0, "text": "hello", "speaker": "A"}]
        with self.assertRaises(PhaseVerificationError) as ctx:
            verify_phase2(bad)
        self.assertIn("DIARIZATION", ctx.exception.message.upper())

    def test_non_numeric_timestamp_fails(self):
        bad = [{"start_time": "zero", "end_time": 1.0, "text": "hello"}]
        with self.assertRaises(PhaseVerificationError):
            verify_phase2(bad)


# ===================================================================
# Phase 3 Validator Tests
# ===================================================================


class TestVerifyPhase3(unittest.TestCase):

    def test_valid_structured(self):
        verify_phase3(_valid_structured())

    def test_empty_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase3([])

    def test_invalid_speaker_fails(self):
        bad = [{"speaker": "BOT", "text": "hi", "confidence": 0.5}]
        with self.assertRaises(PhaseVerificationError):
            verify_phase3(bad)

    def test_confidence_out_of_range_fails(self):
        bad = [{"speaker": "AGENT", "text": "hi", "confidence": 1.5}]
        with self.assertRaises(PhaseVerificationError):
            verify_phase3(bad)

    def test_missing_confidence_fails(self):
        bad = [{"speaker": "AGENT", "text": "hi"}]
        with self.assertRaises(PhaseVerificationError):
            verify_phase3(bad)


# ===================================================================
# Phase 4 Validator Tests
# ===================================================================


class TestVerifyPhase4(unittest.TestCase):

    def test_valid_phase4(self):
        verify_phase4(_valid_phase4())

    def test_empty_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase4([])

    def test_missing_start_time_fails(self):
        bad = [{"speaker": "AGENT", "text": "hi", "end_time": 1.0}]
        with self.assertRaises(PhaseVerificationError):
            verify_phase4(bad)


# ===================================================================
# Phase 5 Validator Tests
# ===================================================================


class TestVerifyPhase5(unittest.TestCase):

    def test_valid_sentiment(self):
        verify_phase5(_valid_sentiment())

    def test_invalid_label_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase5({"label": "happy", "confidence": 0.9})

    def test_missing_confidence_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase5({"label": "calm"})

    def test_risk_key_forbidden(self):
        bad = {"label": "calm", "confidence": 0.9, "risk_score": 50}
        with self.assertRaises(PhaseVerificationError):
            verify_phase5(bad)


# ===================================================================
# Phase 6 Validator Tests
# ===================================================================


class TestVerifyPhase6(unittest.TestCase):

    def test_valid_phase6(self):
        verify_phase6(
            _valid_intent(), "weak", True, _valid_entities()
        )

    def test_invalid_intent_label(self):
        bad_intent = {"label": "bribery", "confidence": 0.5, "conditionality": "low"}
        with self.assertRaises(PhaseVerificationError):
            verify_phase6(bad_intent, "weak", False, _valid_entities())

    def test_invalid_obligation(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase6(_valid_intent(), "maybe", False, _valid_entities())

    def test_contradictions_not_bool(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase6(_valid_intent(), "weak", "yes", _valid_entities())

    def test_risk_in_intent_forbidden(self):
        bad_intent = {
            "label": "refusal", "confidence": 0.8,
            "conditionality": "low", "risk_score": 90,
        }
        with self.assertRaises(PhaseVerificationError):
            verify_phase6(bad_intent, "none", False, _valid_entities())


# ===================================================================
# Phase 7 Validator Tests
# ===================================================================


class TestVerifyPhase7(unittest.TestCase):

    def test_valid_risk(self):
        verify_phase7(_valid_risk())

    def test_missing_risk_score(self):
        bad = {"fraud_likelihood": "high", "confidence": 0.8, "key_risk_factors": []}
        with self.assertRaises(PhaseVerificationError):
            verify_phase7(bad)

    def test_risk_score_out_of_range(self):
        bad = _valid_risk()
        bad["risk_score"] = 150
        with self.assertRaises(PhaseVerificationError):
            verify_phase7(bad)

    def test_invalid_fraud_likelihood(self):
        bad = _valid_risk()
        bad["fraud_likelihood"] = "extreme"
        with self.assertRaises(PhaseVerificationError):
            verify_phase7(bad)


# ===================================================================
# Phase 8 Validator Tests
# ===================================================================


class TestVerifyPhase8(unittest.TestCase):

    def test_valid_summary(self):
        verify_phase8(
            "Customer made a conditional repayment promise under stress."
        )

    def test_empty_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase8("")

    def test_no_period_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase8("No period at the end")

    def test_banned_word_fails(self):
        with self.assertRaises(PhaseVerificationError):
            verify_phase8("The customer lied about the payment.")


# ===================================================================
# Audio Quality Validator Tests
# ===================================================================


class TestVerifyAudioQuality(unittest.TestCase):

    def test_valid_quality(self):
        verify_audio_quality(_valid_audio_quality())

    def test_invalid_noise_level(self):
        bad = {"noise_level": "extreme", "call_stability": "high", "speech_naturalness": "normal"}
        with self.assertRaises(PhaseVerificationError):
            verify_audio_quality(bad)

    def test_invalid_naturalness(self):
        bad = {"noise_level": "low", "call_stability": "high", "speech_naturalness": "robotic"}
        with self.assertRaises(PhaseVerificationError):
            verify_audio_quality(bad)


# ===================================================================
# Risk Signal Derivation Tests
# ===================================================================


class TestDeriveRiskSignals(unittest.TestCase):

    def test_audio_trust_flags_all_bad(self):
        quality = {"noise_level": "high", "call_stability": "low", "speech_naturalness": "suspicious"}
        flags = _derive_audio_trust_flags(quality)
        self.assertIn("high_background_noise", flags)
        self.assertIn("low_call_stability", flags)
        self.assertIn("unnatural_speech_pattern", flags)

    def test_audio_trust_flags_all_good(self):
        quality = {"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"}
        flags = _derive_audio_trust_flags(quality)
        self.assertEqual(flags, [])

    def test_behavioral_flags_from_risk_factors(self):
        factors = ["conditional_commitment", "contradictory_statements"]
        flags = _derive_behavioral_flags(factors, True)
        self.assertIn("conditional_commitment", flags)
        self.assertIn("statement_contradiction", flags)

    def test_behavioral_flags_contradiction_absent_factors(self):
        """Contradiction flag added even if not in risk factors."""
        flags = _derive_behavioral_flags([], True)
        self.assertIn("statement_contradiction", flags)

    def test_behavioral_flags_no_contradictions(self):
        flags = _derive_behavioral_flags([], False)
        self.assertEqual(flags, [])


# ===================================================================
# Speaker Analysis Derivation Tests
# ===================================================================


class TestDerriveSpeakerAnalysis(unittest.TestCase):

    def test_basic_speaker_analysis(self):
        utts = _valid_structured()
        result = _derive_speaker_analysis(utts)
        self.assertTrue(result["customer_only_analysis"])
        self.assertFalse(result["agent_influence_detected"])

    def test_agent_influence_detected(self):
        utts = [
            {"speaker": "AGENT", "text": "Surely you know this is overdue", "confidence": 0.9},
            {"speaker": "CUSTOMER", "text": "I know", "confidence": 0.8},
        ]
        result = _derive_speaker_analysis(utts)
        self.assertTrue(result["agent_influence_detected"])


# ===================================================================
# Phase 3 → Phase 4 Bridge Tests
# ===================================================================


class TestBridgePhase3ToPhase4(unittest.TestCase):

    def test_bridge_preserves_speaker_and_text(self):
        structured = _valid_structured()
        transcript = _valid_transcript()
        bridged = _bridge_phase3_to_phase4(structured, transcript)

        self.assertEqual(len(bridged), 2)
        self.assertEqual(bridged[0]["speaker"], "AGENT")
        self.assertEqual(bridged[1]["speaker"], "CUSTOMER")
        self.assertIn("start_time", bridged[0])
        self.assertIn("end_time", bridged[0])

    def test_bridge_empty_returns_empty(self):
        result = _bridge_phase3_to_phase4([], [])
        self.assertEqual(result, [])


# ===================================================================
# Final JSON Assembly Tests
# ===================================================================


class TestAssembleFinalJSON(unittest.TestCase):

    def _build_final(self):
        return _assemble_final_json(
            call_language="hinglish",
            audio_quality=_valid_audio_quality(),
            speaker_analysis={
                "customer_only_analysis": True,
                "agent_influence_detected": False,
            },
            sentiment=_valid_sentiment(),
            intent=_valid_intent(),
            obligation_strength="weak",
            entities=_valid_entities(),
            contradictions_detected=True,
            audio_trust_flags=["low_call_stability", "unnatural_speech_pattern"],
            behavioral_flags=["conditional_commitment", "statement_contradiction"],
            risk_assessment=_valid_risk(),
            summary="Customer made a conditional repayment promise under stress.",
        )

    def test_top_level_keys(self):
        result = self._build_final()
        expected_keys = {
            "call_context",
            "speaker_analysis",
            "nlp_insights",
            "risk_signals",
            "risk_assessment",
            "summary_for_rag",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_no_extra_keys(self):
        result = self._build_final()
        # No identifiers allowed
        for forbidden in ("call_id", "customer_id", "loan_id", "transcript", "debug"):
            self.assertNotIn(forbidden, result)

    def test_call_context_structure(self):
        result = self._build_final()
        cc = result["call_context"]
        self.assertEqual(cc["call_language"], "hinglish")
        self.assertIn("call_quality", cc)
        cq = cc["call_quality"]
        self.assertIn("noise_level", cq)
        self.assertIn("call_stability", cq)
        self.assertIn("speech_naturalness", cq)

    def test_nlp_insights_structure(self):
        result = self._build_final()
        nlp = result["nlp_insights"]
        self.assertIn("intent", nlp)
        self.assertIn("sentiment", nlp)
        self.assertIn("obligation_strength", nlp)
        self.assertIn("entities", nlp)
        self.assertIn("contradictions_detected", nlp)

        # Intent sub-fields
        self.assertIn("label", nlp["intent"])
        self.assertIn("confidence", nlp["intent"])
        self.assertIn("conditionality", nlp["intent"])

        # Sentiment sub-fields
        self.assertIn("label", nlp["sentiment"])
        self.assertIn("confidence", nlp["sentiment"])

        # Entities sub-fields
        self.assertIn("payment_commitment", nlp["entities"])
        self.assertIn("amount_mentioned", nlp["entities"])

    def test_risk_signals_structure(self):
        result = self._build_final()
        rs = result["risk_signals"]
        self.assertIn("audio_trust_flags", rs)
        self.assertIn("behavioral_flags", rs)
        self.assertIsInstance(rs["audio_trust_flags"], list)
        self.assertIsInstance(rs["behavioral_flags"], list)

    def test_risk_assessment_structure(self):
        result = self._build_final()
        ra = result["risk_assessment"]
        self.assertIn("risk_score", ra)
        self.assertIn("fraud_likelihood", ra)
        self.assertIn("confidence", ra)
        # key_risk_factors should NOT be in the final output
        self.assertNotIn("key_risk_factors", ra)

    def test_summary_is_string(self):
        result = self._build_final()
        self.assertIsInstance(result["summary_for_rag"], str)
        self.assertTrue(len(result["summary_for_rag"]) > 0)


# ===================================================================
# Full Pipeline Mock Test
# ===================================================================


class TestFullPipelineMock(unittest.TestCase):
    """
    Mock all external dependencies and verify the pipeline
    produces a valid final JSON.
    """

    @patch("src.pipeline.generate_summary")
    @patch("src.pipeline.compute_risk")
    @patch("src.pipeline.build_signal_bundle")
    @patch("src.pipeline.extract_entities")
    @patch("src.pipeline.detect_contradictions")
    @patch("src.pipeline.derive_obligation_strength")
    @patch("src.pipeline.classify_intent")
    @patch("src.pipeline.analyze_sentiment")
    @patch("src.pipeline.redact_utterances")
    @patch("src.pipeline.normalize_utterances")
    @patch("src.pipeline.structure_semantically")
    @patch("src.pipeline.detect_language")
    @patch("src.pipeline.transcribe")
    @patch("src.pipeline.analyze_audio_quality")
    @patch("src.pipeline.normalize")
    def test_pipeline_assembles_valid_json(
        self,
        mock_normalize,
        mock_audio_quality,
        mock_transcribe,
        mock_detect_lang,
        mock_structure,
        mock_norm_utt,
        mock_redact,
        mock_sentiment,
        mock_intent,
        mock_obligation,
        mock_contradictions,
        mock_entities,
        mock_signal_bundle,
        mock_risk,
        mock_summary,
    ):
        # Setup mocks
        mock_normalize.return_value = b"fake_normalized_audio"
        mock_audio_quality.return_value = _valid_audio_quality()

        mock_lang = MagicMock()
        mock_lang.language_name = "Hindi"
        mock_detect_lang.return_value = mock_lang

        mock_transcribe.return_value = _valid_transcript()
        mock_structure.return_value = _valid_structured()
        mock_norm_utt.return_value = _valid_phase4()
        mock_redact.return_value = _valid_phase4()
        mock_sentiment.return_value = _valid_sentiment()
        mock_intent.return_value = _valid_intent()
        mock_obligation.return_value = "weak"
        mock_contradictions.return_value = True
        mock_entities.return_value = _valid_entities()

        mock_bundle = MagicMock()
        mock_signal_bundle.return_value = mock_bundle
        mock_risk.return_value = _valid_risk()

        mock_summary.return_value = (
            "Customer made a conditional repayment promise under stress."
        )

        from src.pipeline import run_pipeline

        result = run_pipeline(b"fake_audio", "test.wav")

        # Verify top-level schema
        expected_keys = {
            "call_context",
            "speaker_analysis",
            "nlp_insights",
            "risk_signals",
            "risk_assessment",
            "summary_for_rag",
        }
        self.assertEqual(set(result.keys()), expected_keys)

        # Verify no forbidden keys
        for forbidden in ("call_id", "customer_id", "loan_id", "transcript"):
            self.assertNotIn(forbidden, result)

        # Verify types
        self.assertIsInstance(result["call_context"], dict)
        self.assertIsInstance(result["speaker_analysis"], dict)
        self.assertIsInstance(result["nlp_insights"], dict)
        self.assertIsInstance(result["risk_signals"], dict)
        self.assertIsInstance(result["risk_assessment"], dict)
        self.assertIsInstance(result["summary_for_rag"], str)

        # Verify call order — all phases were invoked
        mock_normalize.assert_called_once()
        mock_audio_quality.assert_called_once()
        mock_transcribe.assert_called_once()
        mock_structure.assert_called_once()
        mock_norm_utt.assert_called_once()
        mock_redact.assert_called_once()
        mock_sentiment.assert_called_once()
        mock_intent.assert_called_once()
        mock_obligation.assert_called_once()
        mock_contradictions.assert_called_once()
        mock_entities.assert_called_once()
        mock_signal_bundle.assert_called_once()
        mock_risk.assert_called_once()
        mock_summary.assert_called_once()


if __name__ == "__main__":
    unittest.main()
