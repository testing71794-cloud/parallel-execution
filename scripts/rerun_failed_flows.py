#!/usr/bin/env python3
"""Re-run ATP flows that have FAIL status files."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from execution.atp_folder_paths import discover_atp_yaml_files, resolve_atp_subfolder, safe_flow_stem
from execution.maestro_runner import run_run_one_flow_device_bat

STATUS_DIR = REPO / "status"
MAESTRO = Path(r"C:\Tools\maestro-parallel\bin\maestro.bat")
DEVICE = os.environ.get("ATP_DEVICE", "ZA222RFQ75")
APP = "com.kodaksmile"
RERUN_SUITES = {
    "atp_signup_login",
    "atp_onboarding",
    "atp_settings",
    "atp_precut",
    "atp_collage",
}


def _is_fail(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace").upper()
    return "FAIL" in text and "PASS" not in text.split("FAIL")[0][-20:]


def _flow_path(suite: str, safe_stem: str) -> Path | None:
    folder_map = {
        "atp_signup_login": "SignUp_Login",
        "atp_onboarding": "Onboarding",
        "atp_settings": "Settings",
        "atp_precut": "Precut",
        "atp_collage": "Collage",
        "atp_camera": "Camera",
    }
    folder = folder_map.get(suite)
    if not folder:
        return None
    for yf in discover_atp_yaml_files(REPO, folder):
        if safe_flow_stem(yf.stem) == safe_stem:
            return yf
    return None


def main() -> int:
    failed: list[tuple[str, Path]] = []
    for sf in sorted(STATUS_DIR.glob("*.txt")):
        m = re.match(r"^(atp_[a-z_]+)__(.+)__([A-Z0-9]+)\.txt$", sf.name)
        if not m or not _is_fail(sf):
            continue
        suite, safe_stem, _dev = m.group(1), m.group(2), m.group(3)
        if suite not in RERUN_SUITES:
            continue
        flow = _flow_path(suite, safe_stem)
        if flow:
            failed.append((suite, flow))
    print(f"[rerun_failed] count={len(failed)}")
    rc = 0
    for suite, flow in failed:
        print(f"[rerun] {suite} :: {flow.name}")
        r = run_run_one_flow_device_bat(
            repo=REPO,
            suite_id=suite,
            flow_path=flow,
            device_id=DEVICE,
            app_id=APP,
            clear_state="true",
            maestro_launcher=MAESTRO,
        )
        print(f"[rerun] exit={r} flow={flow.name}")
        if r != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
