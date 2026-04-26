"""OpenRouter failure analysis: prompt contract, JSON safety, mandatory login example (mocked)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from intelligent_platform.ai_failure_analyzer import (
    MODEL_FALLBACK,
    MODEL_PRIMARY,
    _build_user_prompt,
    analyze_failure,
)
from intelligent_platform.json_safety import safe_json_parse
from intelligent_platform.openrouter_client import MODEL_FALLBACK as OFB
from intelligent_platform.openrouter_client import MODEL_PRIMARY as OPR


class TestOpenRouterAnalysis(unittest.TestCase):
    def test_model_constants_explicit(self) -> None:
        self.assertEqual(OPR, "mistralai/mistral-7b-instruct")
        self.assertEqual(OFB, "meta-llama/llama-3.3-70b-instruct:free")
        self.assertEqual(MODEL_PRIMARY, OPR)
        self.assertEqual(MODEL_FALLBACK, OFB)

    def test_prompt_contains_strict_sections(self) -> None:
        p = _build_user_prompt({"error_message": "x", "test_name": "t"})
        self.assertIn("Think step-by-step internally", p)
        self.assertIn("Output ONLY valid JSON", p)
        self.assertIn("Failure Data:", p)
        self.assertIn('"category": "locator | timing | api | crash | assertion"', p)

    def test_safe_json_parse_direct(self) -> None:
        raw = '{"category":"locator","root_cause":"r","suggestion":"s","is_test_issue":true,"confidence":0.85}'
        d = safe_json_parse(raw)
        self.assertEqual(d["category"], "locator")
        self.assertEqual(d["confidence"], 0.85)

    def test_safe_json_parse_fenced(self) -> None:
        raw = """Here is JSON:
```json
{"category":"timing","root_cause":"x","suggestion":"y","is_test_issue":false,"confidence":0.5}
```"""
        d = safe_json_parse(raw)
        self.assertEqual(d["category"], "timing")

    def test_mandatory_login_case_via_mocked_primary(self) -> None:
        """Input: login_button not found → structured locator + test issue (mocked API)."""
        expected = {
            "category": "locator",
            "root_cause": "Login button element not found, possibly due to incorrect locator or UI change",
            "suggestion": "Verify locator strategy and update selector for login button",
            "is_test_issue": True,
            "confidence": 0.85,
        }
        failure = {
            "test_name": "LoginTest",
            "error_message": "Login test failed: element with id login_button not found",
            "step_failed": "",
        }

        def fake_call(messages, model, **kwargs):
            self.assertEqual(model, MODEL_PRIMARY)
            return json.dumps(expected)

        with patch("intelligent_platform.ai_failure_analyzer.call_openrouter", side_effect=fake_call):
            with patch(
                "intelligent_platform.ai_failure_analyzer.config.ai_health_marks_unavailable",
                return_value=False,
            ):
                with patch("intelligent_platform.ai_failure_analyzer.config.openrouter_configured", return_value=True):
                    with patch("intelligent_platform.ai_failure_analyzer.config.openrouter_api_key", return_value="sk-test"):
                        out = analyze_failure(failure)

        self.assertEqual(out["category"], "locator")
        self.assertIn("Login button", out["root_cause"])
        self.assertIn("locator", out["suggestion"].lower())
        self.assertTrue(out["is_test_issue"])
        self.assertGreaterEqual(out["confidence"], 0.8)

    def test_primary_bad_then_fallback_ok(self) -> None:
        good = json.dumps(
            {
                "category": "assertion",
                "root_cause": "Text mismatch on label",
                "suggestion": "Update expected string",
                "is_test_issue": True,
                "confidence": 0.7,
            }
        )
        calls: list[str] = []

        def side_effect(messages, model, **kwargs):
            calls.append(model)
            if model == MODEL_PRIMARY:
                return "not json at all"
            return good

        f = {"error_message": "assertion failed on label X", "test_name": "t1"}
        with patch("intelligent_platform.ai_failure_analyzer.call_openrouter", side_effect=side_effect):
            with patch(
                "intelligent_platform.ai_failure_analyzer.config.ai_health_marks_unavailable",
                return_value=False,
            ):
                with patch("intelligent_platform.ai_failure_analyzer.config.openrouter_configured", return_value=True):
                    with patch("intelligent_platform.ai_failure_analyzer.config.openrouter_api_key", return_value="k"):
                        out = analyze_failure(f)
        self.assertIn(MODEL_PRIMARY, calls)
        self.assertIn(MODEL_FALLBACK, calls)
        self.assertEqual(out["category"], "assertion")
        self.assertTrue(out["is_test_issue"])


if __name__ == "__main__":
    unittest.main()
