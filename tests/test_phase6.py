"""
tests/test_phase6.py
=====================
Phase 6 Tests — Intent, Obligation Strength, Contradiction Detection

Test categories:
    1. OFFLINE UNIT TESTS — no OpenAI API key required
       - Intent response parser validation
       - Contradiction response parser validation
       - Obligation strength deterministic logic (all branches)
       - Customer utterance filtering
       - Edge cases (empty input, agent-only, etc.)

    2. LIVE INTEGRATION TESTS — requires OPENAI_API_KEY
       - End-to-end intent classification
       - End-to-end contradiction detection
       - Full Phase 6 pipeline with realistic scenarios
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.nlp.intent import (
    IntentLabel,
    Conditionality,
    _filter_customer_utterances as intent_filter,
    _parse_intent_response,
    _build_user_message as intent_build_msg,
    classify_intent,
    _DEFAULT_INTENT,
    _VALID_INTENT_LABELS,
    _VALID_CONDITIONALITY,
)
from src.nlp.contradictions import (
    _filter_customer_utterances as contra_filter,
    _parse_contradiction_response,
    _build_user_message as contra_build_msg,
    detect_contradictions,
)
from src.nlp.obligation import (
    ObligationStrength,
    derive_obligation_strength,
    _count_marker_matches,
    _STRONG_PATTERN,
    _WEAK_PATTERN,
    _CONDITIONAL_PATTERN,
)


# ===================================================================
# Test fixtures — realistic Phase 4 output
# ===================================================================

UTTERANCES_PROMISE_STRONG = [
    {"speaker": "AGENT", "text": "You have an overdue payment of <CREDIT_CARD>.", "start_time": 0.0, "end_time": 3.0},
    {"speaker": "CUSTOMER", "text": "I will pay tomorrow, I promise. You have my word.", "start_time": 3.1, "end_time": 7.0},
    {"speaker": "AGENT", "text": "Can you confirm the amount?", "start_time": 7.1, "end_time": 9.0},
    {"speaker": "CUSTOMER", "text": "Yes, I will definitely transfer the full amount without fail.", "start_time": 9.1, "end_time": 13.0},
]

UTTERANCES_DELAY_CONDITIONAL = [
    {"speaker": "AGENT", "text": "Your payment is overdue.", "start_time": 0.0, "end_time": 2.5},
    {"speaker": "CUSTOMER", "text": "I know, but my salary has not come yet.", "start_time": 2.6, "end_time": 5.5},
    {"speaker": "CUSTOMER", "text": "If my salary arrives by Friday, I should be able to pay next week.", "start_time": 5.6, "end_time": 10.0},
]

UTTERANCES_REFUSAL = [
    {"speaker": "AGENT", "text": "We need you to make a payment.", "start_time": 0.0, "end_time": 2.5},
    {"speaker": "CUSTOMER", "text": "I am not going to pay. This is not my debt.", "start_time": 2.6, "end_time": 6.0},
]

UTTERANCES_CONTRADICTION = [
    {"speaker": "AGENT", "text": "Our records show an outstanding loan.", "start_time": 0.0, "end_time": 3.0},
    {"speaker": "CUSTOMER", "text": "I never took any loan from you.", "start_time": 3.1, "end_time": 5.5},
    {"speaker": "AGENT", "text": "We have documentation of the disbursement.", "start_time": 5.6, "end_time": 8.0},
    {"speaker": "CUSTOMER", "text": "Well, I already paid most of it back.", "start_time": 8.1, "end_time": 11.0},
]

UTTERANCES_NO_CONTRADICTION = [
    {"speaker": "AGENT", "text": "Can you pay today?", "start_time": 0.0, "end_time": 2.0},
    {"speaker": "CUSTOMER", "text": "I need some more time.", "start_time": 2.1, "end_time": 4.0},
    {"speaker": "CUSTOMER", "text": "Maybe next week I can arrange the funds.", "start_time": 4.1, "end_time": 7.0},
]

UTTERANCES_AGENT_ONLY = [
    {"speaker": "AGENT", "text": "You need to pay now.", "start_time": 0.0, "end_time": 3.0},
    {"speaker": "AGENT", "text": "This is urgent.", "start_time": 3.1, "end_time": 5.0},
]

UTTERANCES_EMPTY = []

UTTERANCES_SINGLE_CUSTOMER = [
    {"speaker": "CUSTOMER", "text": "What is this about?", "start_time": 0.0, "end_time": 2.0},
]

UTTERANCES_DEFLECTION = [
    {"speaker": "AGENT", "text": "Can you confirm when you will pay?", "start_time": 0.0, "end_time": 3.0},
    {"speaker": "CUSTOMER", "text": "I am busy right now, call me later.", "start_time": 3.1, "end_time": 6.0},
    {"speaker": "CUSTOMER", "text": "I do not have time for this.", "start_time": 6.1, "end_time": 8.0},
]

UTTERANCES_DISPUTE = [
    {"speaker": "AGENT", "text": "You owe a balance of ten thousand.", "start_time": 0.0, "end_time": 3.0},
    {"speaker": "CUSTOMER", "text": "That amount is wrong. I was charged extra fees that are not valid.", "start_time": 3.1, "end_time": 7.0},
    {"speaker": "CUSTOMER", "text": "I want to dispute these charges. Send me the breakdown.", "start_time": 7.1, "end_time": 11.0},
]


# ===================================================================
# 1. OFFLINE UNIT TESTS
# ===================================================================


class TestIntentEnums(unittest.TestCase):
    """Verify intent label and conditionality enums are correct."""

    def test_intent_labels_match_spec(self):
        expected = {
            "repayment_promise", "repayment_delay", "refusal",
            "deflection", "information_seeking", "dispute", "unknown",
        }
        self.assertEqual(_VALID_INTENT_LABELS, expected)

    def test_conditionality_values(self):
        expected = {"low", "medium", "high"}
        self.assertEqual(_VALID_CONDITIONALITY, expected)

    def test_obligation_strength_values(self):
        expected = {"strong", "weak", "conditional", "none"}
        actual = {m.value for m in ObligationStrength}
        self.assertEqual(actual, expected)


class TestIntentResponseParser(unittest.TestCase):
    """Test _parse_intent_response with valid and invalid inputs."""

    def test_valid_response(self):
        raw = '{"label": "repayment_promise", "confidence": 0.91, "conditionality": "low"}'
        result = _parse_intent_response(raw)
        self.assertEqual(result["label"], "repayment_promise")
        self.assertEqual(result["confidence"], 0.91)
        self.assertEqual(result["conditionality"], "low")

    def test_valid_all_labels(self):
        for label in _VALID_INTENT_LABELS:
            raw = json.dumps({"label": label, "confidence": 0.5, "conditionality": "medium"})
            result = _parse_intent_response(raw)
            self.assertEqual(result["label"], label)

    def test_confidence_clamped_to_bounds(self):
        raw = '{"label": "refusal", "confidence": 0.0, "conditionality": "low"}'
        result = _parse_intent_response(raw)
        self.assertEqual(result["confidence"], 0.0)

        raw = '{"label": "refusal", "confidence": 1.0, "conditionality": "low"}'
        result = _parse_intent_response(raw)
        self.assertEqual(result["confidence"], 1.0)

    def test_confidence_rounded(self):
        raw = '{"label": "dispute", "confidence": 0.8567, "conditionality": "high"}'
        result = _parse_intent_response(raw)
        self.assertEqual(result["confidence"], 0.86)

    def test_invalid_label_rejected(self):
        raw = '{"label": "anger", "confidence": 0.5, "conditionality": "low"}'
        with self.assertRaises(ValueError):
            _parse_intent_response(raw)

    def test_invalid_conditionality_rejected(self):
        raw = '{"label": "refusal", "confidence": 0.5, "conditionality": "extreme"}'
        with self.assertRaises(ValueError):
            _parse_intent_response(raw)

    def test_confidence_out_of_range_rejected(self):
        raw = '{"label": "refusal", "confidence": 1.5, "conditionality": "low"}'
        with self.assertRaises(ValueError):
            _parse_intent_response(raw)

        raw = '{"label": "refusal", "confidence": -0.1, "conditionality": "low"}'
        with self.assertRaises(ValueError):
            _parse_intent_response(raw)

    def test_non_json_rejected(self):
        with self.assertRaises(ValueError):
            _parse_intent_response("This is not JSON")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            _parse_intent_response("[1, 2, 3]")

    def test_missing_keys_rejected(self):
        raw = '{"label": "refusal"}'
        with self.assertRaises(ValueError):
            _parse_intent_response(raw)

    def test_confidence_non_number_rejected(self):
        raw = '{"label": "refusal", "confidence": "high", "conditionality": "low"}'
        with self.assertRaises(ValueError):
            _parse_intent_response(raw)


class TestContradictionResponseParser(unittest.TestCase):
    """Test _parse_contradiction_response with valid and invalid inputs."""

    def test_true(self):
        self.assertTrue(_parse_contradiction_response('{"contradictions_detected": true}'))

    def test_false(self):
        self.assertFalse(_parse_contradiction_response('{"contradictions_detected": false}'))

    def test_non_boolean_rejected(self):
        with self.assertRaises(ValueError):
            _parse_contradiction_response('{"contradictions_detected": "yes"}')

    def test_non_json_rejected(self):
        with self.assertRaises(ValueError):
            _parse_contradiction_response("not json")

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError):
            _parse_contradiction_response("true")

    def test_missing_key_rejected(self):
        with self.assertRaises(ValueError):
            _parse_contradiction_response('{"result": true}')

    def test_null_value_rejected(self):
        with self.assertRaises(ValueError):
            _parse_contradiction_response('{"contradictions_detected": null}')


class TestCustomerUtteranceFiltering(unittest.TestCase):
    """Test that only CUSTOMER utterances are extracted."""

    def test_mixed_speakers(self):
        texts = intent_filter(UTTERANCES_PROMISE_STRONG)
        self.assertEqual(len(texts), 2)
        self.assertTrue(all("AGENT" not in t for t in texts))

    def test_agent_only_returns_empty(self):
        self.assertEqual(intent_filter(UTTERANCES_AGENT_ONLY), [])

    def test_empty_returns_empty(self):
        self.assertEqual(intent_filter(UTTERANCES_EMPTY), [])

    def test_case_insensitive_speaker(self):
        utts = [{"speaker": "customer", "text": "Hello", "start_time": 0, "end_time": 1}]
        self.assertEqual(len(intent_filter(utts)), 1)

    def test_strips_whitespace(self):
        utts = [{"speaker": "CUSTOMER", "text": "  hello  ", "start_time": 0, "end_time": 1}]
        self.assertEqual(intent_filter(utts), ["hello"])

    def test_empty_text_skipped(self):
        utts = [
            {"speaker": "CUSTOMER", "text": "", "start_time": 0, "end_time": 1},
            {"speaker": "CUSTOMER", "text": "real text", "start_time": 1, "end_time": 2},
        ]
        self.assertEqual(intent_filter(utts), ["real text"])

    def test_contradiction_filter_same_behavior(self):
        """Both modules share the same filtering logic."""
        a = intent_filter(UTTERANCES_PROMISE_STRONG)
        b = contra_filter(UTTERANCES_PROMISE_STRONG)
        self.assertEqual(a, b)


class TestUserMessageBuilding(unittest.TestCase):
    """Test user message construction."""

    def test_intent_concatenation(self):
        msg = intent_build_msg(["line1", "line2"])
        self.assertEqual(msg, "line1\nline2")

    def test_contradiction_numbered(self):
        msg = contra_build_msg(["first", "second", "third"])
        self.assertIn("1. first", msg)
        self.assertIn("2. second", msg)
        self.assertIn("3. third", msg)


class TestObligationStrengthDeterministic(unittest.TestCase):
    """Test obligation derivation logic — all branches."""

    # --- Non-commitment intents → none ---

    def test_refusal_returns_none(self):
        intent = {"label": "refusal", "confidence": 0.9, "conditionality": "low"}
        self.assertEqual(derive_obligation_strength(intent, UTTERANCES_REFUSAL), "none")

    def test_deflection_returns_none(self):
        intent = {"label": "deflection", "confidence": 0.8, "conditionality": "low"}
        self.assertEqual(derive_obligation_strength(intent, UTTERANCES_DEFLECTION), "none")

    def test_information_seeking_returns_none(self):
        intent = {"label": "information_seeking", "confidence": 0.7, "conditionality": "low"}
        self.assertEqual(derive_obligation_strength(intent, UTTERANCES_SINGLE_CUSTOMER), "none")

    def test_dispute_returns_none(self):
        intent = {"label": "dispute", "confidence": 0.85, "conditionality": "low"}
        self.assertEqual(derive_obligation_strength(intent, UTTERANCES_DISPUTE), "none")

    def test_unknown_returns_none(self):
        intent = {"label": "unknown", "confidence": 0.3, "conditionality": "low"}
        self.assertEqual(derive_obligation_strength(intent, UTTERANCES_EMPTY), "none")

    # --- repayment_promise + low conditionality + strong markers → strong ---

    def test_promise_low_strong_markers(self):
        intent = {"label": "repayment_promise", "confidence": 0.95, "conditionality": "low"}
        result = derive_obligation_strength(intent, UTTERANCES_PROMISE_STRONG)
        self.assertEqual(result, "strong")

    # --- repayment_promise + low conditionality + no strong markers → weak ---

    def test_promise_low_no_strong_markers(self):
        intent = {"label": "repayment_promise", "confidence": 0.8, "conditionality": "low"}
        utts = [
            {"speaker": "CUSTOMER", "text": "Okay I will do it.", "start_time": 0, "end_time": 2},
        ]
        result = derive_obligation_strength(intent, utts)
        self.assertEqual(result, "weak")

    # --- repayment_promise + medium conditionality + conditional markers → conditional ---

    def test_promise_medium_conditional_markers(self):
        intent = {"label": "repayment_promise", "confidence": 0.7, "conditionality": "medium"}
        utts = [
            {"speaker": "CUSTOMER", "text": "If my salary comes, I will pay.", "start_time": 0, "end_time": 3},
        ]
        result = derive_obligation_strength(intent, utts)
        self.assertEqual(result, "conditional")

    # --- repayment_promise + medium conditionality + strong > weak → weak ---

    def test_promise_medium_strong_dominates(self):
        intent = {"label": "repayment_promise", "confidence": 0.75, "conditionality": "medium"}
        utts = [
            {"speaker": "CUSTOMER", "text": "I will definitely pay. I promise.", "start_time": 0, "end_time": 3},
        ]
        result = derive_obligation_strength(intent, utts)
        self.assertEqual(result, "weak")

    # --- repayment_promise + medium conditionality + no markers → conditional ---

    def test_promise_medium_no_markers(self):
        intent = {"label": "repayment_promise", "confidence": 0.6, "conditionality": "medium"}
        utts = [
            {"speaker": "CUSTOMER", "text": "Okay sure.", "start_time": 0, "end_time": 1},
        ]
        result = derive_obligation_strength(intent, utts)
        self.assertEqual(result, "conditional")

    # --- repayment_promise + high conditionality → conditional ---

    def test_promise_high_always_conditional(self):
        intent = {"label": "repayment_promise", "confidence": 0.5, "conditionality": "high"}
        result = derive_obligation_strength(intent, UTTERANCES_PROMISE_STRONG)
        self.assertEqual(result, "conditional")

    # --- repayment_delay + low → weak ---

    def test_delay_low_returns_weak(self):
        intent = {"label": "repayment_delay", "confidence": 0.8, "conditionality": "low"}
        utts = [
            {"speaker": "CUSTOMER", "text": "I need a few more days.", "start_time": 0, "end_time": 3},
        ]
        result = derive_obligation_strength(intent, utts)
        self.assertEqual(result, "weak")

    # --- repayment_delay + medium → conditional ---

    def test_delay_medium_returns_conditional(self):
        intent = {"label": "repayment_delay", "confidence": 0.7, "conditionality": "medium"}
        result = derive_obligation_strength(intent, UTTERANCES_DELAY_CONDITIONAL)
        self.assertEqual(result, "conditional")

    # --- repayment_delay + high → conditional ---

    def test_delay_high_returns_conditional(self):
        intent = {"label": "repayment_delay", "confidence": 0.6, "conditionality": "high"}
        result = derive_obligation_strength(intent, UTTERANCES_DELAY_CONDITIONAL)
        self.assertEqual(result, "conditional")

    # --- Edge: agent-only utterances ---

    def test_agent_only_no_markers_found(self):
        """Obligation still derived from intent; agent text is ignored."""
        intent = {"label": "repayment_promise", "confidence": 0.9, "conditionality": "low"}
        result = derive_obligation_strength(intent, UTTERANCES_AGENT_ONLY)
        # No customer text → no strong markers → weak
        self.assertEqual(result, "weak")

    # --- Edge: empty utterances ---

    def test_empty_utterances(self):
        intent = {"label": "repayment_promise", "confidence": 0.9, "conditionality": "low"}
        result = derive_obligation_strength(intent, UTTERANCES_EMPTY)
        self.assertEqual(result, "weak")

    # --- Edge: missing intent keys default safely ---

    def test_missing_label_defaults_none(self):
        result = derive_obligation_strength({}, UTTERANCES_EMPTY)
        self.assertEqual(result, "none")


class TestLinguisticMarkerPatterns(unittest.TestCase):
    """Verify that regex patterns match expected markers."""

    def test_strong_markers_detected(self):
        text = "I will pay tomorrow. I promise. Definitely, without fail."
        count = _count_marker_matches(text, _STRONG_PATTERN)
        self.assertGreaterEqual(count, 3)

    def test_weak_markers_detected(self):
        text = "Maybe I can pay. I am not sure. I will try."
        count = _count_marker_matches(text, _WEAK_PATTERN)
        self.assertGreaterEqual(count, 3)

    def test_conditional_markers_detected(self):
        text = "If my salary arrives, I will pay. Once the funds are cleared."
        count = _count_marker_matches(text, _CONDITIONAL_PATTERN)
        self.assertGreaterEqual(count, 1)

    def test_no_markers_in_neutral_text(self):
        text = "What is the account balance?"
        self.assertEqual(_count_marker_matches(text, _STRONG_PATTERN), 0)
        self.assertEqual(_count_marker_matches(text, _WEAK_PATTERN), 0)


class TestClassifyIntentWithMock(unittest.TestCase):
    """Test classify_intent with mocked OpenAI API."""

    def _mock_openai_response(self, content: str):
        """Create a mock OpenAI response."""
        mock_message = MagicMock()
        mock_message.content = content
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    @patch("src.nlp.intent.OpenAI")
    def test_normal_classification(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_openai_response(
            '{"label": "repayment_promise", "confidence": 0.92, "conditionality": "low"}'
        )

        result = classify_intent(UTTERANCES_PROMISE_STRONG)

        self.assertEqual(result["label"], "repayment_promise")
        self.assertEqual(result["confidence"], 0.92)
        self.assertEqual(result["conditionality"], "low")

    @patch("src.nlp.intent.OpenAI")
    def test_agent_only_returns_default(self, mock_openai_cls):
        result = classify_intent(UTTERANCES_AGENT_ONLY)
        self.assertEqual(result, _DEFAULT_INTENT)
        # OpenAI should NOT have been called
        mock_openai_cls.return_value.chat.completions.create.assert_not_called()

    @patch("src.nlp.intent.OpenAI")
    def test_empty_returns_default(self, mock_openai_cls):
        result = classify_intent(UTTERANCES_EMPTY)
        self.assertEqual(result, _DEFAULT_INTENT)

    @patch("src.nlp.intent.OpenAI")
    def test_invalid_response_raises(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_openai_response(
            '{"label": "invalid_label", "confidence": 0.5, "conditionality": "low"}'
        )

        with self.assertRaises(ValueError):
            classify_intent(UTTERANCES_PROMISE_STRONG)

    @patch("src.nlp.intent.OpenAI")
    def test_only_customer_text_sent(self, mock_openai_cls):
        """Verify that AGENT text is never included in the OpenAI call."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_openai_response(
            '{"label": "refusal", "confidence": 0.8, "conditionality": "low"}'
        )

        classify_intent(UTTERANCES_REFUSAL)

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        self.assertNotIn("We need you to make a payment", user_msg)
        self.assertIn("I am not going to pay", user_msg)


class TestDetectContradictionsWithMock(unittest.TestCase):
    """Test detect_contradictions with mocked OpenAI API."""

    def _mock_openai_response(self, content: str):
        mock_message = MagicMock()
        mock_message.content = content
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    @patch("src.nlp.contradictions.OpenAI")
    def test_contradiction_detected(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_openai_response(
            '{"contradictions_detected": true}'
        )

        result = detect_contradictions(UTTERANCES_CONTRADICTION)
        self.assertTrue(result)

    @patch("src.nlp.contradictions.OpenAI")
    def test_no_contradiction(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_openai_response(
            '{"contradictions_detected": false}'
        )

        result = detect_contradictions(UTTERANCES_NO_CONTRADICTION)
        self.assertFalse(result)

    @patch("src.nlp.contradictions.OpenAI")
    def test_agent_only_returns_false(self, mock_openai_cls):
        result = detect_contradictions(UTTERANCES_AGENT_ONLY)
        self.assertFalse(result)
        mock_openai_cls.return_value.chat.completions.create.assert_not_called()

    @patch("src.nlp.contradictions.OpenAI")
    def test_empty_returns_false(self, mock_openai_cls):
        result = detect_contradictions(UTTERANCES_EMPTY)
        self.assertFalse(result)

    @patch("src.nlp.contradictions.OpenAI")
    def test_single_utterance_returns_false(self, mock_openai_cls):
        result = detect_contradictions(UTTERANCES_SINGLE_CUSTOMER)
        self.assertFalse(result)
        mock_openai_cls.return_value.chat.completions.create.assert_not_called()

    @patch("src.nlp.contradictions.OpenAI")
    def test_only_customer_text_sent(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_openai_response(
            '{"contradictions_detected": false}'
        )

        detect_contradictions(UTTERANCES_CONTRADICTION)

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        # AGENT text must not be present
        self.assertNotIn("Our records show", user_msg)
        self.assertNotIn("We have documentation", user_msg)
        # CUSTOMER text must be present
        self.assertIn("I never took any loan", user_msg)
        self.assertIn("I already paid most of it", user_msg)


class TestPhase6OutputStructure(unittest.TestCase):
    """Verify combined Phase 6 output matches the required schema."""

    @patch("src.nlp.intent.OpenAI")
    @patch("src.nlp.contradictions.OpenAI")
    def test_full_output_structure(self, mock_contra_cls, mock_intent_cls):
        # Mock intent
        mock_intent_client = MagicMock()
        mock_intent_cls.return_value = mock_intent_client
        intent_resp = MagicMock()
        intent_resp.message.content = '{"label": "repayment_delay", "confidence": 0.85, "conditionality": "medium"}'
        mock_intent_client.chat.completions.create.return_value = MagicMock(choices=[intent_resp])

        # Mock contradictions
        mock_contra_client = MagicMock()
        mock_contra_cls.return_value = mock_contra_client
        contra_resp = MagicMock()
        contra_resp.message.content = '{"contradictions_detected": false}'
        mock_contra_client.chat.completions.create.return_value = MagicMock(choices=[contra_resp])

        # Run Phase 6 pipeline
        intent_result = classify_intent(UTTERANCES_DELAY_CONDITIONAL)
        contradictions = detect_contradictions(UTTERANCES_DELAY_CONDITIONAL)
        obligation = derive_obligation_strength(intent_result, UTTERANCES_DELAY_CONDITIONAL)

        # Assemble output
        phase6_output = {
            "intent": intent_result,
            "obligation_strength": obligation,
            "contradictions_detected": contradictions,
        }

        # Validate structure
        self.assertIn("intent", phase6_output)
        self.assertIn("obligation_strength", phase6_output)
        self.assertIn("contradictions_detected", phase6_output)

        # Validate intent sub-structure
        self.assertIn("label", phase6_output["intent"])
        self.assertIn("confidence", phase6_output["intent"])
        self.assertIn("conditionality", phase6_output["intent"])

        # Validate enum values
        self.assertIn(phase6_output["intent"]["label"], _VALID_INTENT_LABELS)
        self.assertIn(phase6_output["intent"]["conditionality"], _VALID_CONDITIONALITY)
        self.assertIn(phase6_output["obligation_strength"], {"strong", "weak", "conditional", "none"})
        self.assertIsInstance(phase6_output["contradictions_detected"], bool)
        self.assertIsInstance(phase6_output["intent"]["confidence"], float)
        self.assertGreaterEqual(phase6_output["intent"]["confidence"], 0.0)
        self.assertLessEqual(phase6_output["intent"]["confidence"], 1.0)

        # Must NOT contain downstream fields
        self.assertNotIn("risk_score", phase6_output)
        self.assertNotIn("fraud_likelihood", phase6_output)
        self.assertNotIn("sentiment", phase6_output)
        self.assertNotIn("summary", phase6_output)


# ===================================================================
# 2. LIVE INTEGRATION TESTS (requires OPENAI_API_KEY)
# ===================================================================


@unittest.skipUnless(
    os.environ.get("OPENAI_API_KEY"),
    "OPENAI_API_KEY not set — skipping live integration tests",
)
class TestLiveIntentClassification(unittest.TestCase):
    """End-to-end intent classification with real OpenAI API."""

    def test_promise_intent(self):
        result = classify_intent(UTTERANCES_PROMISE_STRONG)
        self.assertIn(result["label"], _VALID_INTENT_LABELS)
        self.assertEqual(result["label"], "repayment_promise")
        self.assertGreaterEqual(result["confidence"], 0.5)
        self.assertIn(result["conditionality"], _VALID_CONDITIONALITY)

    def test_delay_intent(self):
        result = classify_intent(UTTERANCES_DELAY_CONDITIONAL)
        self.assertIn(result["label"], _VALID_INTENT_LABELS)
        self.assertIn(result["label"], {"repayment_delay", "repayment_promise"})
        self.assertIn(result["conditionality"], _VALID_CONDITIONALITY)

    def test_refusal_intent(self):
        result = classify_intent(UTTERANCES_REFUSAL)
        self.assertIn(result["label"], {"refusal", "dispute"})
        self.assertGreaterEqual(result["confidence"], 0.5)

    def test_deflection_intent(self):
        result = classify_intent(UTTERANCES_DEFLECTION)
        self.assertIn(result["label"], _VALID_INTENT_LABELS)

    def test_dispute_intent(self):
        result = classify_intent(UTTERANCES_DISPUTE)
        self.assertIn(result["label"], {"dispute", "information_seeking"})


@unittest.skipUnless(
    os.environ.get("OPENAI_API_KEY"),
    "OPENAI_API_KEY not set — skipping live integration tests",
)
class TestLiveContradictionDetection(unittest.TestCase):
    """End-to-end contradiction detection with real OpenAI API."""

    def test_contradictory_call(self):
        result = detect_contradictions(UTTERANCES_CONTRADICTION)
        self.assertIsInstance(result, bool)
        self.assertTrue(result)  # Clear contradiction: denies loan then says paid part

    def test_non_contradictory_call(self):
        result = detect_contradictions(UTTERANCES_NO_CONTRADICTION)
        self.assertIsInstance(result, bool)
        self.assertFalse(result)


@unittest.skipUnless(
    os.environ.get("OPENAI_API_KEY"),
    "OPENAI_API_KEY not set — skipping live integration tests",
)
class TestLiveFullPhase6Pipeline(unittest.TestCase):
    """End-to-end Phase 6 pipeline: intent → obligation → contradictions."""

    def _run_phase6(self, utterances):
        intent = classify_intent(utterances)
        contradictions = detect_contradictions(utterances)
        obligation = derive_obligation_strength(intent, utterances)
        return {
            "intent": intent,
            "obligation_strength": obligation,
            "contradictions_detected": contradictions,
        }

    def test_strong_promise_scenario(self):
        output = self._run_phase6(UTTERANCES_PROMISE_STRONG)
        self.assertEqual(output["intent"]["label"], "repayment_promise")
        self.assertIn(output["obligation_strength"], {"strong", "weak"})
        self.assertIsInstance(output["contradictions_detected"], bool)
        print(f"\n[LIVE] Strong promise: {json.dumps(output, indent=2)}")

    def test_conditional_delay_scenario(self):
        output = self._run_phase6(UTTERANCES_DELAY_CONDITIONAL)
        self.assertIn(output["intent"]["label"], {"repayment_delay", "repayment_promise"})
        self.assertIn(output["obligation_strength"], {"weak", "conditional"})
        print(f"\n[LIVE] Conditional delay: {json.dumps(output, indent=2)}")

    def test_refusal_scenario(self):
        output = self._run_phase6(UTTERANCES_REFUSAL)
        self.assertEqual(output["obligation_strength"], "none")
        print(f"\n[LIVE] Refusal: {json.dumps(output, indent=2)}")

    def test_contradiction_scenario(self):
        output = self._run_phase6(UTTERANCES_CONTRADICTION)
        self.assertTrue(output["contradictions_detected"])
        print(f"\n[LIVE] Contradiction: {json.dumps(output, indent=2)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
