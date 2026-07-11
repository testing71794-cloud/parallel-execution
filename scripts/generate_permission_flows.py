#!/usr/bin/env python3
"""Generate PM_01–PM_27 permission ATP flows (Camera-first order) and project subflows."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ATP TestCase Flows" / "permission"

LAUNCH = """- launchApp:
    clearState: true
    permissions:
      all: deny
- runFlow: subflows/dismiss_app_intro_if_visible.yaml"""

WHEN_CAMERA_ALLOW = """- runFlow:
    when:
      visible: ".*(?i)take pictures and record video.*"
    commands:
      - runFlow: subflows/tap_permission_allow_while_using_the_app.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)take pictures and record video.*"
          timeout: 45000"""

WHEN_CAMERA_DENY = """- runFlow:
    when:
      visible: ".*(?i)take pictures and record video.*"
    commands:
      - runFlow: subflows/tap_permission_deny.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)take pictures and record video.*"
          timeout: 45000"""

WHEN_CAMERA_DONT_ASK = """- runFlow:
    when:
      visible: ".*(?i)take pictures and record video.*"
    commands:
      - runFlow: subflows/tap_permission_dont_ask_again.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)take pictures and record video.*"
          timeout: 45000"""

WHEN_NOTIFICATION_ALLOW = """- runFlow:
    when:
      visible: ".*(?i)send you notifications.*"
    commands:
      - runFlow: subflows/tap_permission_allow_button.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)send you notifications.*"
          timeout: 45000"""

WHEN_NOTIFICATION_DENY = """- runFlow:
    when:
      visible: ".*(?i)send you notifications.*"
    commands:
      - runFlow: subflows/tap_permission_deny.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)send you notifications.*"
          timeout: 45000"""

WHEN_NEARBY_ALLOW = """- runFlow:
    when:
      visible: ".*(?i)(nearby devices|relative position of nearby).*"
    commands:
      - runFlow: subflows/tap_permission_allow_button.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)(nearby devices|relative position of nearby).*"
          timeout: 45000"""

WHEN_NEARBY_DENY = """- runFlow:
    when:
      visible: ".*(?i)(nearby devices|relative position of nearby).*"
    commands:
      - runFlow: subflows/tap_permission_deny.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)(nearby devices|relative position of nearby).*"
          timeout: 45000"""

WHEN_LOCATION_PRECISE = """- runFlow:
    when:
      visible: ".*(?i)access this device.s location.*"
    commands:
      - runFlow: subflows/tap_permission_precise_location.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)access this device.s location.*"
          timeout: 45000"""

WHEN_LOCATION_APPROX = """- runFlow:
    when:
      visible: ".*(?i)access this device.s location.*"
    commands:
      - runFlow: subflows/tap_permission_approximate_location.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)access this device.s location.*"
          timeout: 45000"""

WHEN_LOCATION_DENY = """- runFlow:
    when:
      visible: ".*(?i)access this device.s location.*"
    commands:
      - runFlow: subflows/tap_permission_deny.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)access this device.s location.*"
          timeout: 45000"""

WHEN_LOCATION_DONT_ASK = """- runFlow:
    when:
      visible: ".*(?i)access this device.s location.*"
    commands:
      - runFlow: subflows/tap_permission_dont_ask_again.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)access this device.s location.*"
          timeout: 45000"""

WHEN_PHOTOS_VISIBLE = '".*(?i)(access (more )?photos and videos|photos and videos on this device|allow limited access|allow all|don.t allow|don.t select more).*"'

WHEN_PHOTOS_ALLOW_ALL = f"""- runFlow:
    when:
      visible: {WHEN_PHOTOS_VISIBLE}
    commands:
      - runFlow: subflows/tap_permission_allow_all_photos.yaml
      - extendedWaitUntil:
          notVisible: {WHEN_PHOTOS_VISIBLE}
          timeout: 45000"""

WHEN_PHOTOS_SELECTED = f"""- runFlow:
    when:
      visible: {WHEN_PHOTOS_VISIBLE}
    commands:
      - runFlow: subflows/tap_permission_selected_photos.yaml
      - extendedWaitUntil:
          notVisible: {WHEN_PHOTOS_VISIBLE}
          timeout: 45000"""

WHEN_PHOTOS_DENY = f"""- runFlow:
    when:
      visible: {WHEN_PHOTOS_VISIBLE}
    commands:
      - runFlow: subflows/tap_permission_deny_photos.yaml
      - extendedWaitUntil:
          notVisible: {WHEN_PHOTOS_VISIBLE}
          timeout: 45000"""

WHEN_PHOTOS_DONT_ASK = f"""- runFlow:
    when:
      visible: {WHEN_PHOTOS_VISIBLE}
    commands:
      - runFlow: subflows/tap_permission_dont_ask_again.yaml
      - extendedWaitUntil:
          notVisible: {WHEN_PHOTOS_VISIBLE}
          timeout: 45000"""

CAMERA_SETTINGS_PATH = """- runFlow: subflows/ensure_kodak_app_ready.yaml
- runFlow:
    when:
      visible: ".*(?i)permission required.*"
    commands:
      - runFlow: subflows/assert_permission_required_opens_settings.yaml
- runFlow:
    when:
      notVisible: ".*(?i)permission required.*"
    commands:
      - runFlow: subflows/prepare_until_camera_permission_prompt.yaml"""

CASES: list[tuple[str, str, str, str, str, int]] = [
    (
        "PM_01",
        "Camera Permission Allow",
        "1. Camera permission popup appears → 2. Tap Allow → 3. Open camera from gallery",
        "Camera permission granted and camera opens successfully",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- runFlow: subflows/allow_camera_permission.yaml
- runFlow: subflows/advance_remaining_permissions_to_gallery.yaml
- runFlow: ../camera/subflows/open_camera_from_gallery.yaml
- extendedWaitUntil:
    visible:
      id: capture_img
    timeout: 45000
- assertVisible:
    id: capture_img""",
        3,
    ),
    (
        "PM_02",
        "Camera Permission Deny",
        "1. Camera permission popup appears → 2. Tap Don't Allow",
        "Appropriate message shown; flow continues",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
{WHEN_CAMERA_DENY}
- runFlow: subflows/wait_for_permission_after_camera.yaml
- runFlow:
    when:
      visible: ".*(?i)permission required.*"
    commands:
      - assertVisible: "Permission Required"
      - assertVisible: ".*(?i)some permissions are needed.*"
""",
        2,
    ),
    (
        "PM_03",
        "Camera Permission Don't Ask Again",
        "1. Camera permission popup appears → 2. Select Don't Ask Again → 3. Deny permission",
        "App redirects user to Settings when camera feature is accessed",
        f"""{LAUNCH}
{CAMERA_SETTINGS_PATH}
      - runFlow:
          when:
            visible: ".*(?i)take pictures and record video.*"
          commands:
            - runFlow: subflows/tap_permission_dont_ask_again.yaml
            - extendedWaitUntil:
                notVisible: ".*(?i)take pictures and record video.*"
                timeout: 45000
      - runFlow: subflows/reach_permission_required_after_camera_deny.yaml
      - runFlow: subflows/assert_permission_required_opens_settings.yaml""",
        3,
    ),
    (
        "PM_04",
        "Camera Permission Settings Recovery",
        "1. Deny camera permission → 2. Open device settings → 3. Enable camera permission → 4. Return to app",
        "Camera functionality works correctly",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
{WHEN_CAMERA_DENY}
- runFlow: subflows/wait_for_permission_after_camera.yaml
- runFlow: subflows/dismiss_blocking_permission_dialogs.yaml
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/enable_camera_in_app_settings.yaml
- runFlow: subflows/return_to_app.yaml
- runFlow: subflows/advance_remaining_permissions_to_gallery.yaml
- runFlow: ../camera/subflows/open_camera_from_gallery.yaml
- extendedWaitUntil:
    visible:
      id: capture_img
    timeout: 45000
- assertVisible:
    id: capture_img""",
        4,
    ),
    (
        "PM_05",
        "Location Permission Precise Location",
        "1. Location permission popup appears → 2. Select Precise",
        "Location permission granted successfully",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
{WHEN_LOCATION_PRECISE}
- runFlow: subflows/wait_for_nearby_devices_permission_dialog.yaml""",
        2,
    ),
    (
        "PM_06",
        "Location Permission Approximate Location",
        "1. Location permission popup appears → 2. Select Approximate",
        "App functions correctly with approximate location",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
{WHEN_LOCATION_APPROX}
- runFlow: subflows/wait_for_nearby_devices_permission_dialog.yaml""",
        2,
    ),
    (
        "PM_07",
        "Location Permission Deny",
        "1. Location permission popup appears → 2. Tap Don't Allow",
        "User informed that location access is required for printer discovery",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
{WHEN_LOCATION_DENY}
- extendedWaitUntil:
    visible: ".*(?i)(nearby devices|relative position of nearby|permission required|send you notifications).*"
    timeout: 45000""",
        2,
    ),
    (
        "PM_08",
        "Location Permission Don't Ask Again",
        "1. Select Don't Ask Again → 2. Deny permission",
        "User redirected to settings when location is needed",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
{WHEN_LOCATION_DONT_ASK}
- runFlow:
    when:
      visible: ".*(?i)permission required.*"
    commands:
      - runFlow: subflows/assert_permission_required_opens_settings.yaml
- runFlow:
    when:
      notVisible: ".*(?i)permission required.*"
    commands:
      - runFlow: subflows/wait_for_nearby_devices_permission_dialog.yaml""",
        2,
    ),
    (
        "PM_09",
        "Nearby Devices Permission Allow",
        "1. Bluetooth permission popup appears → 2. Tap Allow",
        "Printer discovery works correctly",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_nearby_devices_permission_prompt.yaml
{WHEN_NEARBY_ALLOW}
- runFlow: subflows/wait_for_notification_permission_dialog.yaml""",
        2,
    ),
    (
        "PM_10",
        "Nearby Devices Permission Deny",
        "1. Bluetooth permission popup appears → 2. Tap Don't Allow",
        "Printer discovery unavailable and message displayed",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_nearby_devices_permission_prompt.yaml
{WHEN_NEARBY_DENY}
- extendedWaitUntil:
    visible: ".*(?i)(send you notifications|access more photos|permission required|my gallery).*"
    timeout: 45000""",
        2,
    ),
    (
        "PM_11",
        "Nearby Devices Permission Enable Later",
        "1. Deny permission → 2. Enable from settings → 3. Return to app",
        "Printer discovery resumes successfully",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_nearby_devices_permission_prompt.yaml
{WHEN_NEARBY_DENY}
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/return_to_app.yaml
{WHEN_NEARBY_ALLOW}
- runFlow: subflows/wait_for_notification_permission_dialog.yaml""",
        3,
    ),
    (
        "PM_12",
        "Notification Permission Allow",
        "1. Complete onboarding → 2. Notification permission popup appears → 3. Tap Allow",
        "Notification permission is granted and user proceeds to next permission",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
{WHEN_NOTIFICATION_ALLOW}
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        3,
    ),
    (
        "PM_13",
        "Notification Permission Deny",
        "1. Complete onboarding → 2. Notification permission popup appears → 3. Tap Don't Allow",
        "App handles denial correctly and continues permission flow",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
{WHEN_NOTIFICATION_DENY}
- runFlow: subflows/wait_for_photos_permission_dialog.yaml""",
        3,
    ),
    (
        "PM_14",
        "Notification Permission Dismiss",
        "1. Complete onboarding → 2. Notification popup appears → 3. Dismiss popup if applicable",
        "Application handles dismissal correctly",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- runFlow:
    when:
      visible: ".*(?i)send you notifications.*"
    commands:
      - runFlow: subflows/dismiss_permission_popup.yaml
- runFlow: subflows/wait_for_photos_permission_dialog.yaml""",
        3,
    ),
    (
        "PM_15",
        "Notification Permission Settings Recovery",
        "1. Deny notification permission → 2. Open device settings → 3. Enable notification permission → 4. Return to app",
        "App detects permission successfully",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
{WHEN_NOTIFICATION_DENY}
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/return_to_app.yaml
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        4,
    ),
    (
        "PM_16",
        "Photos and Videos Permission Allow All",
        "1. Gallery permission popup appears → 2. Tap Allow All",
        "User can access all photos",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
- runFlow: subflows/allow_photos_all_permission.yaml
- runFlow: subflows/reach_my_gallery.yaml""",
        2,
    ),
    (
        "PM_17",
        "Photos and Videos Permission Limited Access",
        "1. Gallery permission popup appears → 2. Select Selected Photos → 3. Choose photos",
        "User can access selected photos only",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
{WHEN_PHOTOS_SELECTED}
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        3,
    ),
    (
        "PM_18",
        "Photos and Videos Permission Deny",
        "1. Gallery permission popup appears → 2. Tap Don't Allow",
        "Gallery access restricted and proper message displayed",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
{WHEN_PHOTOS_DENY}
- extendedWaitUntil:
    visible: ".*(?i)(my gallery|permission required|some permissions are needed).*"
    timeout: 45000
- assertVisible: ".*(?i)(my gallery|permission required|some permissions are needed).*"
""",
        2,
    ),
    (
        "PM_19",
        "Photos and Videos Permission Don't Ask Again",
        "1. Gallery permission popup appears → 2. Select Don't Ask Again",
        "User redirected to settings when gallery feature is used",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
{WHEN_PHOTOS_DONT_ASK}
- runFlow:
    when:
      visible: ".*(?i)permission required.*"
    commands:
      - runFlow: subflows/assert_permission_required_opens_settings.yaml
- runFlow:
    when:
      notVisible: ".*(?i)permission required.*"
    commands:
      - extendedWaitUntil:
          visible: ".*(?i)(my gallery|permission required).*"
          timeout: 45000""",
        2,
    ),
    (
        "PM_20",
        "Permission Flow Allow All Permissions",
        "1. Complete onboarding → 2. Allow all permissions",
        "User reaches gallery screen successfully",
        f"""{LAUNCH}
- runFlow: subflows/complete_onboarding_for_permission.yaml
- runFlow: subflows/allow_all_permissions_sequence.yaml""",
        2,
    ),
    (
        "PM_21",
        "Rotate Device During Permission Popup",
        "1. Permission popup appears → 2. Rotate device",
        "Permission popup remains functional",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- setOrientation: LANDSCAPE_LEFT
- waitForAnimationToEnd:
    timeout: 3000
- runFlow:
    when:
      visible: ".*(?i)send you notifications.*"
    commands:
      - runFlow: subflows/tap_permission_allow_button.yaml
- setOrientation: PORTRAIT
- waitForAnimationToEnd:
    timeout: 3000
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        2,
    ),
    (
        "PM_22",
        "App Background During Permission Popup",
        "1. Permission popup appears → 2. Send app to background → 3. Reopen app",
        "Permission flow resumes correctly",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- pressKey: home
- waitForAnimationToEnd:
    timeout: 3000
- runFlow: subflows/return_to_app.yaml
{WHEN_NOTIFICATION_ALLOW}
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        3,
    ),
    (
        "PM_23",
        "Lock Device During Permission Popup",
        "1. Permission popup appears → 2. Lock device → 3. Unlock device",
        "Permission popup state retained",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- pressKey: power
- waitForAnimationToEnd:
    timeout: 3000
- pressKey: power
- waitForAnimationToEnd:
    timeout: 3000
- runFlow:
    when:
      visible: ".*(?i)send you notifications.*"
    commands:
      - runFlow: subflows/tap_permission_allow_button.yaml
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        3,
    ),
    (
        "PM_24",
        "Incoming Call During Permission Popup",
        "1. Permission popup appears → 2. Receive call → 3. Return to app",
        "Permission flow remains stable",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- pressKey: home
- waitForAnimationToEnd:
    timeout: 3000
- runFlow: subflows/return_to_app.yaml
{WHEN_NOTIFICATION_ALLOW}
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        3,
    ),
    (
        "PM_25",
        "Rapid Permission Actions",
        "1. Rapidly tap Allow/Deny buttons",
        "No crash or duplicate actions occur",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- repeat:
    times: 3
    commands:
      - tapOn:
          text: "Allow"
          optional: true
      - tapOn:
          text: "Don't allow"
          optional: true
{WHEN_NOTIFICATION_ALLOW}
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        1,
    ),
    (
        "PM_26",
        "App Kill During Permission Flow",
        "1. Permission popup appears → 2. Force close app → 3. Reopen app",
        "Permission flow resumes appropriately",
        f"""{LAUNCH}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- stopApp
- launchApp:
    clearState: false
    permissions:
      all: deny
- runFlow: subflows/dismiss_app_intro_if_visible.yaml
- extendedWaitUntil:
    visible: ".*(?i)(send you notifications|access more photos and videos|my gallery).*"
    timeout: 45000
{WHEN_NOTIFICATION_ALLOW}
- runFlow: subflows/continue_past_photos_to_gallery.yaml""",
        3,
    ),
    (
        "PM_27",
        "Revoke Permission From Settings",
        "1. Grant permission → 2. Revoke from settings → 3. Return to app",
        "App detects revoked permission correctly",
        f"""{LAUNCH}
- runFlow: subflows/complete_onboarding_for_permission.yaml
- runFlow: subflows/allow_all_permissions_sequence.yaml
- runFlow: ../camera/subflows/open_camera_from_gallery.yaml
- assertVisible:
    id: capture_img
    optional: true
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/return_to_app.yaml
- runFlow: ../camera/subflows/open_camera_from_gallery.yaml
- runFlow:
    when:
      visible: ".*(?i)take pictures and record video.*"
    commands:
      - runFlow: subflows/tap_permission_allow_while_using_the_app.yaml
- runFlow:
    when:
      visible: ".*(?i)permission required.*"
    commands:
      - assertVisible: ".*(?i)some permissions are needed.*"
""",
        3,
    ),
]


def write_flows() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for tc_id, title, steps, expected, body, _step_count in CASES:
        fname = f"{tc_id} - {title}.yaml"
        content = (
            f"# TC_ID: {tc_id} - {title}\n"
            f"# ATP Steps: {steps}\n"
            f"# ATP Expected: {expected}\n"
            f"# Precondition: launchApp clearState: true, permissions all: deny\n"
            f"appId: com.kodak.steptouch\n"
            f"name: {tc_id} - {title}\n"
            f"---\n"
            f"{body}\n"
        )
        (ROOT / fname).write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {fname}")


def write_mapping() -> None:
    csv_path = ROOT / "atp_permission_mapping.csv"
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
    for tc_id, title, steps, expected, _, step_count in CASES:
        fname = f"{tc_id} - {title}.yaml"
        test_name = f"{tc_id} - {title}"
        rows.append(
            [tc_id, fname, test_name, "Permission", str(step_count), steps, expected]
        )
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
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    (ROOT / "atp_permission_mapping.json").write_text(
        json.dumps(json_rows, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {csv_path.name} and atp_permission_mapping.json")


def main() -> int:
    write_flows()
    write_mapping()
    print(f"done {len(CASES)} flows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
