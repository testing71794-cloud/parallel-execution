#!/usr/bin/env python3
"""ADB helpers for GA_07: baseline DCIM count, launch native camera, verify new photo."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_STATE_FILE = _REPO / "reports" / "gallery" / "ga07_state.json"
_DCIM_DIR = "/storage/emulated/0/DCIM/Camera"


def _adb_bin() -> str:
    return (os.environ.get("ADB_EXE") or "adb").strip() or "adb"


def _device_serial() -> str:
    for key in ("ANDROID_SERIAL", "MAESTRO_DEVICE", "DEVICE_ID"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def _adb_cmd(*args: str) -> list[str]:
    cmd = [_adb_bin()]
    serial = _device_serial()
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    return cmd


def _adb_shell(shell_cmd: str) -> tuple[int, str]:
    proc = subprocess.run(
        _adb_cmd("shell", shell_cmd),
        capture_output=True,
        text=True,
        check=False,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, text.strip()


def count_dcim_camera_photos() -> int:
    code, text = _adb_shell(f"ls {_DCIM_DIR} 2>/dev/null")
    if code != 0 and not text:
        return 0
    count = 0
    for line in text.splitlines():
        name = line.strip()
        if not name or "No such file" in name:
            continue
        lower = name.lower()
        if lower.endswith((".jpg", ".jpeg", ".png")):
            count += 1
    return count


def launch_native_still_camera() -> None:
    intents = [
        "am start -a android.media.action.STILL_IMAGE_CAMERA",
        "am start -a android.media.action.IMAGE_CAPTURE",
    ]
    last = ""
    for intent in intents:
        code, text = _adb_shell(intent)
        last = text
        if code == 0 and "Error" not in text:
            time.sleep(2.5)
            return
    raise RuntimeError(f"Failed to launch native camera via adb: {last}")


def _load_state() -> dict:
    if not _STATE_FILE.is_file():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(data: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ga07_baseline() -> dict:
    count = count_dcim_camera_photos()
    state = _load_state()
    state["dcim_count_before"] = count
    _save_state(state)
    return {"dcim_count_before": count}


def ga07_launch() -> dict:
    launch_native_still_camera()
    return {"native_camera_launched": True}


def ga07_verify() -> dict:
    state = _load_state()
    before = int(state.get("dcim_count_before", -1))
    after = count_dcim_camera_photos()
    new_photo = before >= 0 and after > before
    result = {
        "dcim_count_before": before,
        "dcim_count_after": after,
        "new_photo_in_gallery": new_photo,
    }
    if not new_photo:
        result["error"] = (
            f"Gallery refresh verify failed: expected new photo in DCIM/Camera "
            f"(before={before}, after={after})"
        )
    return result


def handle_action(action: str) -> dict:
    key = (action or "").strip().lower()
    if key == "baseline":
        return ga07_baseline()
    if key == "launch":
        return ga07_launch()
    if key == "verify":
        return ga07_verify()
    raise ValueError(f"Unknown GA07 action: {action}")


if __name__ == "__main__":
    import sys

    act = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    print(json.dumps(handle_action(act), indent=2))
