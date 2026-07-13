"""Screenshot Manager — captures device screenshots into artifacts/screenshots."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from agent_utils.adb import adb_run

logger = logging.getLogger("ai-agent.screenshots")


class ScreenshotManager:
    def __init__(self, artifact_root: Path) -> None:
        self.root = Path(artifact_root) / "screenshots"
        self.root.mkdir(parents=True, exist_ok=True)

    def capture(self, device: str, label: str, *, module: str = "general") -> Path | None:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:80]
        out_dir = self.root / module
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        dest = out_dir / f"{stamp}_{safe}.png"
        remote = f"/sdcard/ai_agent_{stamp}.png"
        try:
            cap = adb_run(["shell", "screencap", "-p", remote], device=device, timeout=30)
            if cap.returncode != 0:
                logger.warning("screencap failed device=%s", device)
                return None
            pull = adb_run(["pull", remote, str(dest)], device=device, timeout=60)
            adb_run(["shell", "rm", "-f", remote], device=device, timeout=15)
            if pull.returncode != 0 or not dest.is_file():
                logger.warning("screenshot pull failed device=%s", device)
                return None
            logger.info("screenshot saved %s", dest)
            return dest
        except Exception as exc:  # noqa: BLE001
            logger.warning("screenshot error: %s", exc)
            return None
