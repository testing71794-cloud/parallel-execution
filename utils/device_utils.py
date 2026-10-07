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

# ro.product.model (and variants) -> console/report display label
_MODEL_DISPLAY_ALIASES: dict[str, str] = {
    "sm-m346b": "Samsung M34",
    "moto fusion 50": "Motorola Fusion 50",
}

# Lab-device serial fallbacks when adb is unavailable (email/report agents)
_SERIAL_DISPLAY_ALIASES: dict[str, str] = {
    "rzcwa2b05rb": "Samsung M34",
    "za222rfq75": "Motorola Fusion 50",
}


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
    try:
        r = subprocess.run(
            ["adb", "-s", device_id, "shell", "getprop", prop],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "").strip()


def _normalize_display_name(model: str) -> str:
    m = re.sub(r"[\r\n].*", "", (model or "").strip())
    if not m:
        return m
    alias = _MODEL_DISPLAY_ALIASES.get(m.lower())
    if alias:
        return alias
    return m


def _is_likely_device_serial(value: str) -> bool:
    """Heuristic: ADB serial/UDID (no spaces, typical length) vs friendly label."""
    t = (value or "").strip()
    if not t or " " in t:
        return False
    if len(t) < 8:
        return False
    return bool(re.match(r"^[A-Za-z0-9._-]+$", t))


def render_device_display(display: str = "", device_id: str = "") -> str:
    """
    Human-facing label for reports/email/HTML only. Prefer an already-friendly
    display name; otherwise resolve serial via :func:`get_device_display_name`.
    """
    disp = (display or "").strip()
    did = (device_id or "").strip()
    # Keep labels that are already human-readable (e.g. "16091FDD4004 N6", "Motorola Fusion 50")
    if disp and not _is_likely_device_serial(disp):
        return disp
    if did:
        return get_device_display_name(did)
    if disp and _is_likely_device_serial(disp):
        return get_device_display_name(disp)
    return disp


def get_device_display_name(device_id: str) -> str:
    """
    Human-readable device label for logs and reports (serial unchanged internally).
    Uses ``ro.product.model`` via adb, normalizes known models, caches per serial.
    Falls back to the raw serial when adb lookup fails.
    """
    d = (device_id or "").strip()
    if not d or d in ("List", "unknown"):
        return d or "unknown"
    m = _load_cache()
    if d in m:
        cached = m[d]
        # Retry adb when cache only has a failed self-mapping (serial -> serial).
        if cached and cached != d:
            return cached
    model = _adb_prop(d, "ro.product.model")
    model = re.sub(r"[\r\n].*", "", model).strip()
    if not model:
        out = _SERIAL_DISPLAY_ALIASES.get(d.lower()) or d
    else:
        out = _normalize_display_name(model)
        if out == d:
            out = _SERIAL_DISPLAY_ALIASES.get(d.lower()) or d
    if out != d:
        m[d] = out
        _save_cache(m)
    return out


def get_device_name(device_id: str) -> str:
    """Backward-compatible alias for :func:`get_device_display_name`."""
    return get_device_display_name(device_id)


if __name__ == "__main__":
    # Usage: python -m utils.device_utils <serial>
    sid = sys.argv[1] if len(sys.argv) > 1 else ""
    print(get_device_display_name(sid))
