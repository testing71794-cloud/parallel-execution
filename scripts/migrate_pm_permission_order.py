#!/usr/bin/env python3
"""Reorder PM_01–PM_19 to Camera-first permission sequence; refresh mapping and PERM CSV."""
from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERM = ROOT / "ATP TestCase Flows" / "permission"
DOCS_CSV = ROOT / "docs" / "permission_test_suite_enterprise.csv"
PERM_CSV = PERM / "permission_test_suite_enterprise.csv"

# (old filename, new filename, new_id, new_title)
MIGRATIONS: list[tuple[str, str, str, str]] = [
    ("PM_05 - Camera Permission Allow.yaml", "PM_01 - Camera Permission Allow.yaml", "PM_01", "Camera Permission Allow"),
    ("PM_06 - Camera Permission Deny.yaml", "PM_02 - Camera Permission Deny.yaml", "PM_02", "Camera Permission Deny"),
    ("PM_07 - Camera Permission Don't Ask Again.yaml", "PM_03 - Camera Permission Don't Ask Again.yaml", "PM_03", "Camera Permission Don't Ask Again"),
    ("PM_08 - Camera Permission Settings Recovery.yaml", "PM_04 - Camera Permission Settings Recovery.yaml", "PM_04", "Camera Permission Settings Recovery"),
    ("PM_16 - Location Permission Precise Location.yaml", "PM_05 - Location Permission Precise Location.yaml", "PM_05", "Location Permission Precise Location"),
    ("PM_17 - Location Permission Approximate Location.yaml", "PM_06 - Location Permission Approximate Location.yaml", "PM_06", "Location Permission Approximate Location"),
    ("PM_18 - Location Permission Deny.yaml", "PM_07 - Location Permission Deny.yaml", "PM_07", "Location Permission Deny"),
    ("PM_19 - Location Permission Don't Ask Again.yaml", "PM_08 - Location Permission Don't Ask Again.yaml", "PM_08", "Location Permission Don't Ask Again"),
    ("PM_13 - Bluetooth Permission Allow.yaml", "PM_09 - Nearby Devices Permission Allow.yaml", "PM_09", "Nearby Devices Permission Allow"),
    ("PM_14 - Bluetooth Permission Deny.yaml", "PM_10 - Nearby Devices Permission Deny.yaml", "PM_10", "Nearby Devices Permission Deny"),
    ("PM_15 - Bluetooth Permission Enable Later.yaml", "PM_11 - Nearby Devices Permission Enable Later.yaml", "PM_11", "Nearby Devices Permission Enable Later"),
    ("PM_01 - Notification Permission Allow.yaml", "PM_12 - Notification Permission Allow.yaml", "PM_12", "Notification Permission Allow"),
    ("PM_02 - Notification Permission Deny.yaml", "PM_13 - Notification Permission Deny.yaml", "PM_13", "Notification Permission Deny"),
    ("PM_03 - Notification Permission Dismiss.yaml", "PM_14 - Notification Permission Dismiss.yaml", "PM_14", "Notification Permission Dismiss"),
    ("PM_04 - Notification Permission Settings Recovery.yaml", "PM_15 - Notification Permission Settings Recovery.yaml", "PM_15", "Notification Permission Settings Recovery"),
    ("PM_09 - Gallery Permission Allow All Photos.yaml", "PM_16 - Photos and Videos Permission Allow All.yaml", "PM_16", "Photos and Videos Permission Allow All"),
    ("PM_10 - Gallery Permission Selected Photos.yaml", "PM_17 - Photos and Videos Permission Limited Access.yaml", "PM_17", "Photos and Videos Permission Limited Access"),
    ("PM_11 - Gallery Permission Deny.yaml", "PM_18 - Photos and Videos Permission Deny.yaml", "PM_18", "Photos and Videos Permission Deny"),
    ("PM_12 - Gallery Permission Don't Ask Again.yaml", "PM_19 - Photos and Videos Permission Don't Ask Again.yaml", "PM_19", "Photos and Videos Permission Don't Ask Again"),
]

# Mapping metadata in permission order (steps/expected aligned to each test)
MAPPING_META: list[tuple[str, str, str, int]] = [
    ("PM_01", "Camera Permission Allow", "1. Complete onboarding → 2. Camera permission popup appears → 3. Tap Allow → 4. Open camera", "Camera permission granted and camera opens successfully", 3),
    ("PM_02", "Camera Permission Deny", "1. Camera permission popup appears → 2. Tap Don't allow", "Flow continues to Location; Permission Required NOT shown on first deny", 2),
    ("PM_03", "Camera Permission Don't Ask Again", "1. Camera popup → 2. Don't ask again + Don't allow → 3. Access camera feature", "Permission Required → OK → Android Settings when camera accessed", 3),
    ("PM_04", "Camera Permission Settings Recovery", "1. Deny camera twice → 2. Permission Required → OK → Settings → 3. Grant camera → 4. Return", "Camera functionality restored", 4),
    ("PM_05", "Location Permission Precise Location", "1. Allow Camera → 2. Location popup → 3. Precise + While using the app", "Precise location granted; Nearby Devices dialog next", 2),
    ("PM_06", "Location Permission Approximate Location", "1. Allow Camera → 2. Location popup → 3. Approximate + allow", "Approximate location granted; flow continues", 2),
    ("PM_07", "Location Permission Deny", "1. Allow Camera → 2. Location popup → 3. Don't allow", "Flow continues to Nearby Devices on first deny", 2),
    ("PM_08", "Location Permission Don't Ask Again", "1. Location popup → 2. Don't ask again + deny", "Permission Required → Settings on second deny or feature access", 2),
    ("PM_09", "Nearby Devices Permission Allow", "1. Allow Camera + Location → 2. Nearby Devices popup → 3. Allow", "Nearby granted; Notification dialog next", 2),
    ("PM_10", "Nearby Devices Permission Deny", "1. Nearby Devices popup → 2. Don't allow", "Flow continues on first deny; printer discovery blocked", 2),
    ("PM_11", "Nearby Devices Permission Enable Later", "1. Deny Nearby → 2. Settings → enable → 3. Return", "Nearby permission restored; discovery resumes", 3),
    ("PM_12", "Notification Permission Allow", "1. Allow Camera, Location, Nearby → 2. Notification popup → 3. Allow", "Notification granted; Photos & Videos dialog next", 3),
    ("PM_13", "Notification Permission Deny", "1. Notification popup → 2. Don't allow", "Flow continues to Photos on first deny", 3),
    ("PM_14", "Notification Permission Dismiss", "1. Notification popup → 2. Dismiss if applicable", "App handles dismissal; flow continues", 3),
    ("PM_15", "Notification Permission Settings Recovery", "1. Deny notification → 2. Settings → enable → 3. Return", "Notification permission restored", 4),
    ("PM_16", "Photos and Videos Permission Allow All", "1. Allow upstream permissions → 2. Photos popup → 3. Allow all", "Full gallery accessible; MY GALLERY displayed", 2),
    ("PM_17", "Photos and Videos Permission Limited Access", "1. Photos popup → 2. Allow limited access → 3. Select photos", "Only selected photos visible in gallery", 3),
    ("PM_18", "Photos and Videos Permission Deny", "1. Photos popup → 2. Don't allow (first time)", "Flow continues; Photos re-prompted at end of sequence", 2),
    ("PM_19", "Photos and Videos Permission Don't Ask Again", "1. Photos popup → 2. Deny twice", "Permission Required → OK → Settings; gallery blocked", 2),
    ("PM_20", "Permission Flow Allow All Permissions", "1. Complete onboarding → 2. Allow all permissions in order", "User reaches MY GALLERY successfully", 2),
    ("PM_21", "Rotate Device During Permission Popup", "1. Permission popup → 2. Rotate device → 3. Complete action", "Permission popup remains functional", 2),
    ("PM_22", "App Background During Permission Popup", "1. Permission popup → 2. Background → 3. Resume", "Permission flow resumes correctly", 3),
    ("PM_23", "Lock Device During Permission Popup", "1. Permission popup → 2. Lock → 3. Unlock", "Permission popup state retained", 3),
    ("PM_24", "Incoming Call During Permission Popup", "1. Permission popup → 2. Interrupt → 3. Return", "Permission flow remains stable", 3),
    ("PM_25", "Rapid Permission Actions", "1. Rapidly tap Allow/Deny", "No crash or duplicate actions", 1),
    ("PM_26", "App Kill During Permission Flow", "1. Permission popup → 2. Force close → 3. Reopen", "Permission flow resumes appropriately", 3),
    ("PM_27", "Revoke Permission From Settings", "1. Grant all → 2. Revoke in settings → 3. Return", "App detects revoked permission correctly", 3),
]


def patch_yaml_header(text: str, new_id: str, new_title: str) -> str:
    full = f"{new_id} - {new_title}"
    text = re.sub(r"# TC_ID: PM_\d+ - .+", f"# TC_ID: {full}", text, count=1)
    text = re.sub(r"# ATP Steps: .+", lambda m: m.group(0), text)  # keep steps comment
    text = re.sub(r"name: PM_\d+ - .+", f"name: {full}", text, count=1)
    # Fix legacy Bluetooth/Gallery comments in body if present
    text = text.replace("Bluetooth Permission", "Nearby Devices Permission")
    text = text.replace("Gallery Permission", "Photos and Videos Permission")
    return text


def migrate_yaml_files() -> None:
    staging: dict[str, tuple[str, str]] = {}
    for old_name, new_name, new_id, new_title in MIGRATIONS:
        src = PERM / old_name
        if not src.exists():
            raise FileNotFoundError(f"Missing flow file: {src}")
        content = patch_yaml_header(src.read_text(encoding="utf-8"), new_id, new_title)
        staging[new_name] = (content, new_id)

    for old_name, new_name, _, _ in MIGRATIONS:
        src = PERM / old_name
        if src.exists():
            src.unlink()

    for new_name, (content, _) in sorted(staging.items()):
        (PERM / new_name).write_text(content, encoding="utf-8", newline="\n")
        print(f"migrated -> {new_name}")


def write_mapping() -> None:
    rows = [
        [
            "ATP Test Case ID",
            "YAML File Name",
            "Test Name",
            "Flow Type",
            "Excel Step Count",
            "ATP Steps",
            "ATP Expected",
        ]
    ]
    json_rows = []
    for tc_id, title, steps, expected, step_count in MAPPING_META:
        fname = f"{tc_id} - {title}.yaml"
        test_name = f"{tc_id} - {title}"
        rows.append([tc_id, fname, test_name, "Permission", str(step_count), steps, expected])
        json_rows.append(
            {
                "atpTestCaseId": tc_id,
                "yamlFileName": fname,
                "testName": test_name,
                "flowType": "Permission",
                "excelStepCount": step_count,
                "atpSteps": steps,
                "atpExpected": expected,
            }
        )
    csv_path = PERM / "atp_permission_mapping.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    (PERM / "atp_permission_mapping.json").write_text(
        json.dumps(json_rows, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {csv_path.name} ({len(json_rows)} entries)")


def copy_perm_suite() -> None:
    if DOCS_CSV.exists():
        shutil.copy2(DOCS_CSV, PERM_CSV)
        print(f"copied PERM suite -> {PERM_CSV}")


def main() -> int:
    migrate_yaml_files()
    write_mapping()
    copy_perm_suite()
    print("PM permission order migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
