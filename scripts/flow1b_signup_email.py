#!/usr/bin/env python3
"""
Runtime email for flow1b.yaml only. Prints one line: kodak_<ts>_<random>@test.com
ts = local YYYYMMDDHHmmss, random in [0, 10**9) for parallel-safe uniqueness.
"""
from __future__ import annotations

import random
import time


def main() -> None:
    ts = time.strftime("%Y%m%d%H%M%S")
    r = random.randrange(0, 1_000_000_000)
    print(f"kodak_{ts}_{r}@test.com", end="")


if __name__ == "__main__":
    main()
