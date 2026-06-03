#!/usr/bin/env python3
"""Verify lab Python dependencies are importable (CI / local smoke)."""

from __future__ import annotations

import sys


def main() -> int:
    required = ["numpy", "astropy", "erfa", "pytest"]
    if sys.version_info < (3, 11):
        required.append("tomli")
    missing = []
    for name in required:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        print("Missing packages:", ", ".join(missing), file=sys.stderr)
        print("Install: pip install -r pipeline/requirements.txt", file=sys.stderr)
        return 1
    print("OK: lab Python dependencies satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
