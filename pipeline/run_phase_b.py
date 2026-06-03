#!/usr/bin/env python3
"""Run the Phase B baseline benchmark matrix.

The default matrix is the small offline CI leg so a local validation run stays
quick. Use ``--matrix all`` for the full Phase B plan; those runs are
intentionally long and require live or cached JPL Horizons data.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parent
LAB_ROOT = PIPELINE_DIR.parent
RUN_PIPELINE = PIPELINE_DIR / "run_pipeline.py"

PHASE_B_GROUPS: dict[str, list[str]] = {
    "ci": ["phase_b_ci_seed42.toml"],
    "public": [
        "phase_b_public_seed42.toml",
        "phase_b_public_seed314159.toml",
        "phase_b_public_seed271828.toml",
    ],
    "ephemeris": ["phase_b_ephemeris_seed42.toml"],
    "anise": ["phase_b_anise_parity_seed42.toml"],
    "performance": ["phase_b_performance.toml"],
    "large": ["phase_b_large_validation.toml"],
}
PHASE_B_GROUPS["all"] = [
    *PHASE_B_GROUPS["ci"],
    *PHASE_B_GROUPS["public"],
    *PHASE_B_GROUPS["ephemeris"],
    *PHASE_B_GROUPS["anise"],
    *PHASE_B_GROUPS["performance"],
    *PHASE_B_GROUPS["large"],
]


def config_path(name: str) -> Path:
    return PIPELINE_DIR / "configs" / name


def build_command(config: Path) -> list[str]:
    return [sys.executable, str(RUN_PIPELINE), "--config", str(config)]


def run_export() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pipeline.export_static",
        "--lab-root",
        str(LAB_ROOT),
        "--output",
        str(LAB_ROOT.parent / "public" / "data" / "lab"),
    ]
    print("Export:", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(LAB_ROOT)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase B baseline matrix")
    parser.add_argument(
        "--matrix",
        choices=sorted(PHASE_B_GROUPS),
        default="ci",
        help="Phase B matrix leg to run (default: ci)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop at the first failed config instead of continuing the matrix",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Do not regenerate benches/static_export after successful runs",
    )
    args = parser.parse_args()

    failures: list[tuple[str, int]] = []
    successes = 0
    selected = [config_path(name) for name in PHASE_B_GROUPS[args.matrix]]
    for cfg in selected:
        if not cfg.is_file():
            print(f"Missing config: {cfg.relative_to(LAB_ROOT)}", file=sys.stderr)
            failures.append((cfg.name, 2))
            if args.stop_on_failure:
                break
            continue

        cmd = build_command(cfg)
        display_cfg = cfg.relative_to(LAB_ROOT)
        print(f"\nPhase B config: {display_cfg}", flush=True)
        print("Command:", " ".join(cmd), flush=True)
        if args.dry_run:
            continue

        rc = subprocess.run(cmd, cwd=str(LAB_ROOT)).returncode
        if rc != 0:
            failures.append((cfg.name, rc))
            if args.stop_on_failure:
                break
        else:
            successes += 1

    if args.dry_run:
        return 0 if not failures else 1

    if not args.skip_export and successes:
        rc = run_export()
        if rc != 0:
            failures.append(("export_static", rc))

    if failures:
        print("\nPhase B failures:", file=sys.stderr)
        for name, rc in failures:
            print(f"  {name}: exit {rc}", file=sys.stderr)
        return 1

    print("\nPhase B matrix completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
