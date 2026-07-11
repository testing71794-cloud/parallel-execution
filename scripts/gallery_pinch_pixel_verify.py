"""Local screenshot diff helpers for gallery pinch verify (no OpenRouter)."""
from __future__ import annotations

from pathlib import Path


def png_byte_diff_ratio(before: Path, after: Path) -> float:
    """Fraction of bytes that differ (0.0 = identical files)."""
    b = before.read_bytes()
    a = after.read_bytes()
    if b == a:
        return 0.0
    n = max(len(b), len(a))
    if n == 0:
        return 0.0
    if len(b) != len(a):
        return 1.0
    diff = sum(1 for x, y in zip(b, a) if x != y)
    return diff / n


def pinch_screenshots_changed(before: Path, after: Path, min_ratio: float = 0.002) -> bool:
    """True when before/after PNGs differ enough to suggest a visible pinch change."""
    return png_byte_diff_ratio(before, after) >= min_ratio
