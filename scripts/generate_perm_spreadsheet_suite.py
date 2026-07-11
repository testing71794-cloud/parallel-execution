#!/usr/bin/env python3
"""Generate PERM_001–PERM_045 suite aligned with enterprise spreadsheet + PM Maestro mapping."""
from __future__ import annotations

import csv
import json
from pathlib import Path

PERM_DIR = Path(__file__).resolve().parents[1] / "ATP TestCase Flows" / "permission"

ONBOARD = (
    "Launch app (launchApp clearState: true, permissions all: deny). Tap I'll do it later. "
    "Accept Terms & Conditions. Skip onboarding. "
    "Permission order: Camera → Location → Nearby Devices → Notification → Photos & Videos."
)

DIALOG = (
    "Permission Required dialog: title 'Permission Required'; message "
    "'Some permissions are needed to be allowed to use this app without any problems.'; "
    "OK → Android App Settings."
)

# (id, name, category, description, steps, expected, maestro_flow, automation, comments)
CASES: list[tuple[str, ...]] = [
    (
        "PERM_001", "Allow All Permissions", "General",
        "User accepts all permissions during first-run flow.",
        f"{ONBOARD} Allow Camera (While using), Location (Precise), Nearby, Notification, Photos (Allow all).",
        "MY GALLERY displayed. All features enabled. No Permission Required dialog.",
        "PM_20 - Permission Flow Allow All Permissions.yaml", "Automated", "",
    ),
    (
        "PERM_002", "Gallery All vs Limited Access", "General",
        "Validate full vs limited Photos & Videos access.",
        f"{ONBOARD} Run A: Photos Allow all → verify full library. Run B: Photos Allow limited → select photos → verify subset only.",
        "Allow all: full library visible. Limited: only selected photos in MY GALLERY.",
        "PM_16; PM_17", "Automated", "Two runs: PM_16 then PM_17.",
    ),
    # Camera
    (
        "PERM_003", "Camera — Denied First Time", "Camera",
        "Deny Camera once; flow continues; re-prompt at end.",
        f"{ONBOARD} Camera: Don't allow. Allow Location, Nearby, Notification, Photos.",
        "Flow continues to Location. Permission Required NOT shown. Camera re-asked at end.",
        "PM_02 - Camera Permission Deny.yaml", "Automated", "",
    ),
    (
        "PERM_004", "Camera — Denied Twice", "Camera",
        "Deny Camera on first pass and on end re-prompt.",
        f"{ONBOARD} Deny Camera. Complete flow. Deny Camera again on re-prompt.",
        f"{DIALOG} Camera blocked. OK opens Settings.",
        "PM_03 - Camera Permission Don't Ask Again.yaml", "Automated", "",
    ),
    (
        "PERM_005", "Camera — Recovery from Settings", "Camera",
        "Grant Camera from Settings after deny.",
        f"{ONBOARD} Deny Camera. Open Settings via Permission Required or app settings. Grant Camera. Return to app. Open camera.",
        "Camera works. capture_img visible.",
        "PM_04 - Camera Permission Settings Recovery.yaml", "Automated", "",
    ),
    # Location
    (
        "PERM_006", "Location — Denied First Time", "Location",
        "Deny Location once; flow continues.",
        f"{ONBOARD} Allow Camera. Location: Don't allow. Allow Nearby, Notification, Photos.",
        "Flow continues to Nearby. Location re-asked at end.",
        "PM_07 - Location Permission Deny.yaml", "Automated", "",
    ),
    (
        "PERM_007", "Location — Denied Twice", "Location",
        "Deny Location twice.",
        f"{ONBOARD} Allow Camera. Deny Location twice (first + end re-prompt).",
        f"{DIALOG} Location features blocked.",
        "PM_08 - Location Permission Don't Ask Again.yaml", "Automated", "",
    ),
    (
        "PERM_008", "Location — Recovery from Settings", "Location",
        "Enable Location in Settings after double deny.",
        f"{ONBOARD} Deny Location twice → Permission Required → OK → Settings → enable Location → return.",
        "Location restored. Printer discovery works.",
        "PM_08 + manual settings", "Partial", "Settings UI may use setPermissions fallback.",
    ),
    # Nearby
    (
        "PERM_009", "Nearby Devices — Denied First Time", "Nearby Devices",
        "Deny Nearby once.",
        f"{ONBOARD} Allow Camera, Location. Nearby: Don't allow. Allow Notification, Photos.",
        "Flow continues. Nearby re-asked at end.",
        "PM_10 - Nearby Devices Permission Deny.yaml", "Automated", "",
    ),
    (
        "PERM_010", "Nearby Devices — Denied Twice", "Nearby Devices",
        "Deny Nearby twice.",
        f"{ONBOARD} Deny Nearby on first pass and end re-prompt.",
        f"{DIALOG} Printer discovery blocked.",
        "PM_29 - Nearby Devices Permission Don't Ask Again.yaml", "Automated", "",
    ),
    (
        "PERM_011", "Nearby Devices — Recovery from Settings", "Nearby Devices",
        "Enable Nearby from Settings after deny.",
        f"{ONBOARD} Deny Nearby → Settings → enable → return.",
        "Nearby restored. Discovery resumes.",
        "PM_11 - Nearby Devices Permission Enable Later.yaml", "Automated", "",
    ),
    # Notification
    (
        "PERM_012", "Notification — Denied First Time", "Notification",
        "Deny Notification once.",
        f"{ONBOARD} Allow Camera–Nearby. Notification: Don't allow. Allow Photos.",
        "Flow continues to Photos. Notification re-asked at end.",
        "PM_13 - Notification Permission Deny.yaml", "Automated", "",
    ),
    (
        "PERM_013", "Notification — Denied Twice", "Notification",
        "Deny Notification twice.",
        f"{ONBOARD} Deny Notification twice.",
        f"{DIALOG} Notifications blocked.",
        "PM_30 - Notification Permission Don't Ask Again.yaml", "Automated", "",
    ),
    (
        "PERM_014", "Notification — Recovery from Settings", "Notification",
        "Enable Notification from Settings.",
        f"{ONBOARD} Deny Notification → Settings → enable → return → finish to gallery.",
        "Notifications enabled. Gallery reachable.",
        "PM_15 - Notification Permission Settings Recovery.yaml", "Automated", "",
    ),
    # Photos & Videos
    (
        "PERM_015", "Photos & Videos — Denied First Time", "Photos & Videos",
        "Deny Photos once.",
        f"{ONBOARD} Allow upstream. Photos: Don't allow.",
        "Flow continues. Photos re-prompted at end. Gallery blocked until granted.",
        "PM_18 - Photos and Videos Permission Deny.yaml", "Automated", "",
    ),
    (
        "PERM_016", "Photos & Videos — Denied Twice", "Photos & Videos",
        "Deny Photos twice.",
        f"{ONBOARD} Deny Photos twice.",
        f"{DIALOG} Gallery NOT accessible.",
        "PM_19 - Photos and Videos Permission Don't Ask Again.yaml", "Automated", "",
    ),
    (
        "PERM_017", "Photos & Videos — Recovery from Settings", "Photos & Videos",
        "Grant Photos from Settings after deny.",
        f"{ONBOARD} Deny Photos twice → Settings → Allow all → return.",
        "MY GALLERY immediately accessible with full library.",
        "Manual / TBD", "Partial", "",
    ),
    # Gallery combinations
    (
        "PERM_018", "Camera Denied in Gallery Album", "Gallery Combination",
        "Gallery works; camera feature blocked.",
        f"{ONBOARD} Deny Camera. Allow Photos (Allow all). Open MY GALLERY. Tap camera.",
        "Gallery accessible. Camera blocked or redirects to settings.",
        "PM_02 + PM_16", "Partial", "Gallery Rule 6.",
    ),
    (
        "PERM_019", "All Permissions Denied Except Gallery", "Gallery Combination",
        "Only Photos granted; all upstream denied.",
        f"{ONBOARD} Deny Camera, Location, Nearby, Notification. Photos: Allow all.",
        "MY GALLERY full access. Camera/printer/notification blocked.",
        "PM_10 pattern + PM_16", "Partial", "",
    ),
    (
        "PERM_020", "Select/Deselect Other Permissions in Gallery", "Gallery Combination",
        "Mixed grant/deny during flow.",
        f"{ONBOARD} Allow Camera & Location. Deny Nearby. Allow Notification. Allow Photos.",
        "Gallery works per Photos state. Denied features show blocked states.",
        "Manual combination", "Manual", "",
    ),
    (
        "PERM_021", "Limited Gallery + Camera Denied", "Gallery Combination",
        "Limited photos with camera denied.",
        f"{ONBOARD} Deny Camera. Allow Photos limited (select photos).",
        "Only selected photos visible. Camera blocked.",
        "PM_17 + camera deny", "Partial", "",
    ),
    (
        "PERM_022", "Notifications Denied in Gallery Album", "Gallery Combination",
        "Gallery works with notification denied.",
        f"{ONBOARD} Allow Camera–Nearby & Photos. Deny Notification.",
        "MY GALLERY accessible. Notifications blocked.",
        "PM_13 + PM_16", "Partial", "",
    ),
    # Lifecycle
    (
        "PERM_023", "App Relaunch After Permissions Granted", "Lifecycle",
        "Kill and relaunch after allow-all.",
        f"{ONBOARD} Allow all permissions. Kill app. Relaunch (clearState false).",
        "MY GALLERY or last screen restored. No duplicate permission spam.",
        "PM_20 + relaunch", "Partial", "",
    ),
    (
        "PERM_024", "App Relaunch After Permissions Denied", "Lifecycle",
        "Relaunch mid-flow after partial deny.",
        f"{ONBOARD} Deny Camera. Kill app. Relaunch.",
        "Permission flow resumes from appropriate step.",
        "Manual", "Manual", "",
    ),
    (
        "PERM_025", "Background App During Permission Popup", "Lifecycle",
        "Home and resume during Camera dialog.",
        f"{ONBOARD} Reach Camera dialog. Press Home. Resume app. Allow Camera. Complete flow.",
        "Flow resumes. No crash.",
        "PM_22 - App Background During Permission Popup.yaml", "Automated", "",
    ),
    (
        "PERM_026", "Force Stop During Permission Flow", "Lifecycle",
        "Force-stop and reopen during permissions.",
        f"{ONBOARD} Reach Camera dialog. Force stop. Relaunch. Complete permissions.",
        "Flow resumes appropriately.",
        "PM_26 - App Kill During Permission Flow.yaml", "Automated", "",
    ),
    (
        "PERM_027", "Clear App Data and Relaunch", "Lifecycle",
        "Clear data resets permission flow.",
        "launchApp clearState: true, permissions all: deny. Complete onboarding.",
        "Full onboarding + permission sequence from Camera.",
        "PM_28 - First Launch After Reinstall.yaml", "Automated", "Suite also runs adb pm clear before each test.",
    ),
    (
        "PERM_028", "First Launch After Reinstall", "Lifecycle",
        "Fresh install permission order.",
        "Install APK. Launch. Complete onboarding.",
        "Permission order Camera→Location→Nearby→Notification→Photos enforced.",
        "PM_28 - First Launch After Reinstall.yaml", "Automated", "",
    ),
]

# Validation scenarios 029–045 (17 combination matrix cases for regression / legacy OS)
VALIDATION_SCENARIOS = [
    ("PERM_029", "Permission Validation Scenario 01", "Allow all permissions end-to-end", "PM_20"),
    ("PERM_030", "Permission Validation Scenario 02", "Camera deny first + allow on retry", "PM_02 + PM_01"),
    ("PERM_031", "Permission Validation Scenario 03", "Location Precise allow path", "PM_05"),
    ("PERM_032", "Permission Validation Scenario 04", "Location Approximate allow path", "PM_06"),
    ("PERM_033", "Permission Validation Scenario 05", "Nearby allow path", "PM_09"),
    ("PERM_034", "Permission Validation Scenario 06", "Notification allow path", "PM_12"),
    ("PERM_035", "Permission Validation Scenario 07", "Photos Allow all path", "PM_16"),
    ("PERM_036", "Permission Validation Scenario 08", "Photos Limited access path", "PM_17"),
    ("PERM_037", "Permission Validation Scenario 09", "Camera deny twice → Permission Required", "PM_03"),
    ("PERM_038", "Permission Validation Scenario 10", "Photos deny twice → Permission Required", "PM_19"),
    ("PERM_039", "Permission Validation Scenario 11", "Rotate during permission popup", "PM_21"),
    ("PERM_040", "Permission Validation Scenario 12", "Rapid permission taps", "PM_25"),
    ("PERM_041", "Permission Validation Scenario 13", "Revoke permission from settings", "PM_27"),
    ("PERM_042", "Permission Validation Scenario 14", "Lock device during popup", "PM_23"),
    ("PERM_043", "Permission Validation Scenario 15", "Incoming call simulation", "PM_24"),
    ("PERM_044", "Permission Validation Scenario 16", "Notification dismiss handling", "PM_14"),
    ("PERM_045", "Permission Validation Scenario 17", "End re-prompt order validation", "Manual matrix"),
]

for vid, vname, vdesc, vpm in VALIDATION_SCENARIOS:
    CASES.append(
        (
            vid,
            vname,
            "Validation",
            f"Execute contributor scenario on target device (API 33+ primary; legacy OS as noted). {vdesc}.",
            f"{ONBOARD} Execute scenario steps per {vname}. Validate no crash and correct permission state.",
            "Permission flow follows business rules. App stable.",
            vpm,
            "Regression" if vpm != "Manual matrix" else "Manual",
            "Run on Android 11–16 OEM matrix.",
        )
    )


def write_suite_csv() -> None:
    path = PERM_DIR / "permission_test_suite_enterprise.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(
            [
                "Test Case ID",
                "Name",
                "Category",
                "Description",
                "Steps",
                "Expected Result",
                "Maestro Flow",
                "Automation",
                "Comments",
            ]
        )
        for row in CASES:
            w.writerow(row)
    print(f"wrote {path.name} ({len(CASES)} cases)")


def write_perm_pm_mapping() -> None:
    csv_path = PERM_DIR / "atp_perm_mapping.csv"
    json_rows = []
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "PERM Test Case ID",
                "Name",
                "Category",
                "Maestro Flow",
                "Automation",
                "Primary PM ID",
                "Comments",
            ]
        )
        for row in CASES:
            perm_id, name, cat, _desc, _steps, _exp, maestro, auto, comments = row
            primary_pm = ""
            if maestro.startswith("PM_"):
                primary_pm = maestro.split(" - ")[0].split(";")[0].strip()
            elif "PM_" in maestro:
                primary_pm = maestro.split("PM_")[1].split(" ")[0]
                primary_pm = f"PM_{primary_pm.split('+')[0].strip()}"
            w.writerow([perm_id, name, cat, maestro, auto, primary_pm, comments])
            json_rows.append(
                {
                    "permTestCaseId": perm_id,
                    "name": name,
                    "category": cat,
                    "maestroFlow": maestro,
                    "automation": auto,
                    "primaryPmId": primary_pm,
                    "comments": comments,
                }
            )
    (PERM_DIR / "atp_perm_mapping.json").write_text(
        json.dumps(json_rows, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {csv_path.name} and atp_perm_mapping.json")


def write_readme() -> None:
    readme = PERM_DIR / "README.md"
    readme.write_text(
        """# Permission Test Module

## Test case IDs

| Range | Category |
|-------|----------|
| PERM_001–002 | General (allow all, gallery all vs limited) |
| PERM_003–005 | Camera (deny 1st, deny 2nd, settings recovery) |
| PERM_006–008 | Location |
| PERM_009–011 | Nearby Devices |
| PERM_012–014 | Notification |
| PERM_015–017 | Photos & Videos |
| PERM_018–022 | Gallery combination scenarios |
| PERM_023–028 | App lifecycle / stability |
| PERM_029–045 | Validation scenarios (regression matrix) |

## Permission order (strict)

Camera → Location → Nearby Devices → Notification → Photos & Videos

## Files

| File | Purpose |
|------|---------|
| `permission_test_suite_enterprise.csv` | Manual + automation test spec (PERM_001–045) |
| `atp_perm_mapping.csv` | PERM → Maestro flow mapping |
| `atp_permission_mapping.csv` | PM_01–30 Maestro YAML automation flows |
| `PM_*.yaml` | Executable Maestro flows |
| `subflows/` | Reusable permission subflows |

## Regenerate PERM suite

```powershell
python scripts/generate_perm_spreadsheet_suite.py
python scripts/regenerate_permission_pm_flows.py
```

## Run Maestro automation (PM_01–30)

```powershell
.\\scripts\\run_permission_suite.ps1 -Device <SERIAL>
```
""",
        encoding="utf-8",
    )
    print("wrote README.md")


PM_TO_PERM: dict[str, str] = {
    "PM_01": "PERM_030",
    "PM_02": "PERM_003",
    "PM_03": "PERM_004",
    "PM_04": "PERM_005",
    "PM_05": "PERM_031",
    "PM_06": "PERM_032",
    "PM_07": "PERM_006",
    "PM_08": "PERM_007",
    "PM_09": "PERM_033",
    "PM_10": "PERM_009",
    "PM_11": "PERM_011",
    "PM_12": "PERM_034",
    "PM_13": "PERM_012",
    "PM_14": "PERM_044",
    "PM_15": "PERM_014",
    "PM_16": "PERM_002",
    "PM_17": "PERM_002",
    "PM_18": "PERM_015",
    "PM_19": "PERM_016",
    "PM_20": "PERM_001",
    "PM_21": "PERM_039",
    "PM_22": "PERM_025",
    "PM_23": "PERM_042",
    "PM_24": "PERM_043",
    "PM_25": "PERM_040",
    "PM_26": "PERM_026",
    "PM_27": "PERM_041",
    "PM_28": "PERM_027",
    "PM_29": "PERM_010",
    "PM_30": "PERM_013",
}


def sync_atp_permission_mapping() -> None:
    """Add PERM Test Case ID column to atp_permission_mapping.csv/json."""
    csv_path = PERM_DIR / "atp_permission_mapping.csv"
    if not csv_path.exists():
        return
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = rows[0]
    if "PERM Test Case ID" not in header:
        header = ["PERM Test Case ID"] + header
        rows[0] = header
        for i in range(1, len(rows)):
            pm_id = rows[i][0] if rows[i] else ""
            perm = PM_TO_PERM.get(pm_id, "")
            rows[i] = [perm] + rows[i]
    else:
        perm_idx = header.index("PERM Test Case ID")
        pm_idx = header.index("ATP Test Case ID")
        for i in range(1, len(rows)):
            pm_id = rows[i][pm_idx]
            rows[i][perm_idx] = PM_TO_PERM.get(pm_id, rows[i][perm_idx])
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    json_path = PERM_DIR / "atp_permission_mapping.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for row in data:
            pm = row.get("atpTestCaseId", "")
            row["permTestCaseId"] = PM_TO_PERM.get(pm, row.get("permTestCaseId", ""))
        json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"synced PERM IDs in {csv_path.name}")


def main() -> int:
    PERM_DIR.mkdir(parents=True, exist_ok=True)
    write_suite_csv()
    write_perm_pm_mapping()
    sync_atp_permission_mapping()
    write_readme()
    docs = Path(__file__).resolve().parents[1] / "docs" / "permission_test_suite_enterprise.csv"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_bytes((PERM_DIR / "permission_test_suite_enterprise.csv").read_bytes())
    print(f"synced {docs.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
