"""Video Recorder — starts/stops adb screenrecord per module."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from agent_utils.adb import adb_run, resolve_adb

logger = logging.getLogger("ai-agent.video")


class VideoRecorder:
    """
    Best-effort module recording via ``adb shell screenrecord``.

    ATP may also auto-record via Maestro wrappers; this is additive under artifacts/videos.
    """

    def __init__(self, artifact_root: Path) -> None:
        self.root = Path(artifact_root) / "videos"
        self.root.mkdir(parents=True, exist_ok=True)
        self._proc: subprocess.Popen[str] | None = None
        self._remote: str | None = None
        self._device: str | None = None
        self._local: Path | None = None

    def start(self, device: str, module: str) -> None:
        self.stop(save=False)
        stamp = int(time.time())
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in module)[:60]
        self._remote = f"/sdcard/ai_agent_{safe}_{stamp}.mp4"
        self._local = self.root / f"{safe}_{stamp}.mp4"
        self._device = device
        adb = resolve_adb()
        try:
            self._proc = subprocess.Popen(
                [adb, "-s", device, "shell", "screenrecord", "--time-limit", "180", self._remote],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            logger.info("screenrecord started device=%s module=%s", device, module)
        except OSError as exc:
            logger.warning("screenrecord start failed: %s", exc)
            self._proc = None

    def stop(self, *, save: bool = True) -> Path | None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    self._proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            self._proc = None
            time.sleep(1.0)
        out: Path | None = None
        if save and self._device and self._remote and self._local:
            pull = adb_run(["pull", self._remote, str(self._local)], device=self._device, timeout=120)
            adb_run(["shell", "rm", "-f", self._remote], device=self._device, timeout=15)
            if pull.returncode == 0 and self._local.is_file():
                out = self._local
                logger.info("video saved %s", out)
        self._remote = None
        self._device = None
        self._local = None
        return out
