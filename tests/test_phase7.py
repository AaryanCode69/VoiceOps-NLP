"""
tests/test_phase7.py
=====================
Phase 7 Tests — Risk Scoring Engine

Test categories:
    1. Signal bundle validation (build_signal_bundle)
    2. Sub-score determinism and range checks
    3. Weighted aggregation and clamping
    4. Fraud likelihood threshold classification
    5. Key risk factor traceability
    6. Confidence computation
    7. Custom weight validation
    8. Edge cases (all-low, all-high, default/neutral inputs)
    9. Determinism guarantee (same input → same output)

All tests are offline — no LLM or API calls.
"""

import os
import sys
import unittest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.risk.signals import (
    RiskSignalBundle,
    NoiseLevel,
    CallStability,
    SpeechNaturalness,
    build_signal_bundle,
    _VALID_SENTIMENT_LABELS,
    _VALID_INTENT_LABELS,
    _VALID_CONDITIONALITY,
    _VALID_OBLIGATION,
)
from src.risk.scorer import (
    compute_risk,
    DEFAULT_WEIGHTS,
    FRAUD_THRESHOLD_HIGH,
    FRAUD_THRESHOLD_MEDIUM,
    RISK_FACTOR_THRESHOLD,
    _score_sentiment,
    _score_intent,
    _score_conditionality,
    _score_obligation,
    _score_contradictions,
    _score_audio_trust,
    _validate_weights,
    _compute_confidence,
)


# ===================================================================
# Test fixtures — realistic signal bundles
# ===================================================================

def _low_risk_bundle() -> RiskSignalBundle:
    """All signals indicate low risk."""
    return RiskSignalBundle(
        sentiment_label="calm",
        sentiment_confidence=0.95,
        intent_label="repayment_promise",
        intent_confidence=0.90,
        conditionality="low",
        obligation_strength="strong",
        contradictions_detected=False,
        noise_level="low",
        call_stability="high",
        speech_naturalness="normal",
    )


def _high_risk_bundle() -> RiskSignalBundle:
    """All signals indicate high risk."""
    return RiskSignalBundle(
        sentiment_label="evasive",
        sentiment_confidence=0.92,
        intent_label="deflection",
        intent_confidence=0.88,
        conditionality="high",
        obligation_strength="none",
        contradictions_detected=True,
        noise_level="high",
        call_stability="low",
        speech_naturalness="suspicious",
    )


def _medium_risk_bundle() -> RiskSignalBundle:
    """Mixed signals — moderate risk."""
    return RiskSignalBundle(
        sentiment_label="stressed",
        sentiment_confidence=0.75,
        intent_label="repayment_delay",
        intent_confidence=0.80,
        conditionality="medium",
        obligation_strength="conditional",
        contradictions_detected=False,
        noise_level="medium",
        call_stability="medium",
        speech_naturalness="normal",
    )


def _neutral_bundle() -> RiskSignalBundle:
    """Neutral / default-like signals."""
    return RiskSignalBundle(
        sentiment_label="neutral",
        sentiment_confidence=0.50,
        intent_label="unknown",
        intent_confidence=0.50,
        conditionality="low",
        obligation_strength="none",
        contradictions_detected=False,
        noise_level="low",
        call_stability="high",
        speech_naturalness="normal",
    )


# ===================================================================
# 1. Signal Bundle Validation Tests
# ===================================================================

class TestBuildSignalBundle(unittest.TestCase):
    """Tests for build_signal_bundle validation logic."""

    def test_valid_bundle_creation(self):
        """Valid inputs produce a correctly populated bundle."""
        bundle = build_signal_bundle(
            sentiment={"label": "stressed", "confidence": 0.82},
            intent={"label": "repayment_delay", "confidence": 0.85, "conditionality": "medium"},
            obligation_strength="conditional",
            contradictions_detected=False,
            audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
        )
        self.assertEqual(bundle.sentiment_label, "stressed")
        self.assertEqual(bundle.sentiment_confidence, 0.82)
        self.assertEqual(bundle.intent_label, "repayment_delay")
        self.assertEqual(bundle.intent_confidence, 0.85)
        self.assertEqual(bundle.conditionality, "medium")
        self.assertEqual(bundle.obligation_strength, "conditional")
        self.assertFalse(bundle.contradictions_detected)
        self.assertEqual(bundle.noise_level, "low")
        self.assertEqual(bundle.call_stability, "high")
        self.assertEqual(bundle.speech_naturalness, "normal")

    def test_invalid_sentiment_label(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "happy", "confidence": 0.5},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="none",
                contradictions_detected=False,
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_sentiment_confidence_type(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": "high"},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="none",
                contradictions_detected=False,
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_sentiment_confidence_range(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": 1.5},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="none",
                contradictions_detected=False,
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_intent_label(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": 0.5},
                intent={"label": "bribe", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="none",
                contradictions_detected=False,
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_conditionality(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": 0.5},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "extreme"},
                obligation_strength="none",
                contradictions_detected=False,
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_obligation_strength(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": 0.5},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="maybe",
                contradictions_detected=False,
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_contradictions_type(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": 0.5},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="none",
                contradictions_detected="yes",
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_noise_level(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": 0.5},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="none",
                contradictions_detected=False,
                audio_quality={"noise_level": "extreme", "call_stability": "high", "speech_naturalness": "normal"},
            )

    def test_invalid_speech_naturalness(self):
        with self.assertRaises(ValueError):
            build_signal_bundle(
                sentiment={"label": "calm", "confidence": 0.5},
                intent={"label": "unknown", "confidence": 0.5, "conditionality": "low"},
                obligation_strength="none",
                contradictions_detected=False,
                audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "robot"},
            )

    def test_bundle_equality(self):
        """Two bundles with same values must be equal."""
        b1 = _low_risk_bundle()
        b2 = _low_risk_bundle()
        self.assertEqual(b1, b2)

    def test_bundle_inequality(self):
        """Bundles with different values must not be equal."""
        self.assertNotEqual(_low_risk_bundle(), _high_risk_bundle())


# ===================================================================
# 2. Sub-Score Tests
# ===================================================================

class TestSubScores(unittest.TestCase):
    """Verify each sub-scorer returns values in [0, 100]."""

    def _assert_range(self, value: float, label: str):
        self.assertGreaterEqual(value, 0.0, f"{label} below 0")
        self.assertLessEqual(value, 100.0, f"{label} above 100")

    def test_sentiment_scores_all_labels(self):
        for label in _VALID_SENTIMENT_LABELS:
            for conf in [0.0, 0.5, 1.0]:
                bundle = RiskSignalBundle(
                    sentiment_label=label, sentiment_confidence=conf,
                    intent_label="unknown", intent_confidence=0.5,
                    conditionality="low", obligation_strength="none",
                    contradictions_detected=False,
                    noise_level="low", call_stability="high",
                    speech_naturalness="normal",
                )
                score = _score_sentiment(bundle)
                self._assert_range(score, f"sentiment({label}, {conf})")

    def test_intent_scores_all_labels(self):
        for label in _VALID_INTENT_LABELS:
            for conf in [0.0, 0.5, 1.0]:
                bundle = RiskSignalBundle(
                    sentiment_label="neutral", sentiment_confidence=0.5,
                    intent_label=label, intent_confidence=conf,
                    conditionality="low", obligation_strength="none",
                    contradictions_detected=False,
                    noise_level="low", call_stability="high",
                    speech_naturalness="normal",
                )
                score = _score_intent(bundle)
                self._assert_range(score, f"intent({label}, {conf})")

    def test_conditionality_scores(self):
        for cond in _VALID_CONDITIONALITY:
            bundle = RiskSignalBundle(
                sentiment_label="neutral", sentiment_confidence=0.5,
                intent_label="unknown", intent_confidence=0.5,
                conditionality=cond, obligation_strength="none",
                contradictions_detected=False,
                noise_level="low", call_stability="high",
                speech_naturalness="normal",
            )
            score = _score_conditionality(bundle)
            self._assert_range(score, f"conditionality({cond})")

    def test_obligation_scores(self):
        for obl in _VALID_OBLIGATION:
            bundle = RiskSignalBundle(
                sentiment_label="neutral", sentiment_confidence=0.5,
                intent_label="unknown", intent_confidence=0.5,
                conditionality="low", obligation_strength=obl,
                contradictions_detected=False,
                noise_level="low", call_stability="high",
                speech_naturalness="normal",
            )
            score = _score_obligation(bundle)
            self._assert_range(score, f"obligation({obl})")

    def test_contradiction_scores(self):
        for flag in [True, False]:
            bundle = RiskSignalBundle(
                sentiment_label="neutral", sentiment_confidence=0.5,
                intent_label="unknown", intent_confidence=0.5,
                conditionality="low", obligation_strength="none",
                contradictions_detected=flag,
                noise_level="low", call_stability="high",
                speech_naturalness="normal",
            )
            score = _score_contradictions(bundle)
            self._assert_range(score, f"contradictions({flag})")

    def test_audio_trust_scores(self):
        for noise in ["low", "medium", "high"]:
            for stab in ["low", "medium", "high"]:
                for nat in ["normal", "suspicious"]:
                    bundle = RiskSignalBundle(
                        sentiment_label="neutral", sentiment_confidence=0.5,
                        intent_label="unknown", intent_confidence=0.5,
                        conditionality="low", obligation_strength="none",
                        contradictions_detected=False,
                        noise_level=noise, call_stability=stab,
                        speech_naturalness=nat,
                    )
                    score = _score_audio_trust(bundle)
                    self._assert_range(
                        score,
                        f"audio_trust(noise={noise}, stab={stab}, nat={nat})",
                    )

    def test_evasive_higher_than_calm(self):
        """Evasive sentiment must score higher than calm at same confidence."""
        base = dict(
            intent_label="unknown", intent_confidence=0.5,
            conditionality="low", obligation_strength="none",
            contradictions_detected=False,
            noise_level="low", call_stability="high",
            speech_naturalness="normal",
        )
        calm = _score_sentiment(RiskSignalBundle(
            sentiment_label="calm", sentiment_confidence=0.9, **base))
        evasive = _score_sentiment(RiskSignalBundle(
            sentiment_label="evasive", sentiment_confidence=0.9, **base))
        self.assertGreater(evasive, calm)

    def test_refusal_higher_than_promise(self):
        """Refusal intent must score higher than repayment_promise at same confidence."""
        base = dict(
            sentiment_label="neutral", sentiment_confidence=0.5,
            conditionality="low", obligation_strength="none",
            contradictions_detected=False,
            noise_level="low", call_stability="high",
            speech_naturalness="normal",
        )
        promise = _score_intent(RiskSignalBundle(
            intent_label="repayment_promise", intent_confidence=0.9, **base))
        refusal = _score_intent(RiskSignalBundle(
            intent_label="refusal", intent_confidence=0.9, **base))
        self.assertGreater(refusal, promise)

    def test_contradiction_true_higher_than_false(self):
        base = dict(
            sentiment_label="neutral", sentiment_confidence=0.5,
            intent_label="unknown", intent_confidence=0.5,
            conditionality="low", obligation_strength="none",
            noise_level="low", call_stability="high",
            speech_naturalness="normal",
        )
        no_contra = _score_contradictions(RiskSignalBundle(
            contradictions_detected=False, **base))
        with_contra = _score_contradictions(RiskSignalBundle(
            contradictions_detected=True, **base))
        self.assertGreater(with_contra, no_contra)


# ===================================================================
# 3. Risk Score Range & Aggregation Tests
# ===================================================================

class TestRiskScoreRange(unittest.TestCase):
    """Risk score must always be in [0, 100]."""

    def test_low_risk_score_range(self):
        result = compute_risk(_low_risk_bundle())
        self.assertGreaterEqual(result["risk_score"], 0)
        self.assertLessEqual(result["risk_score"], 100)

    def test_high_risk_score_range(self):
        result = compute_risk(_high_risk_bundle())
        self.assertGreaterEqual(result["risk_score"], 0)
        self.assertLessEqual(result["risk_score"], 100)

    def test_medium_risk_score_range(self):
        result = compute_risk(_medium_risk_bundle())
        self.assertGreaterEqual(result["risk_score"], 0)
        self.assertLessEqual(result["risk_score"], 100)

    def test_neutral_score_range(self):
        result = compute_risk(_neutral_bundle())
        self.assertGreaterEqual(result["risk_score"], 0)
        self.assertLessEqual(result["risk_score"], 100)

    def test_risk_score_is_int(self):
        """Risk score must be an integer."""
        result = compute_risk(_medium_risk_bundle())
        self.assertIsInstance(result["risk_score"], int)


# ===================================================================
# 4. Fraud Likelihood Classification Tests
# ===================================================================

class TestFraudLikelihood(unittest.TestCase):
    """Fraud likelihood must match risk score thresholds."""

    def test_low_risk_produces_low_fraud(self):
        result = compute_risk(_low_risk_bundle())
        self.assertEqual(result["fraud_likelihood"], "low")

    def test_high_risk_produces_high_fraud(self):
        result = compute_risk(_high_risk_bundle())
        self.assertEqual(result["fraud_likelihood"], "high")

    def test_medium_risk_produces_medium_fraud(self):
        result = compute_risk(_medium_risk_bundle())
        self.assertIn(result["fraud_likelihood"], ["medium", "high"])

    def test_fraud_likelihood_valid_values(self):
        """Fraud likelihood must be one of the three allowed values."""
        for bundle_fn in [_low_risk_bundle, _medium_risk_bundle, _high_risk_bundle, _neutral_bundle]:
            result = compute_risk(bundle_fn())
            self.assertIn(result["fraud_likelihood"], ["low", "medium", "high"])

    def test_custom_thresholds(self):
        """Custom thresholds should shift classification."""
        bundle = _medium_risk_bundle()
        result_strict = compute_risk(bundle, fraud_threshold_high=20.0, fraud_threshold_medium=10.0)
        result_loose = compute_risk(bundle, fraud_threshold_high=95.0, fraud_threshold_medium=90.0)
        # With very strict thresholds most scores become "high"
        # With very loose thresholds most scores become "low"
        self.assertIn(result_strict["fraud_likelihood"], ["medium", "high"])
        self.assertEqual(result_loose["fraud_likelihood"], "low")


# ===================================================================
# 5. Key Risk Factor Traceability Tests
# ===================================================================

class TestKeyRiskFactors(unittest.TestCase):
    """Key risk factors must be traceable to input signals."""

    VALID_FACTORS = {
        "high_emotional_stress",
        "risky_intent",
        "conditional_commitment",
        "weak_obligation",
        "contradictory_statements",
        "suspicious_audio_signals",
    }

    def test_all_factors_are_valid_labels(self):
        """Every returned factor must be from the known set."""
        for bundle_fn in [_low_risk_bundle, _medium_risk_bundle, _high_risk_bundle, _neutral_bundle]:
            result = compute_risk(bundle_fn())
            for factor in result["key_risk_factors"]:
                self.assertIn(factor, self.VALID_FACTORS)

    def test_low_risk_has_few_factors(self):
        """Low-risk bundle should have minimal risk factors."""
        result = compute_risk(_low_risk_bundle())
        self.assertLessEqual(len(result["key_risk_factors"]), 1)

    def test_high_risk_has_multiple_factors(self):
        """High-risk bundle should flag multiple contributing factors."""
        result = compute_risk(_high_risk_bundle())
        self.assertGreater(len(result["key_risk_factors"]), 2)

    def test_contradiction_factor_present_when_detected(self):
        """Contradictions detected → 'contradictory_statements' must be in factors."""
        bundle = _high_risk_bundle()  # has contradictions_detected=True
        result = compute_risk(bundle)
        self.assertIn("contradictory_statements", result["key_risk_factors"])

    def test_contradiction_factor_absent_when_not_detected(self):
        """No contradictions → 'contradictory_statements' must not be in factors."""
        bundle = _low_risk_bundle()  # has contradictions_detected=False
        result = compute_risk(bundle)
        self.assertNotIn("contradictory_statements", result["key_risk_factors"])

    def test_factors_is_list(self):
        result = compute_risk(_low_risk_bundle())
        self.assertIsInstance(result["key_risk_factors"], list)


# ===================================================================
# 6. Confidence Computation Tests
# ===================================================================

class TestConfidence(unittest.TestCase):
    """Confidence must be in [0.0, 1.0] and reflect input quality."""

    def test_confidence_range(self):
        for bundle_fn in [_low_risk_bundle, _medium_risk_bundle, _high_risk_bundle, _neutral_bundle]:
            result = compute_risk(bundle_fn())
            self.assertGreaterEqual(result["confidence"], 0.0)
            self.assertLessEqual(result["confidence"], 1.0)

    def test_high_upstream_confidence_produces_high_scorer_confidence(self):
        """Bundle with high upstream confidences should yield high overall confidence."""
        bundle = RiskSignalBundle(
            sentiment_label="neutral", sentiment_confidence=0.95,
            intent_label="unknown", intent_confidence=0.95,
            conditionality="low", obligation_strength="none",
            contradictions_detected=False,
            noise_level="low", call_stability="high",
            speech_naturalness="normal",
        )
        conf = _compute_confidence(bundle)
        self.assertGreaterEqual(conf, 0.90)

    def test_zero_upstream_confidence_has_floor(self):
        """Even with zero upstream confidence, a deterministic floor exists."""
        bundle = RiskSignalBundle(
            sentiment_label="neutral", sentiment_confidence=0.0,
            intent_label="unknown", intent_confidence=0.0,
            conditionality="low", obligation_strength="none",
            contradictions_detected=False,
            noise_level="low", call_stability="high",
            speech_naturalness="normal",
        )
        conf = _compute_confidence(bundle)
        self.assertGreater(conf, 0.0)

    def test_confidence_is_float(self):
        result = compute_risk(_medium_risk_bundle())
        self.assertIsInstance(result["confidence"], float)


# ===================================================================
# 7. Weight Validation Tests
# ===================================================================

class TestWeightValidation(unittest.TestCase):
    """Custom weights must be validated."""

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_missing_key_raises(self):
        bad_weights = {k: v for k, v in DEFAULT_WEIGHTS.items() if k != "sentiment"}
        with self.assertRaises(ValueError):
            _validate_weights(bad_weights)

    def test_extra_key_raises(self):
        bad_weights = {**DEFAULT_WEIGHTS, "extra": 0.0}
        with self.assertRaises(ValueError):
            _validate_weights(bad_weights)

    def test_weights_not_summing_to_one_raises(self):
        bad_weights = {k: 0.5 for k in DEFAULT_WEIGHTS}
        with self.assertRaises(ValueError):
            _validate_weights(bad_weights)

    def test_custom_valid_weights_accepted(self):
        custom = {
            "sentiment": 0.30,
            "intent": 0.30,
            "conditionality": 0.10,
            "obligation": 0.10,
            "contradictions": 0.10,
            "audio_trust": 0.10,
        }
        result = _validate_weights(custom)
        self.assertEqual(result, custom)


# ===================================================================
# 8. Determinism Tests
# ===================================================================

class TestDeterminism(unittest.TestCase):
    """Same inputs must always produce identical outputs."""

    def test_repeated_low_risk(self):
        results = [compute_risk(_low_risk_bundle()) for _ in range(10)]
        for r in results[1:]:
            self.assertEqual(r, results[0])

    def test_repeated_high_risk(self):
        results = [compute_risk(_high_risk_bundle()) for _ in range(10)]
        for r in results[1:]:
            self.assertEqual(r, results[0])

    def test_repeated_medium_risk(self):
        results = [compute_risk(_medium_risk_bundle()) for _ in range(10)]
        for r in results[1:]:
            self.assertEqual(r, results[0])


# ===================================================================
# 9. Output Structure Tests
# ===================================================================

class TestOutputStructure(unittest.TestCase):
    """Output must have exactly the required keys, no more."""

    REQUIRED_KEYS = {"risk_score", "fraud_likelihood", "confidence", "key_risk_factors"}

    def test_output_keys_exact(self):
        for bundle_fn in [_low_risk_bundle, _medium_risk_bundle, _high_risk_bundle, _neutral_bundle]:
            result = compute_risk(bundle_fn())
            self.assertEqual(set(result.keys()), self.REQUIRED_KEYS)

    def test_no_explanations_in_output(self):
        """Output must not contain explanation-like keys."""
        forbidden_keys = {"explanation", "summary", "description", "text", "transcript", "id"}
        for bundle_fn in [_low_risk_bundle, _high_risk_bundle]:
            result = compute_risk(bundle_fn())
            self.assertTrue(forbidden_keys.isdisjoint(set(result.keys())))


# ===================================================================
# 10. Integration Tests — Realistic Scenarios
# ===================================================================

class TestRealisticScenarios(unittest.TestCase):
    """End-to-end scenarios verifying the scoring makes sense."""

    def test_cooperative_customer(self):
        """Customer who is calm, promises repayment, no contradictions → low risk."""
        bundle = build_signal_bundle(
            sentiment={"label": "calm", "confidence": 0.90},
            intent={"label": "repayment_promise", "confidence": 0.92, "conditionality": "low"},
            obligation_strength="strong",
            contradictions_detected=False,
            audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
        )
        result = compute_risk(bundle)
        self.assertLess(result["risk_score"], 35)
        self.assertEqual(result["fraud_likelihood"], "low")

    def test_evasive_contradictory_customer(self):
        """Evasive, deflecting, contradictory, suspicious audio → high risk."""
        bundle = build_signal_bundle(
            sentiment={"label": "evasive", "confidence": 0.88},
            intent={"label": "deflection", "confidence": 0.85, "conditionality": "high"},
            obligation_strength="none",
            contradictions_detected=True,
            audio_quality={"noise_level": "high", "call_stability": "low", "speech_naturalness": "suspicious"},
        )
        result = compute_risk(bundle)
        self.assertGreaterEqual(result["risk_score"], 65)
        self.assertEqual(result["fraud_likelihood"], "high")
        self.assertIn("contradictory_statements", result["key_risk_factors"])

    def test_stressed_delay_customer(self):
        """Stressed, delaying, conditional obligation → medium risk."""
        bundle = build_signal_bundle(
            sentiment={"label": "stressed", "confidence": 0.78},
            intent={"label": "repayment_delay", "confidence": 0.80, "conditionality": "medium"},
            obligation_strength="conditional",
            contradictions_detected=False,
            audio_quality={"noise_level": "medium", "call_stability": "medium", "speech_naturalness": "normal"},
        )
        result = compute_risk(bundle)
        self.assertGreaterEqual(result["risk_score"], 30)
        self.assertLessEqual(result["risk_score"], 70)

    def test_disputing_customer_clean_audio(self):
        """Customer disputes debt, clean audio, no contradictions."""
        bundle = build_signal_bundle(
            sentiment={"label": "frustrated", "confidence": 0.82},
            intent={"label": "dispute", "confidence": 0.90, "conditionality": "low"},
            obligation_strength="none",
            contradictions_detected=False,
            audio_quality={"noise_level": "low", "call_stability": "high", "speech_naturalness": "normal"},
        )
        result = compute_risk(bundle)
        # Dispute + frustrated + no obligation = elevated risk, but clean audio helps
        self.assertGreaterEqual(result["risk_score"], 35)
        self.assertIn(result["fraud_likelihood"], ["medium", "high"])


if __name__ == "__main__":
    unittest.main()
