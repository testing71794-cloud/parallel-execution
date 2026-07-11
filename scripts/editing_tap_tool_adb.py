#!/usr/bin/env python3
"""ADB-only edit-toolbar helper (safe mid-Maestro; no Appium/u2 server conflict).

Uses `uiautomator dump` + `input tap/swipe` so Maestro can keep its session.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = Path(r"C:\Users\HP\AppData\Local\Android\Sdk\platform-tools\adb.exe")


def adb(serial: str, *args: str, timeout: float = 30) -> str:
    cmd = [str(ADB), "-s", serial, *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if p.returncode != 0 and "UI hierchary dumped" not in (p.stderr or "") and "UI hierarchy dumped" not in (p.stderr or ""):
        # uiautomator dump writes success to stderr sometimes
        err = (p.stderr or p.stdout or "").strip()
        if err and "hierarchy dumped" not in err.lower():
            raise RuntimeError(f"adb {' '.join(args)} failed: {err[:300]}")
    return (p.stdout or "") + (p.stderr or "")


def dump_nodes(serial: str) -> list[dict]:
    remote = "/sdcard/atp_ui.xml"
    adb(serial, "shell", "uiautomator", "dump", remote)
    local = Path(__file__).resolve().parents[1] / "reports" / "editing" / f"ui_{serial}.xml"
    local.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(ADB), "-s", serial, "pull", remote, str(local)], capture_output=True, check=False)
    if not local.is_file():
        return []
    root = ET.fromstring(local.read_text(encoding="utf-8", errors="replace"))
    nodes = []
    for n in root.iter("node"):
        text = n.attrib.get("text") or ""
        desc = n.attrib.get("content-desc") or ""
        rid = n.attrib.get("resource-id") or ""
        bounds = n.attrib.get("bounds") or ""
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        nodes.append(
            {
                "text": text,
                "desc": desc,
                "rid": rid,
                "cx": (x1 + x2) // 2,
                "cy": (y1 + y2) // 2,
                "y1": y1,
                "y2": y2,
            }
        )
    return nodes


def find_label(nodes: list[dict], label: str) -> dict | None:
    cands = [label, label.rstrip("s"), label + "s"]
    for c in cands:
        for n in nodes:
            if n["text"] == c or n["desc"] == c:
                return n
        for n in nodes:
            if c.lower() in (n["text"] or "").lower() or c.lower() in (n["desc"] or "").lower():
                return n
    return None


def tap(serial: str, x: int, y: int) -> None:
    adb(serial, "shell", "input", "tap", str(x), str(y))
    time.sleep(0.5)


def swipe(serial: str, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
    adb(serial, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))
    time.sleep(0.4)


def wm_size(serial: str) -> tuple[int, int]:
    out = adb(serial, "shell", "wm", "size")
    m = re.search(r"(\d+)x(\d+)", out)
    if not m:
        return 1080, 2400
    return int(m.group(1)), int(m.group(2))


def open_edit_tab(serial: str) -> None:
    nodes = dump_nodes(serial)
    n = find_label(nodes, "Edit")
    if n:
        tap(serial, n["cx"], n["cy"])
        time.sleep(0.7)


def find_and_tap_tool(serial: str, label: str, max_swipes: int = 12) -> bool:
    w, h = wm_size(serial)
    y = int(h * 0.91)
    x1, x2 = int(w * 0.88), int(w * 0.15)
    for direction in ("left", "right"):
        for _ in range(max_swipes):
            nodes = dump_nodes(serial)
            n = find_label(nodes, label)
            if n:
                tap(serial, n["cx"], n["cy"])
                return True
            if direction == "left":
                swipe(serial, x1, y, x2, y, 350)
            else:
                swipe(serial, x2, y, x1, y, 350)
    return False


def tap_done(serial: str) -> None:
    nodes = dump_nodes(serial)
    for lab in ("Done", "Save", "OK", "Ok"):
        n = find_label(nodes, lab)
        if n:
            tap(serial, n["cx"], n["cy"])
            return


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
    serial = args.serial
    w, h = wm_size(serial)

    if args.cancel_save:
        nodes = dump_nodes(serial)
        dialog_open = any(
            find_label(nodes, lab)
            for lab in (
                "Save Photo?",
                "Don't Save",
                "Dont Save",
                "Discard",
                "Save changes?",
            )
        )
        if not dialog_open:
            n = find_label(nodes, "Close")
            if n:
                tap(serial, n["cx"], n["cy"])
                time.sleep(0.8)
            nodes = dump_nodes(serial)
        for lab in ("Don't Save", "Dont Save", "Discard", "Cancel", "CANCEL", "No"):
            n = find_label(nodes, lab)
            if n:
                tap(serial, n["cx"], n["cy"])
                print(f"[adb] cancel tapped={lab}")
                return 0
        # Last resort: tap left dialog button area
        tap(serial, int(w * 0.28), int(h * 0.58))
        time.sleep(0.5)
        print("[adb] cancel tapped=point_fallback")
        return 0

    if args.ar:
        nodes = dump_nodes(serial)
        n = find_label(nodes, "AR")
        if n:
            tap(serial, n["cx"], n["cy"])
            time.sleep(1.0)
        nodes = dump_nodes(serial)
        for lab in ("While using the app", "Allow", "OK", "Ok"):
            n = find_label(nodes, lab)
            if n:
                tap(serial, n["cx"], n["cy"])
                time.sleep(0.4)
        print("[adb] AR opened")
        return 0

    open_edit_tab(serial)
    label = (args.tool or "").strip()
    aliases = [label]
    if label == "Frames":
        aliases = ["Frames", "Frame"]
    if label == "Stickers":
        aliases = ["Stickers", "Sticker"]
    ok = False
    used = label
    for a in aliases:
        if find_and_tap_tool(serial, a):
            ok = True
            used = a
            break
    if not ok:
        print(f"[adb] ERROR: tool not found: {args.tool}", file=sys.stderr)
        return 3
    print(f"[adb] opened tool={used}")
    time.sleep(0.5)

    if args.input:
        tap(serial, w // 2, int(h * 0.45))
        time.sleep(0.3)
        # type via adb (spaces as %s)
        text = args.input.replace(" ", "%s")
        adb(serial, "shell", "input", "text", text)
        time.sleep(0.3)
        adb(serial, "shell", "input", "keyevent", "4")  # back/hide kb
        time.sleep(0.3)
        tap_done(serial)
    elif args.draw:
        swipe(serial, int(w * 0.35), int(h * 0.45), int(w * 0.75), int(h * 0.65), 400)
        if args.erase:
            nodes = dump_nodes(serial)
            n = find_label(nodes, "Erase")
            if n:
                tap(serial, n["cx"], n["cy"])
                time.sleep(0.3)
                swipe(serial, int(w * 0.35), int(h * 0.45), int(w * 0.75), int(h * 0.65), 400)
        tap_done(serial)
    elif args.frame:
        tap(serial, int(w * 0.56), int(h * 0.75))
        time.sleep(0.5)
        tap_done(serial)
    else:
        # slider adjust
        swipe(serial, int(w * 0.30), int(h * 0.90), int(w * 0.80), int(h * 0.90), 350)
        time.sleep(0.3)
        tap_done(serial)

    print("[adb] apply done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
