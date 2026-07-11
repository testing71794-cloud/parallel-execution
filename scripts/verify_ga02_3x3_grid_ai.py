#!/usr/bin/env python3
"""OpenRouter vision verify for GA_02 3x3 gallery grid. Run after Maestro or standalone."""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intelligent_platform.config import (  # noqa: E402
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    openrouter_api_key,
    openrouter_model_vision,
)
from intelligent_platform.openrouter_client import call_openrouter_vision  # noqa: E402

_SCREENSHOT_NAME = "GA_02_3x3_grid_verify"

_PROMPT = """You are validating a Kodak Step Prints My Gallery screenshot.

Answer ONLY with JSON: {"grid_3x3": true/false, "summary": "one sentence"}

grid_3x3: true when the gallery shows photo thumbnails in a 3-column by 3-row grid (nine visible cells).
It must NOT be a single-column list view or a larger dense grid."""


def _find_screenshot(name: str, search_roots: list[Path]) -> Path | None:
    for root in search_roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob(f"*{name}*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                return p
    return None


def resolve_adb_exe() -> str | None:
    adb_exe = os.environ.get("ADB_EXE", "").strip()
    if adb_exe and Path(adb_exe).is_file():
        return adb_exe
    for env_name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(env_name, "").strip()
        if not root:
            continue
        candidate = Path(root) / "platform-tools" / "adb.exe"
        if candidate.is_file():
            return str(candidate)
        candidate = Path(root) / "platform-tools" / "adb"
        if candidate.is_file():
            return str(candidate)
    local_sdk = Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe"
    if local_sdk.is_file():
        return str(local_sdk)
    return shutil.which("adb")


def resolve_device_serial() -> str | None:
    for env_name in ("ANDROID_SERIAL", "MAESTRO_DEVICE", "DEVICE_ID", "ATP_DEVICE"):
        serial = os.environ.get(env_name, "").strip()
        if serial:
            return serial
    repo_serials = _REPO / "detected_devices.txt"
    if repo_serials.is_file():
        for line in repo_serials.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return line.split()[0]
    adb = resolve_adb_exe()
    if not adb:
        return None
    try:
        proc = subprocess.run(
            [adb, "devices"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in (proc.stdout or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None


def capture_adb_png(serial: str | None = None) -> bytes:
    adb = resolve_adb_exe()
    if not adb:
        raise RuntimeError("adb not found on PATH or in Android SDK platform-tools")
    serial = serial or resolve_device_serial()
    cmd = [adb]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["exec-out", "screencap", "-p"])
    proc = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"adb screencap failed (exit {proc.returncode}): {err[:300]}")
    data = proc.stdout or b""
    if len(data) < 1000:
        raise RuntimeError("adb screencap returned empty or invalid PNG")
    return data


def verify_image_bytes(data: bytes, *, source: str = "screenshot") -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "grid_3x3": None,
            "summary": "OPENROUTER_API_KEY not set — skip AI verify",
            "skipped": True,
        }
    b64 = base64.standard_b64encode(data).decode("ascii")
    mime = "image/png"
    messages = [
        {"role": "system", "content": _PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Verify this My Gallery screenshot shows a 3x3 grid layout."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        },
    ]
    try:
        raw, model_used = call_openrouter_vision(
            messages,
            api_key=key,
            base_url=OPENROUTER_BASE_URL,
            model=openrouter_model_vision(),
            http_referer=OPENROUTER_HTTP_REFERER,
            app_title=OPENROUTER_APP_TITLE,
            max_tokens=400,
        )
    except Exception as e:
        return {
            "grid_3x3": None,
            "summary": f"OpenRouter unavailable: {e}",
            "skipped": True,
        }
    try:
        text = (raw or "").strip()
        if "```" in text:
            for part in text.split("```"):
                chunk = part.strip()
                if chunk.lower().startswith("json"):
                    chunk = chunk[4:].strip()
                if chunk.startswith("{"):
                    text = chunk
                    break
        if not text.startswith("{"):
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        result = json.loads(text)
        if isinstance(result, dict):
            result["model_used"] = model_used
            result["source"] = source
        return result
    except json.JSONDecodeError:
        return {"grid_3x3": False, "summary": raw[:500], "skipped": False, "source": source}


def verify_image(path: Path) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "grid_3x3": None,
            "summary": "OPENROUTER_API_KEY not set — skip AI verify",
            "skipped": True,
        }
    return verify_image_bytes(path.read_bytes(), source=str(path))


def default_search_roots() -> list[Path]:
    repo = _REPO
    roots: list[Path] = [
        repo,
        repo / "reports" / "gallery",
        repo / "reports" / "gallery" / "maestro-debug",
        Path.home() / ".maestro" / "tests",
        Path.home() / ".maestro" / "screenshots",
    ]
    for parent in [
        repo / "ATP TestCase Flows" / "gallery",
        repo / "ATP TestCase Flows",
    ]:
        roots.extend(
            [
                parent,
                parent / ".maestro" / "screenshots",
                parent / ".maestro" / "tests",
            ]
        )
    return roots


def find_screenshot(name: str, search_roots: list[Path] | None = None) -> Path | None:
    return _find_screenshot(name, search_roots or default_search_roots())


def verify_basename(name: str = _SCREENSHOT_NAME, *, use_adb: bool = True) -> dict:
    path = find_screenshot(name)
    if path is not None and path.is_file():
        return verify_image(path)
    if use_adb:
        try:
            png = capture_adb_png()
            out_dir = _REPO / "reports" / "gallery" / "maestro-debug"
            out_dir.mkdir(parents=True, exist_ok=True)
            live_path = out_dir / f"{name}_adb_live.png"
            live_path.write_bytes(png)
            result = verify_image_bytes(png, source=f"adb:{live_path}")
            return result
        except Exception as e:
            return {
                "grid_3x3": False,
                "summary": f"Screenshot {name}.png not found and adb capture failed: {e}",
                "skipped": False,
            }
    return {
        "grid_3x3": False,
        "summary": f"Screenshot {name}.png not found",
        "skipped": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path, help="Path to PNG/JPG screenshot")
    parser.add_argument(
        "--search",
        type=Path,
        action="append",
        default=[],
        help=f"Directory to search for {_SCREENSHOT_NAME} screenshot",
    )
    parser.add_argument(
        "--adb",
        action="store_true",
        help="Capture live device screen via adb when screenshot file is missing",
    )
    args = parser.parse_args()
    path = args.screenshot
    if path is None:
        roots = args.search or default_search_roots()
        path = find_screenshot(_SCREENSHOT_NAME, roots)
    if path is None or not path.is_file():
        if args.adb:
            result = verify_basename(_SCREENSHOT_NAME, use_adb=True)
            print(json.dumps(result, indent=2))
            if result.get("skipped"):
                return 0
            if result.get("grid_3x3"):
                return 0
            return 1
        print("ERROR: screenshot not found (try --adb for live capture)", file=sys.stderr)
        return 2
    result = verify_image(path)
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return 0
    if result.get("grid_3x3"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
