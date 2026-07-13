"""Logcat Collector — dump device logs per module into artifacts/logcat."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from agent_utils.adb import adb_run

logger = logging.getLogger("ai-agent.logcat")


class LogcatCollector:
    def __init__(self, artifact_root: Path) -> None:
        self.root = Path(artifact_root) / "logcat"
        self.root.mkdir(parents=True, exist_ok=True)

    def clear(self, device: str) -> None:
        adb_run(["logcat", "-c"], device=device, timeout=20)

    def dump(self, device: str, module: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in module)[:60]
        dest = self.root / f"{safe}_{int(time.time())}.txt"
        proc = adb_run(["logcat", "-d", "-v", "threadtime"], device=device, timeout=120)
        text = (proc.stdout or "") + (proc.stderr or "")
        dest.write_text(text, encoding="utf-8", errors="replace")
        logger.info("logcat saved %s bytes=%s", dest, dest.stat().st_size)
        return dest
