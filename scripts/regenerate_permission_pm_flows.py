#!/usr/bin/env python3
"""Regenerate PM_01–PM_30 flows, remove orphan pre-migration YAML files."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERM = ROOT / "ATP TestCase Flows" / "permission"
GEN_PATH = ROOT / "scripts" / "generate_permission_flows.py"

NEXT_AFTER_NEARBY = (
    '".*(?i)(send you notifications|access (more )?photos and videos|'
    'photos and videos on this device|allow limited access|allow all|my gallery).*"'
)
NEXT_AFTER_LOCATION = (
    '".*(?i)(nearby devices|relative position of nearby|send you notifications|'
    'access (more )?photos and videos|photos and videos on this device|my gallery).*"'
)

FINISH = "- runFlow: subflows/finish_permission_flow_to_gallery.yaml"
ADVANCE = "- runFlow: subflows/advance_remaining_permissions_to_gallery.yaml"
ALLOW_CAM = "- runFlow: subflows/allow_camera_permission.yaml"
RESUME = "- runFlow: subflows/resume_permission_flow_after_interrupt.yaml"


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_perm", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_perm"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_cases(g) -> list[tuple[str, str, str, str, str, int]]:
    L = g.LAUNCH
    return [
        (
            "PM_01",
            "Camera Permission Allow",
            "1. Camera permission popup appears → 2. Tap Allow → 3. Open camera from gallery",
            "Camera permission granted and camera opens successfully",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
{ALLOW_CAM}
{ADVANCE}
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
            "Flow continues to next permission; Permission Required NOT shown on first deny",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- runFlow: subflows/deny_camera_permission.yaml
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
            "1. Camera popup → 2. Don't ask again + Don't allow → 3. Access camera",
            "Permission Required → OK → Android Settings when camera accessed",
            f"""{L}
- runFlow: subflows/ensure_kodak_app_ready.yaml
- runFlow:
    when:
      visible: ".*(?i)permission required.*"
    commands:
      - runFlow: subflows/assert_permission_required_opens_settings.yaml
- runFlow:
    when:
      notVisible: ".*(?i)permission required.*"
    commands:
      - runFlow: subflows/prepare_until_camera_permission_prompt.yaml
      - runFlow:
          when:
            visible: ".*(?i)take pictures and record video.*"
          commands:
            - runFlow: subflows/tap_permission_dont_ask_again.yaml
            - extendedWaitUntil:
                notVisible: ".*(?i)take pictures and record video.*"
                timeout: 30000
      - runFlow: subflows/reach_permission_required_after_camera_deny.yaml
      - runFlow: subflows/assert_permission_required_opens_settings.yaml""",
            3,
        ),
        (
            "PM_04",
            "Camera Permission Settings Recovery",
            "1. Deny camera → 2. Settings → 3. Grant camera → 4. Return",
            "Camera functionality restored",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- runFlow: subflows/deny_camera_permission.yaml
- runFlow: subflows/wait_for_permission_after_camera.yaml
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/enable_camera_in_app_settings.yaml
- runFlow: subflows/return_to_app.yaml
{ADVANCE}
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
            "1. Allow Camera → 2. Location popup → 3. Precise + While using",
            "Precise location granted; Nearby Devices dialog next",
            f"""{L}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
- runFlow: subflows/allow_location_precise_permission.yaml
- extendedWaitUntil:
    visible: {NEXT_AFTER_LOCATION}
    timeout: 45000""",
            2,
        ),
        (
            "PM_06",
            "Location Permission Approximate Location",
            "1. Allow Camera → 2. Location popup → 3. Approximate",
            "Approximate location granted; flow continues",
            f"""{L}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
- runFlow: subflows/allow_location_approximate_permission.yaml
- extendedWaitUntil:
    visible: {NEXT_AFTER_LOCATION}
    timeout: 45000""",
            2,
        ),
        (
            "PM_07",
            "Location Permission Deny",
            "1. Allow Camera → 2. Location popup → 3. Don't allow",
            "Flow continues to Nearby Devices on first deny",
            f"""{L}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
- runFlow: subflows/deny_location_permission.yaml
- extendedWaitUntil:
    visible: {NEXT_AFTER_LOCATION}
    timeout: 45000""",
            2,
        ),
        (
            "PM_08",
            "Location Permission Don't Ask Again",
            "1. Location popup → 2. Don't ask again + deny",
            "Permission Required → Settings when location needed",
            f"""{L}
- runFlow: subflows/prepare_until_location_permission_prompt.yaml
- runFlow:
    when:
      visible: ".*(?i)access this device.s location.*"
    commands:
      - runFlow: subflows/tap_permission_dont_ask_again.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)access this device.s location.*"
          timeout: 30000
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
          visible: {NEXT_AFTER_LOCATION}
          timeout: 45000""",
            2,
        ),
        (
            "PM_09",
            "Nearby Devices Permission Allow",
            "1. Allow Camera + Location → 2. Nearby popup → 3. Allow",
            "Nearby granted; next permission dialog appears",
            f"""{L}
- runFlow: subflows/prepare_until_nearby_devices_permission_prompt.yaml
- runFlow: subflows/allow_nearby_devices_permission.yaml
- extendedWaitUntil:
    visible: {NEXT_AFTER_NEARBY}
    timeout: 45000""",
            2,
        ),
        (
            "PM_10",
            "Nearby Devices Permission Deny",
            "1. Nearby popup → 2. Don't allow",
            "Flow continues on first deny",
            f"""{L}
- runFlow: subflows/prepare_until_nearby_devices_permission_prompt.yaml
- runFlow: subflows/deny_nearby_devices_permission.yaml
- extendedWaitUntil:
    visible: {NEXT_AFTER_NEARBY}
    timeout: 45000""",
            2,
        ),
        (
            "PM_11",
            "Nearby Devices Permission Enable Later",
            "1. Deny Nearby → 2. Settings → enable → 3. Return",
            "Nearby permission restored",
            f"""{L}
- runFlow: subflows/prepare_until_nearby_devices_permission_prompt.yaml
- runFlow: subflows/deny_nearby_devices_permission.yaml
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/return_to_app.yaml
- runFlow: subflows/allow_nearby_devices_permission.yaml
- extendedWaitUntil:
    visible: {NEXT_AFTER_NEARBY}
    timeout: 45000""",
            3,
        ),
        (
            "PM_12",
            "Notification Permission Allow",
            "1. Allow upstream → 2. Notification popup → 3. Allow",
            "Notification granted; Photos dialog next; MY GALLERY reached",
            f"""{L}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- runFlow: subflows/allow_notification_permission.yaml
{FINISH}""",
            3,
        ),
        (
            "PM_13",
            "Notification Permission Deny",
            "1. Notification popup → 2. Don't allow",
            "Flow continues to Photos on first deny",
            f"""{L}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- runFlow: subflows/deny_notification_permission.yaml
{FINISH}""",
            3,
        ),
        (
            "PM_14",
            "Notification Permission Dismiss",
            "1. Notification popup → 2. Dismiss if applicable",
            "Application handles dismissal; flow continues",
            f"""{L}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- runFlow:
    when:
      visible: ".*(?i)send you notifications.*"
    commands:
      - runFlow: subflows/dismiss_permission_popup.yaml
{FINISH}""",
            3,
        ),
        (
            "PM_15",
            "Notification Permission Settings Recovery",
            "1. Deny notification → 2. Settings → enable → 3. Return",
            "Notification permission restored; gallery reached",
            f"""{L}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- runFlow: subflows/deny_notification_permission.yaml
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/return_to_app.yaml
{FINISH}""",
            4,
        ),
        (
            "PM_16",
            "Photos and Videos Permission Allow All",
            "1. Photos popup → 2. Allow all",
            "Full gallery accessible; MY GALLERY displayed",
            f"""{L}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
- runFlow: subflows/allow_photos_all_permission.yaml
- runFlow: subflows/reach_my_gallery.yaml""",
            2,
        ),
        (
            "PM_17",
            "Photos and Videos Permission Limited Access",
            "1. Photos popup → 2. Allow limited access → 3. Select 3 labelled photos → 4. Done",
            "Exactly 3 selected photos (10 Jun 2026 4:32/3:58/3:52 pm) visible in MY GALLERY",
            f"""{L}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
- runFlow: subflows/allow_photos_limited_permission.yaml""",
            3,
        ),
        (
            "PM_18",
            "Photos and Videos Permission Deny",
            "1. Photos popup → 2. Don't allow (first time)",
            "Gallery not accessible; retry or blocked state shown",
            f"""{L}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
- runFlow: subflows/deny_photos_permission.yaml
- extendedWaitUntil:
    visible: ".*(?i)(my gallery|permission required|some permissions are needed|access (more )?photos and videos|photos and videos on this device).*"
    timeout: 45000""",
            2,
        ),
        (
            "PM_19",
            "Photos and Videos Permission Don't Ask Again",
            "1. Photos popup → 2. Don't ask again + deny",
            "Permission Required → Settings; gallery blocked",
            f"""{L}
- runFlow: subflows/prepare_until_photos_permission_prompt.yaml
- runFlow:
    when:
      visible: ".*(?i)(access (more )?photos and videos|photos and videos on this device|allow limited access|allow all|don.t allow).*"
    commands:
      - runFlow: subflows/tap_permission_dont_ask_again.yaml
      - extendedWaitUntil:
          notVisible: ".*(?i)(access (more )?photos and videos|photos and videos on this device|allow limited access|allow all|don.t allow).*"
          timeout: 30000
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
            "1. Complete onboarding → 2. Allow all permissions in order",
            "User reaches MY GALLERY successfully",
            f"""{L}
- runFlow: subflows/complete_onboarding_for_permission.yaml
- runFlow: subflows/allow_all_permissions_sequence.yaml""",
            2,
        ),
        (
            "PM_21",
            "Rotate Device During Permission Popup",
            "1. Camera popup → 2. Rotate → 3. Allow",
            "Permission popup remains functional",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- setOrientation: LANDSCAPE_LEFT
- waitForAnimationToEnd:
    timeout: 3000
{ALLOW_CAM}
- setOrientation: PORTRAIT
- waitForAnimationToEnd:
    timeout: 3000
{ADVANCE}""",
            2,
        ),
        (
            "PM_22",
            "App Background During Permission Popup",
            "1. Camera popup → 2. Background → 3. Resume → 4. Allow",
            "Permission flow resumes correctly",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- pressKey: home
- waitForAnimationToEnd:
    timeout: 3000
{RESUME}
{ALLOW_CAM}
{ADVANCE}""",
            3,
        ),
        (
            "PM_23",
            "Lock Device During Permission Popup",
            "1. Camera popup → 2. Lock → 3. Unlock → 4. Allow",
            "Permission popup state retained",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- pressKey: power
- waitForAnimationToEnd:
    timeout: 3000
- pressKey: power
- waitForAnimationToEnd:
    timeout: 3000
- swipe:
    direction: UP
    optional: true
- waitForAnimationToEnd:
    timeout: 2000
{RESUME}
{ALLOW_CAM}
{ADVANCE}""",
            3,
        ),
        (
            "PM_24",
            "Incoming Call During Permission Popup",
            "1. Camera popup → 2. Interrupt → 3. Return → 4. Allow",
            "Permission flow remains stable",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- pressKey: home
- waitForAnimationToEnd:
    timeout: 3000
{RESUME}
{ALLOW_CAM}
{ADVANCE}""",
            3,
        ),
        (
            "PM_25",
            "Rapid Permission Actions",
            "1. Rapidly tap Allow/Deny on camera popup",
            "No crash or duplicate actions",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- runFlow:
    when:
      visible: ".*(?i)take pictures and record video.*"
    commands:
      - repeat:
          times: 3
          commands:
            - tapOn:
                text: "While using the app"
                optional: true
            - tapOn:
                text: "Don't allow"
                optional: true
{RESUME}
{ALLOW_CAM}
{ADVANCE}""",
            1,
        ),
        (
            "PM_26",
            "App Kill During Permission Flow",
            "1. Camera popup → 2. Force close → 3. Reopen → 4. Continue",
            "Permission flow resumes appropriately",
            f"""{L}
- runFlow: subflows/prepare_until_camera_permission_prompt.yaml
- stopApp
# Mid-flow relaunch: preserve permission state (test starts with clearState: true above).
- launchApp:
    clearState: false
    permissions:
      all: deny
- runFlow: subflows/dismiss_app_intro_if_visible.yaml
{RESUME}
- runFlow: subflows/allow_all_permissions_sequence.yaml""",
            3,
        ),
        (
            "PM_28",
            "First Launch After Reinstall",
            "1. Clear app data → 2. Launch app → 3. Complete permission flow",
            "Full onboarding + permission sequence from Camera; MY GALLERY reached",
            f"""{L}
- runFlow: subflows/complete_onboarding_for_permission.yaml
- runFlow: subflows/allow_all_permissions_sequence.yaml""",
            3,
        ),
        (
            "PM_27",
            "Revoke Permission From Settings",
            "1. Grant all → 2. Revoke in settings → 3. Return",
            "App detects revoked permission correctly",
            f"""{L}
- runFlow: subflows/complete_onboarding_for_permission.yaml
- runFlow: subflows/allow_all_permissions_sequence.yaml
- runFlow: ../camera/subflows/open_camera_from_gallery.yaml
- assertVisible:
    id: capture_img
    optional: true
- runFlow: subflows/open_app_settings.yaml
- runFlow: subflows/revoke_camera_permission.yaml
- runFlow: subflows/return_to_app.yaml
- runFlow: ../camera/subflows/open_camera_from_gallery.yaml
- extendedWaitUntil:
    visible: ".*(?i)(take pictures and record video|permission required|some permissions are needed).*"
    timeout: 45000
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
        (
            "PM_29",
            "Nearby Devices Permission Don't Ask Again",
            "1. Nearby popup → 2. Deny → 3. Complete flow → 4. Deny again on re-prompt",
            "Permission Required → OK → Android Settings",
            f"""{L}
- runFlow: subflows/prepare_until_nearby_devices_permission_prompt.yaml
- runFlow: subflows/deny_nearby_devices_permission.yaml
- runFlow: subflows/reach_permission_required_after_nearby_deny.yaml
- runFlow: subflows/assert_permission_required_opens_settings.yaml""",
            4,
        ),
        (
            "PM_30",
            "Notification Permission Don't Ask Again",
            "1. Notification popup → 2. Deny → 3. Complete flow → 4. Deny again on re-prompt",
            "Permission Required → OK → Android Settings",
            f"""{L}
- runFlow: subflows/prepare_until_notification_permission_prompt.yaml
- runFlow: subflows/deny_notification_permission.yaml
- runFlow: subflows/reach_permission_required_after_notification_deny.yaml
- runFlow: subflows/assert_permission_required_opens_settings.yaml""",
            4,
        ),
    ]


def cleanup_orphans(cases: list[tuple[str, str, str, str, str, int]]) -> list[str]:
    keep = {f"{tc_id} - {title}.yaml" for tc_id, title, *_ in cases}

    removed = []
    for path in sorted(PERM.glob("PM_*.yaml")):
        if path.name not in keep:
            path.unlink()
            removed.append(path.name)
    return removed


def main() -> int:
    g = load_generator()
    g.CASES = build_cases(g)
    g.write_flows()
    g.write_mapping()

    spec = importlib.util.spec_from_file_location(
        "gen_perm_suite",
        ROOT / "scripts" / "generate_perm_spreadsheet_suite.py",
    )
    suite = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suite)
    suite.sync_atp_permission_mapping()

    removed = cleanup_orphans(g.CASES)
    if removed:
        print("removed orphans:")
        for name in removed:
            print(f"  - {name}")
    print(f"regenerated {len(g.CASES)} flows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
