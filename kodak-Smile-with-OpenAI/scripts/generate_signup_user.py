#!/usr/bin/env python3
"""
Generate a unique Kodak-style signup user per device and run.
Writes reports/signup_users/<device>_signup_user.json (no global shared file).
Optionally writes a .bat to set EMAIL, FULL_NAME, PASSWORD, SIGNUP_RUN_ID, SIGNUP_ATTEMPT.

Runtime: if OpenRouter is configured (OpenRouterAPI / OPENROUTER_API_KEY) and
KODAK_SIGNUP_USE_AI is not 0, tries AI once for fullName / label / password; otherwise
or on any failure, uses deterministic values. --no-ai forces deterministic only.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import secrets
import string
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("kodak.signup_gen")


def _safe_device_id(device: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (device or "nodev").strip())[:48]
    return s or "nodev"


def _rand_alnum(n: int) -> str:
    a = string.ascii_letters + string.digits
    return "".join(secrets.choice(a) for _ in range(n))


def _default_password() -> str:
    # No & < > " | in password — safe for .bat; meets typical app rules (upper, lower, digit, length)
    return f"Kodak{_rand_alnum(1).upper()}{_rand_alnum(6).lower()}{secrets.randbelow(9)}a"


def _env_signup_use_ai() -> bool:
    return (os.environ.get("KODAK_SIGNUP_USE_AI", "1") or "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _sanitize_bat_value(s: str) -> str:
    # Maestro -e and Windows .bat: avoid " & < > | % ^ and newlines
    t = re.sub(r'["&<>|^%\r\n\t]+', "", (s or "")).strip()
    return t


def _fix_name_simple(s: str, *, key: str) -> str:
    t = re.sub(r'["\r\n\t]+', "", (s or "").strip())[:50]
    t = re.sub(r"[^A-Za-z0-9 -]+", "", t)[:50].strip() or f"KodakT{key[:6]}{_rand_alnum(2)}"
    return t


def _sanitize_label(s: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "", (s or "").lower())[:12]
    return raw if len(raw) >= 4 else ""


def _password_ok_for_bat(s: str) -> bool:
    t = s or ""
    if len(t) < 8 or len(t) > 24:
        return False
    if re.search(r'["&<>|^%]', t):
        return False
    if not re.search(r"[A-Z]", t):
        return False
    if not re.search(r"[a-z]", t):
        return False
    if not re.search(r"[0-9]", t):
        return False
    return bool(re.match(r"^[A-Za-z0-9!]+$", t))


def _sanitize_password(s: str) -> str | None:
    t = _sanitize_bat_value(s)
    if _password_ok_for_bat(t):
        return t
    return None


def _ai_signup_values(
    *, repo: Path, device_key: str, ts: int, run_id: str, is_retry: bool
) -> dict[str, str] | None:
    if is_retry:
        return None
    if not _env_signup_use_ai():
        return None
    r = repo
    if str(r) not in sys.path:
        sys.path.insert(0, str(r))
    try:
        from intelligent_platform import config
        from intelligent_platform.json_safety import safe_json_parse
        from intelligent_platform.openrouter_client import call_openrouter
    except Exception as e:
        logger.debug("AI signup import/skip: %s", e)
        return None
    if not config.openrouter_key_present():
        return None
    system = "You return only minified JSON. No markdown, no explanation."
    user = f"""Propose a disposable automated-test signup for a mobile app.
deviceKeyFragment={device_key[:12]!r}
timeHint={ts}
runId={run_id!r}
Return this JSON only:
{{
  "fullName": "two to four English words, title case, max 45 chars, letters and spaces only",
  "label": "lowercase letters 6-12 chars, single word, used in email local part (no spaces, no @)",
  "password": "10-20 chars, at least one uppercase, one lowercase, one digit, only A-Za-z0-9! (use ! only; no @ # $ percent)"
}}"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        text = call_openrouter(
            messages,
            config.openrouter_model_primary(),
            api_key=config.openrouter_api_key(),
            base_url=config.OPENROUTER_BASE_URL,
            http_referer=config.OPENROUTER_HTTP_REFERER,
            app_title="Kodak Signup test user generator",
        )
        parsed = safe_json_parse(text)
    except Exception as e:
        logger.info("OpenRouter signup generation skipped: %s", e)
        return None
    fn = _fix_name_simple(str(parsed.get("fullName", "")), key=device_key)
    label = _sanitize_label(str(parsed.get("label", "")))
    if not label:
        label = f"test{_rand_alnum(6).lower()}"
    pw = _sanitize_password(str(parsed.get("password", "")))
    if not pw:
        pw = _default_password()
    rand = secrets.randbelow(10**6)
    email = f"kodak_{label}_{device_key[:6]}_{ts%1000000:06d}{rand%10000:04d}@example.com"
    email = re.sub(r"[^a-z0-9@._+-]+", "", email, flags=re.I) or f"kodak_test_{_rand_alnum(8).lower()}@example.com"
    if email.count("@") != 1 or " " in email:
        return None
    return {
        "fullName": fn,
        "email": email,
        "password": pw,
        "source": "openrouter",
    }


def _load_json(p: Path) -> dict[str, Any]:
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True, help="ADB device serial (unique per parallel worker)")
    ap.add_argument(
        "--repo",
        default="",
        help="Repo root (default: parent of scripts/)",
    )
    ap.add_argument(
        "--retry",
        action="store_true",
        help="Regenerate after duplicate-user failure (increments attempt, new email).",
    )
    ap.add_argument(
        "--write-bat",
        default="",
        help="Path to a small .bat that sets EMAIL, FULL_NAME, PASSWORD, SIGNUP_RUN_ID, SIGNUP_ATTEMPT",
    )
    ap.add_argument(
        "--stdout-json",
        action="store_true",
        help="Print one JSON line to stdout (for tools).",
    )
    ap.add_argument(
        "--json-basename",
        default="",
        help="Filename for <basename>_signup_user.json (e.g. batch SAFE_DEVICE for parallel).",
    )
    ap.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip OpenRouter; use only local random (deterministic) signup values.",
    )
    args = ap.parse_args()

    repo = Path(args.repo or "").resolve()
    if not repo or repo == Path.cwd():
        repo = Path(__file__).resolve().parents[1]
    out_dir = repo / "reports" / "signup_users"
    out_dir.mkdir(parents=True, exist_ok=True)
    did = (args.device or "").strip()
    key = (args.json_basename or "").strip() or _safe_device_id(did)
    key = _safe_device_id(key)
    jpath = out_dir / f"{key}_signup_user.json"

    prev = _load_json(jpath)
    if args.retry and prev:
        attempt = int(prev.get("attempt", 1)) + 1
    else:
        attempt = 1

    ts = int(time.time())
    run_id = f"{ts}-{_rand_alnum(6)}" if not args.retry else f"{ts}-retry{_rand_alnum(4)}-{_rand_alnum(4)}"

    em_local = f"kodak_test_{key[:24]}_{ts}_{secrets.randbelow(10**6):06d}@example.com"
    # No spaces in email: Windows .bat -e and shell-safe for Maestro CLI; fullName may have spaces
    full = f"KodakT{key[:6]}{_rand_alnum(2)}"
    signup_source = "deterministic"

    if args.retry and prev.get("password"):
        password = str(prev["password"])
    else:
        password = _default_password()

    if not args.no_ai and not args.retry:
        got = _ai_signup_values(
            repo=repo,
            device_key=key,
            ts=ts,
            run_id=run_id,
            is_retry=bool(args.retry),
        )
        if got:
            em_local = got["email"]
            full = got["fullName"]
            if not (args.retry and prev.get("password")):
                password = got["password"]
            signup_source = got.get("source", "openrouter")

    record: dict[str, Any] = {
        "deviceId": did,
        "deviceKey": key,
        "email": em_local,
        "fullName": full,
        "password": password,
        "runId": run_id,
        "attempt": attempt,
        "timestampUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "isRetry": bool(args.retry),
        "signupSource": signup_source,
    }
    if args.retry and prev and prev.get("email"):
        record["previousEmail"] = prev.get("email", "")

    jpath.write_text(json.dumps(record, indent=2), encoding="utf-8")

    if args.write_bat:
        batp = Path(args.write_bat)
        batp.parent.mkdir(parents=True, exist_ok=True)
        # .bat: avoid special characters in values for cmd; password is alnum- safe
        lines = [
            "@echo off",
            f'set "EMAIL={em_local}"',
            f'set "FULL_NAME={full}"',
            f'set "PASSWORD={password}"',
            f'set "SIGNUP_RUN_ID={run_id}"',
            f'set "SIGNUP_ATTEMPT={attempt}"',
        ]
        batp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.stdout_json:
        out_k = (
            "email",
            "fullName",
            "password",
            "runId",
            "attempt",
            "signupSource",
        )
        print(json.dumps({k: record[k] for k in out_k if k in record}))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
