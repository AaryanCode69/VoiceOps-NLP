"""
tests/test_phase8.py
=====================
Phase 8 Tests — RAG Summary Generator

Test categories:
    1. OFFLINE UNIT TESTS — no OpenAI API key required
       - Input validation (all fields)
       - Template-based fallback summary generation
       - Summary constraint enforcement (one sentence, no banned words, no numbers)
       - Determinism guarantee (same input → same output)
       - OpenAI input construction
       - Summary validation logic
       - Edge cases (all-low, all-high, empty risk factors)

    2. MOCK INTEGRATION TESTS — OpenAI mocked
       - OpenAI success path with valid summary
       - OpenAI failure → fallback
       - OpenAI returns invalid summary → fallback
       - OpenAI returns banned words → fallback

All tests are offline — no LLM or API calls.
"""

import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.rag.summary_generator import (
    generate_summary,
    _validate_inputs,
    _generate_template_summary,
    _build_openai_input,
    _validate_summary,
    _VALID_INTENT_LABELS,
    _VALID_CONDITIONALITY,
    _VALID_OBLIGATION,
    _VALID_FRAUD_LIKELIHOOD,
    _VALID_RISK_FACTORS,
    _BANNED_WORDS,
)


# ===================================================================
# Test fixtures — realistic Phase 6 / Phase 7 structured outputs
# ===================================================================

def _low_risk_inputs() -> dict:
    """All signals indicate low risk."""
    return {
        "intent_label": "repayment_promise",
        "conditionality": "low",
        "obligation_strength": "strong",
        "contradictions_detected": False,
        "risk_score": 8,
        "fraud_likelihood": "low",
        "key_risk_factors": [],
    }


def _high_risk_inputs() -> dict:
    """All signals indicate high risk."""
    return {
        "intent_label": "deflection",
        "conditionality": "high",
        "obligation_strength": "none",
        "contradictions_detected": True,
        "risk_score": 82,
        "fraud_likelihood": "high",
        "key_risk_factors": [
            "conditional_commitment",
            "contradictory_statements",
            "high_emotional_stress",
        ],
    }


def _medium_risk_inputs() -> dict:
    """Mixed signals — moderate risk."""
    return {
        "intent_label": "repayment_delay",
        "conditionality": "medium",
        "obligation_strength": "conditional",
        "contradictions_detected": False,
        "risk_score": 45,
        "fraud_likelihood": "medium",
        "key_risk_factors": ["conditional_commitment", "weak_obligation"],
    }


# ===================================================================
# 1. INPUT VALIDATION TESTS
# ===================================================================


class TestInputValidation(unittest.TestCase):
    """Tests for _validate_inputs — all fields must be validated."""

    def test_valid_low_risk(self):
        """Valid low-risk inputs should not raise."""
        _validate_inputs(**_low_risk_inputs())

    def test_valid_high_risk(self):
        """Valid high-risk inputs should not raise."""
        _validate_inputs(**_high_risk_inputs())

    def test_valid_medium_risk(self):
        """Valid medium-risk inputs should not raise."""
        _validate_inputs(**_medium_risk_inputs())

    def test_invalid_intent_label(self):
        inputs = _low_risk_inputs()
        inputs["intent_label"] = "bribery"
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_invalid_conditionality(self):
        inputs = _low_risk_inputs()
        inputs["conditionality"] = "extreme"
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_invalid_obligation_strength(self):
        inputs = _low_risk_inputs()
        inputs["obligation_strength"] = "maybe"
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_invalid_contradictions_type(self):
        inputs = _low_risk_inputs()
        inputs["contradictions_detected"] = "yes"
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_invalid_risk_score_type(self):
        inputs = _low_risk_inputs()
        inputs["risk_score"] = 45.5
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_risk_score_below_zero(self):
        inputs = _low_risk_inputs()
        inputs["risk_score"] = -1
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_risk_score_above_100(self):
        inputs = _low_risk_inputs()
        inputs["risk_score"] = 101
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_invalid_fraud_likelihood(self):
        inputs = _low_risk_inputs()
        inputs["fraud_likelihood"] = "extreme"
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_invalid_risk_factor(self):
        inputs = _low_risk_inputs()
        inputs["key_risk_factors"] = ["unknown_factor"]
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_risk_factors_not_list(self):
        inputs = _low_risk_inputs()
        inputs["key_risk_factors"] = "conditional_commitment"
        with self.assertRaises(ValueError):
            _validate_inputs(**inputs)

    def test_all_valid_intent_labels(self):
        """Every valid intent label should pass validation."""
        for label in _VALID_INTENT_LABELS:
            inputs = _low_risk_inputs()
            inputs["intent_label"] = label
            _validate_inputs(**inputs)  # Should not raise

    def test_all_valid_obligation_strengths(self):
        """Every valid obligation strength should pass validation."""
        for strength in _VALID_OBLIGATION:
            inputs = _low_risk_inputs()
            inputs["obligation_strength"] = strength
            _validate_inputs(**inputs)

    def test_all_valid_fraud_likelihoods(self):
        """Every valid fraud likelihood should pass validation."""
        for likelihood in _VALID_FRAUD_LIKELIHOOD:
            inputs = _low_risk_inputs()
            inputs["fraud_likelihood"] = likelihood
            _validate_inputs(**inputs)

    def test_all_valid_risk_factors(self):
        """Every valid risk factor should pass validation."""
        for factor in _VALID_RISK_FACTORS:
            inputs = _low_risk_inputs()
            inputs["key_risk_factors"] = [factor]
            _validate_inputs(**inputs)

    def test_risk_score_boundary_zero(self):
        inputs = _low_risk_inputs()
        inputs["risk_score"] = 0
        _validate_inputs(**inputs)

    def test_risk_score_boundary_100(self):
        inputs = _low_risk_inputs()
        inputs["risk_score"] = 100
        _validate_inputs(**inputs)


# ===================================================================
# 2. TEMPLATE SUMMARY TESTS
# ===================================================================


class TestTemplateSummary(unittest.TestCase):
    """Tests for _generate_template_summary — deterministic fallback."""

    def _get_template(self, **overrides) -> str:
        base = {
            "intent_label": "repayment_promise",
            "conditionality": "low",
            "obligation_strength": "strong",
            "contradictions_detected": False,
            "fraud_likelihood": "low",
            "key_risk_factors": [],
        }
        base.update(overrides)
        return _generate_template_summary(**base)

    def test_returns_string(self):
        summary = self._get_template()
        self.assertIsInstance(summary, str)

    def test_ends_with_period(self):
        summary = self._get_template()
        self.assertTrue(summary.strip().endswith("."))

    def test_single_sentence(self):
        """Template summary must be exactly one sentence."""
        summary = self._get_template()
        period_count = summary.count(".")
        self.assertEqual(period_count, 1, f"Expected 1 period, got {period_count}: {summary!r}")

    def test_no_banned_words(self):
        for inputs_fn in [_low_risk_inputs, _medium_risk_inputs, _high_risk_inputs]:
            inputs = inputs_fn()
            # Remove risk_score (not used in template)
            inputs.pop("risk_score", None)
            summary = _generate_template_summary(**inputs)
            summary_words = set(summary.lower().split())
            for word in _BANNED_WORDS:
                self.assertNotIn(
                    word, summary_words,
                    f"Banned word {word!r} found in: {summary!r}"
                )

    def test_no_numeric_scores(self):
        """Template summary must not contain numeric values."""
        for inputs_fn in [_low_risk_inputs, _medium_risk_inputs, _high_risk_inputs]:
            inputs = inputs_fn()
            inputs.pop("risk_score", None)
            summary = _generate_template_summary(**inputs)
            self.assertIsNone(
                re.search(r'\b\d{1,3}\b', summary),
                f"Numeric value found in: {summary!r}"
            )

    def test_low_risk_phrasing(self):
        summary = self._get_template(fraud_likelihood="low")
        self.assertIn("within normal parameters", summary)

    def test_medium_risk_phrasing(self):
        summary = self._get_template(fraud_likelihood="medium")
        self.assertIn("warranting closer attention", summary)

    def test_high_risk_phrasing(self):
        summary = self._get_template(fraud_likelihood="high")
        self.assertIn("requiring further review", summary)

    def test_contradictions_included(self):
        summary = self._get_template(contradictions_detected=True)
        self.assertIn("contradiction", summary.lower())

    def test_deterministic_same_output(self):
        """Same inputs must produce identical output every time."""
        inputs = _high_risk_inputs()
        inputs.pop("risk_score", None)
        s1 = _generate_template_summary(**inputs)
        s2 = _generate_template_summary(**inputs)
        s3 = _generate_template_summary(**inputs)
        self.assertEqual(s1, s2)
        self.assertEqual(s2, s3)

    def test_all_intent_labels_produce_valid_summary(self):
        """Every intent label should produce a valid single-sentence summary."""
        for label in _VALID_INTENT_LABELS:
            summary = self._get_template(intent_label=label)
            self.assertTrue(summary.endswith("."), f"Bad summary for {label}: {summary!r}")
            self.assertGreater(len(summary), 20, f"Summary too short for {label}")

    def test_all_obligation_strengths_produce_valid_summary(self):
        for strength in _VALID_OBLIGATION:
            summary = self._get_template(obligation_strength=strength)
            self.assertTrue(summary.endswith("."))
            self.assertGreater(len(summary), 20)

    def test_empty_risk_factors(self):
        summary = self._get_template(key_risk_factors=[])
        self.assertIsInstance(summary, str)
        self.assertTrue(summary.endswith("."))

    def test_multiple_risk_factors(self):
        summary = self._get_template(
            key_risk_factors=[
                "high_emotional_stress",
                "contradictory_statements",
                "suspicious_audio_signals",
            ]
        )
        self.assertIsInstance(summary, str)
        self.assertTrue(summary.endswith("."))


# ===================================================================
# 3. SUMMARY VALIDATION TESTS
# ===================================================================


class TestSummaryValidation(unittest.TestCase):
    """Tests for _validate_summary — constraint enforcement."""

    def test_valid_summary(self):
        result = _validate_summary(
            "Customer expressed a repayment promise with strong commitment, "
            "indicating low risk and within normal parameters."
        )
        self.assertIsInstance(result, str)

    def test_empty_summary_rejected(self):
        with self.assertRaises(ValueError):
            _validate_summary("")

    def test_no_period_rejected(self):
        with self.assertRaises(ValueError):
            _validate_summary("This summary has no period")

    def test_multiple_sentences_rejected(self):
        with self.assertRaises(ValueError):
            _validate_summary("First sentence. Second sentence.")

    def test_banned_word_rejected(self):
        with self.assertRaises(ValueError):
            _validate_summary("Customer is a fraudster and should be investigated.")

    def test_numeric_score_rejected(self):
        with self.assertRaises(ValueError):
            _validate_summary("Customer has a risk score of 78 indicating high risk.")

    def test_banned_word_lied(self):
        with self.assertRaises(ValueError):
            _validate_summary("Customer lied about their payment.")

    def test_banned_word_scam(self):
        with self.assertRaises(ValueError):
            _validate_summary("This appears to be a scam call.")


# ===================================================================
# 4. OPENAI INPUT CONSTRUCTION TESTS
# ===================================================================


class TestOpenAIInput(unittest.TestCase):
    """Tests for _build_openai_input — structured signal serialization."""

    def test_returns_valid_json(self):
        import json
        result = _build_openai_input(
            intent_label="deflection",
            conditionality="high",
            obligation_strength="none",
            contradictions_detected=True,
            fraud_likelihood="high",
            key_risk_factors=["contradictory_statements"],
        )
        parsed = json.loads(result)
        self.assertIsInstance(parsed, dict)

    def test_contains_all_fields(self):
        import json
        result = _build_openai_input(
            intent_label="refusal",
            conditionality="medium",
            obligation_strength="weak",
            contradictions_detected=False,
            fraud_likelihood="medium",
            key_risk_factors=["weak_obligation"],
        )
        parsed = json.loads(result)
        expected_keys = {
            "intent", "conditionality", "obligation_strength",
            "contradictions_detected", "fraud_likelihood", "key_risk_factors",
        }
        self.assertEqual(set(parsed.keys()), expected_keys)

    def test_no_transcript_data(self):
        """OpenAI input must never contain raw transcript text."""
        import json
        result = _build_openai_input(
            intent_label="repayment_promise",
            conditionality="low",
            obligation_strength="strong",
            contradictions_detected=False,
            fraud_likelihood="low",
            key_risk_factors=[],
        )
        parsed = json.loads(result)
        # Must not have transcript, text, utterance, or speaker keys
        for key in ["transcript", "text", "utterance", "speaker", "audio"]:
            self.assertNotIn(key, parsed)

    def test_no_risk_score_in_input(self):
        """risk_score (numeric) must not be sent to OpenAI."""
        import json
        result = _build_openai_input(
            intent_label="dispute",
            conditionality="high",
            obligation_strength="conditional",
            contradictions_detected=True,
            fraud_likelihood="high",
            key_risk_factors=["risky_intent"],
        )
        parsed = json.loads(result)
        self.assertNotIn("risk_score", parsed)


# ===================================================================
# 5. FULL PIPELINE TESTS (OpenAI mocked)
# ===================================================================


class TestGenerateSummaryWithMock(unittest.TestCase):
    """Tests for generate_summary — full pipeline with mocked OpenAI."""

    @patch("src.rag.summary_generator._call_openai")
    def test_openai_success(self, mock_openai):
        """When OpenAI returns a valid summary, it should be used."""
        mock_openai.return_value = (
            "Customer expressed deflective responses with no discernible "
            "commitment, indicating elevated risk and requiring further review."
        )
        inputs = _high_risk_inputs()
        result = generate_summary(**inputs)
        self.assertTrue(result.endswith("."))
        mock_openai.assert_called_once()

    @patch("src.rag.summary_generator._call_openai")
    def test_openai_failure_falls_back(self, mock_openai):
        """When OpenAI fails, fallback template must be used."""
        mock_openai.side_effect = Exception("API unavailable")
        inputs = _high_risk_inputs()
        result = generate_summary(**inputs)
        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith("."))
        # Should still contain relevant phrasing from template
        self.assertIn("requiring further review", result)

    @patch("src.rag.summary_generator._call_openai")
    def test_openai_banned_word_falls_back(self, mock_openai):
        """If OpenAI returns banned words, fallback must be used."""
        mock_openai.return_value = "Customer is a fraudster who lied."
        inputs = _high_risk_inputs()
        result = generate_summary(**inputs)
        # Should fall back to template — no banned words
        result_words = set(result.lower().split())
        for word in _BANNED_WORDS:
            self.assertNotIn(word, result_words)

    @patch("src.rag.summary_generator._call_openai")
    def test_openai_multi_sentence_falls_back(self, mock_openai):
        """If OpenAI returns multiple sentences, fallback must be used."""
        mock_openai.return_value = "First sentence. Second sentence."
        inputs = _medium_risk_inputs()
        result = generate_summary(**inputs)
        # Fallback template always produces single sentence
        period_count = result.count(".")
        self.assertEqual(period_count, 1)

    @patch("src.rag.summary_generator._call_openai")
    def test_openai_numeric_score_falls_back(self, mock_openai):
        """If OpenAI returns numeric scores, fallback must be used."""
        mock_openai.return_value = "Customer has risk level 78 requiring review."
        inputs = _high_risk_inputs()
        result = generate_summary(**inputs)
        self.assertIsNone(re.search(r'\b\d{1,3}\b', result))

    def test_invalid_inputs_raise(self):
        """Invalid inputs must raise ValueError before any generation."""
        with self.assertRaises(ValueError):
            generate_summary(
                intent_label="INVALID",
                conditionality="low",
                obligation_strength="strong",
                contradictions_detected=False,
                risk_score=10,
                fraud_likelihood="low",
                key_risk_factors=[],
            )

    @patch("src.rag.summary_generator._call_openai")
    def test_no_openai_key_falls_back(self, mock_openai):
        """If OPENAI_API_KEY is missing, fallback must be used."""
        mock_openai.side_effect = EnvironmentError("OPENAI_API_KEY not set")
        inputs = _low_risk_inputs()
        result = generate_summary(**inputs)
        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith("."))


# ===================================================================
# 6. DETERMINISM TESTS
# ===================================================================


class TestDeterminism(unittest.TestCase):
    """Same inputs must always produce identical output."""

    @patch("src.rag.summary_generator._call_openai")
    def test_deterministic_with_fallback(self, mock_openai):
        """Template fallback must be deterministic."""
        mock_openai.side_effect = Exception("API unavailable")

        for inputs_fn in [_low_risk_inputs, _medium_risk_inputs, _high_risk_inputs]:
            inputs = inputs_fn()
            results = [generate_summary(**inputs) for _ in range(5)]
            self.assertEqual(len(set(results)), 1,
                             f"Non-deterministic for {inputs_fn.__name__}: {results}")


# ===================================================================
# 7. EMBEDDING SAFETY TESTS
# ===================================================================


class TestEmbeddingSafety(unittest.TestCase):
    """Summaries must be safe for semantic embedding."""

    @patch("src.rag.summary_generator._call_openai")
    def test_no_pii_patterns(self, mock_openai):
        """Output must not contain PII-like patterns."""
        mock_openai.side_effect = Exception("fallback")
        for inputs_fn in [_low_risk_inputs, _medium_risk_inputs, _high_risk_inputs]:
            inputs = inputs_fn()
            summary = generate_summary(**inputs)
            # No credit card patterns
            self.assertIsNone(re.search(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', summary))
            # No phone number patterns
            self.assertIsNone(re.search(r'\b\d{10,}\b', summary))
            # No email patterns
            self.assertIsNone(re.search(r'\S+@\S+\.\S+', summary))

    @patch("src.rag.summary_generator._call_openai")
    def test_no_identifiers(self, mock_openai):
        """Output must not contain identifiers."""
        mock_openai.side_effect = Exception("fallback")
        for inputs_fn in [_low_risk_inputs, _medium_risk_inputs, _high_risk_inputs]:
            inputs = inputs_fn()
            summary = generate_summary(**inputs)
            for keyword in ["customer_id", "call_id", "loan_id", "account"]:
                self.assertNotIn(keyword, summary.lower())


# ===================================================================
# 8. EDGE CASE TESTS
# ===================================================================


class TestEdgeCases(unittest.TestCase):
    """Edge cases for summary generation."""

    @patch("src.rag.summary_generator._call_openai")
    def test_all_risk_factors_at_once(self, mock_openai):
        """All six risk factors should still produce valid summary."""
        mock_openai.side_effect = Exception("fallback")
        inputs = _high_risk_inputs()
        inputs["key_risk_factors"] = list(_VALID_RISK_FACTORS)
        summary = generate_summary(**inputs)
        self.assertTrue(summary.endswith("."))
        self.assertEqual(summary.count("."), 1)

    @patch("src.rag.summary_generator._call_openai")
    def test_unknown_intent(self, mock_openai):
        """Unknown intent should still produce valid summary."""
        mock_openai.side_effect = Exception("fallback")
        summary = generate_summary(
            intent_label="unknown",
            conditionality="medium",
            obligation_strength="none",
            contradictions_detected=False,
            risk_score=50,
            fraud_likelihood="medium",
            key_risk_factors=[],
        )
        self.assertIsInstance(summary, str)
        self.assertTrue(summary.endswith("."))

    @patch("src.rag.summary_generator._call_openai")
    def test_zero_risk_score(self, mock_openai):
        """Zero risk score boundary should work."""
        mock_openai.side_effect = Exception("fallback")
        summary = generate_summary(
            intent_label="repayment_promise",
            conditionality="low",
            obligation_strength="strong",
            contradictions_detected=False,
            risk_score=0,
            fraud_likelihood="low",
            key_risk_factors=[],
        )
        self.assertIsInstance(summary, str)

    @patch("src.rag.summary_generator._call_openai")
    def test_max_risk_score(self, mock_openai):
        """Max risk score boundary should work."""
        mock_openai.side_effect = Exception("fallback")
        summary = generate_summary(
            intent_label="refusal",
            conditionality="high",
            obligation_strength="none",
            contradictions_detected=True,
            risk_score=100,
            fraud_likelihood="high",
            key_risk_factors=["risky_intent", "contradictory_statements"],
        )
        self.assertIsInstance(summary, str)
        self.assertTrue(summary.endswith("."))


if __name__ == "__main__":
    unittest.main()
