"""Unit tests for status_normalize (FLAKY → FAIL, soft-OK → PASS, log reasons)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from status_normalize import (  # noqa: E402
    extract_failure_reason_from_log,
    is_reportable_failure,
    normalize_status,
    resolve_display_failure_reason,
)


def test_normalize_flaky_to_fail():
    assert normalize_status("FLAKY", "MAESTRO_FAILED") == "FAIL"
    assert normalize_status("flaky", "") == "FAIL"


def test_normalize_soft_pass_reasons():
    for reason in (
        "RECORDING_STOP_EOF_FLOW_OK",
        "MAESTRO_FAIL_REATTEMPT_OK",
        "MAESTRO_DEVICE_RETRY_OK",
        "MAESTRO_DRIVER_REINSTALL_OK",
        "SIGNUP_DUPLICATE_RETRY",
    ):
        assert normalize_status("FLAKY", reason) == "PASS"
        assert normalize_status("FAIL", reason) == "PASS"
        assert not is_reportable_failure("FLAKY", reason)


def test_extract_assertion_from_log(tmp_path: Path):
    log = tmp_path / "flow.log"
    log.write_text(
        "Running flow: TC_CA_01\n"
        "Tap on id: camera\n"
        "Assertion is false: id: shutter_button is visible\n"
        "FAILED\n",
        encoding="utf-8",
    )
    reason = extract_failure_reason_from_log(log, fallback="MAESTRO_FAILED")
    assert "Assertion is false" in reason
    assert "shutter_button" in reason


def test_resolve_prefers_log_over_generic(tmp_path: Path):
    log = tmp_path / "flow.log"
    log.write_text("Element not found: text=Print\n", encoding="utf-8")
    reason = resolve_display_failure_reason(
        status="FLAKY",
        reason="MAESTRO_FAILED",
        log_path=log,
        ai_analysis="Flaky run — see log for first failure and retry context.",
    )
    assert "Element not found" in reason
