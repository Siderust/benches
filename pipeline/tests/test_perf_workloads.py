from __future__ import annotations

import math
from unittest.mock import patch

from pipeline import orchestrator
from pipeline import scorecard


def test_empty_performance_schema_has_three_workloads() -> None:
    perf = orchestrator.empty_performance_workloads()
    assert set(perf) == {"scalar_warm", "batch_throughput", "setup_metrics"}
    assert perf == {"scalar_warm": None, "batch_throughput": None, "setup_metrics": None}


def test_run_perf_workloads_shape_and_values() -> None:
    calls = []

    def gen(n: int, seed: int):
        return ([float(seed)] * n,)

    def fmt(values):
        return "stub_perf\n" + str(len(values)) + "\n"

    def fake_multi(cmd, input_text, label, rounds=10, *, extra_env=None, timeout=120):
        calls.append((label, rounds, input_text.splitlines()[1]))
        count = int(input_text.splitlines()[1])
        per_op = 200.0 if "scalar" in label else 100.0
        return {
            "per_op_ns": per_op,
            "per_op_ns_cv_pct": 2.5,
            "throughput_ops_s": 1e9 / per_op,
            "batch_size": count,
            "valid": True,
            "warnings": [],
        }

    with patch.object(orchestrator, "run_multi_sample_perf", side_effect=fake_multi), \
         patch.object(orchestrator, "run_adapter", return_value={"setup_ms": 1.25, "measured": True}):
        perf = orchestrator.run_perf_workloads(["stub"], "gmst_era", gen, fmt, 42, scalar_rounds=3)

    assert set(perf) == {"scalar_warm", "batch_throughput", "setup_metrics"}
    assert perf["scalar_warm"]["ns_per_op"] >= perf["batch_throughput"]["ns_per_op"]
    assert perf["scalar_warm"]["rounds"] == 3
    assert perf["scalar_warm"]["n_per_round"] == orchestrator.SCALAR_WARM_N
    assert perf["batch_throughput"]["rounds"] == orchestrator.BATCH_THROUGHPUT_ROUNDS
    assert perf["batch_throughput"]["n"] == orchestrator.BATCH_THROUGHPUT_N
    assert perf["batch_throughput"]["items_per_sec"] > 0
    assert math.isfinite(perf["setup_metrics"]["setup_ms"])
    assert perf["setup_metrics"]["setup_ms"] >= 0
    assert perf["setup_metrics"]["measured"] is True


def test_scorecard_surfaces_three_workload_columns() -> None:
    row = {
        "experiment": "gmst_era",
        "candidate_library": "siderust",
        "candidate_profile": "iau2006a",
        "tier": "public",
        "rankable_accuracy": True,
        "accuracy": {"gmst_error_arcsec": {"p50": 0.0, "p99": 0.0, "max": 0.0, "rms": 0.0, "mean": 0.0}},
        "performance": {
            "scalar_warm": {"ns_per_op": 200.0, "cv": 1.0, "rounds": 10, "n_per_round": 5000, "warmup": 100, "valid": True},
            "batch_throughput": {"ns_per_op": 100.0, "items_per_sec": 10_000_000.0, "n": 100000, "rounds": 5, "valid": True},
            "setup_metrics": {"setup_ms": 0.0, "measured": True},
        },
        "alignment": {},
    }
    card = scorecard.compute_scorecard("unit", {"gmst_era": [row]})
    out = card["families"][0]["experiments"][0]["rows"][0]

    assert out["scalar_warm_ns_per_op"] == 200.0
    assert out["batch_throughput_ns_per_op"] == 100.0
    assert out["batch_throughput_items_per_sec"] == 10_000_000.0
    assert out["setup_ms"] == 0.0
    assert out["setup_measured"] is True
    assert out["performance"]["scalar_warm"] is not None


def test_legacy_flat_perf_is_additively_readable() -> None:
    perf = scorecard._perf_workloads({"per_op_ns": 123.0, "per_op_ns_cv_pct": 4.0, "rounds": 2, "batch_size": 50, "valid": True})
    assert set(perf) == {"scalar_warm", "batch_throughput", "setup_metrics"}
    assert perf["scalar_warm"]["ns_per_op"] == 123.0
    assert perf["batch_throughput"] is None
    assert perf["setup_metrics"] is None
