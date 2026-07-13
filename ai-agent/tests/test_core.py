"""Unit tests for Kodak Smile AI Agent (no device required)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[1]
REPO = AGENT.parent
sys.path.insert(0, str(AGENT))
sys.path.insert(0, str(REPO))

from log_analysis.crash_detector import CrashDetector  # noqa: E402
from models import ModulePlan, ModuleResult, TestStatus  # noqa: E402
from reporting import ReportGenerator, decide_verdict  # noqa: E402
from models import RegressionSummary, DeviceInfo, ReleaseVerdict  # noqa: E402
from retry_manager import RetryManager  # noqa: E402
from test_planner import TestPlanner  # noqa: E402
from vision import NullVisionProvider, get_vision_provider  # noqa: E402


def test_crash_detector_finds_fatal():
    text = "01-01 12:00:00.000  123  456 E AndroidRuntime: FATAL EXCEPTION: main\n"
    findings = CrashDetector().analyze(text)
    assert any(f.kind == "fatal_exception" for f in findings)


def test_retry_manager_recovers():
    plan = ModulePlan(name="X", folder="X", flow_count=1)
    calls = {"n": 0}

    def runner(_p: ModulePlan) -> ModuleResult:
        calls["n"] += 1
        if calls["n"] == 1:
            return ModuleResult(module="X", status=TestStatus.FAIL, exit_code=1)
        return ModuleResult(module="X", status=TestStatus.PASS, exit_code=0)

    out = RetryManager(1).run_with_retry(plan, runner)
    assert out.status == TestStatus.RETRIED_PASS
    assert calls["n"] == 2


def test_planner_discovers_smile_folders():
    plans = TestPlanner(REPO).build_plan()
    names = {p.name for p in plans}
    # At least some known Smile ATP folders should exist in this repo
    assert names.intersection({"Camera", "Editing", "Onboarding", "Settings", "SignUp_Login"})


def test_vision_null_provider():
    v = get_vision_provider("null")
    assert isinstance(v, NullVisionProvider)
    r = v.compare_images(Path("a.png"), Path("b.png"))
    assert r.provider == "null"


def test_reports_write(tmp_path: Path):
    summary = RegressionSummary(
        build="test",
        date_iso="2026-01-01",
        app_package="com.kodaksmile",
        total_tests=1,
        passed=1,
        failed=0,
        skipped=0,
        duration_sec=1.0,
        devices=[DeviceInfo(serial="ABC", model="Pixel", android_version="14")],
        modules=[ModuleResult(module="Camera", status=TestStatus.PASS, passed=1)],
        recommendation=ReleaseVerdict.READY_FOR_RELEASE,
        artifact_root=str(tmp_path / "artifacts"),
    )
    summary.recommendation = decide_verdict(summary)
    paths = ReportGenerator(tmp_path / "reports").write_all(summary)
    assert paths["json"].is_file()
    assert paths["html"].is_file()
    assert paths["markdown"].is_file()
    assert paths["signoff"].is_file()
    assert paths["failed_tests"].is_file()
    assert "READY" in paths["signoff"].read_text(encoding="utf-8")
    assert "No failed tests" in paths["failed_tests"].read_text(encoding="utf-8")


def test_failed_tests_html_only_failures(tmp_path: Path):
    from reporting.failed_tests_report import render_failed_tests_html

    rows = [
        {
            "suite": "atp_editing",
            "test_name": "ED_01 - Filter dedicated with AI",
            "device_id": "ZA222RFQ75",
            "status": "FAIL",
            "failure_reason": "MAESTRO_FAILED",
            "ai_analysis": "—",
            "video_artifact": "ED_01_-_Filter_dedicated_with_AI.mp4",
            "screenshot_artifact": "",
        }
    ]
    html = render_failed_tests_html(
        rows,
        artifact_url="http://jenkins/job/1/artifact/build-summary/failed_tests_artifacts.zip",
    )
    assert "ED_01" in html
    assert "MAESTRO_FAILED" in html
    assert "Failed Test Artifacts" in html
    assert "st-fail" in html
    assert "PASS" not in html.replace("Failed Test Artifacts", "")
    out = tmp_path / "failed_tests.html"
    out.write_text(html, encoding="utf-8")
    assert out.is_file()
