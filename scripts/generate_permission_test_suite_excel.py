#!/usr/bin/env python3
"""Generate enterprise permission combination test suite (Excel-ready CSV)."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ATP TestCase Flows" / "permission" / "permission_test_suite_enterprise.csv"

COLUMNS = [
    "Test Case ID",
    "Module",
    "Scenario",
    "Steps",
    "Expected Result",
]

ENTRY = (
    "1. Launch app (adb pm clear com.kodak.steptouch; launchApp permissions all deny). "
    "2. Tap I'll do it later. 3. Accept Terms & Conditions. 4. Skip onboarding screens. "
    "5. Permission sequence starts (Camera → Location → Nearby Devices → Notification → Photos & Videos)."
)

PERM_REQUIRED = (
    "Permission Required dialog: title 'Permission Required'; message "
    "'Some permissions are needed to be allowed to use this app without any problems.'; "
    "OK button visible. Tap OK → Android App Settings (App info with Permissions) opens."
)

CASES: list[tuple[str, str, str, str, str]] = [
    # --- A. Happy Paths ---
    (
        "PERM_001",
        "Permission",
        "Happy path — all permissions allowed (While using / Allow all)",
        f"{ENTRY} 6. Camera: tap While using the app. 7. Location: Precise + While using the app. "
        "8. Nearby Devices: Allow. 9. Notifications: Allow. 10. Photos & Videos: Allow all.",
        "All five permissions granted. MY GALLERY screen displayed. No Permission Required dialog. "
        "Camera opens (capture control visible). Full photo library accessible in gallery.",
    ),
    (
        "PERM_002",
        "Permission",
        "Happy path — Camera Only this time; all other permissions allowed",
        f"{ENTRY} 6. Camera: tap Only this time. 7–10. Allow Location (Precise, While using), "
        "Nearby Devices, Notifications, Photos & Videos (Allow all).",
        "Camera granted for session. Flow completes to MY GALLERY. Camera feature usable in current session. "
        "Remaining permissions persistently granted.",
    ),
    (
        "PERM_003",
        "Permission",
        "Happy path — Location Precise + While using the app",
        f"{ENTRY} 6. Allow Camera (While using). 7. Location: select Precise, tap While using the app. "
        "8–10. Allow Nearby Devices, Notifications, Photos & Videos (Allow all).",
        "Precise location granted. Nearby Devices dialog appears next. MY GALLERY reached. "
        "No Permission Required dialog.",
    ),
    (
        "PERM_004",
        "Permission",
        "Happy path — Location Approximate + While using the app",
        f"{ENTRY} 6. Allow Camera. 7. Location: select Approximate, tap While using the app. "
        "8–10. Allow Nearby Devices, Notifications, Photos & Videos (Allow all).",
        "Approximate location granted. Flow advances to Nearby Devices then completes to MY GALLERY.",
    ),
    (
        "PERM_005",
        "Permission",
        "Happy path — Gallery Allow all (full library access)",
        f"{ENTRY} 6–9. Allow Camera, Location, Nearby Devices, Notifications. "
        "10. Photos & Videos: tap Allow all.",
        "Photos & Videos permission granted with full access. MY GALLERY shows complete device photo library. "
        "User can browse all photos; no limited-access banner.",
    ),
    (
        "PERM_006",
        "Permission",
        "Happy path — Gallery Allow limited access",
        f"{ENTRY} 6–9. Allow Camera, Location, Nearby Devices, Notifications. "
        "10. Photos & Videos: tap Allow limited access; select photos; confirm selection.",
        "Limited gallery access granted. MY GALLERY displays only selected photos. "
        "Photos outside selection are not visible in app gallery.",
    ),
    # --- B. Permission Combination Scenarios ---
    (
        "PERM_007",
        "Permission",
        "Combination — Camera Allow; Location Allow; Nearby Allow; Notification Allow; Gallery Allow all",
        f"{ENTRY} 6. Camera: While using the app. 7. Location: Precise + While using. "
        "8. Nearby: Allow. 9. Notification: Allow. 10. Photos: Allow all.",
        "Identical to full allow path: MY GALLERY with full library; camera and all features enabled.",
    ),
    (
        "PERM_008",
        "Permission",
        "Combination — Camera Denied; Location Allow; Nearby Allow; Notification Allow; Gallery Allow all",
        f"{ENTRY} 6. Camera: Don't allow. 7–10. Allow Location, Nearby, Notification, Photos (Allow all). "
        "11. At end-of-flow Camera re-prompt: tap While using the app OR leave denied if testing gallery-only.",
        "First Camera deny: flow continues to Location without Permission Required. "
        "Gallery Allow all succeeds — MY GALLERY fully accessible (Rule 6). Camera feature blocked until Camera granted on retry.",
    ),
    (
        "PERM_009",
        "Permission",
        "Combination — Camera Denied; Location Denied; Nearby Allow; Notification Allow; Gallery Allow all",
        f"{ENTRY} 6. Camera: Don't allow. 7. Location: Don't allow. 8–10. Allow Nearby, Notification, Photos (Allow all).",
        "Camera and Location denied on first pass; flow continues. Gallery fully accessible after Photos Allow all. "
        "Camera and location-dependent features show blocked/error states; gallery unaffected.",
    ),
    (
        "PERM_010",
        "Permission",
        "Combination — Camera Denied; Location Denied; Nearby Denied; Notification Denied; Gallery Allow all",
        f"{ENTRY} 6. Camera: Don't allow. 7. Location: Don't allow. 8. Nearby: Don't allow. "
        "9. Notification: Don't allow. 10. Photos: Allow all.",
        "All non-gallery permissions denied on first pass; flow continues each step. "
        "MY GALLERY fully accessible with Allow all (Rule 6). Printer discovery and camera remain blocked.",
    ),
    (
        "PERM_011",
        "Permission",
        "Combination — Camera Denied; Location Denied; Nearby Denied; Notification Denied; Gallery Limited access",
        f"{ENTRY} 6–9. Deny Camera, Location, Nearby, Notification (Don't allow each). "
        "10. Photos: Allow limited access; select 3 photos; confirm.",
        "Upstream permissions denied; gallery still works with limited access. "
        "Only selected photos visible in MY GALLERY; camera/printer/notification features blocked.",
    ),
    (
        "PERM_012",
        "Permission",
        "Combination — all upstream allowed; Gallery Denied first time",
        f"{ENTRY} 6–9. Allow Camera, Location, Nearby, Notification. 10. Photos & Videos: Don't allow.",
        "First Gallery deny: app continues (no Permission Required yet). Photos permission re-requested at end of flow. "
        "Gallery not accessible until granted on retry or via settings.",
    ),
    (
        "PERM_013",
        "Permission",
        "Combination — all upstream allowed; Gallery Denied twice (Permission Required)",
        f"{ENTRY} 6–9. Allow Camera, Location, Nearby, Notification. 10. Photos: Don't allow. "
        "11. On Photos re-prompt at end: Don't allow again.",
        f"{PERM_REQUIRED} Gallery NOT accessible. MY GALLERY blocked or empty. "
        "Dialog cannot be dismissed without OK; no crash.",
    ),
    # --- C. Retry Flow — Deny first, Allow second ---
    (
        "PERM_014",
        "Permission",
        "Retry — Camera denied first time; allowed on end-of-flow re-prompt",
        f"{ENTRY} 6. Camera: Don't allow. 7–10. Allow Location, Nearby, Notification, Photos. "
        "11. Camera re-prompted at end: tap While using the app.",
        "First deny skipped to Location. Camera re-asked at end. Second action grants Camera. "
        "MY GALLERY reached; camera feature opens successfully.",
    ),
    (
        "PERM_015",
        "Permission",
        "Retry — Location denied first time; allowed on end-of-flow re-prompt",
        f"{ENTRY} 6. Allow Camera. 7. Location: Don't allow. 8–10. Allow Nearby, Notification, Photos. "
        "11. Location re-prompted at end: Precise + While using the app.",
        "Location denied once; flow continues. End retry grants Location. MY GALLERY accessible.",
    ),
    (
        "PERM_016",
        "Permission",
        "Retry — Nearby Devices denied first time; allowed on end-of-flow re-prompt",
        f"{ENTRY} 6–7. Allow Camera and Location. 8. Nearby: Don't allow. 9–10. Allow Notification and Photos. "
        "11. Nearby re-prompted at end: Allow.",
        "Nearby denied once; flow continues. End retry grants Nearby. MY GALLERY accessible; printer discovery enabled.",
    ),
    (
        "PERM_017",
        "Permission",
        "Retry — Notification denied first time; allowed on end-of-flow re-prompt",
        f"{ENTRY} 6–8. Allow Camera, Location, Nearby. 9. Notification: Don't allow. 10. Photos: Allow all. "
        "11. Notification re-prompted at end: Allow.",
        "Notification denied once; flow continues to Photos. End retry grants Notification. MY GALLERY fully accessible.",
    ),
    (
        "PERM_018",
        "Permission",
        "Retry — Photos & Videos denied first time; Allow all on end-of-flow re-prompt",
        f"{ENTRY} 6–9. Allow Camera, Location, Nearby, Notification. 10. Photos: Don't allow. "
        "11. Photos re-prompted at end: Allow all.",
        "First Gallery deny continues flow. End retry grants full access. MY GALLERY shows full library immediately.",
    ),
    # --- C. Retry Flow — Deny twice → Permission Required (per permission) ---
    (
        "PERM_019",
        "Permission",
        "Retry — Camera denied twice; Permission Required dialog full validation",
        f"{ENTRY} 6. Camera: Don't allow. 7–10. Allow remaining permissions. "
        "11. Camera re-prompt at end: Don't allow again. 12. Verify dialog. 13. Tap OK.",
        f"After second Camera deny only: {PERM_REQUIRED} "
        "Dialog NOT shown after first deny. Camera feature blocked. App does not crash.",
    ),
    (
        "PERM_020",
        "Permission",
        "Retry — Location denied twice; Permission Required dialog full validation",
        f"{ENTRY} 6. Allow Camera. 7. Location: Don't allow. 8–10. Allow Nearby, Notification, Photos. "
        "11. Location re-prompt: Don't allow again. 12. Verify dialog title, message, OK. 13. Tap OK.",
        f"Second Location deny triggers {PERM_REQUIRED} "
        "Not shown on first deny. Location-dependent features blocked.",
    ),
    (
        "PERM_021",
        "Permission",
        "Retry — Nearby Devices denied twice; Permission Required dialog full validation",
        f"{ENTRY} 6–7. Allow Camera and Location. 8. Nearby: Don't allow. 9–10. Allow Notification and Photos. "
        "11. Nearby re-prompt: Don't allow again. 12. Assert title 'Permission Required' and message text. 13. Tap OK.",
        f"Second Nearby deny: {PERM_REQUIRED} Printer/nearby discovery blocked. Gallery still accessible if Photos allowed.",
    ),
    (
        "PERM_022",
        "Permission",
        "Retry — Notification denied twice; Permission Required dialog full validation",
        f"{ENTRY} 6–8. Allow Camera, Location, Nearby. 9. Notification: Don't allow. 10. Photos: Allow all. "
        "11. Notification re-prompt: Don't allow again. 12. Validate OK visible. 13. Tap OK.",
        f"Second Notification deny: {PERM_REQUIRED} Push notifications remain blocked. Gallery unaffected.",
    ),
    (
        "PERM_023",
        "Permission",
        "Retry — Photos & Videos denied twice; Permission Required dialog full validation",
        f"{ENTRY} 6–9. Allow Camera, Location, Nearby, Notification. 10. Photos: Don't allow. "
        "11. Photos re-prompt: Don't allow again. 12. Verify exact title and message. 13. Tap OK.",
        f"Second Photos deny: {PERM_REQUIRED} Gallery NOT accessible (Rule 5). "
        "Full library and limited access both blocked until Photos granted.",
    ),
    # --- D. Gallery Specific ---
    (
        "PERM_024",
        "Permission",
        "Gallery — Allow all; verify full library visible",
        f"{ENTRY} 6–9. Allow upstream permissions. 10. Photos: Allow all. 11. Scroll gallery grid.",
        "MY GALLERY displays all device photos and videos. No permission error state. "
        "Photo count matches device library (or app-reported full access).",
    ),
    (
        "PERM_025",
        "Permission",
        "Gallery — Allow limited access with selected photos",
        f"{ENTRY} 6–9. Allow upstream. 10. Photos: Allow limited access. 11. Select 5 specific photos. 12. Confirm.",
        "MY GALLERY shows exactly the 5 selected photos. No other device photos visible in app.",
    ),
    (
        "PERM_026",
        "Permission",
        "Gallery — Modify selected photos (add/remove from limited set)",
        f"{ENTRY} 6–9. Allow upstream. 10. Photos: Allow limited access; select 3 photos. "
        "11. Reach MY GALLERY. 12. Open system photo-picker to modify selection; add 2 photos, remove 1.",
        "Updated selection reflected in MY GALLERY: 4 photos visible (3−1+2). "
        "Removed photo no longer shown; newly added photos appear.",
    ),
    (
        "PERM_027",
        "Permission",
        "Gallery — Verify only selected photos visible (negative check)",
        f"{ENTRY} 6–9. Allow upstream. 10. Allow limited access; select 2 known photos (note filenames). "
        "11. Search/scroll MY GALLERY for a non-selected photo.",
        "Only the 2 selected photos appear in MY GALLERY. Non-selected device photos are not accessible in app. "
        "Rule 3 confirmed: gallery depends only on Photos & Videos permission.",
    ),
    (
        "PERM_028",
        "Permission",
        "Gallery — Don't allow first time; re-prompt at end (no Permission Required yet)",
        f"{ENTRY} 6–9. Allow upstream. 10. Photos: Don't allow.",
        "Flow continues without Permission Required dialog. Photos re-requested at end of permission sequence. "
        "Gallery not accessible until second prompt answered.",
    ),
    (
        "PERM_029",
        "Permission",
        "Gallery — Don't allow twice; Permission Required and gallery blocked",
        f"{ENTRY} 6–9. Allow upstream. 10. Photos: Don't allow. 11. End re-prompt: Don't allow again.",
        f"{PERM_REQUIRED} MY GALLERY inaccessible. Permission error or empty state shown. "
        "Camera/Location/Nearby/Notification state does not restore gallery access.",
    ),
    (
        "PERM_030",
        "Permission",
        "Gallery — works when Camera, Location, Nearby, Notification all denied + Allow all photos",
        f"{ENTRY} 6–9. Deny Camera, Location, Nearby, Notification (each Don't allow). "
        "10. Photos: Allow all. 11. Open MY GALLERY.",
        "Rule 6: MY GALLERY fully accessible despite all upstream denials. Camera icon shows blocked/settings redirect. "
        "Gallery grid populated with full library.",
    ),
    # --- E. Android Settings Recovery ---
    (
        "PERM_031",
        "Permission",
        "Settings recovery — Camera: grant from Settings after Permission Required",
        f"{ENTRY} 6. Deny Camera twice (first pass + end retry). 7. On Permission Required tap OK. "
        "8. Android Settings → Permissions → Camera → Allow while using the app. 9. Return to app. 10. Open camera.",
        "Camera permission OS-granted. Permission Required dismissed. Camera opens (capture control visible). "
        "App state retained; no crash on return.",
    ),
    (
        "PERM_032",
        "Permission",
        "Settings recovery — Location: grant from Settings after Permission Required",
        f"{ENTRY} 6. Allow Camera. 7. Deny Location twice. 8. Permission Required → OK → Settings. "
        "9. Enable Location (Precise, While using). 10. Return to app.",
        "Location restored. Location-dependent features functional. Permission Required not re-shown. App state retained.",
    ),
    (
        "PERM_033",
        "Permission",
        "Settings recovery — Nearby Devices: grant from Settings after Permission Required",
        f"{ENTRY} 6–7. Allow Camera and Location. 8. Deny Nearby twice. 9. Permission Required → OK → Settings. "
        "10. Enable Nearby devices. 11. Return to app.",
        "Nearby permission restored. Printer discovery available. Gallery unaffected.",
    ),
    (
        "PERM_034",
        "Permission",
        "Settings recovery — Notification: grant from Settings after Permission Required",
        f"{ENTRY} 6–8. Allow Camera, Location, Nearby. 9. Deny Notification twice. "
        "10. Permission Required → OK → Settings → enable Notifications. 11. Return to app.",
        "Notifications enabled in OS. App resumes without crash. Notification-dependent behavior restored.",
    ),
    (
        "PERM_035",
        "Permission",
        "Settings recovery — Photos & Videos: grant Allow all; gallery immediately accessible",
        f"{ENTRY} 6–9. Allow upstream. 10. Deny Photos twice → Permission Required → OK → Settings. "
        "11. Photos and videos → Allow all. 12. Return to app without relaunch.",
        "Gallery immediately accessible on return. MY GALLERY shows full library. "
        "No second app restart required. Permission Required dismissed.",
    ),
    # --- Negative & Dialog Validation ---
    (
        "PERM_036",
        "Permission",
        "Negative — Permission Required dialog cannot be bypassed (Back / tap outside)",
        f"{ENTRY} 6. Trigger Permission Required (deny Camera twice). 7. Press device Back. "
        "8. Attempt tap outside dialog. 9. Press Home and resume app.",
        "Dialog persists or reappears; user cannot reach MY GALLERY or camera without OK → Settings or granting permission. "
        "App does not crash.",
    ),
    (
        "PERM_037",
        "Permission",
        "Negative — Permission Required appears ONLY after second denial (not first)",
        f"{ENTRY} 6. Camera: Don't allow (first time only). 7. Observe screen before Location dialog.",
        "Permission Required NOT displayed after first Camera deny. Location permission dialog appears next. "
        "Title 'Permission Required' absent.",
    ),
    (
        "PERM_038",
        "Permission",
        "Negative — Permission Required exact title and message text validation (all deny-twice paths)",
        f"{ENTRY} 6–9. Allow upstream. 10–11. Deny Photos twice to trigger dialog. "
        "12. Assert title = 'Permission Required'. 13. Assert message contains "
        "'Some permissions are needed to be allowed to use this app without any problems.'",
        "Title and message match exactly. OK button visible and tappable. No alternate or truncated text.",
    ),
    (
        "PERM_039",
        "Permission",
        "Negative — App state retained after returning from Settings without granting",
        f"{ENTRY} 6. Deny Camera twice → Permission Required → OK → Settings. "
        "7. Press Back without changing permissions. 8. Return to app.",
        "App resumes to same screen/state. Permission Required re-shown or feature remains blocked. "
        "No data loss; no crash; gallery state unchanged.",
    ),
    (
        "PERM_040",
        "Permission",
        "Negative — App state retained after returning from Settings with grant",
        f"{ENTRY} 6. Deny Camera twice → Settings → grant Camera → return to app.",
        "App resumes; previously completed permission steps not re-requested unnecessarily. "
        "Granted Camera immediately functional. MY GALLERY state preserved if already reached.",
    ),
    # --- Additional meaningful combinations ---
    (
        "PERM_041",
        "Permission",
        "Combination — Location Precise + Only this time; all else allowed",
        f"{ENTRY} 6. Allow Camera. 7. Location: Precise + Only this time. 8–10. Allow Nearby, Notification, Photos (Allow all).",
        "Location granted for session. MY GALLERY accessible. Flow completes without Permission Required.",
    ),
    (
        "PERM_042",
        "Permission",
        "Combination — Location Approximate + Only this time; all else allowed",
        f"{ENTRY} 6. Allow Camera. 7. Location: Approximate + Only this time. 8–10. Allow Nearby, Notification, Photos.",
        "Approximate location for session only. MY GALLERY full access. No blocking dialog.",
    ),
    (
        "PERM_043",
        "Permission",
        "Combination — Nearby Denied; Gallery Allow all (gallery independent of Nearby)",
        f"{ENTRY} 6–7. Allow Camera and Location. 8. Nearby: Don't allow. 9–10. Allow Notification and Photos (Allow all).",
        "Nearby denied on first pass; gallery fully accessible. Printer discovery blocked until Nearby granted on retry.",
    ),
    (
        "PERM_044",
        "Permission",
        "Combination — Notification Denied; Gallery Limited access (both independent features)",
        f"{ENTRY} 6–8. Allow Camera, Location, Nearby. 9. Notification: Don't allow. "
        "10. Photos: Allow limited access; select photos.",
        "Notifications blocked; limited gallery works. Only selected photos in MY GALLERY.",
    ),
    (
        "PERM_045",
        "Permission",
        "Retry — End-of-flow re-prompt order matches original permission sequence",
        f"{ENTRY} 6. Deny Camera and Location (first pass). 7–10. Allow Nearby, Notification, Photos. "
        "11. Observe end re-prompt order: Camera first, then Location.",
        "Denied permissions re-requested at end in original order: Camera → Location → Nearby → Notification → Photos. "
        "Each appears once before flow completes.",
    ),
]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(COLUMNS)
        writer.writerows(CASES)
    print(f"Wrote {len(CASES)} test cases to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
