"""Print a short filesystem-safe segment for a device serial (ATP per-device folders)."""
import re
import sys

if __name__ == "__main__":
    d = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    seg = re.sub(r"[^a-zA-Z0-9._-]+", "_", d)[:48] or "dev"
    print(seg)
