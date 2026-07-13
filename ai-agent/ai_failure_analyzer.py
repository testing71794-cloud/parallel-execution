"""AI Failure Analyzer — classifies failures using rules + optional intelligent_platform."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from models import FailureAnalysis, FailureCategory
from log_analysis.crash_detector import CrashDetector

logger = logging.getLogger("ai-agent.failure")


class AIFailureAnalyzer:
    """
    Classifies failures into automation / app / device / environment / known / unknown.

    Soft-depends on ``intelligent_platform`` when available; always has rule fallback.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.crash = CrashDetector()

    def analyze(
        self,
        *,
        module: str,
        maestro_log: str = "",
        logcat_text: str = "",
        screenshot_hint: str = "",
    ) -> FailureAnalysis:
        crashes = self.crash.analyze(logcat_text or maestro_log)
        crash_kinds = self.crash.summarize(crashes)

        # Rule-based classification first (deterministic, offline).
        analysis = self._rules(module, maestro_log, logcat_text, crash_kinds)
        analysis.crashes = crash_kinds

        if analysis.category != FailureCategory.UNKNOWN_ISSUE and analysis.confidence >= 0.7:
            return analysis

        # Optional LLM enrichment via existing intelligent_platform.
        enriched = self._llm_enrich(module, maestro_log, logcat_text, screenshot_hint, analysis)
        return enriched or analysis

    def _rules(
        self,
        module: str,
        maestro_log: str,
        logcat_text: str,
        crash_kinds: list[str],
    ) -> FailureAnalysis:
        blob = f"{maestro_log}\n{logcat_text}".lower()

        if any(k.startswith("fatal") or k.startswith("native") or k.startswith("anr") or k.startswith("oom") for k in crash_kinds):
            return FailureAnalysis(
                category=FailureCategory.APPLICATION_BUG,
                root_cause=f"Crash/ANR/OOM signals in logcat for module {module}: {', '.join(crash_kinds)}",
                suggestion="Capture bug report, reproduce manually, check recent app build.",
                confidence=0.85,
                is_test_issue=False,
            )
        if "connection refused" in blob or "driver" in blob and "7001" in blob:
            return FailureAnalysis(
                category=FailureCategory.ENVIRONMENT_ISSUE,
                root_cause="Maestro Android driver / port conflict on host",
                suggestion="Ensure host runtime mutex or per-device driver ports; kill stale java/maestro.",
                confidence=0.8,
                is_test_issue=True,
            )
        if "element not found" in blob or "assertion is false" in blob or "assert that" in blob and "failed" in blob:
            return FailureAnalysis(
                category=FailureCategory.AUTOMATION_ISSUE,
                root_cause="UI assertion/selector mismatch in Maestro flow",
                suggestion="Inspect hierarchy dump and update selector or add extendedWaitUntil.",
                confidence=0.75,
                is_test_issue=True,
            )
        if "device offline" in blob or "not found" in blob and "device" in blob:
            return FailureAnalysis(
                category=FailureCategory.DEVICE_ISSUE,
                root_cause="ADB device became unavailable during run",
                suggestion="Re-seat USB/Wi-Fi debug; re-run module on healthy device.",
                confidence=0.8,
                is_test_issue=False,
            )
        if "bluetooth" in ",".join(crash_kinds) or "printer" in ",".join(crash_kinds):
            return FailureAnalysis(
                category=FailureCategory.ENVIRONMENT_ISSUE,
                root_cause="Bluetooth/printer connectivity errors in logcat",
                suggestion="Verify printer power/pairing and nearby-device permissions.",
                confidence=0.7,
                is_test_issue=False,
            )
        if re.search(r"known.?issue|wontfix|won't fix", blob):
            return FailureAnalysis(
                category=FailureCategory.KNOWN_ISSUE,
                root_cause="Marked or matched known issue pattern",
                suggestion="Track in known-issues register; do not block release unless severity raised.",
                confidence=0.6,
                is_test_issue=False,
            )
        return FailureAnalysis(
            category=FailureCategory.UNKNOWN_ISSUE,
            root_cause=f"Unclassified failure in module {module}",
            suggestion="Review Maestro debug output, screenshots, and logcat manually.",
            confidence=0.3,
            is_test_issue=False,
        )

    def _llm_enrich(
        self,
        module: str,
        maestro_log: str,
        logcat_text: str,
        screenshot_hint: str,
        base: FailureAnalysis,
    ) -> FailureAnalysis | None:
        try:
            if str(self.repo_root) not in sys.path:
                sys.path.insert(0, str(self.repo_root))
            from intelligent_platform.ai_failure_analyzer import analyze_failure

            payload = {
                "module": module,
                "maestro_log_tail": (maestro_log or "")[-8000:],
                "logcat_tail": (logcat_text or "")[-8000:],
                "screenshot": screenshot_hint,
                "rule_category": base.category.value,
            }
            result = analyze_failure(payload)
            if not isinstance(result, dict):
                return None
            cat_map = {
                "locator": FailureCategory.AUTOMATION_ISSUE,
                "timing": FailureCategory.AUTOMATION_ISSUE,
                "assertion": FailureCategory.AUTOMATION_ISSUE,
                "api": FailureCategory.APPLICATION_BUG,
                "crash": FailureCategory.APPLICATION_BUG,
            }
            category = cat_map.get(str(result.get("category", "")).lower(), base.category)
            return FailureAnalysis(
                category=category,
                root_cause=str(result.get("root_cause") or base.root_cause),
                suggestion=str(result.get("suggestion") or base.suggestion),
                confidence=float(result.get("confidence") or base.confidence),
                is_test_issue=bool(result.get("is_test_issue", base.is_test_issue)),
                crashes=base.crashes,
                raw=result,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("LLM enrich skipped: %s", exc)
            return None
