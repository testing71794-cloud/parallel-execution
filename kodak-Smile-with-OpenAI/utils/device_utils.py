"""
Resolve a human-readable device name from a serial (ADB) with simple file cache.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Repo root: utils/ is one level below root
REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / ".device_name_cache.json"


def _load_cache() -> dict[str, str]:
    if not CACHE.is_file():
        return {}
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(m: dict[str, str]) -> None:
    try:
        CACHE.write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _adb_prop(device_id: str, prop: str) -> str:
    r = subprocess.run(
        ["adb", "-s", device_id, "shell", "getprop", prop],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return (r.stdout or "").strip()


def get_device_name(device_id: str) -> str:
    """
    Return a readable name: "Brand Model" (e.g. "Google Pixel 6") or the raw id on failure.
    Caches serial -> name in .device_name_cache.json (gitignored).
    """
    d = (device_id or "").strip()
    if not d or d in ("List", "unknown"):
        return d or "unknown"
    m = _load_cache()
    if d in m:
        return m[d]
    brand = _adb_prop(d, "ro.product.brand")
    model = _adb_prop(d, "ro.product.model")
    brand = re.sub(r"[\r\n].*", "", brand).strip()
    model = re.sub(r"[\r\n].*", "", model).strip()
    if not brand and not model:
        out = d
    else:
        b = (brand or "").strip()
        o = (model or "").strip()
        out = f"{b} {o}".strip() or d
    m[d] = out
    _save_cache(m)
    return out


if __name__ == "__main__":
    # Usage: python -m utils.device_utils <serial>
    sid = sys.argv[1] if len(sys.argv) > 1 else ""
    print(get_device_name(sid))
