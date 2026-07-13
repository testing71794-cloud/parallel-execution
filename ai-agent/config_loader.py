"""Agent configuration (env + YAML). Never mutates existing ATP/Jenkins config."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_APP_PACKAGE = "com.kodaksmile"
DEFAULT_MAESTRO_CMD = "maestro.bat"

# Logical feature names → ATP folders (Smile layout). Unknown folders still auto-discover.
FEATURE_ALIASES: dict[str, str] = {
    "login": "SignUp_Login",
    "signup": "SignUp_Login",
    "onboarding": "Onboarding",
    "camera": "Camera",
    "gallery": "Camera",  # Smile has no Gallery folder; map to closest ATP suite
    "editing": "Editing",
    "frames": "Editing",
    "stickers": "Editing",
    "filters": "Editing",
    "brightness": "Editing",
    "contrast": "Editing",
    "saturation": "Editing",
    "temperature": "Editing",
    "crop": "Editing",
    "rotate": "Editing",
    "print": "Printing",
    "printing": "Printing",
    "settings": "Settings",
    "printer connection": "Onboarding",
    "connection": "Onboarding",
    "collage": "Collage",
    "precut": "Precut",
}


@dataclass
class AgentConfig:
    repo_root: Path
    enabled: bool = True
    mode: str = "assist"  # observe | assist | autonomous
    app_package: str = DEFAULT_APP_PACKAGE
    maestro_cmd: str = DEFAULT_MAESTRO_CMD
    clear_state: str = "true"
    apk_path: str | None = None
    max_retries: int = 1
    parallel_devices: bool = True
    run_ai_analysis: bool = True
    capture_logcat: bool = True
    capture_screenshots: bool = True
    capture_videos: bool = True  # relies on existing ATP auto-record when available
    artifact_root: Path | None = None
    report_root: Path | None = None
    modules_include: list[str] = field(default_factory=list)
    modules_exclude: list[str] = field(default_factory=list)
    build_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()
        if self.artifact_root is None:
            self.artifact_root = self.repo_root / "artifacts"
        else:
            self.artifact_root = Path(self.artifact_root).resolve()
        if self.report_root is None:
            self.report_root = self.repo_root / "ai-agent" / "reports"
        else:
            self.report_root = Path(self.report_root).resolve()
        if not self.build_id:
            self.build_id = (
                os.environ.get("BUILD_ID")
                or os.environ.get("BUILD_NUMBER")
                or "local"
            )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def load_config(repo_root: Path | None = None, *, overrides: dict[str, Any] | None = None) -> AgentConfig:
    """Load config from env and optional ``ai-agent/config/agent.yaml``."""
    root = Path(repo_root or Path.cwd()).resolve()
    yaml_path = root / "ai-agent" / "config" / "agent.yaml"
    data: dict[str, Any] = {}
    if yaml_path.is_file():
        with yaml_path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                data = loaded

    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    enabled = _env_bool("AI_AGENT_ENABLED", True) and _env_bool("RUN_AI_AGENT", True)
    if "enabled" in data:
        enabled = bool(data["enabled"]) and enabled

    cfg = AgentConfig(
        repo_root=root,
        enabled=enabled,
        mode=str(data.get("mode") or os.environ.get("AI_AGENT_MODE") or "assist"),
        app_package=str(
            data.get("app_package")
            or os.environ.get("APP_PACKAGE")
            or DEFAULT_APP_PACKAGE
        ),
        maestro_cmd=str(
            data.get("maestro_cmd")
            or os.environ.get("MAESTRO_CMD")
            or DEFAULT_MAESTRO_CMD
        ),
        clear_state=str(data.get("clear_state") or os.environ.get("CLEAR_STATE") or "true"),
        apk_path=(data.get("apk_path") or os.environ.get("APK_PATH") or None),
        max_retries=int(data.get("max_retries") or os.environ.get("AI_AGENT_MAX_RETRIES") or 1),
        parallel_devices=_env_bool("AI_AGENT_PARALLEL_DEVICES", bool(data.get("parallel_devices", True))),
        run_ai_analysis=_env_bool("AI_AGENT_RUN_ANALYSIS", bool(data.get("run_ai_analysis", True))),
        capture_logcat=_env_bool("AI_AGENT_LOGCAT", bool(data.get("capture_logcat", True))),
        capture_screenshots=_env_bool("AI_AGENT_SCREENSHOTS", bool(data.get("capture_screenshots", True))),
        capture_videos=_env_bool("AI_AGENT_VIDEOS", bool(data.get("capture_videos", True))),
        modules_include=list(data.get("modules_include") or []),
        modules_exclude=list(data.get("modules_exclude") or []),
        build_id=str(data.get("build_id") or ""),
        extra={k: v for k, v in data.items() if k not in {
            "enabled", "mode", "app_package", "maestro_cmd", "clear_state", "apk_path",
            "max_retries", "parallel_devices", "run_ai_analysis", "capture_logcat",
            "capture_screenshots", "capture_videos", "modules_include", "modules_exclude",
            "build_id",
        }},
    )
    return cfg
