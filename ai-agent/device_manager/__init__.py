"""Device Manager — detect healthy Android devices via adb."""

from __future__ import annotations

import logging
from pathlib import Path

from models import DeviceInfo
from agent_utils.adb import adb_run

logger = logging.getLogger("ai-agent.device")


class DeviceManager:
    """Discovers and filters ADB devices. Never modifies app state."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root else None

    def list_raw_serials(self) -> list[tuple[str, str]]:
        """Return (serial, state) pairs from ``adb devices``."""
        proc = adb_run(["devices"])
        pairs: list[tuple[str, str]] = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line or line.lower().startswith("list of devices"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                pairs.append((parts[0], parts[1]))
        return pairs

    def enrich(self, serial: str, state: str) -> DeviceInfo:
        info = DeviceInfo(serial=serial, state=state, healthy=state == "device")
        if state != "device":
            info.skip_reason = f"state={state}"
            info.healthy = False
            return info
        try:
            model = adb_run(["shell", "getprop", "ro.product.model"], device=serial, timeout=20)
            info.model = (model.stdout or "").strip() or serial
            ver = adb_run(["shell", "getprop", "ro.build.version.release"], device=serial, timeout=20)
            info.android_version = (ver.stdout or "").strip()
            boot = adb_run(["shell", "getprop", "sys.boot_completed"], device=serial, timeout=20)
            if (boot.stdout or "").strip() not in ("1",):
                info.healthy = False
                info.skip_reason = "boot_incomplete"
        except Exception as exc:  # noqa: BLE001
            info.healthy = False
            info.skip_reason = f"probe_error:{exc}"
        return info

    def list_healthy_devices(self) -> list[DeviceInfo]:
        devices: list[DeviceInfo] = []
        for serial, state in self.list_raw_serials():
            info = self.enrich(serial, state)
            devices.append(info)
            if info.healthy:
                logger.info("device healthy serial=%s model=%s android=%s", serial, info.model, info.android_version)
            else:
                logger.warning("device skipped serial=%s reason=%s", serial, info.skip_reason)
        return [d for d in devices if d.healthy]

    def list_all(self) -> list[DeviceInfo]:
        return [self.enrich(s, st) for s, st in self.list_raw_serials()]
