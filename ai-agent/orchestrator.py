"""Full regression orchestrator — wires all agent modules (SOLID composition root)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ai_failure_analyzer import AIFailureAnalyzer
from apk_installer import ApkInstaller
from config_loader import AgentConfig
from device_manager import DeviceManager
from log_analysis.crash_detector import CrashDetector
from logcat_collector import LogcatCollector
from maestro_runner import MaestroRunner
from models import (
    DeviceInfo,
    ModulePlan,
    ModuleResult,
    RegressionSummary,
    TestStatus,
)
from reporting import ReportGenerator, decide_verdict, utc_now_iso
from retry_manager import RetryManager
from screenshot_manager import ScreenshotManager
from test_planner import TestPlanner
from agent_utils.logging_utils import append_jsonl
from video_recorder import VideoRecorder
from vision import VisionProvider, get_vision_provider

logger = logging.getLogger("ai-agent.orchestrator")


class AgentOrchestrator:
    """
    Composition root for the Kodak Smile AI Agent.

    Executes existing ATP modules via ``jenkins_atp_stage`` — never edits Maestro YAML.
    """

    def __init__(
        self,
        config: AgentConfig,
        *,
        device_manager: DeviceManager | None = None,
        planner: TestPlanner | None = None,
        runner: MaestroRunner | None = None,
        vision: VisionProvider | None = None,
    ) -> None:
        self.cfg = config
        self.devices = device_manager or DeviceManager(config.repo_root)
        self.planner = planner or TestPlanner(config.repo_root)
        self.runner = runner or MaestroRunner(
            config.repo_root,
            app_package=config.app_package,
            maestro_cmd=config.maestro_cmd,
            clear_state=config.clear_state,
        )
        self.apk = ApkInstaller(config.app_package)
        self.retry = RetryManager(config.max_retries)
        self.screens = ScreenshotManager(config.artifact_root)  # type: ignore[arg-type]
        self.videos = VideoRecorder(config.artifact_root)  # type: ignore[arg-type]
        self.logcat = LogcatCollector(config.artifact_root)  # type: ignore[arg-type]
        self.crashes = CrashDetector()
        self.failures = AIFailureAnalyzer(config.repo_root)
        self.reports = ReportGenerator(config.report_root)  # type: ignore[arg-type]
        self.vision = vision or get_vision_provider()
        self.decision_log = config.repo_root / "ai-agent" / "logs" / "decisions" / "decisions.jsonl"

    def run_full_regression(self) -> tuple[int, RegressionSummary]:
        cfg = self.cfg
        cfg.artifact_root.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
        cfg.report_root.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]

        healthy = self.devices.list_healthy_devices()
        if not healthy:
            summary = self._empty_summary([], "No healthy Android devices connected")
            self.reports.write_all(summary)
            return 1, summary

        # APK ensure (optional path)
        for d in healthy:
            ok = self.apk.ensure(d.serial, Path(cfg.apk_path) if cfg.apk_path else None)
            if not ok and cfg.apk_path:
                d.healthy = False
                d.skip_reason = "apk_install_failed"
        healthy = [d for d in healthy if d.healthy]
        if not healthy:
            summary = self._empty_summary(self.devices.list_all(), "APK not installed on any device")
            self.reports.write_all(summary)
            return 1, summary

        plans = self.planner.build_plan(
            include=cfg.modules_include,
            exclude=cfg.modules_exclude,
        )
        if not plans:
            summary = self._empty_summary(healthy, "No ATP modules discovered")
            self.reports.write_all(summary)
            return 1, summary

        if cfg.mode == "observe":
            logger.info("observe mode — planning only, no Maestro execution")
            summary = self._observe_summary(healthy, plans)
            self.reports.write_all(summary)
            return 0, summary

        primary = healthy[0]
        results: list[ModuleResult] = []
        crash_all: list[str] = []

        # Modules run sequentially (stable for shared printers / app state).
        # Multi-device support: assign primary; ATP orchestrator may still fan-out internally.
        for plan in plans:
            result = self._run_one_module(plan, primary)
            results.append(result)
            if result.failure and result.failure.crashes:
                crash_all.extend(result.failure.crashes)
            append_jsonl(
                self.decision_log,
                {
                    "module": plan.name,
                    "status": result.status.value,
                    "exit_code": result.exit_code,
                    "failure": result.failure.to_dict() if result.failure else None,
                },
            )

        summary = self._build_summary(healthy, plans, results, crash_all)
        summary.recommendation = decide_verdict(summary)
        self.reports.write_all(summary)

        # Optional post-run intelligent_platform (does not replace its own Excel output).
        if cfg.run_ai_analysis:
            self._maybe_run_platform_ai()

        rc = 0 if summary.failed == 0 else 2
        return rc, summary

    def _run_one_module(self, plan: ModulePlan, device: DeviceInfo) -> ModuleResult:
        cfg = self.cfg
        logger.info("=== module start %s on %s ===", plan.name, device.serial)

        if cfg.capture_logcat:
            self.logcat.clear(device.serial)
        if cfg.capture_screenshots:
            self.screens.capture(device.serial, "before", module=plan.name)
        if cfg.capture_videos:
            self.videos.start(device.serial, plan.name)

        def _invoke(p: ModulePlan) -> ModuleResult:
            return self.runner.run_module(p, device_hint=device.serial)

        if cfg.mode == "autonomous" or cfg.mode == "assist":
            result = self.retry.run_with_retry(plan, _invoke)
        else:
            result = _invoke(plan)

        video_path = self.videos.stop(save=cfg.capture_videos) if cfg.capture_videos else None
        shot = None
        if cfg.capture_screenshots:
            label = "success" if result.status in (TestStatus.PASS, TestStatus.RETRIED_PASS) else "failure"
            shot = self.screens.capture(device.serial, label, module=plan.name)

        logcat_path = ""
        logcat_text = ""
        if cfg.capture_logcat:
            lp = self.logcat.dump(device.serial, plan.name)
            logcat_path = str(lp)
            logcat_text = lp.read_text(encoding="utf-8", errors="replace")

        result.device_serial = device.serial
        result.device_model = device.model
        result.android_version = device.android_version
        result.logcat_path = logcat_path
        if shot:
            result.screenshot_paths.append(str(shot))
        if video_path:
            result.video_paths.append(str(video_path))

        if result.status not in (TestStatus.PASS, TestStatus.RETRIED_PASS):
            result.failure = self.failures.analyze(
                module=plan.name,
                maestro_log=result.notes,
                logcat_text=logcat_text,
                screenshot_hint=str(shot or ""),
            )
            # Vision hook (no-op unless provider configured)
            if shot and self.vision:
                try:
                    self.vision.verify_expected_ui(Path(shot), f"module {plan.name} recovered UI")
                except Exception:  # noqa: BLE001
                    pass

        logger.info(
            "=== module end %s status=%s duration=%ss ===",
            plan.name,
            result.status.value,
            result.duration_sec,
        )
        return result

    def _build_summary(
        self,
        devices: list[DeviceInfo],
        plans: list[ModulePlan],
        results: list[ModuleResult],
        crash_all: list[str],
    ) -> RegressionSummary:
        passed = sum(1 for r in results if r.status in (TestStatus.PASS, TestStatus.RETRIED_PASS))
        failed = sum(1 for r in results if r.status in (TestStatus.FAIL, TestStatus.RETRIED_FAIL))
        skipped = sum(1 for r in results if r.status == TestStatus.SKIP)
        total_flows = sum(p.flow_count for p in plans)
        duration = sum(r.duration_sec for r in results)
        top_issues = []
        critical = []
        for r in results:
            if r.failure:
                top_issues.append(f"{r.module}: {r.failure.root_cause}")
                if r.failure.category.value in ("application_bug", "device_issue") and r.failure.confidence >= 0.7:
                    critical.append(f"{r.module}: {r.failure.root_cause}")
        coverage = (
            f"Discovered {len(plans)} ATP modules / ~{total_flows} flows under ATP TestCase Flows. "
            f"Features mapped: Login/Signup, Onboarding, Camera, Editing (frames/stickers/filters/"
            f"brightness/contrast/saturation/temperature/crop/rotate), Print, Settings, Printer Connection."
        )
        return RegressionSummary(
            build=self.cfg.build_id,
            date_iso=utc_now_iso(),
            app_package=self.cfg.app_package,
            total_tests=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_sec=round(duration, 2),
            devices=devices,
            modules=results,
            top_issues=top_issues[:20],
            critical_issues=critical[:20],
            crash_summary=sorted(set(crash_all))[:20],
            coverage_notes=coverage,
            artifact_root=str(self.cfg.artifact_root),
        )

    def _empty_summary(self, devices: list[DeviceInfo], reason: str) -> RegressionSummary:
        s = RegressionSummary(
            build=self.cfg.build_id,
            date_iso=utc_now_iso(),
            app_package=self.cfg.app_package,
            total_tests=0,
            passed=0,
            failed=1,
            skipped=0,
            duration_sec=0,
            devices=devices,
            modules=[],
            top_issues=[reason],
            critical_issues=[reason],
            coverage_notes=reason,
            artifact_root=str(self.cfg.artifact_root),
        )
        s.recommendation = decide_verdict(s)
        return s

    def _observe_summary(self, devices: list[DeviceInfo], plans: list[ModulePlan]) -> RegressionSummary:
        mods = [
            ModuleResult(
                module=p.name,
                status=TestStatus.SKIP,
                skipped=p.flow_count,
                notes="observe mode — not executed",
            )
            for p in plans
        ]
        s = RegressionSummary(
            build=self.cfg.build_id,
            date_iso=utc_now_iso(),
            app_package=self.cfg.app_package,
            total_tests=len(mods),
            passed=0,
            failed=0,
            skipped=len(mods),
            duration_sec=0,
            devices=devices,
            modules=mods,
            coverage_notes=f"Observe plan: {[p.name for p in plans]}",
            artifact_root=str(self.cfg.artifact_root),
        )
        # Observe is informational — mark ready only if plan non-empty
        from models import ReleaseVerdict

        s.recommendation = ReleaseVerdict.READY_FOR_RELEASE if plans else ReleaseVerdict.NOT_READY
        return s

    def _maybe_run_platform_ai(self) -> None:
        try:
            import subprocess
            import sys

            logger.info("invoking intelligent_platform post-analysis (optional)")
            subprocess.run(
                [sys.executable, "-m", "intelligent_platform"],
                cwd=str(self.cfg.repo_root),
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("intelligent_platform skipped: %s", exc)
