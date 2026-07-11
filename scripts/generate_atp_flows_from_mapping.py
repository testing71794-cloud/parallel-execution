#!/usr/bin/env python3
"""
Generate ATP TestCase Flows YAML from ATP_TestCase_Maestro_Mapping.csv (or optional xlsx).

Uses existing Kodak Step Print conventions:
  ATP TestCase Flows/<module>/<ID>.yaml
  subflows under each module; reuses ../../flows/ where applicable.

Does not modify existing YAML files unless --force is passed.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ATP_ROOT = REPO / "ATP TestCase Flows"
MAPPING_CSV = REPO / "ATP_TestCase_Maestro_Mapping.csv"
APP_ID = "com.kodak.steptouch"

MODULE_FOLDER = {
    "SignUp_Login": "signup-login",
    "Onboarding": "onboarding",
    "Connection": "connection",
    "Printing": "printing",
    "Editing": "editing",
    "Camera": "camera",
    "Settings": "settings",
}

# IDs already present in repo (do not overwrite).
EXISTING_IDS = {
    "SU_01", "SU_02", "SU_03", "SU_05", "SU_06", "SU_07", "SU_08", "SU_09", "SU_10",
    "ON_01", "ON_02", "ON_03", "SE_03",
    "CO_01", "CO_02", "CO_03", "CO_04",
    "CA_01", "CA_02", "CA_03", "CA_04", "CA_05", "CA_06", "CA_07",
    "CA_E01", "CA_E02", "CA_E03", "CA_E04",
}

HEADER = """appId: {app_id}
name: {name}
---
"""


def _safe_name(tc_id: str, title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", f"{tc_id}_{title}").strip("_")
    return slug[:80]


def _yaml_path(module: str, tc_id: str) -> Path:
    folder = MODULE_FOLDER.get(module, module.lower().replace("_", "-"))
    return ATP_ROOT / folder / f"{tc_id}.yaml"


def _write(path: Path, content: str, *, force: bool) -> bool:
    if path.is_file() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def _signup_body(tc_id: str, title: str) -> str:
    templates: dict[str, str] = {
        "SU_04": """# ATP SU_04 – Password too short.
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Full Name*"
- inputText: Maestro ATP User
- tapOn: "Email*"
- inputText: maestro.short.pwd@yopmail.com
- tapOn: "Password*"
- inputText: "Ab1"
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(8 character|too short|password must).*"
    timeout: 2000
""",
        "SU_04B": """# ATP SU_04B – Password missing uppercase.
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Full Name*"
- inputText: Maestro ATP User
- tapOn: "Email*"
- inputText: maestro.noupper@yopmail.com
- tapOn: "Password*"
- inputText: testpass1a
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(uppercase|upper case).*"
    timeout: 2000
""",
        "SU_04C": """# ATP SU_04C – Password missing lowercase.
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Full Name*"
- inputText: Maestro ATP User
- tapOn: "Email*"
- inputText: maestro.nolower@yopmail.com
- tapOn: "Password*"
- inputText: TESTPASS1A
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(lowercase|lower case).*"
    timeout: 2000
""",
        "SU_03B": """# ATP SU_03B – Invalid email (no domain).
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Full Name*"
- inputText: Maestro ATP User
- tapOn: "Email*"
- inputText: user@
- tapOn: "Password*"
- inputText: TestPass1a
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible: "Please provide your valid email"
    timeout: 2000
""",
        "SU_03C": """# ATP SU_03C – Invalid email (spaces).
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Full Name*"
- inputText: Maestro ATP User
- tapOn: "Email*"
- inputText: "bad email @test.com"
- tapOn: "Password*"
- inputText: TestPass1a
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible: "Please provide your valid email"
    timeout: 2000
""",
        "SU_E01": """# ATP SU_E01 – Empty name validation.
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Email*"
- inputText: maestro.empty.name@yopmail.com
- tapOn: "Password*"
- inputText: TestPass1a
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(name|full name).*"
    timeout: 2000
""",
        "SU_E02": """# ATP SU_E02 – Empty email validation.
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Full Name*"
- inputText: Maestro ATP User
- tapOn: "Password*"
- inputText: TestPass1a
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(email|valid email).*"
    timeout: 2000
""",
        "SU_E03": """# ATP SU_E03 – Terms unchecked (signup blocked or terms required).
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- assertVisible: "Create an account"
- tapOn: "Full Name*"
- inputText: Maestro ATP User
- runScript: scripts/gen_unique_email.js
- tapOn: "Email*"
- inputText: ${output.signupEmail}
- tapOn: "Password*"
- inputText: TestPass1a
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "SIGN UP"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(terms|agree).*"
    timeout: 2000
""",
        "SU_07B": """# ATP SU_07B – Login with non-existent email.
- launchApp:
    clearState: true
- runFlow: subflows/post_launch_through_signup.yaml
- tapOn: "Log In"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible: "LOGIN"
    timeout: 2000
- tapOn:
    text: "Email"
    optional: true
- inputText: no.such.user.99999@example.invalid
- tapOn:
    text: "Password"
    optional: true
- inputText: WrongPass999!
- hideKeyboard
- waitForAnimationToEnd:
    timeout: 2000
- tapOn: "LOGIN"
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(wrong credential|invalid email|invalid password).*"
    timeout: 2000
""",
    }
    if tc_id in templates:
        return templates[tc_id]
    return f"# ATP {tc_id} – {title}\n# TODO: refine steps from Kodak Step Print ATP 2026.xlsx\n- launchApp:\n    clearState: true\n- runFlow: subflows/post_launch_through_signup.yaml\n"


def _connection_body(tc_id: str, title: str) -> str:
    base = """- launchApp:
    clearState: true
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- assertVisible: "My gallery"
"""
    extras: dict[str, str] = {
        "CO_E01": base + """- tapOn:
    point: "92%, 10%"
    label: Bluetooth – disconnect entry
- waitForAnimationToEnd:
    timeout: 2000
- runFlow:
    when:
      visible: "Disconnect"
    commands:
      - tapOn: "Disconnect"
      - waitForAnimationToEnd:
    timeout: 2000
- runFlow:
    when:
      visible: "Connected"
    commands:
      - assertNotVisible: "Connected"
""",
        "CO_E02": base + """- tapOn:
    point: "92%, 10%"
- waitForAnimationToEnd:
    timeout: 2000
- runFlow:
    when:
      visible: "Connect"
    commands:
      - tapOn: "Connect"
      - waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ${BT_DEVICE_NAME}
    timeout: 2000
- tapOn:
    text: ${BT_DEVICE_NAME}
- runFlow: subflows/pairing_optional.yaml
- assertVisible:
    text: "Connected"
    optional: true
""",
        "CO_E03": """# ATP CO_E03 – Out of range / device not listed (manual: power printer off or move away).
- launchApp:
    clearState: true
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- tapOn:
    point: "92%, 10%"
- waitForAnimationToEnd:
    timeout: 2000
- runFlow:
    when:
      visible: "Connect"
    commands:
      - tapOn: "Connect"
      - waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(search|couldn't find|not found|no device).*"
    timeout: 2000
""",
        "CO_E04": """# ATP CO_E04 – Printer powered off during session (hardware precondition).
- launchApp:
    clearState: false
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- assertVisible: "My gallery"
- extendedWaitUntil:
    visible:
      text: ".*(?i)(disconnected|not connected|connect).*"
    timeout: 2000
""",
    }
    return extras.get(tc_id, f"# ATP {tc_id} – {title}\n{base}")


def _editing_body(tc_id: str, title: str) -> str:
    flow_map = {
        "ED_01": "ED_01_enter_edit_mode.yaml",
        "ED_02": "ED_02_filters.yaml",
        "ED_03": "ED_03_fit_crop.yaml",
        "ED_04": "ED_04_rotate.yaml",
        "ED_05": "ED_05_brightness.yaml",
        "ED_06": "ED_06_contrast.yaml",
        "ED_07": "ED_07_warmth.yaml",
        "ED_08": "ED_08_saturation.yaml",
        "ED_09": "ED_09_highlights.yaml",
        "ED_10": "ED_10_shadows.yaml",
        "ED_11": "ED_11_stickers.yaml",
        "ED_12": "ED_12_text.yaml",
        "ED_13": "ED_13_doodle.yaml",
        "ED_14": "ED_14_erase_doodle.yaml",
        "ED_15": "ED_15_frames.yaml",
        "ED_16": "ED_16_ar_video.yaml",
        "ED_17": "ED_17_scan_ar_video.yaml",
        "ED_E01": "ED_E01_cancel_without_saving.yaml",
        "ED_E02": "ED_E02_multiple_edits.yaml",
        "ED_E03": "ED_E02_multiple_edits.yaml",
    }
    rel = flow_map.get(tc_id)
    if not rel:
        return f"# ATP {tc_id} – {title}\n- launchApp:\n    clearState: true\n"
    return f"""# ATP {tc_id} – {title}
- launchApp:
    clearState: true
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- assertVisible: "My gallery"
- runFlow: ../../flows/editing/{rel}
"""


def _printing_body(tc_id: str, title: str) -> str:
    preamble = """- launchApp:
    clearState: true
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- assertVisible: "My gallery"
- tapOn:
    point: "50%, 45%"
    label: Gallery photo
- waitForAnimationToEnd:
    timeout: 2000
"""
    if tc_id == "PR_01":
        return f"""# ATP PR_01 – Print single photo. Env: BT_DEVICE_NAME
{preamble}
- tapOn:
    text: "Print"
    optional: true
- waitForAnimationToEnd:
    timeout: 2000
- runFlow:
    when:
      visible: "Connect"
    commands:
      - tapOn: "Connect"
      - waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ${{BT_DEVICE_NAME}}
    timeout: 2000
- tapOn:
    text: ${{BT_DEVICE_NAME}}
- runFlow: ../connection/subflows/pairing_optional.yaml
- runFlow: ../../flows/waitForPrinting.yaml
"""
    if tc_id.startswith("PR_E"):
        return f"""# ATP {tc_id} – {title} (hardware / edge setup required)
{preamble}
- tapOn:
    text: "Print"
    optional: true
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(paper|jam|overheat|cooldown|error).*"
    timeout: 2000
"""
    return f"""# ATP {tc_id} – {title}
{preamble}
- tapOn:
    text: "Print"
    optional: true
- waitForAnimationToEnd:
    timeout: 2000
- runFlow: ../../flows/printFromPreview_withReconnect.yaml
"""


def _camera_body(tc_id: str, title: str) -> str:
    return f"""# TC_ID: {tc_id}
# ATP Name: {title}
# See ATP TestCase Flows/camera/atp_camera_mapping.json (sync from xlsx via scripts/sync_atp_camera_from_xlsx.py)
- launchApp:
    clearState: true
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- runFlow: subflows/open_camera_from_gallery.yaml
# TODO: align remaining steps with atp_camera_mapping.json for {tc_id}
"""


def _settings_body(tc_id: str, title: str) -> str:
    if tc_id == "SE_01":
        return f"""# ATP SE_01 – {title}
- launchApp:
    clearState: true
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- extendedWaitUntil:
    visible: "My gallery"
    timeout: 2000
- runFlow: ../../flows/Settings.yaml
"""
    if tc_id == "SE_03":
        return ""  # exists under onboarding/
    return f"""# ATP {tc_id} – {title}
- launchApp:
    clearState: true
- runFlow: ../signup-login/subflows/reach_gallery_after_onboarding_skip.yaml
- extendedWaitUntil:
    visible: "My gallery"
    timeout: 2000
- tapOn:
    point: "8%, 10%"
    optional: true
- tapOn:
    id: settingImageView
    optional: true
- waitForAnimationToEnd:
    timeout: 2000
- extendedWaitUntil:
    visible:
      text: ".*(?i)(quick tips|support|settings).*"
    timeout: 2000
"""


def _onboarding_body(tc_id: str, title: str) -> str:
    return f"""# ATP {tc_id} – {title}
# TODO: align steps with Kodak Step Print ATP 2026.xlsx (see ON_01–ON_03 in repo).
- launchApp:
    clearState: true
- runFlow: subflows/reach_onboarding_after_terms.yaml
"""


def build_content(module: str, tc_id: str, title: str) -> str | None:
    if tc_id in EXISTING_IDS:
        return None
    name = f"{tc_id} - {title}"
    header = HEADER.format(app_id=APP_ID, name=name)
    if module == "SignUp_Login":
        body = _signup_body(tc_id, title)
    elif module == "Connection":
        body = _connection_body(tc_id, title)
    elif module == "Editing":
        body = _editing_body(tc_id, title)
    elif module == "Printing":
        body = _printing_body(tc_id, title)
    elif module == "Camera":
        body = _camera_body(tc_id, title)
    elif module == "Settings":
        if tc_id == "SE_03":
            return None
        body = _settings_body(tc_id, title)
        if not body:
            return None
    elif module == "Onboarding":
        body = _onboarding_body(tc_id, title)
    else:
        body = f"- launchApp:\n    clearState: true\n"
    return header + body


def load_rows(xlsx: Path | None) -> list[dict[str, str]]:
    if xlsx and xlsx.is_file():
        try:
            import openpyxl

            wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []
            headers = [str(h or "").strip() for h in rows[0]]
            out: list[dict[str, str]] = []
            for row in rows[1:]:
                d = {headers[i]: str(row[i] or "").strip() for i in range(len(headers)) if headers[i]}
                tid = d.get("TestCaseID") or d.get("ATP Test Case ID") or d.get("TestCase ID") or ""
                if tid:
                    out.append(
                        {
                            "TestCaseID": tid,
                            "Module": d.get("Module") or d.get("Flow Type") or "",
                            "TestCaseTitle": d.get("TestCaseTitle") or d.get("Test Name") or "",
                        }
                    )
            return out
        except ImportError:
            print("[gen] openpyxl not installed; use CSV mapping", flush=True)
    if not MAPPING_CSV.is_file():
        return []
    with MAPPING_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", type=Path, help="Kodak Step Print ATP 2026.xlsx path")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    xlsx = args.xlsx
    if xlsx is None:
        for candidate in (
            REPO / "Kodak Step Print ATP 2026.xlsx",
            REPO / "docs" / "Kodak Step Print ATP 2026.xlsx",
        ):
            if candidate.is_file():
                xlsx = candidate
                break
    rows = load_rows(xlsx)
    if not rows:
        print("No mapping rows found.", flush=True)
        return 1
    created: list[str] = []
    skipped: list[str] = []
    for row in rows:
        tc_id = row["TestCaseID"].strip()
        module = row["Module"].strip()
        title = row["TestCaseTitle"].strip()
        content = build_content(module, tc_id, title)
        if content is None:
            skipped.append(tc_id)
            continue
        path = _yaml_path(module, tc_id)
        if args.dry_run:
            print(f"would write {path}", flush=True)
            created.append(str(path))
            continue
        if _write(path, content, force=args.force):
            created.append(str(path.relative_to(REPO)))
    print(f"[gen] created={len(created)} skipped_existing={len(skipped)}", flush=True)
    for p in created[:30]:
        print(f"  + {p}", flush=True)
    if len(created) > 30:
        print(f"  ... and {len(created) - 30} more", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
