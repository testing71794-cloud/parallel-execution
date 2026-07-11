#!/usr/bin/env python3
"""uiautomator2 helper: open Kodak Smile Edit tool by label (toolbar horizontal scroll).

Usage:
  python scripts/editing_tap_tool_u2.py ZA222RFQ75 Saturation
  python scripts/editing_tap_tool_u2.py ZA222RFQ75 Stickers --apply-swipe
  python scripts/editing_tap_tool_u2.py ZA222RFQ75 Text --input "Hello"
  python scripts/editing_tap_tool_u2.py ZA222RFQ75 Doodle --draw
  python scripts/editing_tap_tool_u2.py ZA222RFQ75 Frames --frame
  python scripts/editing_tap_tool_u2.py ZA222RFQ75 AR --ar
  python scripts/editing_tap_tool_u2.py ZA222RFQ75 --cancel-save
"""
from __future__ import annotations

import argparse
import sys
import time


def connect(serial: str):
    import uiautomator2 as u2

    d = u2.connect(serial)
    d.implicitly_wait(5.0)
    return d


def tap_edit_tab(d) -> None:
    if d(text="Edit").exists(timeout=3):
        d(text="Edit").click()
        time.sleep(0.8)


def find_and_tap_tool(d, label: str, max_swipes: int = 12) -> bool:
    # Already visible?
    for cand in (label, label.rstrip("s"), label + "s"):
        if d(text=cand).exists(timeout=1) or d(textContains=cand).exists(timeout=0.5):
            (d(text=cand) if d(text=cand).exists else d(textContains=cand)).click()
            time.sleep(0.8)
            return True
    # Horizontal swipe on bottom toolbar band (~91% height)
    info = d.info
    w, h = info["displayWidth"], info["displayHeight"]
    y = int(h * 0.91)
    x1, x2 = int(w * 0.88), int(w * 0.15)
    for _ in range(max_swipes):
        if d(text=label).exists(timeout=0.6) or d(textContains=label).exists(timeout=0.3):
            el = d(text=label) if d(text=label).exists else d(textContains=label)
            el.click()
            time.sleep(0.8)
            return True
        d.swipe(x1, y, x2, y, 0.25)
        time.sleep(0.35)
    # Try reverse direction once
    for _ in range(max_swipes):
        if d(text=label).exists(timeout=0.6) or d(textContains=label).exists(timeout=0.3):
            el = d(text=label) if d(text=label).exists else d(textContains=label)
            el.click()
            time.sleep(0.8)
            return True
        d.swipe(x2, y, x1, y, 0.25)
        time.sleep(0.35)
    return False


def apply_slider(d) -> None:
    info = d.info
    w, h = info["displayWidth"], info["displayHeight"]
    y = int(h * 0.90)
    d.swipe(int(w * 0.30), y, int(w * 0.80), y, 0.3)
    time.sleep(0.4)
    if d(text="Done").exists(timeout=2):
        d(text="Done").click()
        time.sleep(0.6)


def apply_done(d) -> None:
    if d(text="Done").exists(timeout=2):
        d(text="Done").click()
        time.sleep(0.6)
    elif d(text="Save").exists(timeout=1):
        d(text="Save").click()
        time.sleep(0.6)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("serial")
    p.add_argument("tool", nargs="?", default="")
    p.add_argument("--apply-swipe", action="store_true")
    p.add_argument("--input", default="")
    p.add_argument("--draw", action="store_true")
    p.add_argument("--frame", action="store_true")
    p.add_argument("--ar", action="store_true")
    p.add_argument("--cancel-save", action="store_true")
    p.add_argument("--erase", action="store_true")
    args = p.parse_args()

    d = connect(args.serial)

    if args.cancel_save:
        if d(text="Close").exists(timeout=3):
            d(text="Close").click()
            time.sleep(0.8)
        for t in ("Don't Save", "Dont Save", "Discard", "Cancel", "CANCEL", "No"):
            if d(text=t).exists(timeout=1.5):
                d(text=t).click()
                time.sleep(0.5)
                print(f"[u2] cancel tapped={t}")
                return 0
        # dialog button by id heuristics
        if d(resourceIdMatches=".*cancel.*").exists(timeout=1):
            d(resourceIdMatches=".*cancel.*").click()
            print("[u2] cancel by resourceId")
            return 0
        print("[u2] ERROR: cancel button not found", file=sys.stderr)
        return 2

    if args.ar:
        if d(text="AR").exists(timeout=3):
            d(text="AR").click()
            time.sleep(1.2)
        # dismiss permission if any
        for t in ("While using the app", "Allow", "OK", "Ok"):
            if d(text=t).exists(timeout=1):
                d(text=t).click()
                time.sleep(0.5)
        print("[u2] AR opened")
        return 0

    tap_edit_tab(d)
    label = args.tool.strip()
    if not label:
        print("[u2] ERROR: tool label required", file=sys.stderr)
        return 2
    # Frames UI may say Frame
    aliases = [label]
    if label == "Frames":
        aliases = ["Frames", "Frame"]
    if label == "Stickers":
        aliases = ["Stickers", "Sticker"]
    ok = False
    for a in aliases:
        if find_and_tap_tool(d, a):
            ok = True
            label = a
            break
    if not ok:
        print(f"[u2] ERROR: tool not found: {args.tool}", file=sys.stderr)
        return 3
    print(f"[u2] opened tool={label}")

    info = d.info
    w, h = info["displayWidth"], info["displayHeight"]

    if args.apply_swipe:
        apply_slider(d)
    elif args.input:
        # tap canvas center and type
        d.click(w // 2, int(h * 0.45))
        time.sleep(0.4)
        d.send_keys(args.input, clear=False)
        time.sleep(0.4)
        d.press("back")
        time.sleep(0.3)
        apply_done(d)
    elif args.draw:
        d.swipe(int(w * 0.35), int(h * 0.45), int(w * 0.75), int(h * 0.65), 0.4)
        time.sleep(0.4)
        if args.erase and d(text="Erase").exists(timeout=1):
            d(text="Erase").click()
            time.sleep(0.4)
            d.swipe(int(w * 0.35), int(h * 0.45), int(w * 0.75), int(h * 0.65), 0.4)
        apply_done(d)
    elif args.frame:
        # tap a frame thumbnail area
        d.click(int(w * 0.56), int(h * 0.75))
        time.sleep(0.6)
        apply_done(d)
    else:
        apply_slider(d)

    print("[u2] apply done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
