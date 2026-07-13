"""APK Installer — optional install/verify without touching Maestro YAML."""

from __future__ import annotations

import logging
from pathlib import Path

from agent_utils.adb import adb_run

logger = logging.getLogger("ai-agent.apk")


class ApkInstaller:
    def __init__(self, app_package: str) -> None:
        self.app_package = app_package

    def is_installed(self, device: str) -> bool:
        proc = adb_run(["shell", "pm", "path", self.app_package], device=device, timeout=45)
        out = ((proc.stdout or "") + (proc.stderr or "")).lower()
        return proc.returncode == 0 and "package:" in out

    def install(self, device: str, apk_path: Path) -> bool:
        apk = Path(apk_path)
        if not apk.is_file():
            logger.error("APK missing: %s", apk)
            return False
        logger.info("installing apk device=%s path=%s", device, apk)
        proc = adb_run(["install", "-r", "-d", str(apk)], device=device, timeout=300)
        ok = proc.returncode == 0
        if not ok:
            logger.error("install failed: %s", (proc.stdout or "") + (proc.stderr or ""))
        return ok

    def ensure(self, device: str, apk_path: Path | None) -> bool:
        if self.is_installed(device):
            logger.info("app already installed device=%s package=%s", device, self.app_package)
            return True
        if apk_path:
            return self.install(device, Path(apk_path))
        logger.error("package %s not installed and no APK_PATH provided", self.app_package)
        return False
