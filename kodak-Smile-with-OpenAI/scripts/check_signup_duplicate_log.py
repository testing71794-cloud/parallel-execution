#!/usr/bin/env python3
"""
Exit 0 = log likely shows duplicate user / email already registered (safe to retry with new email).
Exit 1 = not clearly a duplicate-user case (or missing file).
"""
import re
import sys
from pathlib import Path

# Maestro + typical app / backend phrasing
_PAT = re.compile(
    r"(already (have an account|registered|exists)|"
    r"email.?(is )?(already|taken|in use|registered)|"
    r"user(name)?.?(is )?taken|"
    r"account.?(already|exists)|"
    r"duplicate.?(user|email)|"
    r"sign up failed.*(exist|taken|already)|"
    r"this email)",
    re.I,
)


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    p = Path(sys.argv[1])
    if not p.is_file():
        return 1
    try:
        text = p.read_text(encoding="utf-8", errors="replace")[-120_000:]
    except OSError:
        return 1
    if _PAT.search(text):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
