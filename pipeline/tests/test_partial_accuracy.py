"""Partial adapter accuracy must not be rankable."""

from __future__ import annotations

import sys
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR.parent))

import orchestrator as orch


def test_partial_accuracy_status():
    acc = {
        "count_requested": 10,
        "count_valid": 7,
        "nan_count": 2,
        "inf_count": 1,
        "angular_error_mas": {"p99": 1.0},
    }
    assert orch._accuracy_status_from_metrics(acc) == "partial"


def test_perf_invalid_when_case_count_mismatch():
    perf = {
        "scalar_warm": {
            "ns_per_op": 50.0,
            "cv": 1.0,
            "valid": True,
            "n_per_round": 50,
            "count_requested": 1000,
            "count_valid": 50,
            "error_count": 950,
        },
        "batch_throughput": None,
        "setup_metrics": None,
    }
    out = orch._invalidate_perf_if_incomplete(perf, expected_scalar_n=1000)
    assert out["scalar_warm"]["valid"] is False
    assert any("50" in w or "perf" in w.lower() for w in out["scalar_warm"]["warnings"])
