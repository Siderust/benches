#!/usr/bin/env python3
"""Re-time performance workloads for rows that missed perf_valid (CV > 20%)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = LAB_ROOT / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

from cache_manager import default_cache_root, export_cache_env  # noqa: E402
import orchestrator as o  # noqa: E402

RUN_ID = "2026-07-07_18-29-38"
SEED = 42
ATTEMPTS = 12
PERF_ROUNDS = 30
PERF_WARMUP = 500
PERF_SCALAR_N = 5000

TARGETS: list[tuple[str, str, object, object]] = [
    (
        "gmst_era",
        "libnova",
        o.generate_gmst_era_inputs,
        o.format_gmst_perf_input,
    ),
    (
        "equ_horizontal",
        "libnova",
        o.generate_equ_horizontal_inputs,
        o.format_equ_horizontal_perf_input,
    ),
    (
        "saturn_barycenter_position",
        "siderust:spk_barycenter",
        lambda n, seed: (o.generate_planet_position_inputs(n, seed),),
        lambda epochs: o._format_external_position_perf_input("saturn_barycenter_position", epochs),
    ),
    (
        "uranus_barycenter_position",
        "anise",
        lambda n, seed: (o.generate_planet_position_inputs(n, seed),),
        lambda epochs: o._format_external_position_perf_input("uranus_barycenter_position", epochs),
    ),
    (
        "kepler_solver",
        "siderust",
        o.generate_kepler_inputs,
        o.format_kepler_perf_input,
    ),
]


def _setup_env() -> None:
    cache_root = default_cache_root()
    os.environ.update(export_cache_env(cache_root))
    o.configure_run(
        adapters=["siderust", "astropy", "libnova", "anise"],
        siderust_profiles=["iau2006a"],
    )


def _result_path(run_dir: Path, exp: str, candidate_id: str) -> Path:
    lib, _, profile = candidate_id.partition(":")
    if profile and not (lib == "siderust" and profile == "iau2006a"):
        stem = f"{lib}_{profile}"
    else:
        stem = lib
    return run_dir / exp / f"{stem}.json"


def _scalar_valid(perf: dict | None) -> bool:
    if not isinstance(perf, dict):
        return False
    block = perf.get("scalar_warm")
    return isinstance(block, dict) and block.get("valid") is True


def _scalar_cv(perf: dict | None) -> float:
    if not isinstance(perf, dict):
        return float("inf")
    block = perf.get("scalar_warm") or {}
    cv = block.get("cv")
    return float(cv) if cv is not None else float("inf")


def _cmd_for(exp: str, candidate_id: str) -> list[str]:
    for label, cmd in o.candidate_adapters_for(exp):
        if o.candidate_id_for(label) == candidate_id:
            return cmd
    raise KeyError(f"No adapter command for {exp} / {candidate_id}")


def retry_target(run_dir: Path, exp: str, candidate_id: str, input_gen, perf_fmt) -> bool:
    path = _result_path(run_dir, exp, candidate_id)
    row = json.loads(path.read_text())
    best_perf = row.get("performance")
    best_cv = _scalar_cv(best_perf)
    best_valid = _scalar_valid(best_perf)
    cmd = _cmd_for(exp, candidate_id)

    print(f"\n== {exp} / {candidate_id} (initial cv={best_cv:.1f}, valid={best_valid}) ==")
    for attempt in range(1, ATTEMPTS + 1):
        perf = o.run_perf_workloads(
            cmd,
            exp,
            input_gen,
            perf_fmt,
            SEED,
            scalar_rounds=PERF_ROUNDS,
            scalar_n=PERF_SCALAR_N,
            warmup=PERF_WARMUP,
            timeout_s=300,
        )
        cv = _scalar_cv(perf)
        valid = _scalar_valid(perf)
        print(f"  attempt {attempt}: cv={cv:.1f} valid={valid}")
        if valid:
            row["performance"] = perf
            path.write_text(json.dumps(row, indent=2))
            print(f"  ✓ patched {path.name}")
            return True
        if cv < best_cv:
            best_cv = cv
            best_perf = perf
    if best_valid or _scalar_valid(best_perf):
        row["performance"] = best_perf
        path.write_text(json.dumps(row, indent=2))
        print(f"  ~ patched best effort cv={best_cv:.1f}")
        return _scalar_valid(best_perf)
    print(f"  ✗ still invalid (best cv={best_cv:.1f})")
    return False


def main() -> int:
    _setup_env()
    run_dir = LAB_ROOT / "results" / RUN_ID
    if not run_dir.is_dir():
        print(f"Missing run dir: {run_dir}", file=sys.stderr)
        return 1

    ok = 0
    for exp, candidate_id, input_gen, perf_fmt in TARGETS:
        if retry_target(run_dir, exp, candidate_id, input_gen, perf_fmt):
            ok += 1

    print(f"\nFixed {ok}/{len(TARGETS)} targets")
    return 0 if ok == len(TARGETS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
