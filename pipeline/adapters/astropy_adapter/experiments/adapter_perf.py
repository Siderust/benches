"""Shared Phase-6 performance JSON helpers for the Astropy adapter."""

import json
import sys


def astropy_perf_result(experiment, library, n, elapsed_ns, sink):
    """Build a valid perf round dict matching the siderust/anise contract."""
    return {
        "experiment": experiment,
        "library": library,
        "count_requested": n,
        "count_valid": n,
        "error_count": 0,
        "count": n,
        "valid": True,
        "skipped": False,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }


def emit_astropy_perf_result(experiment, library, n, elapsed_ns, sink):
    json.dump(astropy_perf_result(experiment, library, n, elapsed_ns, sink), sys.stdout, indent=None)
    print()


def astropy_perf_skipped_result(experiment, reason, library="astropy"):
    result = {
        "experiment": experiment,
        "library": library,
        "status": "skipped",
        "skipped": True,
        "valid": False,
        "reason": reason,
        "count_requested": 0,
        "count_valid": 0,
        "error_count": 0,
        "count": 0,
    }
    json.dump(result, sys.stdout, indent=None)
    print()
