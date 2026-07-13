"""Shared domain models for the Kodak Smile AI Agent."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class FailureCategory(str, Enum):
    AUTOMATION_ISSUE = "automation_issue"
    APPLICATION_BUG = "application_bug"
    DEVICE_ISSUE = "device_issue"
    ENVIRONMENT_ISSUE = "environment_issue"
    KNOWN_ISSUE = "known_issue"
    UNKNOWN_ISSUE = "unknown_issue"


class TestStatus(str, Enum):
    __test__ = False  # prevent pytest collecting this enum as a test class

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    RETRIED_PASS = "RETRIED_PASS"
    RETRIED_FAIL = "RETRIED_FAIL"


class ReleaseVerdict(str, Enum):
    READY_FOR_RELEASE = "READY FOR RELEASE"
    NOT_READY = "NOT READY"


@dataclass
class DeviceInfo:
    serial: str
    state: str = "device"
    model: str = ""
    android_version: str = ""
    healthy: bool = True
    skip_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModulePlan:
    """Discovered ATP module (folder under ATP TestCase Flows)."""

    name: str
    folder: str
    flow_count: int
    flow_paths: list[str] = field(default_factory=list)
    priority: int = 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FailureAnalysis:
    category: FailureCategory = FailureCategory.UNKNOWN_ISSUE
    root_cause: str = ""
    suggestion: str = ""
    confidence: float = 0.0
    is_test_issue: bool = False
    crashes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d


@dataclass
class ModuleResult:
    module: str
    status: TestStatus
    device_serial: str = ""
    device_model: str = ""
    android_version: str = ""
    duration_sec: float = 0.0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    retried: bool = False
    exit_code: int = 0
    log_path: str = ""
    screenshot_paths: list[str] = field(default_factory=list)
    video_paths: list[str] = field(default_factory=list)
    logcat_path: str = ""
    failure: FailureAnalysis | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        if self.failure:
            d["failure"] = self.failure.to_dict()
        return d


@dataclass
class RegressionSummary:
    build: str
    date_iso: str
    app_package: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    duration_sec: float
    devices: list[DeviceInfo]
    modules: list[ModuleResult]
    top_issues: list[str] = field(default_factory=list)
    critical_issues: list[str] = field(default_factory=list)
    crash_summary: list[str] = field(default_factory=list)
    recommendation: ReleaseVerdict = ReleaseVerdict.NOT_READY
    coverage_notes: str = ""
    artifact_root: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "build": self.build,
            "date": self.date_iso,
            "app_package": self.app_package,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_sec": self.duration_sec,
            "devices": [d.to_dict() for d in self.devices],
            "modules": [m.to_dict() for m in self.modules],
            "top_issues": self.top_issues,
            "critical_issues": self.critical_issues,
            "crash_summary": self.crash_summary,
            "recommendation": self.recommendation.value,
            "coverage_notes": self.coverage_notes,
            "artifact_root": self.artifact_root,
        }
